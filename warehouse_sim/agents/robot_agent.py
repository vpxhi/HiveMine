"""
Robot Agent — Physical warehouse robot with state machine and battery management.

Owner: Rohith (cb.sc.u4cse23018) — Robot Intelligence
Responsibility: Executes assigned paths step-by-step, manages battery consumption,
follows a 7-state FSM, and broadcasts telemetry to the Fleet Manager every tick.

PEAS Formulation:
    Performance: Task completion time, safe navigation, battery discipline.
    Environment: Physical/simulated grid cell, shelf, packing station, charging dock.
    Actuators: move(), pick(), drop(), dock_to_charge().
    Sensors: Local grid occupancy, battery level, assigned route.
"""

from __future__ import annotations

from collections import deque
import math
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import mesa
from ..algorithms.astar import a_star
from ..network import MessageType

if TYPE_CHECKING:
    from ..model import WarehouseModel


# Battery constants
BATTERY_DRAIN_PER_MOVE = 1.0
BATTERY_DRAIN_PER_PICK = 2.0
BATTERY_CHARGE_PER_TICK = 5.0
BATTERY_LOW_THRESHOLD = 45.0
PICK_TICKS = 2
DROP_TICKS = 2


class RobotAgent(mesa.Agent):
    """
    Physical warehouse robot executing pick-and-deliver tasks.

    State Machine:
        IDLE → EN_ROUTE_TO_SHELF → PICKING → EN_ROUTE_TO_PACKING →
        DROPPING → RETURNING → IDLE

    Robots begin returning to a dock with enough reserve for the planned route.
    """

    def __init__(
        self,
        model: WarehouseModel,
        robot_id: int,
        start_pos: Tuple[int, int],
    ) -> None:
        """Initialize the robot at its starting position."""
        super().__init__(model)
        self.robot_id: int = robot_id
        self.pos_tuple: Tuple[int, int] = start_pos
        self.battery: float = 100.0
        self.status: str = "IDLE"
        self.current_path: List[Tuple[int, int]] = []
        self.path_index: int = 0
        self.current_task: Optional[Any] = None
        self.tasks_completed: int = 0
        self._action_timer: int = 0
        self._pre_charge_status: str = "IDLE"
        self._pre_charge_task: Optional[Any] = None
        self._charging_dock: Optional[Tuple[int, int]] = None
        self._return_path: List[Tuple[int, int]] = []
        self.local_task_knowledge: Dict[int, Dict[str, Any]] = {}
        self.local_event_memory: List[Dict[str, Any]] = []
        self.local_decision_history: List[Dict[str, Any]] = []
        self.local_task_queue: List[int] = []
        self.nearby_agents: List[int] = []
        self._last_network_neighbors: Optional[Tuple[int, ...]] = None
        self.communication_status = "CONNECTED"
        self.last_decision = "Waiting for a task announcement"
        self.last_decision_reason = "No eligible local task is known"
        self.independent_decisions = 0
        self._last_bid_tick: Dict[int, int] = {}
        self._processed_message_ids: set[str] = set()
        self._processed_message_order = deque()
        self._local_trace_sequence = 0

    def receive_assignment(self, task: Any) -> None:
        """Receive a task assignment from the Fleet Manager."""
        self.current_task = task
        self.status = "EN_ROUTE_TO_SHELF"

    def update_path(self, path: List[Tuple[int, int]]) -> None:
        """Update the robot's current navigation path."""
        self.current_path = path
        self.path_index = 0

    def hold(self) -> None:
        """Hold in place (wait) — used for deadlock resolution."""
        self.path_index = max(0, self.path_index)

    def _record_local_event(self, event_type: str, **details: Any) -> None:
        """Keep a bounded, robot-local trace for dashboard explanation."""
        self._local_trace_sequence += 1
        self.local_decision_history.append({
            "event_type": event_type,
            "tick": self.model.current_tick,
            "local_sequence": self._local_trace_sequence,
            "partitioned": self.model.network.partition_count > 1,
            **details,
        })
        if len(self.local_decision_history) > 500:
            del self.local_decision_history[:-500]

    def sense(self) -> None:
        """Observe local state and process only messages delivered to this robot."""
        network = self.model.network
        current_neighbors = tuple(network.neighbors(self.robot_id))
        if self._last_network_neighbors is not None and current_neighbors != self._last_network_neighbors:
            lost = sorted(set(self._last_network_neighbors) - set(current_neighbors))
            added = sorted(set(current_neighbors) - set(self._last_network_neighbors))
            self._record_local_event(
                "communication_neighbors_changed",
                previous_neighbors=list(self._last_network_neighbors),
                current_neighbors=list(current_neighbors),
                lost_neighbors=lost,
                added_neighbors=added,
            )
        self.nearby_agents = list(current_neighbors)
        self._last_network_neighbors = current_neighbors
        self.communication_status = "CONNECTED" if self.nearby_agents else "ISOLATED"
        for message in network.receive(f"Robot-{self.robot_id}"):
            if message.message_id in self._processed_message_ids:
                continue
            if len(self._processed_message_order) >= 5000:
                self._processed_message_ids.discard(self._processed_message_order.popleft())
            self._processed_message_order.append(message.message_id)
            self._processed_message_ids.add(message.message_id)
            payload = message.payload
            received_event = message.as_dict()
            self._local_trace_sequence += 1
            received_event.update({
                "received_tick": self.model.current_tick,
                "local_sequence": self._local_trace_sequence,
                "received_during_partition": network.partition_count > 1,
                "received_neighbor_ids": list(current_neighbors),
            })
            self.local_event_memory.append(received_event)
            if len(self.local_event_memory) > 500:
                del self.local_event_memory[:-500]
            if message.message_type == MessageType.TASK_ANNOUNCEMENT:
                task_id = int(payload["task_id"])
                existing = self.local_task_knowledge.get(task_id)
                if existing is None:
                    self.local_task_knowledge[task_id] = {
                        **payload, "announce_tick": self.model.current_tick,
                        "bids": {}, "claims": {}, "completed": False,
                        "bid_exclusions": {},
                    }
                elif existing.get("owner") is None and not existing.get("completed"):
                    existing.update(payload)
                    existing["announce_tick"] = self.model.current_tick
                    existing["bids"] = {}
                    self._last_bid_tick.pop(task_id, None)
                self.local_task_queue = sorted(self.local_task_knowledge)
                self._send_bid(task_id)
            elif message.message_type == MessageType.TASK_BID:
                try:
                    task_id, bidder, score = int(payload["task_id"]), int(payload["robot_id"]), float(payload["score"])
                except (KeyError, TypeError, ValueError):
                    self.model.auction_metrics["invalid_auction_messages_rejected"] += 1
                    continue
                task = self.local_task_knowledge.get(task_id)
                if task is not None and bidder in self.model.robots and math.isfinite(score):
                    task["bids"][bidder] = score
                else:
                    self.model.auction_metrics["invalid_auction_messages_rejected"] += 1
            elif message.message_type == MessageType.TASK_CLAIM:
                self._record_claim(payload)
            elif message.message_type == MessageType.TASK_COMPLETE:
                task_id = int(payload["task_id"])
                task = self.local_task_knowledge.get(task_id)
                if task is not None:
                    task["completed"] = True
                self._stop_superseded_task(task_id)
            elif message.message_type == MessageType.STATE_SYNC:
                network.state_sync_received += 1
                self._merge_state(payload)
            elif message.message_type == MessageType.TASK_ABANDON:
                task = self.local_task_knowledge.get(int(payload["task_id"]))
                if task:
                    task["claims"].pop(int(payload["robot_id"]), None)
                    task.setdefault("claim_expiry", {}).pop(int(payload["robot_id"]), None)
                    if task.get("owner") == int(payload["robot_id"]):
                        task.pop("owner", None)
                        task["announce_tick"] = self.model.current_tick
                        task["bids"] = {}
                        self._last_bid_tick.pop(int(payload["task_id"]), None)

        # Publish local status periodically. This is informational; assignments
        # are computed by each robot from its own sensor values and received bids.
        if self.model.current_tick % 3 == self.robot_id % 3:
            network.broadcast(f"Robot-{self.robot_id}", MessageType.ROBOT_STATUS,
                              {"robot_id": self.robot_id, "pos": list(self.pos_tuple),
                               "battery": self.battery, "status": self.status,
                               "current_task": getattr(self.current_task, "task_id", None)},
                              self.model.current_tick)
        if self.current_task is not None and self.model.current_tick % 10 == self.robot_id % 10:
            known = self.local_task_knowledge.get(self.current_task.task_id)
            if known is not None:
                score = known.get("claims", {}).get(self.robot_id, self._bid_score(known))
                known.setdefault("claim_expiry", {})[self.robot_id] = self.model.current_tick + 30
                network.broadcast(f"Robot-{self.robot_id}", MessageType.TASK_CLAIM,
                                  {"task_id": self.current_task.task_id, "robot_id": self.robot_id,
                                   "score": score, "lease_until": self.model.current_tick + 30},
                                  self.model.current_tick)

    def _bid_score(self, task: Dict[str, Any]) -> float:
        x, y = task["shelf_location"]
        distance = abs(self.pos_tuple[0] - x) + abs(self.pos_tuple[1] - y)
        urgency = -4.0 if task.get("priority") == "urgent" else 0.0
        return round(distance + (100.0 - self.battery) * 0.12 + urgency, 6)

    def _send_bid(self, task_id: int) -> None:
        task = self.local_task_knowledge[task_id]
        reason = None
        if task.get("completed") or task_id in self.model.completed_task_ids:
            reason = "task already completed"
        elif self.status != "IDLE":
            reason = f"robot is {self.status.lower().replace('_', ' ')}"
        elif self.battery < 25:
            reason = "battery below 25% bidding threshold"
        if reason:
            exclusions = task.setdefault("bid_exclusions", {})
            if exclusions.get(self.robot_id) != reason:
                exclusions[self.robot_id] = reason
                self.model.log_message(f"Robot-{self.robot_id}", "Auction", {
                    "action": "auction_bid_excluded", "task_id": task_id,
                    "robot_id": self.robot_id, "reason": reason})
            return
        task.setdefault("bid_exclusions", {}).pop(self.robot_id, None)
        distance = abs(self.pos_tuple[0] - int(task["shelf_location"][0])) + \
                   abs(self.pos_tuple[1] - int(task["shelf_location"][1]))
        battery_adjustment = (100.0 - self.battery) * 0.12
        urgency_adjustment = -4.0 if task.get("priority") == "urgent" else 0.0
        score = self._bid_score(task)
        task["bids"][self.robot_id] = score
        bid_messages = self.model.network.broadcast(
            f"Robot-{self.robot_id}", MessageType.TASK_BID,
            {"task_id": task_id, "robot_id": self.robot_id,
             "score": score, "battery": self.battery,
             "pos": list(self.pos_tuple)}, self.model.current_tick)
        self._last_bid_tick[task_id] = self.model.current_tick
        bid_key = (task_id, self.robot_id)
        if bid_key not in self.model._counted_bids:
            self.model._counted_bids.add(bid_key)
            self.model.auction_metrics["bids_submitted"] += 1
        self.model.log_message(f"Robot-{self.robot_id}", "Auction", {
            "action": "auction_bid_calculated", "task_id": task_id,
            "robot_id": self.robot_id, "score": score,
            "distance": distance,
            "battery_adjustment": battery_adjustment,
            "urgency_adjustment": urgency_adjustment,
            "position": list(self.pos_tuple),
            "battery": self.battery,
            "priority": task.get("priority", "normal"),
            "cost": "Manhattan distance + 0.12 × battery used - 4 for urgent work"})
        self._record_local_event(
            "bid_calculated", task_id=task_id, score=score, distance=distance,
            battery_adjustment=battery_adjustment,
            urgency_adjustment=urgency_adjustment, position=list(self.pos_tuple),
            battery=self.battery, priority=task.get("priority", "normal"),
        )
        robot_recipients = [
            int(message.recipient.split("-")[1]) for message in bid_messages
            if message.recipient.startswith("Robot-")
        ]
        self._record_local_event(
            "bid_broadcast", task_id=task_id,
            recipients=robot_recipients,
            message_ids=[message.message_id for message in bid_messages],
        )
        self.last_decision = f"Bid on task {task_id}"
        self.last_decision_reason = f"Local bid score {score:.2f}; lower is better"

    def _prune_expired_claims(self, task: Dict[str, Any]) -> None:
        expiries = task.setdefault("claim_expiry", {})
        claims = task.setdefault("claims", {})
        for rid in claims:
            expiries.setdefault(rid, self.model.current_tick + 30)
        expired = [rid for rid in claims if int(expiries.get(rid, 0)) <= self.model.current_tick]
        for rid in expired:
            claims.pop(rid, None)
            expiries.pop(rid, None)
        owner = task.get("owner")
        if owner is not None and owner not in claims:
            task.pop("owner", None)

    def _record_claim(self, payload: Dict[str, Any]) -> None:
        try:
            task_id, owner = int(payload["task_id"]), int(payload["robot_id"])
            score = float(payload["score"])
        except (KeyError, TypeError, ValueError):
            self.model.auction_metrics["invalid_auction_messages_rejected"] += 1
            return
        if owner not in self.model.robots or not math.isfinite(score):
            self.model.auction_metrics["invalid_auction_messages_rejected"] += 1
            return
        task = self.local_task_knowledge.get(task_id)
        if task is None:
            return
        if task_id in self.model.completed_task_ids:
            task["completed"] = True
            return
        if self.model.robots[owner].status == "FAILED":
            task.setdefault("claims", {}).pop(owner, None)
            task.setdefault("claim_expiry", {}).pop(owner, None)
            if task.get("owner") == owner:
                task.pop("owner", None)
            return
        claims = task["claims"]
        if task.get("completed"):
            return
        self._prune_expired_claims(task)
        claims = task["claims"]
        try:
            lease_until = int(payload.get("lease_until", self.model.current_tick + 30))
        except (TypeError, ValueError):
            self.model.auction_metrics["invalid_auction_messages_rejected"] += 1
            return
        claims[owner] = score
        task.setdefault("claim_expiry", {})[owner] = lease_until
        world_task = next((item for item in self.model.order_agent.all_tasks if item.task_id == task_id), None)
        if world_task is not None and world_task.status != "COMPLETED":
            world_task.status = "IN_PROGRESS"
            world_task.assigned_robot = owner
        if len(claims) > 1:
            conflict_key, is_new = self.model.network.record_claim_conflict(task_id, claims)
            winner = min(claims, key=lambda rid: (claims[rid], rid))
            task["owner"] = winner
            if world_task is not None and world_task.status != "COMPLETED":
                world_task.assigned_robot = winner
            if winner != self.robot_id and getattr(self.current_task, "task_id", None) == task_id:
                self._stop_superseded_task(task_id)
                self.model.network.duplicate_claims_prevented += 1
                self.model.network.broadcast(f"Robot-{self.robot_id}", MessageType.TASK_ABANDON,
                                             {"task_id": task_id, "robot_id": self.robot_id}, self.model.current_tick)
            if self.model.network.record_claim_resolution(conflict_key) and is_new:
                self.model.log_message("RobotNetwork", "RobotNetwork", {
                    "action": "task_conflict_reconciled", "task_id": task_id,
                    "claims": {str(rid): value for rid, value in sorted(claims.items())},
                    "rule": "lowest bid score, then lowest robot ID", "winner": winner})

    def _abandon_local_task(self, task_id: int) -> None:
        task = self.local_task_knowledge.get(task_id)
        world_task = next((t for t in self.model.order_agent.all_tasks if t.task_id == task_id), None)
        if (world_task is not None and world_task.status != "COMPLETED"
                and world_task.assigned_robot in (-1, self.robot_id)):
            world_task.status = "PENDING"
            world_task.assigned_robot = -1
        if task is not None:
            task.pop("owner", None)
            task.setdefault("claims", {}).pop(self.robot_id, None)
            task.setdefault("claim_expiry", {}).pop(self.robot_id, None)
            task["bids"] = {}
            task["announce_tick"] = self.model.current_tick
            self._last_bid_tick.pop(task_id, None)
        self.model.network.broadcast(f"Robot-{self.robot_id}", MessageType.TASK_ABANDON,
                                     {"task_id": task_id, "robot_id": self.robot_id}, self.model.current_tick)

    def _stop_superseded_task(self, task_id: int) -> None:
        """Stop uncompleted travel when a completion or winning claim supersedes it."""
        if getattr(self.current_task, "task_id", None) != task_id:
            return
        self.model.inventory_agent.release(self.current_task.shelf_location, self.robot_id)
        self.model.traffic_controller._clear_reservations(self.robot_id)
        self.current_task = None
        self.current_path = []
        self.path_index = 0
        if self.status != "FAILED":
            self.status = "IDLE"

    def publish_state_sync(self) -> None:
        """Share locally learned task and completion state after reconnect."""
        payload = {"robot_id": self.robot_id,
                   "tasks": [{"task_id": tid, "task": {k: v for k, v in data.items() if k not in ("bids", "claims")},
                              "bids": dict(data.get("bids", {})), "claims": dict(data.get("claims", {}))}
                             for tid, data in self.local_task_knowledge.items()]}
        self.model.network.broadcast(f"Robot-{self.robot_id}", MessageType.STATE_SYNC, payload, self.model.current_tick)

    def _merge_state(self, payload: Dict[str, Any]) -> None:
        changes = 0
        for item in payload.get("tasks", []):
            tid = int(item["task_id"])
            existing = self.local_task_knowledge.get(tid)
            if existing is None:
                existing = {**item["task"], "bids": {}, "claims": {}, "announce_tick": self.model.current_tick,
                            "bid_exclusions": {}}
                self.local_task_knowledge[tid] = existing
                changes += 1
            existing["bids"].update({int(k): float(v) for k, v in item.get("bids", {}).items()})
            existing["completed"] = bool(existing.get("completed") or item["task"].get("completed", False))
            if existing["completed"]:
                existing.pop("owner", None)
                existing["claims"].clear()
                self._stop_superseded_task(tid)
            else:
                existing.setdefault("claim_expiry", {}).update({int(k): int(v) for k, v in item["task"].get("claim_expiry", {}).items()})
                before = len(existing["claims"])
                existing["claims"] = {
                    int(k): float(v) for k, v in existing["claims"].items()
                    if int(k) in self.model.robots and self.model.robots[int(k)].status != "FAILED"
                }
                existing["claims"].update({
                    int(k): float(v) for k, v in item.get("claims", {}).items()
                    if int(k) in self.model.robots and self.model.robots[int(k)].status != "FAILED"
                })
                if existing.get("owner") in self.model.robots and self.model.robots[existing["owner"]].status == "FAILED":
                    existing.pop("owner", None)
                existing["claim_expiry"] = {
                    int(k): int(v) for k, v in existing.get("claim_expiry", {}).items()
                    if int(k) in self.model.robots and self.model.robots[int(k)].status != "FAILED"
                }
                for owner in existing["claims"]:
                    existing["claim_expiry"].setdefault(owner, self.model.current_tick + 30)
                self._prune_expired_claims(existing)
                if len(existing["claims"]) > before:
                    changes += 1
            if len(existing["claims"]) > 1:
                conflict_key, is_new = self.model.network.record_claim_conflict(tid, existing["claims"])
                previous_owner = existing.get("owner")
                existing["owner"] = min(existing["claims"], key=lambda rid: (existing["claims"][rid], rid))
                world_task = next((task for task in self.model.order_agent.all_tasks if task.task_id == tid), None)
                if world_task is not None and world_task.status != "COMPLETED":
                    world_task.status = "IN_PROGRESS"
                    world_task.assigned_robot = existing["owner"]
                if existing["owner"] != previous_owner:
                    changes += 1
                if self.model.network.record_claim_resolution(conflict_key) and is_new:
                    self.model.log_message(f"Robot-{self.robot_id}", "RobotNetwork", {
                        "action": "task_conflict_reconciled", "task_id": tid,
                        "claims": {str(rid): value for rid, value in sorted(existing["claims"].items())},
                        "rule": "lowest bid score, then lowest robot ID", "winner": existing["owner"]})
                if existing["owner"] != self.robot_id and getattr(self.current_task, "task_id", None) == tid:
                    self.model.network.duplicate_claims_prevented += 1
                    self._stop_superseded_task(tid)
        if changes:
            self.model.network.reconciliation_count += 1
            self.model.log_message(f"Robot-{self.robot_id}", "RobotNetwork", {
                "action": "state_reconciled", "changes": changes,
                "tasks_known": len(self.local_task_knowledge)})
            self._record_local_event(
                "state_synchronised", changes=changes,
                tasks_known=len(self.local_task_knowledge),
            )

    def decide(self) -> None:
        """Decide what action to take based on current state."""
        # Keep enough energy to reach the closest dock, including a small
        # reserve for detours caused by blocked aisles.
        dock_routes = [
            a_star(self.model.grid_width, self.model.grid_height, self.pos_tuple,
                   dock, self.model.blocked_cells)
            for dock in self.model.charging_docks
        ]
        reachable_lengths = [len(path) - 1 for path in dock_routes if path]
        safe_charge_threshold = (
            max(BATTERY_LOW_THRESHOLD, min(reachable_lengths) + 5.0)
            if reachable_lengths else BATTERY_LOW_THRESHOLD
        )
        if (
            self.battery <= safe_charge_threshold
            and self.status not in ("CHARGING", "EN_ROUTE_TO_CHARGE", "WAITING_FOR_CHARGE",
                                    "NEEDS_CHARGE", "FAILED")
        ):
            self._pre_charge_status = self.status
            self._pre_charge_task = self.current_task
            self.status = "NEEDS_CHARGE"
        # Consensus-inspired peer auction: wait one tick for reachable peer bids,
        # then choose the lowest advertised score with robot ID as stable tie-break.
        if self.status == "IDLE":
            for task_id in self.local_task_queue:
                task = self.local_task_knowledge[task_id]
                self._prune_expired_claims(task)
                owner = task.get("owner")
                expiry = task.get("claim_expiry", {}).get(owner, 0) if owner is not None else 0
                if owner is not None and expiry < self.model.current_tick and (owner != self.robot_id or self.current_task is None):
                    task.pop("owner", None)
                    task["claims"].pop(owner, None)
                    task.setdefault("claim_expiry", {}).pop(owner, None)
                if task.get("completed") or task.get("owner") is not None:
                    continue
                if task_id not in self._last_bid_tick:
                    self._send_bid(task_id)
                if self.model.current_tick - task["announce_tick"] < 1 or not task["bids"]:
                    continue
                winner = min(task["bids"], key=lambda rid: (task["bids"][rid], rid))
                if winner != self.robot_id:
                    continue
                self._accept_local_task(task_id, task)
                break

    def _accept_local_task(self, task_id: int, task_data: Dict[str, Any]) -> None:
        from .order_agent import Task
        if task_id in self.model.completed_task_ids or task_data.get("completed"):
            task_data["completed"] = True
            return
        task = Task(int(task_data.get("priority_rank", 1)), int(task_data.get("arrival_tick", 0)),
                    task_id, str(task_data["sku"]), int(task_data["qty"]),
                    str(task_data["priority"]), "IN_PROGRESS", self.robot_id,
                    tuple(task_data["shelf_location"]))
        if not self.model.inventory_agent.reserve(task.shelf_location, self.robot_id, task.sku, task.qty):
            task_data["bids"].pop(self.robot_id, None)
            self._last_bid_tick.pop(task_id, None)
            task_data["announce_tick"] = self.model.current_tick
            self.last_decision = f"Deferred task {task_id}"
            self.last_decision_reason = "Shared shelf resource was already reserved or stock was unavailable"
            return
        self.current_task = task
        self.status = "EN_ROUTE_TO_SHELF"
        task_data["owner"] = self.robot_id
        task_data["claims"][self.robot_id] = task_data["bids"].get(self.robot_id, self._bid_score(task_data))
        task_data.setdefault("claim_expiry", {})[self.robot_id] = self.model.current_tick + 30
        self.model.network.broadcast(f"Robot-{self.robot_id}", MessageType.TASK_CLAIM,
                                     {"task_id": task_id, "robot_id": self.robot_id,
                                      "score": task_data["claims"][self.robot_id], "lease_until": self.model.current_tick + 30},
                                     self.model.current_tick)
        self.model.auction_metrics["successful_allocations"] += 1
        world_task = next((item for item in self.model.order_agent.all_tasks if item.task_id == task_id), None)
        if world_task is not None and world_task.status != "COMPLETED":
            world_task.status = "IN_PROGRESS"
            world_task.assigned_robot = self.robot_id
        path = self.model.traffic_controller.request_route(self.robot_id, self.pos_tuple, task.shelf_location)
        if path:
            self.update_path(path)
            self.model.partition_decisions += int(self.model.network.partition_count > 1)
            self.independent_decisions += int(self.model.network.partition_count > 1)
            self.last_decision = f"Claimed task {task_id}"
            self.last_decision_reason = f"Lowest locally known bid ({task_data['claims'][self.robot_id]:.2f})"
            task_data["decision"] = self.last_decision_reason
            selected_score = float(task_data["claims"][self.robot_id])
            bid_record = next((
                event for event in reversed(self.local_decision_history)
                if event.get("event_type") == "bid_calculated"
                and event.get("task_id") == task_id
                and math.isclose(float(event.get("score", float("inf"))), selected_score,
                                 rel_tol=0.0, abs_tol=1e-9)
            ), None)
            self._record_local_event(
                "task_selected", task_id=task_id,
                bid=selected_score,
                available_bids={int(rid): float(value)
                                for rid, value in task_data["bids"].items()},
                reason=self.last_decision_reason,
                bid_calculation=({
                    key: bid_record[key] for key in (
                        "score", "distance", "battery_adjustment",
                        "urgency_adjustment", "position", "battery", "priority",
                    ) if key in bid_record
                } if bid_record else None),
            )
            self.model.log_message(f"Robot-{self.robot_id}", "RobotNetwork", {
                "action": "distributed_task_claim", "task_id": task_id,
                "robot_id": self.robot_id, "bid": task_data["claims"][self.robot_id],
                "bids": {str(rid): score for rid, score in sorted(task_data["bids"].items())},
                "known_bids": len(task_data["bids"])})
        else:
            self.model.inventory_agent.release(task.shelf_location, self.robot_id)
            self.current_task = None
            self.status = "IDLE"
            self._abandon_local_task(task_id)

    def act(self) -> None:
        """Execute one tick of robot behavior based on current state."""
        if self.status == "FAILED":
            return

        if self.status == "NEEDS_CHARGE":
            self._initiate_charging()
            return

        if self.status == "WAITING_FOR_CHARGE":
            return

        if self.status == "CHARGING":
            self._charge_tick()
            return

        if self.status == "IDLE":
            return

        if self.status in ("EN_ROUTE_TO_SHELF", "EN_ROUTE_TO_PACKING", "EN_ROUTE_TO_CHARGE", "RETURNING"):
            self._follow_path()
            return

        if self.status == "PICKING":
            self._pick_tick()
            return

        if self.status == "DROPPING":
            self._drop_tick()
            return

    def _follow_path(self) -> None:
        """Move one step along the current path."""
        if not self.current_path or self.path_index >= len(self.current_path) - 1:
            self._arrive_at_destination()
            return

        self.path_index += 1
        next_pos = self.current_path[self.path_index]

        # Check if next cell is occupied by another robot
        # Allow sharing at packing station and charging docks (work areas)
        inside_grid = 0 <= next_pos[0] < self.model.grid_width and 0 <= next_pos[1] < self.model.grid_height
        is_shared_area = next_pos == self.model.packing_station

        if not inside_grid or next_pos in self.model.blocked_cells:
            self.path_index -= 1
            self.model.traffic_controller.blocked_moves += 1
            return
        if not is_shared_area:
            occupants = self.model.get_robots_at(next_pos)
            if any(r.robot_id != self.robot_id for r in occupants):
                self.path_index -= 1
                self.model.traffic_controller.blocked_moves += 1
                return

        self.pos_tuple = next_pos
        self.battery = max(0, self.battery - BATTERY_DRAIN_PER_MOVE)

        # Update grid position
        if hasattr(self, 'pos') and self.pos is not None:
            self.model.grid.move_agent(self, next_pos)

    def _arrive_at_destination(self) -> None:
        """Handle arrival at the current destination."""
        if self.status == "EN_ROUTE_TO_SHELF":
            self.status = "PICKING"
            self._action_timer = PICK_TICKS
        elif self.status == "EN_ROUTE_TO_PACKING":
            self.status = "DROPPING"
            self._action_timer = DROP_TICKS
        elif self.status == "RETURNING":
            self.status = "IDLE"
            self.current_path = []
            self.path_index = 0
        elif self.status == "EN_ROUTE_TO_CHARGE":
            self.status = "CHARGING"
            self.current_path = []
            self.path_index = 0

    def _pick_tick(self) -> None:
        """Process one tick of the picking action."""
        self._action_timer -= 1
        self.battery = max(0, self.battery - BATTERY_DRAIN_PER_PICK)

        if self._action_timer <= 0:
            # Picking complete — head to packing station
            self.status = "EN_ROUTE_TO_PACKING"
            packing = self.model.packing_station
            path = self.model.traffic_controller.request_route(
                self.robot_id, self.pos_tuple, packing
            )
            if path:
                self.update_path(path)
            else:
                # Fallback: try next tick
                self.status = "PICKING"
                self._action_timer = 1

            self.model.log_message(
                from_agent=f"Robot-{self.robot_id}",
                to_agent="TrafficController",
                payload={
                    "action": "request_route_to_packing",
                    "from": self.pos_tuple,
                    "to": packing,
                },
            )

    def _drop_tick(self) -> None:
        """Process one tick of the dropping action."""
        self._action_timer -= 1

        if self._action_timer <= 0:
            # Dropping complete — task finished
            completed = False
            if self.current_task is not None:
                task_id = self.current_task.task_id
                completed = self.model.complete_distributed_task(self.robot_id, task_id)
                if task_id in self.local_task_knowledge:
                    task_data = self.local_task_knowledge[task_id]
                    task_data["completed"] = completed
                    if not completed:
                        task_data.pop("owner", None)
                        task_data["claims"].clear()
                        task_data["announce_tick"] = self.model.current_tick
            if completed:
                self.tasks_completed += 1

            # Clear reservations so other robots can use the paths
            self.model.traffic_controller._clear_reservations(self.robot_id)

            # Return to idle
            self.status = "IDLE"
            self.current_task = None
            self.current_path = []
            self.path_index = 0

    def _initiate_charging(self) -> None:
        """Request a charging dock from the Charging Agent."""
        # If we had an in-progress task, hand it off
        if self.current_task and self._pre_charge_status in (
            "EN_ROUTE_TO_SHELF",
            "EN_ROUTE_TO_PACKING",
        ):
            self.model.fleet_manager.handle_battery_handoff(self.robot_id)
            task_id = self.current_task.task_id
            self.model.inventory_agent.release(self.current_task.shelf_location, self.robot_id)
            task = next((t for t in self.model.order_agent.all_tasks if t.task_id == task_id), None)
            if task is not None and task.status != "COMPLETED":
                task.status = "PENDING"
                task.assigned_robot = -1
            self._abandon_local_task(task_id)
            self.current_task = None

        dock = self.model.charging_agent.request_charge(self.robot_id, self.pos_tuple)
        if dock is None:
            self.status = "WAITING_FOR_CHARGE"
            self.current_path = []
            self.path_index = 0
        elif self.pos_tuple == dock:
            self.status = "CHARGING"
        else:
            self.status = "EN_ROUTE_TO_CHARGE"

        self.model.log_message(
            from_agent=f"Robot-{self.robot_id}",
            to_agent="ChargingAgent",
            payload={
                "action": "request_charge",
                "battery": self.battery,
                "pos": self.pos_tuple,
            },
        )

    def _charge_tick(self) -> None:
        """Process one tick of charging."""
        if self._charging_dock is None or self.pos_tuple != self._charging_dock:
            self.status = "EN_ROUTE_TO_CHARGE" if self._charging_dock is not None else "WAITING_FOR_CHARGE"
            return
        self.battery = min(100.0, self.battery + BATTERY_CHARGE_PER_TICK)

        if self.battery >= 95.0:
            # Fully charged — release dock and resume
            self.model.charging_agent.release_robot(self.robot_id)
            self._charging_dock = None
            self.status = "IDLE"
            self.current_path = []
            self.path_index = 0

            self.model.log_message(
                from_agent=f"Robot-{self.robot_id}",
                to_agent="ChargingAgent",
                payload={"action": "charge_complete", "battery": self.battery},
            )
