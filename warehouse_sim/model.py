"""
Warehouse Simulation Engine — Mesa Model orchestrating all agents.

Owner: Rohith (cb.sc.u4cse23018) & Kalyan (cb.sc.u4cse23060)
Responsibility: Holds the 20x20 MultiGrid, instantiates all agent types,
runs the staged scheduler (sense → decide → act), collects metrics via
DataCollector, and logs inter-agent messages to simulation_log.jsonl.

The model is the single source of truth for the warehouse state and is
callable from both the CLI (main.py) and the Streamlit dashboard.
"""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

import mesa
import numpy as np

from .agents.charging_agent import ChargingAgent
from .agents.customer_agent import CustomerAgent
from .agents.fleet_manager_agent import FleetManagerAgent
from .agents.inventory_agent import InventoryAgent
from .agents.order_agent import OrderAgent
from .agents.robot_agent import RobotAgent
from .agents.traffic_controller_agent import TrafficControllerAgent
from .network import MessageType, NetworkSimulator


# ── Grid Layout Constants ─────────────────────────────────────────────
GRID_WIDTH = 20
GRID_HEIGHT = 20
NUM_ROBOTS = 5

# Shelf locations — distributed across the grid in two "aisles"
SHELF_LOCATIONS: List[Tuple[int, int]] = [
    (3, 4), (3, 8), (3, 12), (3, 16),
    (8, 4), (8, 8), (8, 12), (8, 16),
    (13, 4), (13, 8),
]

# Packing station — bottom-right area
PACKING_STATION: Tuple[int, int] = (17, 2)

# Charging docks — near entrance
CHARGING_DOCKS: List[Tuple[int, int]] = [(1, 1), (1, 18)]

# Robot starting positions — near the entrance
ROBOT_START_POSITIONS: List[Tuple[int, int]] = [
    (0, 0), (0, 5), (0, 10), (0, 15), (0, 19),
]


