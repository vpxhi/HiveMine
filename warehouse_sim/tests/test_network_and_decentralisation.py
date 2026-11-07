"""Deterministic network, local-auction and reconciliation coverage for HiveMine."""

from warehouse_sim.events import isolate_robot, network_partition, restore_network
from warehouse_sim.model import WarehouseModel
from warehouse_sim.network import MessageType, NetworkSimulator


def test_message_routes_through_normal_peer_graph():
    net = NetworkSimulator(range(5), seed=7)
    message = net.send("Robot-0", "Robot-4", MessageType.ROBOT_STATUS, {"x": 1}, 0)
    assert message.path == ("Robot-0", "Robot-1", "Robot-2", "Robot-3", "Robot-4")
    net.advance(1)
    assert net.receive("Robot-4")[0].payload == {"x": 1}
    assert net.counters["delivered"] == 1


def test_disconnected_link_blocks_message_routing():
    net = NetworkSimulator(range(5), seed=7)
    net.disconnect("Robot-1", "Robot-2")
    message = net.send("Robot-0", "Robot-4", MessageType.TASK_BID, {"task_id": 1}, 0)
    assert message.delivery_status == "dropped"
    assert not net.receive("Robot-4")


def test_complete_and_partial_partitions_have_real_components():
    net = NetworkSimulator(range(5), seed=7)
    net.set_partition([[0, 1], [2, 3, 4]])
    assert net.partition_count == 2
    assert net.connected_robot_ids(0) == {0, 1}
    assert net.connected_robot_ids(4) == {2, 3, 4}
    assert net.send("Robot-1", "Robot-4", MessageType.TASK_BID, {}, 0).delivery_status == "dropped"
    net.isolate(2)
    assert net.connected_robot_ids(2) == {2}
    assert net.partition_count == 3


def test_single_robot_isolation_updates_topology():
    model = WarehouseModel(seed=11)
    result = isolate_robot(model, 4)
    assert result["status"] == "injected"
    assert model.network.connected_robot_ids(4) == {4}
    assert model.get_network_state()["metrics"]["partitions"] == 2


def test_message_delay_and_expiry_are_enforced():
    net = NetworkSimulator(range(5), seed=2, ttl=3)
    net.set_conditions(latency=2)
    net.send("Robot-0", "Robot-1", MessageType.ROBOT_STATUS, {}, 0)
    net.advance(1)
    assert net.receive("Robot-1") == []
    net.advance(2)
    assert net.receive("Robot-1") == []
    net.advance(3)
    assert len(net.receive("Robot-1")) == 1
    assert net.counters["delayed"] == 1


def test_packet_loss_is_seeded_and_counted():
    net = NetworkSimulator(range(5), seed=4)
    net.set_conditions(packet_loss=1.0)
    message = net.send("Robot-0", "Robot-1", MessageType.TASK_BID, {}, 0)
    assert message.delivery_status == "dropped"
    assert net.counters["dropped"] == 1


def test_expired_message_does_not_arrive():
    net = NetworkSimulator(range(5), seed=4, ttl=1)
    net.set_conditions(latency=4)
    net.send("Robot-0", "Robot-1", MessageType.TASK_BID, {}, 0)
    net.advance(2)
    assert not net.receive("Robot-1")
    assert net.counters["dropped"] == 1


def test_each_robot_calculates_its_own_bid_and_explanation():
    model = WarehouseModel(seed=5)
    task = {"task_id": 90, "sku": "SKU-001", "qty": 1, "priority": "urgent",
            "priority_rank": 0, "arrival_tick": 1, "shelf_location": [3, 4],
            "announce_tick": 1, "bids": {}, "claims": {}}
    near, far = model.robots[0], model.robots[4]
    near.local_task_knowledge[90] = dict(task)
    far.local_task_knowledge[90] = dict(task)
    near.local_task_queue = [90]; far.local_task_queue = [90]
    near._send_bid(90); far._send_bid(90)
    assert near.local_task_knowledge[90]["bids"][0] < far.local_task_knowledge[90]["bids"][4]
    assert "score" in near.last_decision_reason


def test_disconnected_groups_allocate_from_their_local_task_view():
    model = WarehouseModel(seed=5)
    model.network.set_partition([[0, 1], [2, 3, 4]])
    for rid, task_id in ((0, 91), (4, 92)):
        robot = model.robots[rid]
        sku, shelf = ("SKU-001", [3, 4]) if rid == 0 else ("SKU-006", [8, 8])
        robot.local_task_knowledge[task_id] = {"task_id": task_id, "sku": sku, "qty": 1,
            "priority": "normal", "priority_rank": 1, "arrival_tick": 0,
            "shelf_location": shelf, "announce_tick": 0, "bids": {}, "claims": {}}
        robot.local_task_queue = [task_id]
    model.current_tick = 2
    model.robots[0].decide(); model.robots[4].decide()
    assert model.robots[0].current_task.task_id == 91
    assert model.robots[4].current_task.task_id == 92
    assert model.partition_decisions == 2


