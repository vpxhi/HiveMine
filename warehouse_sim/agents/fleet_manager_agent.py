"""
Fleet Manager Agent — Assigns robots to tasks using scored allocation.

Owner: Kalyan (cb.sc.u4cse23060) — Warehouse Intelligence
Responsibility: Maintains the live robot registry, scores candidate robots
using the multi-factor allocation formula, assigns the best robot, and
handles task reassignment on robot failure.

PEAS Formulation:
    Performance: Assignment optimality (distance + battery + workload), minimized idle robots.
    Environment: Live robot registry (location, battery %, current job).
    Actuators: assign_robot(task, robot_id).
    Sensors: Robot telemetry stream, task queue from Inventory Agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import mesa

from ..algorithms.task_allocation import allocate_task

if TYPE_CHECKING:
    from ..model import WarehouseModel
    from .order_agent import Task


class FleetManagerAgent(mesa.Agent):
    """
    Manages the robot fleet by assigning tasks to the best-fit robot.

    Uses scored allocation (distance + battery + workload + priority) to
    minimize average task completion time. Handles immediate reassignment
    when a robot fails mid-task.
    """

    def __init__(self, model: WarehouseModel) -> None:
        """Initialize the fleet manager."""
        super().__init__(model)
        self.robot_registry: Dict[int, Dict[str, Any]] = {}
        self.pending_assignments: List[Any] = []
        self.tasks_in_progress: Dict[int, Any] = {}  # robot_id -> task

    def register_robot(self, robot_id: int, pos: Tuple[int, int]) -> None:
        """Register a new robot in the fleet registry."""
        self.robot_registry[robot_id] = {
            "pos": pos,
            "battery": 100.0,
            "status": "IDLE",
            "workload": 0,
            "current_task": None,
        }

    def update_telemetry(
        self,
        robot_id: int,
        pos: Tuple[int, int],
        battery: float,
        status: str,
    ) -> None:
        """Update a robot's telemetry in the registry."""
        if robot_id in self.robot_registry:
            self.robot_registry[robot_id]["pos"] = pos
            self.robot_registry[robot_id]["battery"] = battery
            self.robot_registry[robot_id]["status"] = status

    def assign_task(self, task: Any) -> bool:
        """
        Assign a task to the best available robot.

        Uses the scored allocation function to select the optimal robot
        based on distance, battery, workload, and task priority.

        Args:
            task: The Task object to assign.

        Returns:
            True if assignment succeeded, False if no robot available.
        """
        robots_info = {
            rid: info
            for rid, info in self.robot_registry.items()
        }

        is_urgent = task.priority == "urgent"
        best_robot_id = allocate_task(
            robots_info, task.shelf_location, is_urgent
        )

        if best_robot_id is None:
            # No available robot — queue for later
            self.pending_assignments.append(task)
            return False

        # Assign the robot
        self._execute_assignment(best_robot_id, task)
        return True

    def _execute_assignment(self, robot_id: int, task: Any) -> None:
        """Execute the actual robot-task assignment."""
        self.robot_registry[robot_id]["status"] = "BUSY"
        self.robot_registry[robot_id]["workload"] += 1
        self.robot_registry[robot_id]["current_task"] = task.task_id
        self.tasks_in_progress[robot_id] = task

        task.status = "IN_PROGRESS"
        task.assigned_robot = robot_id

        # Reserve the shelf via inventory agent
        self.model.inventory_agent.reserve(task.shelf_location, robot_id)

        # Request route from traffic controller
        robot_pos = self.robot_registry[robot_id]["pos"]
        self.model.traffic_controller.request_route(
            robot_id, robot_pos, task.shelf_location
        )

        # Notify the robot
        robot = self.model.get_robot_by_id(robot_id)
        if robot:
            robot.receive_assignment(task)

        self.model.log_message(
            from_agent="FleetManager",
            to_agent=f"Robot-{robot_id}",
            payload={
                "action": "assign_task",
                "task_id": task.task_id,
                "shelf_location": task.shelf_location,
                "robot_id": robot_id,
            },
        )

    def handle_robot_failure(self, robot_id: int) -> None:
        """
        Handle a robot failure by reassigning its in-progress task.

        Args:
            robot_id: The failed robot's ID.
        """
        self.robot_registry[robot_id]["status"] = "FAILED"

        if robot_id in self.tasks_in_progress:
            task = self.tasks_in_progress.pop(robot_id)
            # Release the shelf reservation
            self.model.inventory_agent.release(task.shelf_location)
            # Re-queue the task
            task.status = "PENDING"
            task.assigned_robot = -1
            self.pending_assignments.append(task)

            self.model.log_message(
                from_agent="FleetManager",
                to_agent="OrderAgent",
                payload={
                    "action": "task_reassignment",
                    "task_id": task.task_id,
                    "failed_robot": robot_id,
                    "reason": "robot_failure",
                },
            )

    def handle_battery_handoff(self, robot_id: int) -> None:
        """Hand off a task from a low-battery robot to another robot."""
        if robot_id in self.tasks_in_progress:
            task = self.tasks_in_progress.pop(robot_id)
            self.model.inventory_agent.release(task.shelf_location)
            task.status = "PENDING"
            task.assigned_robot = -1
            self.pending_assignments.append(task)

            self.model.log_message(
                from_agent="FleetManager",
                to_agent="System",
                payload={
                    "action": "battery_handoff",
                    "task_id": task.task_id,
                    "from_robot": robot_id,
                },
            )

    def complete_task(self, robot_id: int) -> None:
        """Mark a robot's current task as complete and free the robot."""
        if robot_id in self.tasks_in_progress:
            task = self.tasks_in_progress.pop(robot_id)
            self.robot_registry[robot_id]["workload"] = max(
                0, self.robot_registry[robot_id]["workload"] - 1
            )
            self.robot_registry[robot_id]["status"] = "IDLE"
            self.robot_registry[robot_id]["current_task"] = None
            self.model.inventory_agent.release(task.shelf_location)
            self.model.inventory_agent.decrement_stock(
                task.shelf_location, task.sku, task.qty
            )
            self.model.order_agent.mark_task_completed(task.task_id)

            self.model.log_message(
                from_agent="FleetManager",
                to_agent="OrderAgent",
                payload={
                    "action": "task_completed",
                    "task_id": task.task_id,
                    "robot_id": robot_id,
                },
            )

    def sense(self) -> None:
        """Sense robot telemetry (robots push updates to the registry)."""
        pass

    def decide(self) -> None:
        """Check if any pending assignments can now be fulfilled."""
        self._retryable_tasks = []
        for task in self.pending_assignments:
            if task.status == "PENDING":
                self._retryable_tasks.append(task)

    def act(self) -> None:
        """Retry pending assignments."""
        still_pending = []
        for task in self._retryable_tasks:
            robots_info = {
                rid: info
                for rid, info in self.robot_registry.items()
            }
            is_urgent = task.priority == "urgent"
            best = allocate_task(robots_info, task.shelf_location, is_urgent)

            if best is not None:
                self._execute_assignment(best, task)
                if task in self.pending_assignments:
                    self.pending_assignments.remove(task)
            else:
                still_pending.append(task)
