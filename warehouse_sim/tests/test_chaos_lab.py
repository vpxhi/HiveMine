"""Regression coverage for the Chaos Lab's real simulation disruptions."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from warehouse_sim.events import (
    block_cell,
    disconnect_all_robots,
    isolate_robot,
    kill_robot,
    network_partition,
    restore_network,
    set_network_conditions,
)
from warehouse_sim.model import WarehouseModel
from warehouse_sim.visualization.warehouse_3d import build_warehouse_scene


def test_chaos_actions_change_network_and_warehouse_state():
    model = WarehouseModel(seed=42, persist_log=False)

    split = network_partition(model, 2)
    assert split["groups"] == [[0, 1], [2, 3, 4]]
    assert model.network.partition_count == 2

    isolate_robot(model, 4)
    assert model.network.partition_count == 3

    disconnect_all_robots(model)
    assert model.network.partition_count == len(model.robots)
    assert all(len(group) == 1 for group in model.network.robot_components())

    set_network_conditions(model, latency=3, packet_loss=0.4)
    assert model.network.latency == 3
    assert model.network.packet_loss == 0.4

    aisle = (19, 19)
    blocked = block_cell(model, aisle)
    assert blocked["status"] == "recovery_in_progress"
    assert aisle in model.blocked_cells

    failure = kill_robot(model, 2)
    assert failure["robot_id"] == 2
    assert model.robots[2].status == "FAILED"

    restore_network(model)
    assert model.network.partition_count == 1
    assert model.network.latency == 0
    assert model.network.packet_loss == 0
    assert model.robots[2].status == "FAILED"
    assert aisle in model.blocked_cells


def test_partition_visual_uses_group_colours_and_disabled_links():
    model = WarehouseModel(seed=42, persist_log=False)
    network_partition(model, 2)

    figure = build_warehouse_scene(model, selected_robot=2)
    bodies = {trace.name: trace for trace in figure.data
              if isinstance(trace.name, str) and trace.name.startswith("Robot ")}
    assert bodies["Robot 01"].color != bodies["Robot 03"].color
    assert any(trace.name == "Connection interrupted" for trace in figure.data)
    assert any(trace.name == "Selected robot 03" for trace in figure.data)

    disconnect_all_robots(model)
    blackout = build_warehouse_scene(model)
    assert sum(trace.name == "Connection interrupted" for trace in blackout.data) == len(model.robots) - 1
    assert not any(trace.name == "Robots connected" for trace in blackout.data)


def test_chaos_lab_demo_controls_disruptions_restore_and_reset():
    dashboard = Path(__file__).parents[1] / "dashboard.py"
    app = AppTest.from_file(str(dashboard), default_timeout=30).run()
    app.segmented_control(key="main_navigation").set_value("Chaos Lab").run()
    assert not app.exception

    app.button(key="judge_demo_start").click().run()
    assert not app.exception
    assert app.session_state["judge_demo_active"]
    assert app.session_state["model"].seed == 42

    app.button(key="judge_demo_pause").click().run()
    assert not app.exception
    assert not app.session_state["running"]
    app.button(key="judge_demo_pause").click().run()
    assert not app.exception
    assert app.session_state["running"]
    app.button(key="judge_demo_replay").click().run()
    assert not app.exception
    assert app.session_state["judge_demo_active"]
    assert app.session_state["model"].current_tick <= 1
    for _ in range(60):
        if app.session_state["judge_demo_complete"]:
            break
        app.run()
        assert not app.exception, [str(error) for error in app.exception]
    demo_model = app.session_state["model"]
    assert app.session_state["judge_demo_complete"]
    assert demo_model.network.partition_count == 1
    assert not demo_model._reconciliation_active
    assert demo_model.network.state_sync_received > 0
    assert demo_model.partition_decisions > 0
    assert demo_model.partition_tasks_completed > 0
    assert demo_model.network.reconciliation_count > 0
    first_run_metrics = (
        demo_model.partition_tasks_completed,
        demo_model.partition_decisions,
        demo_model.network.state_sync_received,
        demo_model.network.reconciliation_count,
    )
    app.button(key="judge_demo_replay").click().run()
    assert not app.exception
    for _ in range(60):
        if app.session_state["judge_demo_complete"]:
            break
        app.run()
        assert not app.exception, [str(error) for error in app.exception]
    replay_model = app.session_state["model"]
    replay_metrics = (
        replay_model.partition_tasks_completed,
        replay_model.partition_decisions,
        replay_model.network.state_sync_received,
        replay_model.network.reconciliation_count,
    )
    assert app.session_state["judge_demo_complete"]
    assert replay_metrics == first_run_metrics

    model = lambda: app.session_state["model"]

    def click(key):
        app.button(key=key).click().run()
        assert not app.exception, [str(error) for error in app.exception]

    click("chaos_split")
    assert model().network.partition_count == 2
    click("chaos_restore")
    assert model().network.partition_count == 1
    click("chaos_isolate")
    assert model().network.partition_count == 2
    click("chaos_restore")
    click("chaos_blackout")
    assert model().network.partition_count == len(model().robots)
    click("chaos_restore")

    app.slider(key="chaos_latency").set_value(2)
    app.slider(key="chaos_loss").set_value(0.3)
    click("chaos_unstable")
    assert model().network.latency == 2
    assert model().network.packet_loss == 0.3

    aisle = app.selectbox(key="chaos_aisle_cell").value
    click("chaos_block_aisle")
    assert aisle in model().blocked_cells

    robot_id = app.selectbox(key="chaos_failure_id").value
    click("chaos_robot_failure")
    assert model().robots[robot_id].status == "FAILED"

    click("chaos_restore")
    next(button for button in app.button if button.label == "Reset").click().run()
    assert not app.exception
    assert model().current_tick == 0
    assert model().network.partition_count == 1
    next(button for button in app.button if button.label == "Start Simulation").click().run()
    assert not app.exception
    assert app.session_state["running"]
    next(button for button in app.button if button.label == "Pause").click().run()
    assert not app.exception
    assert not app.session_state["running"]
    next(button for button in app.button if button.label == "Reset").click().run()
    assert not app.exception
    assert model().current_tick == 0