def test_partitioned_claim_conflict_has_deterministic_winner():
    model = WarehouseModel(seed=5)
    robot = model.robots[0]
    robot.local_task_knowledge[93] = {"bids": {}, "claims": {0: 9.0}, "task_id": 93}
    robot._record_claim({"task_id": 93, "robot_id": 4, "score": 5.0})
    assert robot.local_task_knowledge[93]["owner"] == 4
    assert model.network.conflicts_detected == 1
    assert model.network.conflicts_resolved == 1


def test_repeated_conflict_state_sync_does_not_duplicate_resolution_metrics():
    model = WarehouseModel(seed=5)
    robot = model.robots[0]
    robot.local_task_knowledge[95] = {
        "task_id": 95, "completed": False, "bids": {},
        "claims": {0: 9.0}, "claim_expiry": {0: 30},
    }
    sync = {"tasks": [{
        "task_id": 95,
        "task": {"task_id": 95, "completed": False, "claim_expiry": {"4": 30}},
        "bids": {"4": 5.0}, "claims": {"4": 5.0},
    }]}
    robot._merge_state(sync)
    reconciliations = model.network.reconciliation_count
    robot._merge_state(sync)
    assert model.network.conflicts_detected == 1
    assert model.network.conflicts_resolved == 1
    assert model.network.reconciliation_count == reconciliations


def test_invalid_claim_score_is_rejected():
    model = WarehouseModel(seed=5)
    model.robots[0].local_task_knowledge[96] = {"task_id": 96, "bids": {}, "claims": {}}
    model.robots[0]._record_claim({"task_id": 96, "robot_id": 1, "score": float("nan")})
    assert model.robots[0].local_task_knowledge[96]["claims"] == {}
    assert model.auction_metrics["invalid_auction_messages_rejected"] == 1


def test_auction_ties_are_broken_by_lowest_robot_id():
    model = WarehouseModel(seed=5)
    for rid in (0, 1):
        robot = model.robots[rid]
        robot.local_task_knowledge[97] = {
            "task_id": 97, "sku": "SKU-001", "qty": 1, "priority": "normal",
            "priority_rank": 1, "arrival_tick": 0, "shelf_location": [3, 4],
            "announce_tick": 0, "bids": {0: 5.0, 1: 5.0}, "claims": {},
        }
        robot.local_task_queue = [97]
    model.current_tick = 2
    for rid in (0, 1):
        model.robots[rid]._last_bid_tick[97] = model.current_tick
    model.robots[0].decide()
    model.robots[1].decide()
    assert model.robots[0].current_task.task_id == 97
    assert model.robots[1].current_task is None


def test_reconciliation_stops_loser_and_releases_its_shelf():
    model = WarehouseModel(seed=5)
    model.order_agent.receive_order("SKU-001", 1, "normal")
    world_task = model.order_agent.task_queue[0]
    world_task.shelf_location = (3, 4)
    robot = model.robots[0]
    assert model.inventory_agent.reserve((3, 4), 0, "SKU-001", 1)
    robot.current_task = world_task
    robot.status = "EN_ROUTE_TO_SHELF"
    robot.local_task_knowledge[world_task.task_id] = {"task_id": world_task.task_id,
        "bids": {0: 5.0}, "claims": {0: 5.0}, "claim_expiry": {0: 30}, "completed": False}
    robot._merge_state({"tasks": [{"task_id": world_task.task_id,
        "task": {"task_id": world_task.task_id, "completed": False, "claim_expiry": {4: 30}},
        "bids": {4: 3.0}, "claims": {4: 3.0}}]})
    assert robot.local_task_knowledge[world_task.task_id]["owner"] == 4
    assert robot.current_task is None
    assert not model.inventory_agent.shelf_state[(3, 4)]["reserved"]


def test_reconnection_exchanges_and_merges_local_claims():
    model = WarehouseModel(seed=5)
    network_partition(model, 2)
    model.step()
    model.robots[0].local_task_knowledge[94] = {"task_id": 94, "sku": "SKU-001", "qty": 1,
        "priority": "normal", "priority_rank": 1, "arrival_tick": 0, "shelf_location": [3, 4],
        "bids": {0: 3.0}, "claims": {0: 3.0}, "announce_tick": 0}
    model.robots[4].local_task_knowledge[94] = {"task_id": 94, "sku": "SKU-001", "qty": 1,
        "priority": "normal", "priority_rank": 1, "arrival_tick": 0, "shelf_location": [3, 4],
        "bids": {4: 2.0}, "claims": {4: 2.0}, "announce_tick": 0}
    restore_network(model)
    for _ in range(3): model.step()
    assert model.network.reconciliation_count > 0
    assert model.robots[0].local_task_knowledge[94]["owner"] == 4
    assert any(m["payload"].get("action") == "state_reconciled" for m in model.message_log)


