"""
Environmental Shocks — Stress-test functions for live demo scenarios.

Owner: Venkat (cb.sc.u4cse23055) — Operations
Responsibility: Implements 5 callable shock functions that can be triggered
live during the demo to test the system's dynamic replanning and recovery.

Each shock function returns a recovery event dict for dashboard display.
The system must recover from each shock autonomously — no manual restart.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .model import WarehouseModel
from .network import MessageType


def network_partition(model: WarehouseModel, split: int = 2) -> Dict[str, Any]:
    """Disconnect the robot network into two communicating groups."""
    if len(model.robots) < 2:
        return {"error": "At least two robots are required to split the network"}
    split = max(1, min(len(model.robots) - 1, int(split)))
    ids = list(model.robots)
    groups = [ids[:split], ids[split:]]
    model.network.set_partition(groups)
    event = {"shock_type": "network_partition", "tick": model.current_tick,
             "groups": groups, "status": "injected", "recovered": False}
    model.log_message("EventSystem", "RobotNetwork", event)
    model.track_recovery(event)
    return event


def isolate_robot(model: WarehouseModel, robot_id: int) -> Dict[str, Any]:
    """Remove all communication links to one robot."""
    if robot_id not in model.robots:
        return {"error": f"Robot {robot_id} not found"}
    model.network.isolate(robot_id)
    event = {"shock_type": "robot_isolation", "tick": model.current_tick,
             "robot_id": robot_id,
             "groups": [sorted(int(node.split("-")[1]) for node in group)
                        for group in model.network.robot_components()],
             "status": "injected", "recovered": False}
    model.log_message("EventSystem", "RobotNetwork", event)
    model.track_recovery(event)
    return event


def disconnect_all_robots(model: WarehouseModel) -> Dict[str, Any]:
    """Put each robot in a singleton communication group."""
    groups = [[rid] for rid in model.robots]
    model.network.set_partition(groups)
    event = {"shock_type": "network_partition", "preset": "full_network_outage",
             "tick": model.current_tick, "groups": groups,
             "status": "injected", "recovered": False}
    model.log_message("EventSystem", "RobotNetwork", event)
    model.track_recovery(event)
    return event


def set_network_conditions(model: WarehouseModel, latency: int = 0, packet_loss: float = 0.0) -> Dict[str, Any]:
    """Configure transport latency in ticks and packet loss in [0, 1]."""
    model.network.set_conditions(latency, packet_loss)
    event = {"shock_type": "network_conditions", "tick": model.current_tick,
             "latency_ticks": model.network.latency,
             "packet_loss": model.network.packet_loss, "status": "injected"}
    model.log_message("EventSystem", "RobotNetwork", event)
    return event


def restore_network(model: WarehouseModel) -> Dict[str, Any]:
    """Restore the baseline peer topology and transport conditions."""
    was_partitioned = model.network.partition_count > 1
    model.network.restore_all()
    model.network.set_conditions(0, 0)
    model._reconciliation_force_start = was_partitioned
    event = {"shock_type": "network_recovery", "tick": model.current_tick,
             "groups": [sorted(int(node.split("-")[1]) for node in group)
                        for group in model.network.robot_components()],
             "status": "recovery_in_progress" if was_partitioned else "recovered",
             "recovered": not was_partitioned}
    model.log_message("EventSystem", "RobotNetwork", event)
    if was_partitioned:
        model.track_recovery(event)
    return event


def kill_robot(model: WarehouseModel, robot_id: int) -> Dict[str, Any]:
    """
    Shock 1: Robot Failure — instantly disables a robot.

    The Fleet Manager must reassign its in-progress task to the next
    available robot within the same tick.

    Args:
        model: The warehouse model instance.
        robot_id: The robot to kill.

    Returns:
        Recovery event dict with before/after state.
    """
    robot = model.get_robot_by_id(robot_id)
    if robot is None:
        return {"error": f"Robot {robot_id} not found"}

    before_status = robot.status
    before_task = robot.current_task
    failed_cell = robot.pos_tuple

    # Kill the robot
    robot.status = "FAILED"
    robot.current_path = []
    robot._charging_dock = None

    if robot_id in model.charging_agent.charge_queue:
        model.charging_agent.charge_queue.remove(robot_id)
    if robot_id in model.charging_agent.robots_charging:
        model.charging_agent.release_robot(robot_id)

    # Clear its reservations
    model.traffic_controller._clear_reservations(robot_id)
    # A disabled robot in an aisle becomes a physical obstacle. The packing
    # station is intentionally shared by multiple robots in this model and
    # cannot be closed by a single failure.
    rerouted = 0
    if failed_cell != model.packing_station:
        model.blocked_cells.add(failed_cell)
        rerouted = model.traffic_controller.reroute_on_block(failed_cell)

    # Fleet Manager handles reassignment
    model.fleet_manager.handle_robot_failure(robot_id)

    task_id = getattr(before_task, "task_id", None)
    if before_task is not None:
        model.inventory_agent.release(before_task.shelf_location, robot_id)
        before_task.status = "PENDING"
        before_task.assigned_robot = -1
        robot.current_task = None
        model.network.broadcast(f"Robot-{robot_id}", MessageType.TASK_ABANDON,
                                {"task_id": task_id, "robot_id": robot_id}, model.current_tick)

    # Injection is not recovery; recovery is verified by subsequent fleet progress.

    event = {
        "shock_type": "robot_failure",
        "tick": model.current_tick,
        "robot_id": robot_id,
        "failed_position": list(failed_cell),
        "robots_rerouted": rerouted,
        "before_status": before_status,
        "task_reassigned": before_task is not None,
        "task_id": task_id,
        "recovered": False,
        "status": "recovery_in_progress",
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="FleetManager",
        payload=event,
    )
    model.track_recovery(event)

    return event


def block_cell(
    model: WarehouseModel, cell: Tuple[int, int]
) -> Dict[str, Any]:
    """
    Shock 2: Blocked Aisle / Shelf Collapse — marks a cell impassable.

    The Traffic Controller must detect all robots with paths through
    the blocked cell and trigger reroute_on_block().

    Args:
        model: The warehouse model instance.
        cell: The (x, y) cell to block.

    Returns:
        Recovery event dict.
    """
    if cell in model.shelf_locations or cell == model.packing_station:
        return {"error": "Cannot block a shelf or packing station"}
    if cell in model.charging_docks:
        return {"error": "Cannot block a charging dock"}

    affected_robots = [
        robot_id for robot_id, path in model.traffic_controller.active_paths.items()
        if cell in path
    ]
    model.blocked_cells.add(cell)

    # Traffic Controller reroutes affected robots
    rerouted = model.traffic_controller.reroute_on_block(cell)

    # An obstacle is considered recovered only after subsequent safe routing.

    event = {
        "shock_type": "blocked_aisle",
        "tick": model.current_tick,
        "blocked_cell": list(cell),
        "robots_rerouted": rerouted,
        "affected_robots": affected_robots,
        "recovered": False,
        "status": "recovery_in_progress",
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="TrafficController",
        payload=event,
    )
    model.track_recovery(event)

    return event


def force_drain(model: WarehouseModel, robot_id: int) -> Dict[str, Any]:
    """
    Shock 3: Battery Failure — drains a robot's battery to 5%.

    The Charging Agent must redirect it to the nearest dock, and the
    Fleet Manager must hand off its in-progress task if mid-delivery.

    Args:
        model: The warehouse model instance.
        robot_id: The robot to drain.

    Returns:
        Recovery event dict.
    """
    robot = model.get_robot_by_id(robot_id)
    if robot is None:
        return {"error": f"Robot {robot_id} not found"}

    before_battery = robot.battery
    before_status = robot.status

    # Force battery drain
    robot.battery = 5.0
    robot.status = "NEEDS_CHARGE"
    robot._pre_charge_status = before_status
    robot._pre_charge_task = robot.current_task

    # Battery recovery requires charging to a safe threshold.

    event = {
        "shock_type": "battery_failure",
        "tick": model.current_tick,
        "robot_id": robot_id,
        "before_battery": before_battery,
        "after_battery": 5.0,
        "before_status": before_status,
        "recovered": False,
        "status": "recovery_in_progress",
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="ChargingAgent",
        payload=event,
    )
    model.track_recovery(event)

    return event


def flood_urgent_orders(
    model: WarehouseModel, n: int = 10
) -> Dict[str, Any]:
    """
    Shock 4: Traffic Congestion Spike — injects N urgent orders at once.

    The Traffic Controller must demonstrate rerouting/queueing without
    deadlocking.

    Args:
        model: The warehouse model instance.
        n: Number of urgent orders to inject.

    Returns:
        Recovery event dict.
    """
    skus = [f"SKU-{i:03d}" for i in range(1, 21)]
    orders_created = 0
    task_start = model.order_agent._next_task_id

    for _ in range(n):
        sku = model.random.choice(skus)
        qty = model.random.randint(1, 2)
        model.order_agent.receive_order(sku, qty, "urgent")
        orders_created += 1

    # Injecting demand does not mean the demand surge has been fulfilled.

    event = {
        "shock_type": "order_flood",
        "tick": model.current_tick,
        "orders_injected": orders_created,
        "task_ids": list(range(task_start, task_start + orders_created)),
        "total_pending": model.order_agent.get_pending_count(),
        "recovered": False,
        "status": "injected",
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="OrderAgent",
        payload=event,
    )
    model.track_recovery(event)

    return event


def inject_deadlock(model: WarehouseModel) -> Dict[str, Any]:
    """
    Shock 5: Deadlock Injection — forces two robots into a head-on conflict.

    Places two idle robots on a collision course and relies on the
    Traffic Controller's wait-for-graph detection and CBS/rollback
    to resolve the deadlock.

    Args:
        model: The warehouse model instance.

    Returns:
        Recovery event dict.
    """
    # Only reposition idle robots with no task or reserved charging dock. The
    # previous fallback could teleport a robot out of a charging route or
    # abandon an active order, leaving stale resource reservations behind.
    idle_robots = [
        r for r in model.robots.values()
        if r.status == "IDLE" and r.current_task is None and r._charging_dock is None
    ]
    if len(idle_robots) < 2:
        return {"error": "Deadlock injection needs two idle robots without active tasks or charger reservations"}

    robot_a = idle_robots[0]
    robot_b = idle_robots[1]

    # Place them facing each other in a narrow corridor
    # Robot A at (5, 10), goal at (5, 14)
    # Robot B at (5, 14), goal at (5, 10)
    pos_a = (5, 10)
    pos_b = (5, 14)

    targets = {robot_a.robot_id, robot_b.robot_id}
    if any(robot.robot_id not in targets for cell in (pos_a, pos_b)
           for robot in model.get_robots_at(cell)):
        return {"error": "Deadlock test corridor is occupied by a robot that cannot be repositioned safely"}

    model.traffic_controller._clear_reservations(robot_a.robot_id)
    model.traffic_controller._clear_reservations(robot_b.robot_id)

    robot_a.pos_tuple = pos_a
    robot_b.pos_tuple = pos_b

    # Update grid positions
    try:
        model.grid.move_agent(robot_a, pos_a)
        model.grid.move_agent(robot_b, pos_b)
    except Exception:
        pass

    # Request conflicting routes
    path_a = model.traffic_controller.request_route(
        robot_a.robot_id, pos_a, pos_b
    )
    path_b = model.traffic_controller.request_route(
        robot_b.robot_id, pos_b, pos_a
    )

    if path_a:
        robot_a.update_path(path_a)
        robot_a.status = "EN_ROUTE_TO_SHELF"
    if path_b:
        robot_b.update_path(path_b)
        robot_b.status = "EN_ROUTE_TO_SHELF"

    # Force deadlock check
    deadlocks_before = model.traffic_controller.deadlocks_resolved
    resolved = model.traffic_controller.check_and_resolve_deadlocks()

    # Deadlock recovery is measured by the controller's actual resolution count.

    event = {
        "shock_type": "deadlock_injection",
        "tick": model.current_tick,
        "robot_a": robot_a.robot_id,
        "robot_b": robot_b.robot_id,
        "deadlock_resolved": resolved > 0,
        "recovered": resolved > 0,
        "status": "recovered" if resolved > 0 else "recovery_in_progress",
        "deadlocks_before": deadlocks_before,
    }

    model.log_message(
        from_agent="EventSystem",
        to_agent="TrafficController",
        payload=event,
    )
    model.track_recovery(event)

    return event
