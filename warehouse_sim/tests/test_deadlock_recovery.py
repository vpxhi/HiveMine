"""
Tests for Deadlock Detection and Resolution.

Validates:
1. Wait-for cycle is detected correctly.
2. Deadlock is resolved by rolling back the lowest-priority robot.
3. No false positives on acyclic wait-for graphs.
"""

import pytest

from warehouse_sim.algorithms.task_allocation import (
    detect_deadlock,
    resolve_deadlock,
)


class TestDeadlockDetection:
    """Tests for wait-for graph cycle detection."""

    def test_simple_cycle(self):
        """Detect a simple 2-robot deadlock cycle."""
        wait_for = {
            0: {1},
            1: {0},
        }
        cycle = detect_deadlock(wait_for)
        assert cycle is not None
        assert 0 in cycle
        assert 1 in cycle

    def test_three_way_cycle(self):
        """Detect a 3-robot circular deadlock."""
        wait_for = {
            0: {1},
            1: {2},
            2: {0},
        }
        cycle = detect_deadlock(wait_for)
        assert cycle is not None
        assert len(set(cycle)) >= 3

    def test_no_cycle(self):
        """No deadlock in an acyclic wait-for graph."""
        wait_for = {
            0: {1},
            1: {2},
            2: set(),
        }
        cycle = detect_deadlock(wait_for)
        assert cycle is None

    def test_empty_graph(self):
        """No deadlock in an empty graph."""
        cycle = detect_deadlock({})
        assert cycle is None

    def test_self_loop(self):
        """Detect a self-loop (degenerate deadlock)."""
        wait_for = {0: {0}}
        cycle = detect_deadlock(wait_for)
        assert cycle is not None

    def test_complex_graph_with_cycle(self):
        """Detect cycle in a more complex graph."""
        wait_for = {
            0: {1},
            1: {2},
            2: {3},
            3: {1},  # Cycle: 1 -> 2 -> 3 -> 1
            4: {0},
        }
        cycle = detect_deadlock(wait_for)
        assert cycle is not None


class TestDeadlockResolution:
    """Tests for deadlock resolution by yielding lowest-priority robot."""

    def test_lowest_priority_yields(self):
        """The lowest-priority robot in the cycle should yield."""
        cycle = [0, 1, 0]  # Cycle between robots 0 and 1
        priorities = {0: 5, 1: 10}
        yielding = resolve_deadlock(cycle, priorities)
        assert yielding == 0  # Robot 0 has lower priority

    def test_three_way_resolution(self):
        """Correct robot yields in a 3-way cycle."""
        cycle = [0, 1, 2, 0]
        priorities = {0: 3, 1: 1, 2: 5}
        yielding = resolve_deadlock(cycle, priorities)
        assert yielding == 1  # Robot 1 has lowest priority

    def test_equal_priorities(self):
        """When priorities are equal, any robot from the cycle is valid."""
        cycle = [0, 1, 0]
        priorities = {0: 5, 1: 5}
        yielding = resolve_deadlock(cycle, priorities)
        assert yielding in (0, 1)
