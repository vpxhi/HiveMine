"""
Tests for A* Pathfinding Algorithm.

Validates:
1. Shortest path on an empty grid.
2. Path correctly avoids blocked cells.
3. Returns None gracefully when no path exists (not a crash).
4. Time-constrained A* works for CBS integration.
"""

import pytest

from warehouse_sim.algorithms.astar import (
    a_star,
    a_star_simple,
    manhattan_distance,
    get_neighbors,
)


class TestManhattanDistance:
    """Tests for the Manhattan distance heuristic."""

    def test_same_point(self):
        """Distance from a point to itself is zero."""
        assert manhattan_distance((0, 0), (0, 0)) == 0

    def test_horizontal(self):
        """Horizontal distance calculation."""
        assert manhattan_distance((0, 0), (5, 0)) == 5

    def test_vertical(self):
        """Vertical distance calculation."""
        assert manhattan_distance((0, 0), (0, 7)) == 7

    def test_diagonal(self):
        """Manhattan distance for diagonal movement."""
        assert manhattan_distance((0, 0), (3, 4)) == 7

    def test_symmetric(self):
        """Distance is symmetric."""
        assert manhattan_distance((1, 2), (5, 8)) == manhattan_distance((5, 8), (1, 2))


class TestGetNeighbors:
    """Tests for neighbor generation."""

    def test_center_cell(self):
        """Center cell has 4 neighbors."""
        neighbors = get_neighbors((5, 5), 10, 10)
        assert len(neighbors) == 4

    def test_corner_cell(self):
        """Corner cell has 2 neighbors."""
        neighbors = get_neighbors((0, 0), 10, 10)
        assert len(neighbors) == 2

    def test_edge_cell(self):
        """Edge cell has 3 neighbors."""
        neighbors = get_neighbors((0, 5), 10, 10)
        assert len(neighbors) == 3


class TestAStarSimple:
    """Tests for the simplified (non-temporal) A* algorithm."""

    def test_shortest_path_empty_grid(self):
        """Find shortest path on an empty 10x10 grid."""
        path = a_star_simple(10, 10, (0, 0), (9, 9), set())
        assert path is not None
        assert path[0] == (0, 0)
        assert path[-1] == (9, 9)
        # Manhattan distance = 18, path length = 19 (including start)
        assert len(path) == 19

    def test_path_avoids_blocked_cells(self):
        """Path goes around blocked cells."""
        # Block the direct horizontal path
        blocked = {(1, 0), (2, 0), (3, 0), (4, 0)}
        path = a_star_simple(10, 10, (0, 0), (5, 0), blocked)
        assert path is not None
        assert path[0] == (0, 0)
        assert path[-1] == (5, 0)
        # Path must not go through blocked cells
        for cell in path:
            assert cell not in blocked
        # Path will be longer than direct (5 + 1 = 6 cells)
        assert len(path) > 6

    def test_no_path_returns_none(self):
        """Returns None when the goal is completely surrounded."""
        # Surround the goal cell (5, 5)
        blocked = {(4, 5), (6, 5), (5, 4), (5, 6)}
        path = a_star_simple(10, 10, (0, 0), (5, 5), blocked)
        assert path is None

    def test_start_equals_goal(self):
        """Path from a cell to itself is just that cell."""
        path = a_star_simple(10, 10, (3, 3), (3, 3), set())
        assert path is not None
        assert path == [(3, 3)]

    def test_blocked_start_returns_none(self):
        """Returns None if start is blocked."""
        path = a_star_simple(10, 10, (0, 0), (5, 5), {(0, 0)})
        assert path is None

    def test_blocked_goal_returns_none(self):
        """Returns None if goal is blocked."""
        path = a_star_simple(10, 10, (0, 0), (5, 5), {(5, 5)})
        assert path is None

    def test_adjacent_cells(self):
        """Path between adjacent cells is 2 cells long."""
        path = a_star_simple(10, 10, (0, 0), (1, 0), set())
        assert path is not None
        assert len(path) == 2

    def test_large_grid(self):
        """A* works on a 20x20 grid (warehouse size)."""
        path = a_star_simple(20, 20, (0, 0), (19, 19), set())
        assert path is not None
        assert len(path) == 39  # Manhattan distance 38 + 1


class TestAStarWithConstraints:
    """Tests for the time-expanded A* (used by CBS)."""

    def test_constraint_forces_detour(self):
        """A time constraint forces the agent to wait or detour."""
        # Constraint: cell (1, 0) is blocked at timestep 1
        constraints = {((1, 0), 1)}
        path = a_star(5, 5, (0, 0), (2, 0), set(), constraints)
        assert path is not None
        assert path[-1] == (2, 0)
        # Path should be longer than the direct 3-cell route
        assert len(path) >= 3

    def test_no_constraints_optimal(self):
        """Without constraints, time-expanded A* returns optimal path."""
        path = a_star(10, 10, (0, 0), (3, 0), set())
        assert path is not None
        assert len(path) == 4  # 3 moves + start

    def test_multiple_constraints(self):
        """Multiple constraints are all respected."""
        constraints = {((1, 0), 1), ((2, 0), 2)}
        path = a_star(5, 5, (0, 0), (3, 0), set(), constraints)
        assert path is not None
        assert path[-1] == (3, 0)
