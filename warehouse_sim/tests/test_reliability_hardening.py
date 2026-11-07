"""Regression coverage for input validation, collisions and run observability."""

import pytest

from warehouse_sim.model import WarehouseModel
from warehouse_sim.events import block_cell, flood_urgent_orders, force_drain, inject_deadlock, kill_robot
from warehouse_sim.network import MessageType


def test_order_input_rejects_invalid_values_without_creating_tasks():
    model = WarehouseModel(seed=7)
    for sku, qty, priority in (
        ("SKU-001", 0, "normal"),
        ("SKU-001", -1, "normal"),
        ("UNKNOWN", 1, "normal"),
        ("SKU-001", 1, "high"),
    ):
        with pytest.raises(ValueError):
            model.order_agent.receive_order(sku, qty, priority)
    assert model.order_agent.all_tasks == []
    assert model.order_agent.total_orders_received == 0


def test_inventory_rejects_invalid_quantities_and_robots():
    model = WarehouseModel(seed=7)
    shelf = model.shelf_locations[0]
    assert not model.inventory_agent.reserve(shelf, 0, "SKU-001", 0)
    assert not model.inventory_agent.reserve(shelf, 0, "SKU-001", -1)
    assert not model.inventory_agent.reserve(shelf, 99, "SKU-001", 1)
    assert not model.inventory_agent.decrement_stock(shelf, "SKU-001", -1)


def test_deadlock_shock_only_repositions_idle_unreserved_robots():
    """The seeded shock must preserve tasks and charger reservations of live robots."""
    model = WarehouseModel(seed=42, persist_log=False)
    deadlock_result = None
    for tick in range(1, 201):
        model.step()
        if tick == 50:
            kill_robot(model, 2)
        elif tick == 80:
            block_cell(model, (5, 6))
        elif tick == 110:
            force_drain(model, 0)
        elif tick == 140:
            flood_urgent_orders(model, 10)
        elif tick == 170:
            deadlock_result = inject_deadlock(model)

        for robot in model.robots.values():
            if robot.status == "CHARGING":
                assert robot.pos_tuple == robot._charging_dock
                assert robot.pos_tuple in model.charging_docks

    assert deadlock_result is not None
    if "error" not in deadlock_result:
        for robot_id in (deadlock_result["robot_a"], deadlock_result["robot_b"]):
            assert model.robots[robot_id].current_task is None
            assert model.robots[robot_id]._charging_dock is None
    robot = model.robots[0]
    assert robot._charging_dock is None or robot.status in (
        "EN_ROUTE_TO_CHARGE", "CHARGING", "WAITING_FOR_CHARGE", "NEEDS_CHARGE"
    )


def test_expired_or_failed_robot_claims_reopen_orphaned_order():
    model = WarehouseModel(seed=7, persist_log=False)
    model.order_agent.receive_order("SKU-001", 1, "normal")
    task = model.order_agent.all_tasks[0]
    task.status = "IN_PROGRESS"
    task.assigned_robot = 2
    model.robots[2].status = "FAILED"
    for robot in model.robots.values():
        robot.local_task_knowledge[task.task_id] = {
            "task_id": task.task_id,
            "sku": task.sku,
            "qty": task.qty,
            "priority": task.priority,
            "priority_rank": task.priority_rank,
            "arrival_tick": task.arrival_tick,
            "shelf_location": list(model.shelf_locations[0]),
            "owner": 2,
            "bids": {},
            "claims": {2: 4.0},
            "claim_expiry": {2: 100},
            "announce_tick": 0,
            "completed": False,
        }

    model.robots[0]._record_claim({"task_id": task.task_id, "robot_id": 2, "score": 1.0})
    model.robots[0]._merge_state({"tasks": [{
        "task_id": task.task_id,
        "task": {"owner": 2, "claim_expiry": {"2": 100}, "completed": False},
        "bids": {},
        "claims": {"2": 4.0},
    }]})
    model.step()

    assert 2 not in model.robots[0].local_task_knowledge[task.task_id]["claims"]
    assert task.assigned_robot == -1
    assert task.status != "IN_PROGRESS"


def test_failed_robot_obstacle_reroutes_seeded_aisle_traffic():
    model = WarehouseModel(seed=42, persist_log=False)
    failure = None
    for tick in range(1, 241):
        if tick == 31:
            failure = kill_robot(model, 2)
        model.step()

    failed_cell = tuple(failure["failed_position"])
    assert failed_cell in model.blocked_cells
    assert failure["robots_rerouted"] > 0
    assert len(model.completed_task_ids) > 0
    assert model.traffic_controller.collision_count == 0
    assert all(
        failed_cell not in robot.current_path[robot.path_index:]
        for robot in model.robots.values()
        if robot.status != "FAILED"
    )


def test_all_customer_skus_exist_in_initial_inventory():
    model = WarehouseModel(seed=7)
    stocked = {sku for shelf in model.inventory_agent.shelf_state.values() for sku in shelf["skus"]}
    assert stocked == {f"SKU-{sku:03d}" for sku in range(1, 21)}


