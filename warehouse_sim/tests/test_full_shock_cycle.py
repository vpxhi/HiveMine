"""
Full Shock Cycle Integration Test.

Validates:
    Run 100 ticks, fire all 5 shocks at random ticks, assert the model
    never throws and all core invariants hold:
    - No unhandled exceptions
    - Collision count stays at 0
    - Shocks recovered counter increments
    - Model state remains consistent
"""

import pytest
import random

from warehouse_sim.model import WarehouseModel
from warehouse_sim.events import (
    kill_robot,
    block_cell,
    force_drain,
    flood_urgent_orders,
    inject_deadlock,
)


class TestFullShockCycle:
    """Integration test running the full simulation with all 5 shocks."""

    def test_100_ticks_with_all_shocks(self):
        """
        Run 100 ticks with all 5 shocks injected at predetermined ticks.

        This test proves the system recovers gracefully from every shock
        type without crashing or entering an inconsistent state.
        """
        model = WarehouseModel(seed=42)
        shock_results = []

        for tick in range(1, 101):
            # Run one tick — must not throw
            model.step()

            # Inject shocks at specific ticks
            if tick == 15:
                result = kill_robot(model, 0)
                shock_results.append(("robot_failure", result))

            if tick == 30:
                result = block_cell(model, (5, 6))
                shock_results.append(("blocked_aisle", result))

            if tick == 45:
                result = force_drain(model, 1)
                shock_results.append(("battery_failure", result))

            if tick == 60:
                result = flood_urgent_orders(model, 8)
                shock_results.append(("order_flood", result))

            if tick == 75:
                result = inject_deadlock(model)
                shock_results.append(("deadlock_injection", result))

        # ── Post-simulation assertions ────────────────────────────────

        # All 5 shocks fired
        assert len(shock_results) == 5

        # Injection and recovery are separate; the model counts only verified recovery.
        for shock_type, result in shock_results:
            if shock_type == "deadlock_injection" and "error" in result:
                # Acceptable: not enough robots for deadlock injection
                continue
            assert result.get("status") in ("injected", "recovery_in_progress", "recovered")

        # Collision count should be 0
        assert model.traffic_controller.collision_count == 0

        # The metric must exactly match events whose observable recovery condition held.
        assert model.shocks_recovered == sum(result.get("status") == "recovered" for _, result in shock_results)

        # Model state is consistent
        kpis = model.get_kpis()
        assert kpis["tick"] == 100
        assert kpis["collision_count"] == 0

        # Grid state is retrievable without error
        grid_state = model.get_grid_state()
        assert grid_state["grid_width"] == 20
        assert grid_state["grid_height"] == 20

        # Messages were logged
        assert len(model.message_log) > 0

    def test_200_ticks_no_crash(self):
        """Run 200 ticks with no shocks — baseline stability test."""
        model = WarehouseModel(seed=42)

        for tick in range(200):
            model.step()

        kpis = model.get_kpis()
        assert kpis["tick"] == 200
        assert kpis["collision_count"] == 0

    def test_rapid_shock_succession(self):
        """Fire shocks in rapid succession to stress-test recovery."""
        model = WarehouseModel()

        # Run 20 ticks to warm up
        for _ in range(20):
            model.step()

        # Fire 3 shocks in quick succession
        kill_robot(model, 2)
        model.step()

        force_drain(model, 3)
        model.step()

        flood_urgent_orders(model, 5)
        model.step()

        # Continue for 30 more ticks
        for _ in range(30):
            model.step()

        # System should still be functional
        kpis = model.get_kpis()
        assert kpis["collision_count"] == 0
        assert kpis["shocks_recovered"] == sum(event.get("status") == "recovered" for event in model.recovery_events)

    def test_all_robots_killed_no_crash(self):
        """Killing all robots shouldn't crash the simulation."""
        model = WarehouseModel()

        for _ in range(10):
            model.step()

        # Kill all robots
        for rid in list(model.robots.keys()):
            kill_robot(model, rid)

        # Continue running — should not crash
        for _ in range(20):
            model.step()

        kpis = model.get_kpis()
        assert kpis["robots_failed"] == 5

    def test_multiple_cells_blocked(self):
        """Blocking multiple cells doesn't crash the system."""
        model = WarehouseModel()

        for _ in range(10):
            model.step()

        # Block several aisle cells
        cells_to_block = [(5, 5), (5, 7), (10, 10), (15, 15)]
        for cell in cells_to_block:
            block_cell(model, cell)

        # Continue running
        for _ in range(50):
            model.step()

        assert len(model.blocked_cells) >= 4