def test_duplicate_completion_is_idempotent_for_inventory():
    model = WarehouseModel(seed=5)
    model.order_agent.receive_order("SKU-001", 1, "normal")
    task = model.order_agent.task_queue[0]
    task.shelf_location = model.inventory_agent.locate(task.sku)
    assert model.inventory_agent.reserve(task.shelf_location, 0, task.sku, task.qty)
    quantity_before = model.inventory_agent.shelf_state[task.shelf_location]["skus"][task.sku]
    assert model.complete_distributed_task(0, task.task_id)
    assert not model.complete_distributed_task(1, task.task_id)
    assert model.inventory_agent.shelf_state[task.shelf_location]["skus"][task.sku] == quantity_before - 1
    assert len(model.order_agent.completed_tasks) == 1


def test_fault_injection_does_not_claim_recovery_immediately():
    model = WarehouseModel(seed=5)
    event = network_partition(model, 2)
    assert event["status"] == "injected"
    assert model.shocks_recovered == 0
    assert not event["recovered"]
    restore_network(model)
    model.step()
    assert event["status"] == "injected"
    model.step()
    assert event["status"] == "recovered"
    assert model.shocks_recovered == 1


def test_robots_keep_executing_known_tasks_when_isolated():
    model = WarehouseModel(seed=12)
    for _ in range(40): model.step()
    robot = next(r for r in model.robots.values() if r.current_task is not None)
    task_id = robot.current_task.task_id
    isolate_robot(model, robot.robot_id)
    initial_pos = robot.pos_tuple
    for _ in range(8): model.step()
    assert robot.current_task is None or robot.current_task.task_id == task_id
    assert robot.pos_tuple != initial_pos or robot.tasks_completed > 0 or robot.status in ("PICKING", "DROPPING", "CHARGING")
    assert robot.communication_status == "ISOLATED"


def test_collision_safety_survives_partition():
    model = WarehouseModel(seed=21)
    for _ in range(45): model.step()
    network_partition(model, 2)
    for _ in range(30): model.step()
    assert model.traffic_controller.collision_count == 0


def test_normal_partition_progress_recovery_reconciliation_sequence():
    model = WarehouseModel(seed=42)
    for _ in range(45): model.step()
    before = model.get_kpis()["total_tasks_completed"]
    partition = network_partition(model, 2)
    for _ in range(35): model.step()
    during = model.get_kpis()["total_tasks_completed"]
    assert partition["status"] == "injected"
    assert model.network.disconnected_ticks >= 35
    restore_network(model)
    for _ in range(5): model.step()
    assert during >= before
    assert model.network.partition_count == 1
    assert model.network.reconciliation_count > 0
    assert model.get_kpis()["collision_count"] == 0


def test_both_partition_groups_negotiate_and_complete_local_work():
    model = WarehouseModel(seed=42)
    network_partition(model, 2)
    task_payloads = []
    for sku, shelf, source in (("SKU-001", (3, 4), 0), ("SKU-006", (8, 8), 4)):
        model.order_agent.receive_order(sku, 1, "normal")
        task = model.order_agent.task_queue[-1]
        task.shelf_location = shelf
        task.status = "DISPATCHED"
        payload = {"task_id": task.task_id, "sku": sku, "qty": 1,
                   "priority": "normal", "priority_rank": 1,
                   "arrival_tick": model.current_tick, "shelf_location": list(shelf)}
        source_robot = model.robots[source]
        source_robot.local_task_knowledge[task.task_id] = {**payload,
            "announce_tick": model.current_tick + 1, "bids": {}, "claims": {}}
        source_robot.local_task_queue.append(task.task_id)
        model.network.broadcast(f"Robot-{source}", MessageType.TASK_ANNOUNCEMENT,
                                payload, model.current_tick)
        source_robot._send_bid(task.task_id)
        task_payloads.append(task.task_id)
    for _ in range(100):
        model.step()
        if all(tid in model.completed_task_ids for tid in task_payloads):
            break
    progress = model.partition_progress_by_group
    assert progress.get("0-1", 0) >= 1
    assert progress.get("2-3-4", 0) >= 1
    assert model.partition_decisions >= 2


def test_long_simulation_with_network_disruptions_remains_operable():
    model = WarehouseModel(seed=17)
    for tick in range(120):
        if tick == 30: network_partition(model, 2)
        if tick == 75: restore_network(model)
        if tick == 90: isolate_robot(model, 3)
        if tick == 105: restore_network(model)
        model.step()
    assert model.current_tick == 120
    assert model.network.counters["sent"] > 0
    assert model.network.counters["delivered"] > 0
    assert model.network.disconnected_ticks > 0
    assert model.get_kpis()["collision_count"] == 0


def test_fixed_seed_repeats_orders_positions_and_network_counters():
    runs = []
    for _ in range(2):
        model = WarehouseModel(seed=2026)
        for tick in range(50):
            if tick == 20: network_partition(model, 2)
            if tick == 35: restore_network(model)
            model.step()
        runs.append((model.get_kpis()["orders_received"],
                     model.get_kpis()["total_tasks_completed"],
                     [robot.pos_tuple for robot in model.robots.values()],
                     dict(model.network.counters)))
    assert runs[0] == runs[1]