class WarehouseModel(mesa.Model):
    """
    Mesa Model orchestrating the full warehouse fulfillment simulation.

    Grid encodes: shelves (fixed), aisles (walkable), packing station (fixed),
    charging docks (fixed), and currently-blocked cells (mutable for shocks).
    Uses staged execution: sense → decide → act per tick.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        """Initialize the warehouse model with all agents and grid layout."""
        super().__init__()
        self.seed = seed
        self.random.seed(seed)

        self.grid_width = GRID_WIDTH
        self.grid_height = GRID_HEIGHT
        self.grid = mesa.space.MultiGrid(GRID_WIDTH, GRID_HEIGHT, torus=False)

        self.current_tick: int = 0
        self.blocked_cells: set = set()
        self.shelf_locations = list(SHELF_LOCATIONS)
        self.packing_station = PACKING_STATION
        self.charging_docks = list(CHARGING_DOCKS)
        self.message_log: List[Dict[str, Any]] = []
        self.shocks_recovered: int = 0
        self.recovery_events: List[Dict[str, Any]] = []
        self.partition_tasks_completed = 0
        self.partition_progress_by_group: Dict[str, int] = {}
        self.partition_decisions = 0
        self.network_phase = "normal"
        self.phase_metrics: Dict[str, Dict[str, int]] = {
            name: {"ticks": 0, "tasks_completed": 0}
            for name in ("normal", "partitioned", "reconnected")
        }
        self._completed_at_last_step = 0
        self.completed_task_ids: set[int] = set()
        self._was_partitioned = False
        self._log_file_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "simulation_log.jsonl"
        )

        # Clear log file on init
        with open(self._log_file_path, "w") as f:
            pass

        # ── Instantiate singleton agents ──────────────────────────────
        self.order_agent = OrderAgent(self)
        self.inventory_agent = InventoryAgent(self, self.shelf_locations)
        self.fleet_manager = FleetManagerAgent(self)
        self.traffic_controller = TrafficControllerAgent(self)
        self.charging_agent = ChargingAgent(self, self.charging_docks)
        self.customer_agent = CustomerAgent(self)
        self.network = NetworkSimulator(range(NUM_ROBOTS), seed=seed)

        # ── Instantiate robot agents ──────────────────────────────────
        self.robots: Dict[int, RobotAgent] = {}
        for i in range(NUM_ROBOTS):
            start_pos = ROBOT_START_POSITIONS[i % len(ROBOT_START_POSITIONS)]
            robot = RobotAgent(self, robot_id=i, start_pos=start_pos)
            self.robots[i] = robot
            self.fleet_manager.register_robot(i, start_pos)
            self.grid.place_agent(robot, start_pos)
        self._was_partitioned = self.network.partition_count > 1

        # ── Data Collector ────────────────────────────────────────────
        self.datacollector = mesa.DataCollector(
            model_reporters={
                "Orders_Completed": lambda m: len(m.order_agent.completed_tasks),
                "Pending_Tasks": lambda m: m.order_agent.get_pending_count(),
                "Active_Tasks": lambda m: m.order_agent.get_active_count(),
                "Avg_Battery": lambda m: np.mean(
                    [r.battery for r in m.robots.values()]
                ) if m.robots else 0,
                "Robots_Charging": lambda m: m.charging_agent.get_charging_count(),
                "Robots_Active": lambda m: sum(
                    1 for r in m.robots.values() if r.status not in ("IDLE", "FAILED", "CHARGING")
                ),
                "Collision_Count": lambda m: m.traffic_controller.collision_count,
                "Deadlocks_Resolved": lambda m: m.traffic_controller.deadlocks_resolved,
                "Shocks_Recovered": lambda m: m.shocks_recovered,
                "Reroutes": lambda m: m.traffic_controller.reroutes_performed,
            }
        )

    def step(self) -> None:
        """
        Advance the simulation by one tick using staged execution.

        Stage 1 — SENSE: All agents observe the environment.
        Stage 2 — DECIDE: All agents make decisions.
        Stage 3 — ACT: All agents execute their actions.
        """
        self.current_tick += 1
        self.network.advance(self.current_tick)
        is_partitioned = self.network.partition_count > 1
        if self._was_partitioned and not is_partitioned:
            self.network_phase = "reconnected"
            self.log_message("Network", "AllRobots", {"action": "reconnection_reconciliation_started"})
            for robot in self.robots.values():
                robot.publish_state_sync()
        self._was_partitioned = is_partitioned
        if is_partitioned:
            self.network_phase = "partitioned"
        self._verify_recovery_events()

        # ── Stage 1: SENSE ────────────────────────────────────────────
        self.customer_agent.sense()
        self.order_agent.sense()
        self.traffic_controller.sense()
        self.charging_agent.sense()
        self.fleet_manager.sense()
        for robot in self.robots.values():
            if robot.status != "FAILED":
                robot.sense()

        # ── Stage 2: DECIDE ───────────────────────────────────────────
        self.customer_agent.decide()
        self.order_agent.decide()
        self.traffic_controller.decide()
        self.charging_agent.decide()
        self.fleet_manager.decide()
        for robot in self.robots.values():
            if robot.status != "FAILED":
                robot.decide()

        # ── Stage 3: ACT ──────────────────────────────────────────────
        self.customer_agent.act()
        self.order_agent.act()
        self.charging_agent.act()
        self.fleet_manager.act()
        for robot in self.robots.values():
            if robot.status != "FAILED":
                robot.act()
        self.traffic_controller.act()

        # ── Collect data ──────────────────────────────────────────────
        self.datacollector.collect(self)
        completed_now = len(self.completed_task_ids)
        phase = self.phase_metrics[self.network_phase]
        phase["ticks"] += 1
        phase["tasks_completed"] += max(0, completed_now - self._completed_at_last_step)
        self._completed_at_last_step = completed_now

    def announce_task(self, task: Any) -> None:
        """Publish new work to the robot peer network; no fleet assignment is made here."""
        self.network.broadcast("OrderAgent", MessageType.TASK_ANNOUNCEMENT, {
            "task_id": task.task_id, "sku": task.sku, "qty": task.qty,
            "priority": task.priority, "priority_rank": task.priority_rank,
            "arrival_tick": task.arrival_tick, "shelf_location": list(task.shelf_location),
        }, self.current_tick)
        self.log_message("OrderAgent", "RobotNetwork", {"action": "task_announcement", "task_id": task.task_id})

    def track_recovery(self, event: Dict[str, Any]) -> None:
        """Track an injected disruption until its observable recovery condition holds."""
        if event.get("status") == "recovered":
            self.shocks_recovered += 1
        elif event.get("status") in ("recovery_in_progress", "injected"):
            self.recovery_events.append(event)

    def _verify_recovery_events(self) -> None:
        for event in self.recovery_events:
            if event.get("status") == "recovered":
                continue
            kind = event.get("shock_type")
            recovered = False
            if kind == "robot_failure":
                robot_id = event.get("robot_id")
                task_id = event.get("task_id")
                task = next((t for t in self.order_agent.all_tasks if t.task_id == task_id), None) if task_id is not None else None
                recovered = (task is None and any(r.status != "FAILED" for r in self.robots.values())) or (task is not None and task.status not in ("IN_PROGRESS", "DISPATCHED"))
                recovered = recovered or (robot_id is not None and self.robots[robot_id].status == "FAILED" and task is not None and task.status == "PENDING")
            elif kind == "blocked_aisle":
                cell = tuple(event.get("blocked_cell", ()))
                recovered = all(cell not in r.current_path[r.path_index:] for r in self.robots.values() if r.status != "FAILED")
            elif kind == "battery_failure":
                robot = self.robots.get(event.get("robot_id"))
                recovered = bool(robot and robot.battery >= 95 and robot.status != "FAILED")
            elif kind == "order_flood":
                # Successful recovery means all injected urgent work reached terminal state.
                ids = set(event.get("task_ids", []))
                recovered = bool(ids) and ids.issubset(self.completed_task_ids)
            elif kind == "deadlock_injection":
                recovered = bool(event.get("deadlock_resolved")) or self.traffic_controller.deadlocks_resolved > event.get("deadlocks_before", 0)
            elif kind in ("network_partition", "robot_isolation"):
                recovered = self.network.partition_count == 1
            if recovered:
                event["status"] = "recovered"
                event["recovered"] = True
                event["recovered_tick"] = self.current_tick
                self.shocks_recovered += 1
                self.log_message("RecoveryMonitor", "EventSystem", {
                    "action": "recovery_verified", "shock_type": kind,
                    "tick": self.current_tick,
                    "duration_ticks": self.current_tick - event.get("tick", self.current_tick)})

    def complete_distributed_task(self, robot_id: int, task_id: int) -> bool:
        """Commit a physical completion once; the shared world records outcomes, not assignments."""
        if task_id in self.completed_task_ids:
            self.log_message(f"Robot-{robot_id}", "WarehouseWorld", {"action": "duplicate_completion_ignored", "task_id": task_id})
            return False
        task = next((t for t in self.order_agent.all_tasks if t.task_id == task_id), None)
        if task is None:
            return False
        if not self.inventory_agent.decrement_stock(task.shelf_location, task.sku, task.qty):
            self.log_message(f"Robot-{robot_id}", "InventoryAgent", {"action": "completion_rejected_insufficient_stock", "task_id": task_id})
            self.inventory_agent.release(task.shelf_location, robot_id)
            task.status = "PENDING"
            task.assigned_robot = -1
            return False
        self.completed_task_ids.add(task_id)
        self.inventory_agent.release(task.shelf_location, robot_id)
        self.order_agent.mark_task_completed(task_id)
        task.completion_tick = self.current_tick
        if self.network.partition_count > 1:
            self.partition_tasks_completed += 1
            group = "-".join(str(rid) for rid in sorted(self.network.connected_robot_ids(robot_id)))
            self.partition_progress_by_group[group] = self.partition_progress_by_group.get(group, 0) + 1
        self.network.broadcast(f"Robot-{robot_id}", MessageType.TASK_COMPLETE,
                               {"task_id": task_id, "robot_id": robot_id}, self.current_tick)
        self.log_message(f"Robot-{robot_id}", "RobotNetwork", {"action": "task_complete", "task_id": task_id})
        return True

    def get_network_state(self) -> Dict[str, Any]:
        return {
            "nodes": [{"id": f"Robot-{rid}", "robot_id": rid,
                       "status": robot.status, "battery": robot.battery,
                       "neighbors": self.network.neighbors(rid),
                       "connected_group": sorted(self.network.connected_robot_ids(rid))}
                      for rid, robot in self.robots.items()],
            "edges": [[a, b] for a, peers in self.network.adjacency.items()
                      for b in peers if a < b and a.startswith("Robot-") and b.startswith("Robot-")],
            "metrics": {**self.network.counters,
                        "active_connections": self.network.active_connections,
                        "partitions": self.network.partition_count,
                        "disconnected_robots": sum(1 for r in self.robots if not self.network.neighbors(r)),
                        "disconnected_ticks": self.network.disconnected_ticks,
                        "partition_tasks_completed": self.partition_tasks_completed,
                        "partition_progress_by_group": dict(self.partition_progress_by_group),
                        "independent_decisions": sum(r.independent_decisions for r in self.robots.values()),
                        "conflicts_detected": self.network.conflicts_detected,
                        "reconciliations": self.network.reconciliation_count,
                        "phase_comparison": {name: dict(values) for name, values in self.phase_metrics.items()}},
            "messages": [message.as_dict() for message in self.network.activity_log[-30:]],
        }

    def log_message(
        self, from_agent: str, to_agent: str, payload: Dict[str, Any]
    ) -> None:
        """
        Log an inter-agent message to both in-memory log and JSONL file.

        Args:
            from_agent: Name of the sending agent.
            to_agent: Name of the receiving agent.
            payload: Message content dictionary.
        """
        entry = {
            "tick": self.current_tick,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "payload": _serialize_payload(payload),
        }
        self.message_log.append(entry)

        # Append to JSONL file
        try:
            with open(self._log_file_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass  # Don't crash simulation on log failure

    def get_robot_by_id(self, robot_id: int) -> Optional[RobotAgent]:
        """Look up a robot by its ID."""
        return self.robots.get(robot_id)

    def get_robots_at(self, pos: Tuple[int, int]) -> List[RobotAgent]:
        """Get all robots at a specific grid position."""
        return [r for r in self.robots.values() if r.pos_tuple == pos]

    def get_grid_state(self) -> Dict[str, Any]:
        """Return the full grid state for dashboard visualization."""
        robot_positions = {
            rid: {"pos": r.pos_tuple, "status": r.status, "battery": r.battery,
                  "task_id": getattr(r.current_task, "task_id", None),
                  "destination": (r.current_task.shelf_location if r.status == "EN_ROUTE_TO_SHELF" and r.current_task else self.packing_station if r.status == "EN_ROUTE_TO_PACKING" else None),
                  "path": r.current_path[r.path_index:] if r.current_path else [],
                  "communication": r.communication_status,
                  "neighbors": r.nearby_agents, "local_queue": list(r.local_task_queue),
                  "decision": r.last_decision, "decision_reason": r.last_decision_reason}
            for rid, r in self.robots.items()
        }

        shelf_states = {}
        for loc, state in self.inventory_agent.shelf_state.items():
            total_qty = sum(state["skus"].values())
            shelf_states[str(loc)] = {
                "reserved": state["reserved"],
                "total_qty": total_qty,
            }

        return {
            "tick": self.current_tick,
            "grid_width": self.grid_width,
            "grid_height": self.grid_height,
            "robots": robot_positions,
            "shelves": shelf_states,
            "shelf_locations": self.shelf_locations,
            "packing_station": self.packing_station,
            "charging_docks": self.charging_docks,
            "blocked_cells": list(self.blocked_cells),
        }

    def get_kpis(self) -> Dict[str, Any]:
        """Return key performance indicators for dashboard display."""
        active_robots = sum(
            1 for r in self.robots.values()
            if r.status not in ("IDLE", "FAILED", "CHARGING")
        )
        failed_robots = sum(
            1 for r in self.robots.values() if r.status == "FAILED"
        )

        return {
            "tick": self.current_tick,
            "orders_completed": len(self.order_agent.completed_tasks),
            "orders_received": self.order_agent.total_orders_received,
            "pending_tasks": self.order_agent.get_pending_count(),
            "active_robots": active_robots,
            "robots_charging": self.charging_agent.get_charging_count(),
            "robots_failed": failed_robots,
            "robots_queued_charge": self.charging_agent.get_queue_length(),
            "collision_count": self.traffic_controller.collision_count,
            "deadlocks_resolved": self.traffic_controller.deadlocks_resolved,
            "shocks_recovered": self.shocks_recovered,
            "avg_battery": float(np.mean(
                [r.battery for r in self.robots.values()]
            )) if self.robots else 0.0,
            "total_tasks_completed": sum(
                r.tasks_completed for r in self.robots.values()
            ),
            "robot_utilisation": round(sum(1 for r in self.robots.values() if r.status not in ("IDLE", "FAILED", "CHARGING")) / max(1, len(self.robots)) * 100, 1),
            "average_task_time": round(float(np.mean([t.completion_tick - t.arrival_tick for t in self.order_agent.completed_tasks if hasattr(t, "completion_tick")])) if any(hasattr(t, "completion_tick") for t in self.order_agent.completed_tasks) else 0.0, 1),
            "network": self.get_network_state()["metrics"],
        }

    def get_recent_messages(self, n: int = 50) -> List[Dict[str, Any]]:
        """Return the last N inter-agent messages."""
        return self.message_log[-n:]


def _serialize_payload(payload: Dict) -> Dict:
    """Convert any non-serializable values in the payload to strings."""
    result = {}
    for k, v in payload.items():
        if isinstance(v, tuple):
            result[k] = list(v)
        elif isinstance(v, set):
            result[k] = list(v)
        else:
            result[k] = v
    return result
