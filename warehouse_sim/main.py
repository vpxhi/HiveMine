"""
CLI Entry Point — Runs the warehouse simulation for N ticks and prints KPIs.

Owner: Rohith (cb.sc.u4cse23018) — Robot Intelligence
Responsibility: Boots the full simulation with a single `python main.py`
command, runs for a configurable number of ticks, and prints a summary
of key performance indicators.

Usage:
    python -m warehouse_sim.main              # Run 200 ticks (default)
    python -m warehouse_sim.main --ticks 500  # Run 500 ticks
    python -m warehouse_sim.main --shock      # Run with shocks injected
"""

from __future__ import annotations

import argparse
import sys
import io

from .model import WarehouseModel
from .events import (
    kill_robot,
    block_cell,
    force_drain,
    flood_urgent_orders,
    inject_deadlock,
    network_partition,
    restore_network,
)


def run_simulation(ticks: int = 200, inject_shocks: bool = False, seed: int = 42,
                   demo_network: bool = False) -> None:
    """
    Run the warehouse simulation for a given number of ticks.

    Args:
        ticks: Number of simulation ticks to run.
        inject_shocks: Whether to inject shocks during the run.
    """
    print("=" * 60)
    print("  HIVEMINE | PEER-COORDINATED WAREHOUSE DIGITAL TWIN")
    print("=" * 60)
    print("Grid: 20x20 | Robots: 5 | Shelves: 10 | Docks: 2 | Seed: {}".format(seed))
    if demo_network:
        ticks = max(ticks, 120)
        print("Fixed network demo: normal 1–40, partitioned 41–80, recovery 81–{}".format(ticks))
    print("Running for {} ticks...".format(ticks))
    print("-" * 60)

    model = WarehouseModel(seed=seed)

    for tick in range(1, ticks + 1):
        if demo_network and tick == 41:
            network_partition(model, 2)
        elif demo_network and tick == 81:
            restore_network(model)
        model.step()

        # Inject shocks at predetermined intervals
        if inject_shocks and tick > 20:
            if tick == 50:
                print("\n[!] [Tick {}] SHOCK: Killing Robot 2".format(tick))
                result = kill_robot(model, 2)
                print("   Result: {}".format(result))

            if tick == 80:
                print("\n[!] [Tick {}] SHOCK: Blocking cell (5, 6)".format(tick))
                result = block_cell(model, (5, 6))
                print("   Result: {}".format(result))

            if tick == 110:
                print("\n[!] [Tick {}] SHOCK: Draining Robot 0 battery".format(tick))
                result = force_drain(model, 0)
                print("   Result: {}".format(result))

            if tick == 140:
                print("\n[!] [Tick {}] SHOCK: Flooding 10 urgent orders".format(tick))
                result = flood_urgent_orders(model, 10)
                print("   Result: {}".format(result))

            if tick == 170:
                print("\n[!] [Tick {}] SHOCK: Injecting deadlock".format(tick))
                result = inject_deadlock(model)
                print("   Result: {}".format(result))

        # Progress report every 50 ticks
        if tick % 50 == 0:
            kpis = model.get_kpis()
            print("\n[i] [Tick {}] Progress Report:".format(tick))
            print("   Orders: {}/{} completed".format(
                kpis['orders_completed'], kpis['orders_received']))
            print("   Active robots: {}".format(kpis['active_robots']))
            print("   Avg battery: {:.1f}%".format(kpis['avg_battery']))
            print("   Collisions: {}".format(kpis['collision_count']))
            print("   Deadlocks resolved: {}".format(kpis['deadlocks_resolved']))
            print("   Shocks recovered: {}".format(kpis['shocks_recovered']))

    # Final summary
    kpis = model.get_kpis()
    print("\n" + "=" * 60)
    print("  SIMULATION COMPLETE - FINAL KPIs")
    print("=" * 60)
    print("  Total ticks:           {}".format(kpis['tick']))
    print("  Orders received:       {}".format(kpis['orders_received']))
    print("  Orders completed:      {}".format(kpis['orders_completed']))
    print("  Tasks completed:       {}".format(kpis['total_tasks_completed']))
    print("  Pending tasks:         {}".format(kpis['pending_tasks']))
    print("  Avg battery:           {:.1f}%".format(kpis['avg_battery']))
    print("  Robots charging:       {}".format(kpis['robots_charging']))
    print("  Robots failed:         {}".format(kpis['robots_failed']))
    print("  Collisions:            {} (should be 0)".format(kpis['collision_count']))
    print("  Deadlocks resolved:    {}".format(kpis['deadlocks_resolved']))
    print("  Shocks recovered:      {}".format(kpis['shocks_recovered']))
    print("  Inter-agent messages:  {}".format(len(model.message_log)))
    print("=" * 60)

    # Robot status breakdown
    print("\n  ROBOT STATUS:")
    for rid, robot in model.robots.items():
        print(
            "    Robot {}: {} | Battery: {:.0f}% | "
            "Tasks done: {} | Pos: {}".format(
                rid, robot.status, robot.battery,
                robot.tasks_completed, robot.pos_tuple
            )
        )

    print("\n  Full message log: simulation_log.jsonl")
    print("  Messages logged: {}".format(len(model.message_log)))


def main() -> None:
    """Parse CLI arguments and run the simulation."""
    parser = argparse.ArgumentParser(
        description="HiveMine peer-coordinated multi-agent warehouse simulation"
    )
    parser.add_argument(
        "--ticks", type=int, default=200, help="Number of simulation ticks"
    )
    parser.add_argument(
        "--shock",
        action="store_true",
        help="Inject environmental shocks during simulation",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible runs")
    parser.add_argument("--demo-network", action="store_true",
                        help="Run a fixed normal/partition/recovery demonstration")
    args = parser.parse_args()
    run_simulation(ticks=args.ticks, inject_shocks=args.shock, seed=args.seed,
                   demo_network=args.demo_network)


if __name__ == "__main__":
    main()
