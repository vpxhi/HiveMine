"""
Charging Agent — Manages charging dock allocation and robot battery recovery.

Owner: Venkat (cb.sc.u4cse23055) — Operations
Responsibility: Monitors fleet battery levels, assigns nearest free charging
dock, and manages queue when all docks are occupied.

PEAS Formulation:
    Performance: No robot ever hits 0% mid-task, charger utilization balance.
    Environment: Charging station occupancy, fleet battery levels.
    Actuators: queue_for_charge(), release_from_charge().
    Sensors: Battery telemetry broadcast from Fleet Manager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import mesa

from ..algorithms.astar import manhattan_distance

if TYPE_CHECKING:
    from ..model import WarehouseModel

BATTERY_CRITICAL_THRESHOLD = 20.0


class ChargingAgent(mesa.Agent):
    """
    Manages charging dock allocation and robot charging queues.

When a robot requests a dock, the nearest reachable free dock is reserved.
If all docks are occupied, the robot is queued and flagged in the dashboard
as "waiting to charge."
    """

    def __init__(
        self,
        model: WarehouseModel,
        dock_locations: List[Tuple[int, int]],
    ) -> None:
        """Initialize with the positions of charging docks."""
        super().__init__(model)
        self.dock_locations = dock_locations
        # dock_occupancy: maps dock_location -> robot_id or None
        self.dock_occupancy: Dict[Tuple[int, int], Optional[int]] = {
            loc: None for loc in dock_locations
        }
        self.charge_queue: List[int] = []  # robot_ids waiting for a dock
        self.robots_charging: Dict[int, Tuple[int, int]] = {}  # robot_id -> dock

    def request_charge(
        self, robot_id: int, robot_pos: Tuple[int, int]
    ) -> Optional[Tuple[int, int]]:
        """
        Assign the nearest free charging dock to a robot.

        If all docks are full, queue the robot.

        Args:
            robot_id: The robot requesting a charge.
            robot_pos: The robot's current position.

        Returns:
            The dock location if assigned, None if queued.
        """
        if robot_id not in self.model.robots or self.model.robots[robot_id].status == "FAILED":
            return None
        if robot_id in self.robots_charging:
            return self.robots_charging[robot_id]

        # Find a reachable free dock before reserving it.
        free_docks = [
            loc for loc, occupant in self.dock_occupancy.items()
            if occupant is None
            and all(robot.robot_id == robot_id for robot in self.model.get_robots_at(loc))
        ]

        for nearest in sorted(free_docks, key=lambda d: manhattan_distance(robot_pos, d)):
            path = self.model.traffic_controller.request_route(robot_id, robot_pos, nearest)
            if not path:
                continue
            self.dock_occupancy[nearest] = robot_id
            self.robots_charging[robot_id] = nearest
            robot = self.model.get_robot_by_id(robot_id)
            if robot:
                robot._charging_dock = nearest
                robot.update_path(path)
                robot.status = "CHARGING" if robot.pos_tuple == nearest else "EN_ROUTE_TO_CHARGE"
            self.model.log_message("ChargingAgent", f"Robot-{robot_id}", {
                "action": "dock_assigned", "dock_location": nearest})
            return nearest
        if robot_id not in self.charge_queue:
            self.charge_queue.append(robot_id)
        self.model.log_message("ChargingAgent", f"Robot-{robot_id}", {
            "action": "queued_for_charge", "queue_position": len(self.charge_queue)})
        return None

    def release_robot(self, robot_id: int) -> None:
        """
        Release a robot from its charging dock.

        If robots are queued, assign the freed dock to the next in line.

        Args:
            robot_id: The robot that has finished charging.
        """
        if robot_id in self.robots_charging:
            dock = self.robots_charging.pop(robot_id)
            self.dock_occupancy[dock] = None

            self.model.log_message(
                from_agent="ChargingAgent",
                to_agent="System",
                payload={
                    "action": "dock_released",
                    "dock_location": dock,
                    "freed_by": robot_id,
                },
            )

            # Assign dock to next queued robot
            while self.charge_queue:
                next_robot_id = self.charge_queue.pop(0)
                next_robot = self.model.get_robot_by_id(next_robot_id)
                if next_robot and next_robot.status != "FAILED":
                    self.request_charge(next_robot_id, next_robot.pos_tuple)
                    break

    def sense(self) -> None:
        """Monitor fleet battery levels for critical robots."""
        self._critical_robots = []
        for rid, info in self.model.fleet_manager.robot_registry.items():
            if (
                info["battery"] < BATTERY_CRITICAL_THRESHOLD
                and info["status"] not in ("CHARGING", "FAILED")
                and rid not in self.robots_charging
                and rid not in self.charge_queue
            ):
                self._critical_robots.append(rid)

    def decide(self) -> None:
        """Decide which critical robots need immediate charging."""
        pass  # Robots self-report via request_charge()

    def act(self) -> None:
        """Proactively redirect critical-battery robots to charge."""
        for rid in self._critical_robots:
            robot = self.model.get_robot_by_id(rid)
            if robot and robot.status not in (
                "CHARGING", "EN_ROUTE_TO_CHARGE", "WAITING_FOR_CHARGE", "NEEDS_CHARGE", "FAILED"
            ):
                robot.status = "NEEDS_CHARGE"
        physically_available = any(
            owner is None and not self.model.get_robots_at(loc)
            for loc, owner in self.dock_occupancy.items()
        )
        if self.charge_queue and physically_available:
            next_robot_id = self.charge_queue.pop(0)
            next_robot = self.model.get_robot_by_id(next_robot_id)
            if next_robot and next_robot.status != "FAILED":
                self.request_charge(next_robot_id, next_robot.pos_tuple)

    def get_charging_count(self) -> int:
        """Return number of robots currently charging."""
        return sum(1 for robot in self.model.robots.values() if robot.status == "CHARGING")

    def get_queue_length(self) -> int:
        """Return number of robots waiting for a dock."""
        return len(self.charge_queue)
