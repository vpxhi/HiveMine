"""
Tests for Task Allocation Scoring Function.

Validates:
1. Low-battery robot is never assigned a distant task when a closer,
   fuller-battery robot is idle.
2. Urgent tasks get a priority bonus.
3. Scoring function produces consistent orderings.
"""

import pytest

from warehouse_sim.algorithms.task_allocation import (
    score_robot,
    allocate_task,
)


class TestScoreRobot:
    """Tests for the robot scoring function."""

    def test_closer_robot_scores_lower(self):
        """A closer robot should have a lower (better) score."""
        close_score = score_robot(
            robot_pos=(1, 0), robot_battery=80.0,
            robot_workload=0, task_location=(2, 0), is_urgent=False,
        )
        far_score = score_robot(
            robot_pos=(10, 0), robot_battery=80.0,
            robot_workload=0, task_location=(2, 0), is_urgent=False,
        )
        assert close_score < far_score

    def test_higher_battery_scores_lower(self):
        """A robot with more battery should score lower (better)."""
        high_batt = score_robot(
            robot_pos=(0, 0), robot_battery=90.0,
            robot_workload=0, task_location=(5, 5), is_urgent=False,
        )
        low_batt = score_robot(
            robot_pos=(0, 0), robot_battery=20.0,
            robot_workload=0, task_location=(5, 5), is_urgent=False,
        )
        assert high_batt < low_batt

    def test_lower_workload_scores_lower(self):
        """A robot with fewer tasks should score lower (better)."""
        light = score_robot(
            robot_pos=(0, 0), robot_battery=80.0,
            robot_workload=0, task_location=(5, 5), is_urgent=False,
        )
        heavy = score_robot(
            robot_pos=(0, 0), robot_battery=80.0,
            robot_workload=3, task_location=(5, 5), is_urgent=False,
        )
        assert light < heavy

    def test_urgent_bonus_lowers_score(self):
        """Urgent tasks get a priority bonus (lower score)."""
        normal = score_robot(
            robot_pos=(0, 0), robot_battery=80.0,
            robot_workload=0, task_location=(5, 5), is_urgent=False,
        )
        urgent = score_robot(
            robot_pos=(0, 0), robot_battery=80.0,
            robot_workload=0, task_location=(5, 5), is_urgent=True,
        )
        assert urgent < normal


class TestAllocateTask:
    """Tests for the task allocation function."""

    def test_best_robot_selected(self):
        """The closer, higher-battery robot is selected."""
        robots = {
            0: {"pos": (1, 0), "battery": 90.0, "status": "IDLE", "workload": 0},
            1: {"pos": (10, 0), "battery": 30.0, "status": "IDLE", "workload": 2},
        }
        best = allocate_task(robots, task_location=(2, 0), is_urgent=False)
        assert best == 0

    def test_low_battery_robot_excluded(self):
        """A robot below the battery threshold is not assigned."""
        robots = {
            0: {"pos": (1, 0), "battery": 10.0, "status": "IDLE", "workload": 0},
            1: {"pos": (10, 0), "battery": 80.0, "status": "IDLE", "workload": 0},
        }
        best = allocate_task(robots, task_location=(2, 0), is_urgent=False)
        assert best == 1  # Robot 0 excluded due to low battery

    def test_busy_robot_excluded(self):
        """A busy robot is not assigned."""
        robots = {
            0: {"pos": (1, 0), "battery": 90.0, "status": "BUSY", "workload": 1},
            1: {"pos": (10, 0), "battery": 80.0, "status": "IDLE", "workload": 0},
        }
        best = allocate_task(robots, task_location=(2, 0), is_urgent=False)
        assert best == 1

    def test_no_available_robot(self):
        """Returns None when no robot is available."""
        robots = {
            0: {"pos": (1, 0), "battery": 10.0, "status": "BUSY", "workload": 1},
            1: {"pos": (10, 0), "battery": 5.0, "status": "CHARGING", "workload": 0},
        }
        best = allocate_task(robots, task_location=(2, 0), is_urgent=False)
        assert best is None

    def test_empty_fleet(self):
        """Returns None for empty robot fleet."""
        best = allocate_task({}, task_location=(2, 0), is_urgent=False)
        assert best is None

    def test_low_battery_never_assigned_distant_task(self):
        """
        KEY TEST: A low-battery robot is NEVER assigned a distant task
        when a closer, fuller-battery robot is idle.
        """
        robots = {
            0: {"pos": (0, 0), "battery": 25.0, "status": "IDLE", "workload": 0},
            1: {"pos": (3, 3), "battery": 95.0, "status": "IDLE", "workload": 0},
        }
        # Task is at (15, 15) — far away
        best = allocate_task(robots, task_location=(15, 15), is_urgent=False)
        # Robot 1 should be selected (closer with much more battery)
        assert best == 1
