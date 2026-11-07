"""Robot-local knowledge and decision-explanation regression tests."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from warehouse_sim.events import network_partition, restore_network
from warehouse_sim.model import WarehouseModel
from warehouse_sim.robot_perspective import local_knowledge_snapshot, simulation_comparison


def test_local_knowledge_view_excludes_global_tasks_not_received():
    model = WarehouseModel(seed=42, persist_log=False)
    robot = model.robots[4]
    network_partition(model, 2)
    model.order_agent.receive_order("SKU-001", 1, "normal")
    for _ in range(3):
        model.step()

    global_task = model.order_agent.all_tasks[-1]
    local = local_knowledge_snapshot(robot)
    comparison = simulation_comparison(model, robot, local)

    assert global_task.task_id not in {task["task_id"] for task in local["known_tasks"]}
    unavailable = {task["task_id"] for task in comparison["global_tasks_not_in_local_memory"]}
    assert global_task.task_id in unavailable


def test_disconnected_robot_does_not_learn_new_order_until_sync():
    model = WarehouseModel(seed=42, persist_log=False)
    network_partition(model, 2)
    model.order_agent.receive_order("SKU-006", 1, "normal")
    task = model.order_agent.all_tasks[-1]
    for _ in range(4):
        model.step()

    robot = model.robots[4]
    assert task.task_id not in robot.local_task_knowledge
    assert task.task_id in {
        item["task_id"] for item in simulation_comparison(
            model, robot, local_knowledge_snapshot(robot)
        )["global_tasks_not_in_local_memory"]
    }


def test_restore_network_synchronises_previously_unavailable_task():
    model = WarehouseModel(seed=42, persist_log=False)
    network_partition(model, 2)
    model.order_agent.receive_order("SKU-006", 1, "normal")
    task = model.order_agent.all_tasks[-1]
    for _ in range(4):
        model.step()
    robot = model.robots[4]
    assert task.task_id not in robot.local_task_knowledge

    restore_network(model)
    for _ in range(8):
        model.step()
        if task.task_id in robot.local_task_knowledge:
            break

    assert task.task_id in robot.local_task_knowledge
    assert any(
        message.get("message_type") == "state_sync"
        for message in robot.local_event_memory
    )


def test_recorded_bid_factors_reproduce_robot_calculated_score():
    model = WarehouseModel(seed=42, persist_log=False)
    model.order_agent.receive_order("SKU-001", 1, "urgent")
    task = model.order_agent.all_tasks[-1]
    task.shelf_location = model.inventory_agent.locate(task.sku)
    model.announce_task(task)

    model.network.advance(1)
    robot = model.robots[0]
    robot.sense()
    bid = next(
        event for event in robot.local_decision_history
        if event["event_type"] == "bid_calculated" and event["task_id"] == task.task_id
    )

    expected = round(
        bid["distance"] + bid["battery_adjustment"] + bid["urgency_adjustment"], 6
    )
    assert expected == pytest.approx(bid["score"])
    assert bid["urgency_adjustment"] == -4.0
    assert any(
        entry["payload"].get("action") == "auction_bid_calculated"
        and entry["payload"].get("task_id") == task.task_id
        and entry["payload"].get("score") == bid["score"]
        for entry in model.message_log
    )

    selection_model = WarehouseModel(seed=42, persist_log=False)
    for _ in range(30):
        selection_model.step()
    robot_with_selection = next(
        robot for robot in selection_model.robots.values()
        if any(event["event_type"] == "task_selected"
               for event in robot.local_decision_history)
    )
    selected = next(
        event for event in robot_with_selection.local_decision_history
        if event["event_type"] == "task_selected"
    )
    assert selected["bid_calculation"] is not None
    recorded = selected["bid_calculation"]
    assert round(
        recorded["distance"] + recorded["battery_adjustment"]
        + recorded["urgency_adjustment"], 6
    ) == pytest.approx(selected["bid"])
    assert selected["available_bids"][robot_with_selection.robot_id] == pytest.approx(selected["bid"])
    assert min(
        selected["available_bids"],
        key=lambda rid: (selected["available_bids"][rid], rid),
    ) == robot_with_selection.robot_id


def test_explore_renders_robot_perspective_and_global_comparison():
    dashboard = Path(__file__).parents[1] / "dashboard.py"
    app = AppTest.from_file(str(dashboard), default_timeout=30).run()
    app.segmented_control(key="main_navigation").set_value("Robot Intelligence").run()

    assert not app.exception, [str(error) for error in app.exception]
    assert any("INSIDE THE ROBOT'S MIND" in element.value for element in app.markdown)
    assert any("What the Simulation Knows" in element.value for element in app.markdown)
    assert any("WHY DID THIS ROBOT CHOOSE THIS TASK?" in element.value for element in app.markdown)
    app.segmented_control(key="explore_mode").set_value("3D Warehouse").run()
    assert not app.exception, [str(error) for error in app.exception]
    app.segmented_control(key="explore_mode").set_value("Robot Perspective").run()
    assert not app.exception, [str(error) for error in app.exception]


def test_redesigned_navigation_and_presentation_keep_the_same_simulation():
    dashboard = Path(__file__).parents[1] / "dashboard.py"
    app = AppTest.from_file(str(dashboard), default_timeout=30).run()
    assert not app.exception, [str(error) for error in app.exception]
    assert app.segmented_control(key="main_navigation").value == "Mission Control"
    assert any("Five robots. One collective intelligence." in item.value for item in app.markdown)

    model = app.session_state["model"]
    app.toggle(key="presentation_mode").set_value(True).run()
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["presentation_mode"] is True
    assert app.session_state["model"] is model
    assert not any(slider.label == "Simulation speed" for slider in app.slider)
    assert any(button.key == "presentation_open_chaos" for button in app.button)
    app.button(key="presentation_open_chaos").click().run()
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["main_navigation"] == "Chaos Lab"
    assert app.session_state["model"] is model

    app.segmented_control(key="main_navigation").set_value("Robot Intelligence").run()
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["model"] is model
    app.segmented_control(key="main_navigation").set_value("Chaos Lab").run()
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["model"] is model
