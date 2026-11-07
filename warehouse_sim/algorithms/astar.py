"""
A* Pathfinding Algorithm for Warehouse Grid Navigation.

Owner: Rohith (cb.sc.u4cse23018) — Robot Intelligence
Responsibility: Provides single-robot shortest-path computation on a 2D grid
with support for blocked cells and time-expanded constraints (for CBS integration).

Algorithm Justification (vs. Dijkstra):
    A* uses a Manhattan-distance heuristic that is admissible and consistent on
    4-directional grids. This prunes the search space significantly compared to
    Dijkstra, which expands nodes uniformly in all directions regardless of goal
    location. For point-to-point warehouse queries, A* typically explores 40-60%
    fewer nodes than Dijkstra on a 20x20 grid.
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Set, Tuple


def manhattan_distance(a: Tuple[int, int], b: Tuple[int, int]) -> int:
    """Compute Manhattan distance between two grid cells."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def get_neighbors(
    pos: Tuple[int, int],
    grid_width: int,
    grid_height: int,
) -> List[Tuple[int, int]]:
    """Return valid 4-directional neighbors within grid bounds."""
    x, y = pos
    neighbors = []
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < grid_width and 0 <= ny < grid_height:
            neighbors.append((nx, ny))
    return neighbors


def a_star(
    grid_width: int,
    grid_height: int,
    start: Tuple[int, int],
    goal: Tuple[int, int],
    blocked_cells: Set[Tuple[int, int]],
    constraints: Optional[Set[Tuple[Tuple[int, int], int]]] = None,
    max_timesteps: int = 200,
) -> Optional[List[Tuple[int, int]]]:
    """
    Compute shortest path from start to goal on a grid using A*.

    Supports time-expanded constraints for CBS integration. Each constraint
    is a (cell, timestep) tuple indicating the cell is forbidden at that time.

    Args:
        grid_width: Width of the grid.
        grid_height: Height of the grid.
        start: Starting cell (x, y).
        goal: Goal cell (x, y).
        blocked_cells: Set of permanently impassable cells.
        constraints: Optional set of (cell, timestep) pairs that are forbidden.
        max_timesteps: Maximum time horizon to prevent infinite loops.

    Returns:
        List of cells forming the path from start to goal (inclusive),
        or None if no path exists.
    """
    if start in blocked_cells or goal in blocked_cells:
        return None

    if constraints is None:
        constraints = set()

    # State: (x, y, timestep)
    # Priority queue: (f_score, counter, x, y, timestep)
    counter = 0
    open_set: List[Tuple[int, int, int, int, int]] = []
    start_h = manhattan_distance(start, goal)
    heapq.heappush(open_set, (start_h, counter, start[0], start[1], 0))

    # g_score: maps (x, y, t) -> best known cost
    g_score: Dict[Tuple[int, int, int], int] = {(start[0], start[1], 0): 0}

    # came_from: maps (x, y, t) -> (px, py, pt)
    came_from: Dict[Tuple[int, int, int], Optional[Tuple[int, int, int]]] = {
        (start[0], start[1], 0): None
    }

    while open_set:
        f, _, x, y, t = heapq.heappop(open_set)

        # Goal reached
        if (x, y) == goal:
            return _reconstruct_path(came_from, (x, y, t))

        if t >= max_timesteps:
            continue

        current_g = g_score.get((x, y, t), float("inf"))

        # Explore neighbors + wait-in-place action
        moves = get_neighbors((x, y), grid_width, grid_height) + [(x, y)]

        for nx, ny in moves:
            next_t = t + 1

            # Skip permanently blocked cells
            if (nx, ny) in blocked_cells:
                continue

            # Skip time-constrained cells
            if ((nx, ny), next_t) in constraints:
                continue

            tentative_g = current_g + 1
            state = (nx, ny, next_t)

            if tentative_g < g_score.get(state, float("inf")):
                g_score[state] = tentative_g
                came_from[state] = (x, y, t)
                h = manhattan_distance((nx, ny), goal)
                counter += 1
                heapq.heappush(open_set, (tentative_g + h, counter, nx, ny, next_t))

    # No path found
    return None


def _reconstruct_path(
    came_from: Dict[Tuple[int, int, int], Optional[Tuple[int, int, int]]],
    end_state: Tuple[int, int, int],
) -> List[Tuple[int, int]]:
    """Trace back from end_state to reconstruct the spatial path."""
    path = []
    current: Optional[Tuple[int, int, int]] = end_state
    while current is not None:
        path.append((current[0], current[1]))
        current = came_from.get(current)
    path.reverse()
    return path


def a_star_simple(
    grid_width: int,
    grid_height: int,
    start: Tuple[int, int],
    goal: Tuple[int, int],
    blocked_cells: Set[Tuple[int, int]],
) -> Optional[List[Tuple[int, int]]]:
    """
    Simplified A* without time expansion — for basic routing queries.

    This is a convenience wrapper that ignores temporal constraints,
    useful for distance estimation and non-conflicting single-robot paths.

    Args:
        grid_width: Width of the grid.
        grid_height: Height of the grid.
        start: Starting cell (x, y).
        goal: Goal cell (x, y).
        blocked_cells: Set of permanently impassable cells.

    Returns:
        List of cells forming the shortest path, or None if unreachable.
    """
    if start in blocked_cells or goal in blocked_cells:
        return None

    counter = 0
    open_set: List[Tuple[int, int, int, int]] = []
    start_h = manhattan_distance(start, goal)
    heapq.heappush(open_set, (start_h, counter, start[0], start[1]))

    g_score: Dict[Tuple[int, int], int] = {start: 0}
    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}

    while open_set:
        f, _, x, y = heapq.heappop(open_set)

        if (x, y) == goal:
            # Reconstruct
            path = []
            cur: Optional[Tuple[int, int]] = (x, y)
            while cur is not None:
                path.append(cur)
                cur = came_from.get(cur)
            path.reverse()
            return path

        current_g = g_score[(x, y)]

        for nx, ny in get_neighbors((x, y), grid_width, grid_height):
            if (nx, ny) in blocked_cells:
                continue
            tentative_g = current_g + 1
            if tentative_g < g_score.get((nx, ny), float("inf")):
                g_score[(nx, ny)] = tentative_g
                came_from[(nx, ny)] = (x, y)
                h = manhattan_distance((nx, ny), goal)
                counter += 1
                heapq.heappush(open_set, (tentative_g + h, counter, nx, ny))

    return None
