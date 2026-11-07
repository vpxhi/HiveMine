"""Streamlit smoke coverage for the controls used in the judge workflow."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_mission_control_robot_guided_demo_and_chaos_controls():
    dashboard = Path(__file__).parents[1] / "dashboard.py"
    app = AppTest.from_file(str(dashboard), default_timeout=30).run()
    assert not app.exception, [str(error) for error in app.exception]
    assert any(element.type == "plotly_chart" for element in app)
    assert any('aria-label="Live mini map' in str(element.value) for element in app.markdown)
    app.segmented_control(key="console_mode").set_value("Technical").run()
    assert not app.exception, [str(error) for error in app.exception]
    assert any("Packet loss setting" in str(element.value) for element in app.markdown)
    app.segmented_control(key="console_mode").set_value("Operator").run()

    def click_label(label):
        next(button for button in app.button if button.label == label).click().run()

    click_label("Start Simulation")
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["running"]
    app.slider(key="speed").set_value(3).run()
    assert app.session_state["speed"] == 3
    click_label("Pause")
    assert not app.session_state["running"]
    app.button(key="camera_toggle").click().run()
    assert app.session_state["top_down"]

    app.button(key="console_focus_4").click().run()
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["selected_robot"] == 4
    assert app.session_state["main_navigation"] == "Mission Control"
    app.segmented_control(key="main_navigation").set_value("Robot Intelligence").run()
    app.segmented_control(key="explore_mode").set_value("3D Warehouse").run()
    assert not app.exception, [str(error) for error in app.exception]
    app.button(key="perspective_robot_2").click().run()
    assert app.session_state["selected_robot"] == 2
    app.segmented_control(key="explore_mode").set_value("Robot Perspective").run()
    assert not app.exception, [str(error) for error in app.exception]

    app.segmented_control(key="main_navigation").set_value("Mission Control").run()
    click_label("Show me how HiveMine works")
    assert not app.exception, [str(error) for error in app.exception]
    app.button(key="guide_next").click().run()
    assert app.session_state["guided_stage"] == 1
    app.button(key="guide_pause").click().run()
    assert not app.session_state["running"]
    app.button(key="guide_previous").click().run()
    assert app.session_state["guided_stage"] == 0
    app.button(key="guide_next").click().run()
    assert app.session_state["guided_stage"] == 1
    app.button(key="guide_exit").click().run()
    assert not app.session_state["guided"]

    app.segmented_control(key="main_navigation").set_value("Chaos Lab").run()
    for key in ("chaos_split", "chaos_restore", "chaos_isolate", "chaos_blackout"):
        assert any(button.key == key for button in app.button)
    app.button(key="chaos_split").click().run()
    assert app.session_state["model"].network.partition_count == 2
    downloads = app.get("download_button")
    assert any(button.key == "chaos_report_download" for button in downloads)
    assert any(button.key == "chaos_full_evidence" for button in downloads)
    assert any(button.key == "chaos_history_csv" for button in downloads)
    for key in ("chaos_report_download", "chaos_full_evidence", "chaos_history_csv"):
        next(button for button in app.get("download_button") if button.key == key).click().run()
        assert not app.exception, [str(error) for error in app.exception]
        assert next(button for button in app.get("download_button") if button.key == key).value
    app.button(key="chaos_restore").click().run()
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["model"].network.partition_count == 1
    click_label("Reset")
    assert not app.exception, [str(error) for error in app.exception]
    assert app.session_state["model"].current_tick == 0