def test_final_path_cell_does_not_bypass_robot_occupancy_check():
    model = WarehouseModel(seed=7)
    robot = model.robots[0]
    occupied = model.robots[1].pos_tuple
    robot.status = "EN_ROUTE_TO_SHELF"
    robot.current_path = [robot.pos_tuple, occupied]
    robot.path_index = 0
    before = robot.pos_tuple
    robot._follow_path()
    assert robot.pos_tuple == before
    assert robot.path_index == 0
    assert model.traffic_controller.blocked_moves == 1
    model._check_for_physical_collisions()
    assert model.traffic_controller.collision_count == 0


def test_robot_charges_only_after_reaching_reserved_dock():
    model = WarehouseModel(seed=7)
    robot = model.robots[0]
    robot.battery = 10
    robot.status = "NEEDS_CHARGE"
    robot._pre_charge_status = "IDLE"
    for _ in range(6):
        model.step()
        if robot.status == "CHARGING":
            break
    assert robot.pos_tuple == robot._charging_dock
    battery_at_dock = robot.battery
    robot._charge_tick()
    assert robot.battery >= battery_at_dock


def test_robot_seeks_charge_before_battery_is_below_dock_route_cost():
    model = WarehouseModel(seed=22, persist_log=False)
    robot = model.robots[0]
    robot.pos_tuple = (19, 19)
    robot.battery = 24

    robot.decide()

    assert robot.status == "NEEDS_CHARGE"


def test_waiting_robot_is_not_counted_as_charging_or_task_active():
    model = WarehouseModel(seed=7)
    robot = model.robots[0]
    robot.status = "WAITING_FOR_CHARGE"
    assert model.charging_agent.get_charging_count() == 0
    assert model.get_kpis()["active_robots"] == 0


def test_duplicate_task_announcement_is_processed_once():
    model = WarehouseModel(seed=7)
    message = model.network.send("OrderAgent", "Robot-0", MessageType.TASK_ANNOUNCEMENT, {
        "task_id": 101, "sku": "SKU-001", "qty": 1, "priority": "normal",
        "priority_rank": 1, "arrival_tick": 0, "shelf_location": [3, 4],
    }, tick=0)
    model.current_tick = 1
    model.network.advance(1)
    model.network.inboxes["Robot-0"].append(message)
    robot = model.robots[0]
    robot.sense()
    sent_after_first_delivery = model.network.counters["sent"]
    robot.sense()
    assert model.network.counters["sent"] == sent_after_first_delivery
    assert len(robot.local_task_knowledge[101]["bids"]) == 1


def test_claim_lease_expires_and_reopens_local_task():
    model = WarehouseModel(seed=7)
    robot = model.robots[0]
    task = {"task_id": 102, "bids": {}, "claims": {1: 3.0},
            "claim_expiry": {1: 1}, "owner": 1}
    model.current_tick = 2
    robot._prune_expired_claims(task)
    assert task["claims"] == {}
    assert "owner" not in task


def test_cli_demo_reproducible_task_stream_across_comparison_modes():
    from warehouse_sim.dashboard import run_comparison_scenarios

    results = run_comparison_scenarios(seed=42, ticks=120)
    assert {result["Tasks created"] for result in results.values()} == {15}
    assert results["After recovery"]["Reconciliation duration (ticks)"] is not None
    assert results["Network partition"]["Completed during partition"] > 0


def test_physical_collision_counter_detects_illegal_co_occupancy():
    model = WarehouseModel(seed=7)
    model.robots[1].pos_tuple = model.robots[0].pos_tuple
    model._check_for_physical_collisions()
    assert model.traffic_controller.collision_count == 1


def test_traffic_controller_detects_head_on_edge_swap():
    model = WarehouseModel(seed=7)
    model.traffic_controller.active_paths[1] = [(1, 0), (0, 0)]
    model.robots[1].pos_tuple = (1, 0)
    model.robots[1].current_path = [(1, 0), (0, 0)]
    conflicts = model.traffic_controller._check_path_conflicts(0, [(0, 0), (1, 0)])
    assert conflicts == {1}


def test_no_completion_average_is_reported_as_unavailable():
    model = WarehouseModel(seed=7)
    metrics = model.get_kpis()
    assert metrics["average_task_time"] is None
    assert metrics["average_active_robot_utilisation_pct"] is None
    assert metrics["task_completion_rate"] is None


def test_model_initialization_preserves_existing_log_file(tmp_path):
    log_path = tmp_path / "simulation_log.jsonl"
    log_path.write_text('{"existing":"entry"}\n', encoding="utf-8")
    model = WarehouseModel(seed=7, log_file_path=str(log_path))
    assert log_path.read_text(encoding="utf-8") == '{"existing":"entry"}\n'
    model.log_message("test", "test", {"action": "append"})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
