"""
Traffic Controller Agent — Manages multi-robot path planning and reservations.

Owner: Venkat (cb.sc.u4cse23055) — Operations
Responsibility: Owns the space-time reservation table, plans routes using A*,
escalates to CBS on conflict, and reroutes robots when aisles are blocked.

PEAS Formulation:
    Performance: Zero collisions, zero deadlocks, minimized total path cost.
    Environment: Grid map, reservation table, other robots' planned paths.
    Actuators: plan_route(), reroute(), hold_at_node().
    Sensors: Robot positions, aisle-block events, active reservations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

import mesa

from ..algorithms.astar import a_star, a_star_simple
from ..algorithms.cbs import cbs_solve, detect_first_conflict
from ..algorithms.task_allocation import detect_deadlock, resolve_deadlock

if TYPE_CHECKING:
    from ..model import WarehouseModel


class TrafficControllerAgent(mesa.Agent):
    """
    Manages collision-free multi-robot navigation across the warehouse grid.

    Uses A* for single-robot routing and escalates to CBS when conflicts
    are detected. Maintains a reservation table to prevent collisions.
    """

    def __init__(self, model: WarehouseModel) -> None:
        """Initialize the traffic controller."""
        super().__init__(model)
        # reservation_table: maps (cell, timestep) -> robot_id
        self.reservation_table: Dict[Tuple[Tuple[int, int], int], int] = {}
        # Active paths: robot_id -> list of (x,y) positions per timestep
        self.active_paths: Dict[int, List[Tuple[int, int]]] = {}
        self.collision_count: int = 0
        self.deadlocks_resolved: int = 0
        self.reroutes_performed: int = 0

    def request_route(
        self,
        robot_id: int,
        start: Tuple[int, int],
        goal: Tuple[int, int],
    ) -> Optional[List[Tuple[int, int]]]:
        """
        Plan a route for a robot, resolving conflicts if needed.

        First attempts plain A*. If the resulting path conflicts with
        existing reservations, escalates to CBS for the conflicting robots.

        Args:
            robot_id: The robot requesting a route.
            start: Starting cell.
            goal: Goal cell.

        Returns:
            The planned path, or None if no path is feasible.
        """
        blocked = self.model.blocked_cells.copy()

        # Try simple A* first
        path = a_star_simple(
            self.model.grid_width,
            self.model.grid_height,
            start,
            goal,
            blocked,
        )

        if path is None:
            return None

        # Check for conflicts with existing reservations
        conflict_robots = self._check_path_conflicts(robot_id, path)

        if conflict_robots:
            # Escalate to CBS
            path = self._resolve_with_cbs(robot_id, start, goal, conflict_robots)
            if path is None:
                return None

        # Register the path in the reservation table
        self._register_path(robot_id, path)

        self.model.log_message(
            from_agent="TrafficController",
            to_agent=f"Robot-{robot_id}",
            payload={
                "action": "route_planned",
                "path_length": len(path),
                "start": start,
                "goal": goal,
                "used_cbs": len(conflict_robots) > 0 if conflict_robots else False,
            },
        )

        return path

    def _check_path_conflicts(
        self,
        robot_id: int,
        path: List[Tuple[int, int]],
    ) -> Set[int]:
        """Check if a planned path conflicts with existing reservations."""
        conflict_robots: Set[int] = set()
        base_time = self.model.current_tick

        for t, cell in enumerate(path):
            key = (cell, base_time + t)
            if key in self.reservation_table:
                existing_robot = self.reservation_table[key]
                if existing_robot != robot_id:
                    conflict_robots.add(existing_robot)

        return conflict_robots

    def _resolve_with_cbs(
        self,
        robot_id: int,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        conflict_robots: Set[int],
    ) -> Optional[List[Tuple[int, int]]]:
        """Use CBS to resolve conflicts between the requesting robot and others."""
        agents_sg: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]] = {
            robot_id: (start, goal)
        }

        for crid in conflict_robots:
            if crid in self.active_paths and self.active_paths[crid]:
                cr_start = self.active_paths[crid][0]
                cr_goal = self.active_paths[crid][-1]
                agents_sg[crid] = (cr_start, cr_goal)

        blocked = self.model.blocked_cells.copy()
        solution = cbs_solve(
            self.model.grid_width,
            self.model.grid_height,
            agents_sg,
            blocked,
        )

        if solution and robot_id in solution:
            # Update all affected robots' paths
            for aid, new_path in solution.items():
                if aid != robot_id:
                    self._clear_reservations(aid)
                    self._register_path(aid, new_path)
                    # Update the robot's path
                    robot = self.model.get_robot_by_id(aid)
                    if robot:
                        robot.update_path(new_path)
            self.reroutes_performed += 1
            return solution[robot_id]

        return None

    def _register_path(
        self, robot_id: int, path: List[Tuple[int, int]]
    ) -> None:
        """Register a robot's path in the reservation table."""
        self._clear_reservations(robot_id)
        base_time = self.model.current_tick
        self.active_paths[robot_id] = path

        for t, cell in enumerate(path):
            self.reservation_table[(cell, base_time + t)] = robot_id

    def _clear_reservations(self, robot_id: int) -> None:
        """Clear all reservations belonging to a robot."""
        keys_to_remove = [
            k for k, v in self.reservation_table.items() if v == robot_id
        ]
        for k in keys_to_remove:
            del self.reservation_table[k]

        if robot_id in self.active_paths:
            del self.active_paths[robot_id]

    def reroute_on_block(self, blocked_cell: Tuple[int, int]) -> int:
        """
        Reroute all robots whose paths pass through a newly blocked cell.

        Args:
            blocked_cell: The cell that has become impassable.

        Returns:
            Number of robots rerouted.
        """
        affected_robots = []
        for robot_id, path in list(self.active_paths.items()):
            if blocked_cell in path:
                affected_robots.append(robot_id)

        rerouted = 0
        for robot_id in affected_robots:
            robot = self.model.get_robot_by_id(robot_id)
            if robot and robot.current_path:
                # Get current position and goal
                current_pos = robot.pos_tuple
                goal = robot.current_path[-1]

                self._clear_reservations(robot_id)
                new_path = self.request_route(robot_id, current_pos, goal)

                if new_path:
                    robot.update_path(new_path)
                    rerouted += 1
                else:
                    # Park the robot if no path available
                    robot.hold()

        self.model.log_message(
            from_agent="TrafficController",
            to_agent="System",
            payload={
                "action": "reroute_on_block",
                "blocked_cell": blocked_cell,
                "robots_affected": len(affected_robots),
                "robots_rerouted": rerouted,
            },
        )

        return rerouted

    def check_and_resolve_deadlocks(self) -> int:
        """
        Check for deadlocks and resolve them.

        Returns:
            Number of deadlocks resolved this tick.
        """
        # Build wait-for graph
        wait_for: Dict[int, Set[int]] = {}

        for robot_id, path in self.active_paths.items():
            robot = self.model.get_robot_by_id(robot_id)
            if not robot or robot.status == "IDLE":
                continue

            # Check if robot is blocked by another robot
            if robot.path_index < len(path) - 1:
                next_cell = path[robot.path_index + 1] if robot.path_index + 1 < len(path) else None
                if next_cell:
                    for other_id, other_path in self.active_paths.items():
                        if other_id == robot_id:
                            continue
                        other_robot = self.model.get_robot_by_id(other_id)
                        if other_robot and other_robot.pos_tuple == next_cell:
                            wait_for.setdefault(robot_id, set()).add(other_id)

        # Detect cycle
        cycle = detect_deadlock(wait_for)
        if cycle is None:
            return 0

        # Resolve: roll back lowest-priority robot
        priorities = {
            rid: self.model.fleet_manager.robot_registry.get(rid, {}).get(
                "workload", 0
            )
            for rid in cycle
        }
        yielding_robot = resolve_deadlock(cycle, priorities)

        # Force the yielding robot to wait and replan
        robot = self.model.get_robot_by_id(yielding_robot)
        if robot:
            self._clear_reservations(yielding_robot)
            robot.hold()

            # Replan after one tick delay
            if robot.current_path:
                goal = robot.current_path[-1]
                new_path = self.request_route(
                    yielding_robot, robot.pos_tuple, goal
                )
                if new_path:
                    robot.update_path(new_path)

        self.deadlocks_resolved += 1

        self.model.log_message(
            from_agent="TrafficController",
            to_agent="System",
            payload={
                "action": "deadlock_resolved",
                "cycle": cycle,
                "yielding_robot": yielding_robot,
            },
        )

        return 1

    def sense(self) -> None:
        """Clean up stale reservations."""
        stale = [
            k for k in self.reservation_table
            if k[1] < self.model.current_tick - 5
        ]
        for k in stale:
            del self.reservation_table[k]

    def decide(self) -> None:
        """Check for deadlocks."""
        self.check_and_resolve_deadlocks()

    def act(self) -> None:
        """No proactive actions — reactive to route requests."""
        pass
