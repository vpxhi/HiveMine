"""
Conflict-Based Search (CBS) for Multi-Robot Path Planning.

Owner: Rohith (cb.sc.u4cse23018) — Robot Intelligence
Responsibility: Resolves multi-robot path conflicts optimally using a two-level
search: high-level constraint tree + low-level constrained A* per robot.

Algorithm Justification (vs. Priority-Based Planning):
    Priority-based planning assigns fixed priorities to robots and plans
    sequentially — higher-priority robots ignore lower ones. This can starve
    low-priority robots indefinitely and produces suboptimal solutions.
    CBS guarantees optimality under the sum-of-costs objective by systematically
    exploring constraint alternatives. It avoids the joint-state explosion
    (O(cells^robots)) by planning per-agent with constraints, making it
    tractable for 5-10 robots on a 20x20 grid.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .astar import a_star


@dataclass
class Conflict:
    """Represents a conflict between two agents."""

    agent_1: int
    agent_2: int
    location: Tuple[int, int]
    timestep: int
    conflict_type: str  # "vertex" or "edge"
    location_2: Optional[Tuple[int, int]] = None  # For edge conflicts


@dataclass(order=True)
class CTNode:
    """Constraint Tree node for CBS high-level search."""

    cost: int
    node_id: int = field(compare=True)
    constraints: Dict[int, Set[Tuple[Tuple[int, int], int]]] = field(
        default_factory=dict, compare=False
    )
    solution: Dict[int, List[Tuple[int, int]]] = field(
        default_factory=dict, compare=False
    )


def detect_first_conflict(
    solution: Dict[int, List[Tuple[int, int]]],
) -> Optional[Conflict]:
    """
    Detect the first vertex or edge conflict in a set of paths.

    A vertex conflict occurs when two agents occupy the same cell at the
    same timestep. An edge conflict occurs when two agents swap positions
    (head-on collision).

    Args:
        solution: Mapping of agent_id to their planned path.

    Returns:
        The first Conflict found, or None if paths are conflict-free.
    """
    agents = list(solution.keys())
    if len(agents) < 2:
        return None

    # Find max path length
    max_t = max(len(path) for path in solution.values())

    for t in range(max_t):
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a1, a2 = agents[i], agents[j]
                path1, path2 = solution[a1], solution[a2]

                # Get positions (agents stay at goal after path ends)
                pos1 = path1[t] if t < len(path1) else path1[-1]
                pos2 = path2[t] if t < len(path2) else path2[-1]

                # Vertex conflict: same cell, same time
                if pos1 == pos2:
                    return Conflict(
                        agent_1=a1,
                        agent_2=a2,
                        location=pos1,
                        timestep=t,
                        conflict_type="vertex",
                    )

                # Edge conflict: agents swap positions (head-on collision)
                if t > 0:
                    prev1 = path1[t - 1] if t - 1 < len(path1) else path1[-1]
                    prev2 = path2[t - 1] if t - 1 < len(path2) else path2[-1]
                    if pos1 == prev2 and pos2 == prev1:
                        return Conflict(
                            agent_1=a1,
                            agent_2=a2,
                            location=pos1,
                            timestep=t,
                            conflict_type="edge",
                            location_2=pos2,
                        )

    return None


def _get_path_cost(solution: Dict[int, List[Tuple[int, int]]]) -> int:
    """Compute the sum-of-costs for all agent paths."""
    return sum(len(path) - 1 for path in solution.values())


def cbs_solve(
    grid_width: int,
    grid_height: int,
    agents_starts_goals: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
    blocked_cells: Set[Tuple[int, int]],
    max_iterations: int = 500,
) -> Optional[Dict[int, List[Tuple[int, int]]]]:
    """
    Solve multi-robot pathfinding using Conflict-Based Search.

    High-level: maintains a constraint tree where each node holds per-agent
    constraints. On conflict, the node is split into two children — one
    constraining each conflicting agent.

    Low-level: runs constrained A* for each agent.

    Args:
        grid_width: Width of the grid.
        grid_height: Height of the grid.
        agents_starts_goals: Dict mapping agent_id to (start, goal) tuples.
        blocked_cells: Set of permanently impassable cells.
        max_iterations: Safety cap on CBS iterations.

    Returns:
        Dict mapping agent_id to conflict-free path, or None if unsolvable.
    """
    if not agents_starts_goals:
        return {}

    node_counter = 0

    # Build root node: unconstrained paths for all agents
    root_constraints: Dict[int, Set[Tuple[Tuple[int, int], int]]] = {
        aid: set() for aid in agents_starts_goals
    }
    root_solution: Dict[int, List[Tuple[int, int]]] = {}

    for aid, (start, goal) in agents_starts_goals.items():
        path = a_star(grid_width, grid_height, start, goal, blocked_cells)
        if path is None:
            return None  # Agent has no feasible path at all
        root_solution[aid] = path

    root_cost = _get_path_cost(root_solution)
    root = CTNode(
        cost=root_cost,
        node_id=node_counter,
        constraints=root_constraints,
        solution=root_solution,
    )

    open_list: List[CTNode] = []
    heapq.heappush(open_list, root)

    iterations = 0

    while open_list and iterations < max_iterations:
        iterations += 1
        current = heapq.heappop(open_list)

        # Check for conflicts
        conflict = detect_first_conflict(current.solution)
        if conflict is None:
            return current.solution  # Conflict-free solution found

        # Split on the conflict — create two child nodes
        for agent_id in [conflict.agent_1, conflict.agent_2]:
            # Deep copy constraints
            child_constraints = {
                aid: set(c) for aid, c in current.constraints.items()
            }

            # Add new constraint for this agent
            child_constraints[agent_id].add(
                (conflict.location, conflict.timestep)
            )

            # For edge conflicts, also constrain the swap location
            if conflict.conflict_type == "edge" and conflict.location_2:
                child_constraints[agent_id].add(
                    (conflict.location_2, conflict.timestep)
                )

            # Re-plan only the constrained agent
            start, goal = agents_starts_goals[agent_id]
            new_path = a_star(
                grid_width,
                grid_height,
                start,
                goal,
                blocked_cells,
                constraints=child_constraints[agent_id],
            )

            if new_path is None:
                continue  # This branch is infeasible

            # Build child solution
            child_solution = dict(current.solution)
            child_solution[agent_id] = new_path

            child_cost = _get_path_cost(child_solution)
            node_counter += 1
            child = CTNode(
                cost=child_cost,
                node_id=node_counter,
                constraints=child_constraints,
                solution=child_solution,
            )

            heapq.heappush(open_list, child)

    # Max iterations reached or no solution
    return None


def validate_solution(
    solution: Dict[int, List[Tuple[int, int]]],
) -> Tuple[bool, List[Conflict]]:
    """
    Validate that a multi-agent solution has no conflicts.

    Args:
        solution: Dict mapping agent_id to path.

    Returns:
        Tuple of (is_valid, list_of_conflicts).
    """
    conflicts = []
    agents = list(solution.keys())
    max_t = max(len(path) for path in solution.values()) if solution else 0

    for t in range(max_t):
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a1, a2 = agents[i], agents[j]
                path1, path2 = solution[a1], solution[a2]

                pos1 = path1[t] if t < len(path1) else path1[-1]
                pos2 = path2[t] if t < len(path2) else path2[-1]

                if pos1 == pos2:
                    conflicts.append(
                        Conflict(a1, a2, pos1, t, "vertex")
                    )

                if t > 0:
                    prev1 = path1[t - 1] if t - 1 < len(path1) else path1[-1]
                    prev2 = path2[t - 1] if t - 1 < len(path2) else path2[-1]
                    if pos1 == prev2 and pos2 == prev1:
                        conflicts.append(
                            Conflict(a1, a2, pos1, t, "edge", pos2)
                        )

    return len(conflicts) == 0, conflicts
