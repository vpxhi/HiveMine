"""
Tests for Conflict-Based Search (CBS) Algorithm.

Validates:
1. Two robots with a guaranteed vertex conflict — resolved with zero collisions.
2. Two robots with a guaranteed edge conflict (swap case) — resolved.
3. CBS solution validation function works correctly.
4. CBS returns None for impossible configurations.
"""

import pytest

from warehouse_sim.algorithms.cbs import (
    cbs_solve,
    detect_first_conflict,
    validate_solution,
    Conflict,
)


class TestConflictDetection:
    """Tests for the conflict detection function."""

    def test_no_conflict(self):
        """No conflict when paths don't overlap."""
        solution = {
            0: [(0, 0), (1, 0), (2, 0)],
            1: [(0, 2), (1, 2), (2, 2)],
        }
        conflict = detect_first_conflict(solution)
        assert conflict is None

    def test_vertex_conflict_detected(self):
        """Detect vertex conflict (same cell, same time)."""
        solution = {
            0: [(0, 0), (1, 0), (2, 0)],
            1: [(2, 0), (1, 0), (0, 0)],
        }
        conflict = detect_first_conflict(solution)
        assert conflict is not None
        assert conflict.conflict_type == "vertex"
        assert conflict.location == (1, 0)
        assert conflict.timestep == 1

    def test_edge_conflict_detected(self):
        """Detect edge conflict (agents swap positions)."""
        solution = {
            0: [(0, 0), (1, 0)],
            1: [(1, 0), (0, 0)],
        }
        conflict = detect_first_conflict(solution)
        assert conflict is not None
        # Either vertex at t=1 or edge at t=1 should be detected
        assert conflict.timestep == 1

    def test_single_agent_no_conflict(self):
        """Single agent never has a conflict."""
        solution = {0: [(0, 0), (1, 0), (2, 0)]}
        conflict = detect_first_conflict(solution)
        assert conflict is None


class TestCBSSolve:
    """Tests for the CBS solver."""

    def test_no_conflict_scenario(self):
        """CBS returns direct paths when there are no conflicts."""
        agents = {
            0: ((0, 0), (4, 0)),
            1: ((0, 4), (4, 4)),
        }
        solution = cbs_solve(10, 10, agents, set())
        assert solution is not None
        assert 0 in solution
        assert 1 in solution
        # Paths should reach their goals
        assert solution[0][-1] == (4, 0)
        assert solution[1][-1] == (4, 4)

    def test_vertex_conflict_resolution(self):
        """CBS resolves a guaranteed vertex conflict."""
        # Both robots must pass through (2, 0)
        agents = {
            0: ((0, 0), (4, 0)),
            1: ((4, 0), (0, 0)),
        }
        solution = cbs_solve(5, 3, agents, set())
        assert solution is not None

        # Validate: no collisions in the solution
        is_valid, conflicts = validate_solution(solution)
        assert is_valid, f"Solution has conflicts: {conflicts}"

    def test_edge_conflict_resolution(self):
        """CBS resolves head-on collision (edge swap conflict)."""
        # Narrow corridor: robots must swap
        # Block row 1 to force them into row 0
        blocked = {(1, 1), (2, 1), (3, 1)}
        agents = {
            0: ((0, 0), (4, 0)),
            1: ((4, 0), (0, 0)),
        }
        solution = cbs_solve(5, 3, agents, blocked)
        assert solution is not None

        is_valid, conflicts = validate_solution(solution)
        assert is_valid, f"CBS produced conflicting paths: {conflicts}"

    def test_three_robot_conflict(self):
        """CBS handles three-way conflicts."""
        agents = {
            0: ((0, 0), (4, 0)),
            1: ((4, 0), (0, 0)),
            2: ((2, 0), (2, 4)),
        }
        solution = cbs_solve(5, 5, agents, set())
        assert solution is not None

        is_valid, conflicts = validate_solution(solution)
        assert is_valid

    def test_impossible_scenario_returns_none(self):
        """CBS returns None when agents can't reach their goals."""
        # Completely block the only path
        blocked = {(1, 0), (0, 1)}
        agents = {
            0: ((0, 0), (2, 2)),
        }
        solution = cbs_solve(3, 3, agents, blocked)
        assert solution is None

    def test_empty_agents(self):
        """CBS handles empty agent set."""
        solution = cbs_solve(5, 5, {}, set())
        assert solution == {}


class TestSolutionValidation:
    """Tests for the solution validation function."""

    def test_valid_solution(self):
        """Validates a conflict-free solution."""
        solution = {
            0: [(0, 0), (1, 0), (2, 0)],
            1: [(0, 2), (1, 2), (2, 2)],
        }
        is_valid, conflicts = validate_solution(solution)
        assert is_valid
        assert len(conflicts) == 0

    def test_invalid_solution_vertex(self):
        """Detects vertex conflict in invalid solution."""
        solution = {
            0: [(0, 0), (1, 0), (2, 0)],
            1: [(2, 0), (1, 0), (0, 0)],
        }
        is_valid, conflicts = validate_solution(solution)
        assert not is_valid
        assert len(conflicts) > 0
