"""HiveMine: a simple live 3D warehouse and multi-robot demonstration."""

from __future__ import annotations

import json
import os
import sys
import time
from html import escape
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from warehouse_sim.events import (
    block_cell,
    disconnect_all_robots,
    flood_urgent_orders,
    force_drain,
    inject_deadlock,
    isolate_robot,
    kill_robot,
    network_partition,
    restore_network,
    set_network_conditions,
)
from warehouse_sim.model import WarehouseModel
from warehouse_sim.visualization.warehouse_3d import PALETTE, build_warehouse_scene


st.set_page_config(page_title="HiveMine", page_icon="H", layout="wide", initial_sidebar_state="collapsed")

st.html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --hm-ink:#edf1f7; --hm-muted:#9aa6b8; --hm-blue:#76a9ff; --hm-green:#68d8a2; --hm-amber:#f0bd68; --hm-red:#ef7884; --hm-purple:#b5a0ff; }
.stApp { background: radial-gradient(ellipse at 50% -28%, #25334b 0%, #111722 53%); color:var(--hm-ink); }
[data-testid="stHeader"] { background:transparent; }
.block-container { max-width:1680px; padding-top:1.35rem; padding-bottom:2rem; }
h1,h2,h3 { font-family:'Manrope',sans-serif !important; letter-spacing:-.035em; }
p,div,label,button { font-family:'DM Sans',sans-serif; }
.hm-brand { color:#f4f6fa; font-family:'Manrope',sans-serif; font-size:1.75rem; font-weight:800; letter-spacing:-.055em; }
.hm-tagline { color:#a9b5c7; font-size:1rem; margin-top:.18rem; }
.hm-eyebrow { color:#a996ff; font-size:.72rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; }
.hm-hero { border:1px solid #364255; border-radius:22px; padding:1.35rem 1.55rem; background:linear-gradient(112deg,rgba(35,47,66,.88),rgba(24,32,45,.88)); margin:.45rem 0 1rem; }
.hm-hero-title { color:#f3f5f9; font:700 clamp(1.25rem,2.3vw,2rem) 'Manrope',sans-serif; letter-spacing:-.045em; margin:.22rem 0 .22rem; }
.hm-hero-copy { color:#b4bfd0; font-size:.97rem; line-height:1.5; margin:0; max-width:860px; }
.hm-event { padding:.68rem 0; border-bottom:1px solid rgba(135,151,176,.13); color:#d4dbe5; line-height:1.4; font-size:.88rem; }
.hm-event-time { color:#9e8df4; font-size:.73rem; font-weight:700; margin-right:.35rem; }
.hm-network { display:inline-flex; align-items:center; gap:.5rem; border:1px solid #364355; border-radius:999px; padding:.42rem .75rem; color:#dce3ec; background:#1a2230; font-size:.85rem; }
.hm-dot { width:.48rem; height:.48rem; border-radius:50%; display:inline-block; background:#68d8a2; }
div[data-testid="stMetric"] { border-radius:15px; border-color:rgba(131,150,179,.17); background:rgba(27,36,50,.78); padding:.8rem .95rem; }
div[data-testid="stMetricValue"] { font-family:'Manrope',sans-serif; }
.stButton>button { min-height:2.55rem; border-radius:12px; transition:all .16s ease; }
.stButton>button:hover { transform:translateY(-1px); border-color:#a996ff; }
div[role="radiogroup"] label, div[data-testid="stSegmentedControl"] label { border-radius:11px !important; }
[data-testid="stExpander"] { border-radius:14px; border-color:rgba(131,150,179,.18); }
@media(max-width:760px) { .block-container{padding-left:1rem;padding-right:1rem}.hm-hero{padding:1rem}.hm-tagline{font-size:.9rem} }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms!important; transition-duration:.01ms!important; scroll-behavior:auto!important; } }
</style>
""")


ROBOT_STATES = {
    "IDLE": "Ready for a delivery",
    "EN_ROUTE_TO_SHELF": "Picking up an item",
    "PICKING": "Collecting an item",
    "EN_ROUTE_TO_PACKING": "Delivering an item",
    "DROPPING": "Handing over a delivery",
    "RETURNING": "Returning to its route",
    "NEEDS_CHARGE": "Heading to charge",
    "CHARGING": "Charging",
    "FAILED": "Out of service",
}


def fresh_state() -> None:
    st.session_state.model = WarehouseModel(seed=42)
    st.session_state.running = False
    st.session_state.started = False
    st.session_state.speed = 1
    st.session_state.view = "Home"
    st.session_state.main_navigation = "Home"
    st.session_state.selected_robot = 0
    st.session_state.top_down = False
    st.session_state.activity = [{"tick": 0, "text": "The warehouse is ready. Start the simulation to see the robots at work."}]
    st.session_state.activity_cursor = 0
    st.session_state.last_status = {rid: robot.status for rid, robot in st.session_state.model.robots.items()}
    st.session_state.guided = False
    st.session_state.guided_stage = 0
    st.session_state.guided_actions = set()
    st.session_state.guide_partition_baseline = {"completed": 0, "decisions": 0}


if "model" not in st.session_state:
    fresh_state()

model: WarehouseModel = st.session_state.model


def add_activity(text: str, tick: int | None = None) -> None:
    st.session_state.activity.append({"tick": model.current_tick if tick is None else tick, "text": text})
    st.session_state.activity = st.session_state.activity[-80:]


def friendly_message(message: Dict[str, Any]) -> str | None:
    payload = message.get("payload", {})
    action = payload.get("action")
    sender = str(message.get("from_agent", ""))
    robot_id = None
    if sender.startswith("Robot-"):
        try:
            robot_id = int(sender.split("-")[1])
        except ValueError:
            pass
    robot = f"Robot {robot_id + 1:02d}" if robot_id is not None else None
    if action == "place_order":
        return "A customer added a new delivery to the queue."
    if action == "task_announcement":
        return f"A new delivery job is ready for the robots to consider."
    if action == "distributed_task_claim":
        return f"{robot or 'A robot'} accepted a job after comparing its distance and battery with nearby robots."
    if action == "task_complete":
        return f"{robot or 'A robot'} completed a delivery."
    if action == "state_reconciled":
        return f"{robot or 'A robot'} compared notes and updated what it knows."
    if action == "task_conflict_reconciled":
        return "Two robots had chosen the same job. They compared bids and kept one clear owner."
    if action == "duplicate_claim_detected":
        return "Two disconnected teams chose the same job. HiveMine recorded the overlap for later reconciliation."
    if action == "reconnection_reconciliation_started":
        return "Communication is back. Robots are exchanging updates and checking their job lists."
    if action == "recovery_verified":
        return f"HiveMine confirmed that the {payload.get('shock_type', 'disruption').replace('_', ' ')} response worked."
    shock = payload.get("shock_type")
    if shock == "network_partition":
        groups = payload.get("groups", [])
        if payload.get("preset") == "full_network_outage":
            return "Every robot has lost contact with the other robots. Each continues with the jobs it already knows."
        if groups:
            first, second = groups[0], groups[1]
            return f"The connection split: Robots {', '.join(f'{rid+1:02d}' for rid in first)} and Robots {', '.join(f'{rid+1:02d}' for rid in second)} are now in separate groups."
        return "The robots are now working in separate communication groups."
    if shock == "robot_isolation":
        return f"Robot {payload.get('robot_id', 0)+1:02d} lost contact with the other robots and is continuing on its own."
    if shock == "network_recovery":
        return "Communication restored. The robots are reconnecting and comparing their updates."
    if action == "battery_handoff":
        return "A robot handed off its job before heading to a charging dock."
    return None


def sync_activity() -> None:
    messages = model.message_log
    cursor = min(st.session_state.activity_cursor, len(messages))
    for item in messages[cursor:]:
        text = friendly_message(item)
        if text:
            add_activity(text, int(item.get("tick", model.current_tick)))
    st.session_state.activity_cursor = len(messages)
    for rid, robot in model.robots.items():
        before = st.session_state.last_status.get(rid)
        if before != robot.status:
            if robot.status == "EN_ROUTE_TO_SHELF":
                add_activity(f"Robot {rid+1:02d} chose a new delivery and is heading to a shelf.")
            elif robot.status == "EN_ROUTE_TO_PACKING":
                add_activity(f"Robot {rid+1:02d} picked its item and is delivering it to packing.")
            elif robot.status == "CHARGING":
                add_activity(f"Robot {rid+1:02d} is charging so it can keep working safely.")
            elif robot.status == "IDLE" and before not in (None, "IDLE"):
                add_activity(f"Robot {rid+1:02d} is ready for another delivery.")
            st.session_state.last_status[rid] = robot.status


def advance_model(count: int = 1) -> None:
    for _ in range(count):
        model.step()
        sync_activity()


def network_label() -> str:
    if model.network.latency or model.network.packet_loss:
        return "Communication is unstable"
    if model.network.partition_count > 1:
        return f"{model.network.partition_count} groups working separately"
    return "Robots are connected"


def select_home_robot(robot_id: int) -> None:
    st.session_state.selected_robot = robot_id
    st.session_state.view = "Explore"
    st.session_state.main_navigation = "Explore"


def set_running(running: bool) -> None:
    st.session_state.running = running
    if running:
        st.session_state.started = True


def reset_demo() -> None:
    st.session_state.main_navigation = "Home"
    fresh_state()


def apply_partition() -> None:
    result = network_partition(model, 2)
    sync_activity()
    st.session_state.running = True
    st.session_state.started = True
    if "error" in result:
        st.error(result["error"])


def apply_restore() -> None:
    restore_network(model)
    sync_activity()
    st.session_state.running = True


def render_robot_detail(robot_id: int) -> None:
    robot = model.robots[robot_id]
    state = model.get_grid_state()["robots"][robot_id]
    disconnected = model.network.partition_count > 1
    destination = state["destination"]
    if destination == model.packing_station:
        destination_text = "Packing station"
    elif destination:
        shelf_index = model.shelf_locations.index(tuple(destination)) if tuple(destination) in model.shelf_locations else -1
        destination_text = f"Shelf {chr(65+shelf_index)}" if shelf_index >= 0 else f"Grid location {destination}"
    elif robot.status == "CHARGING":
        destination_text = "Charging dock"
    else:
        destination_text = "Waiting for a delivery"

    status = ROBOT_STATES.get(robot.status, robot.status.replace("_", " ").title())
    if disconnected and robot.status != "FAILED":
        status = "Working independently" if robot.current_task else "Waiting independently"
    st.markdown(f"### Robot {robot_id+1:02d}")
    st.markdown(f"**{status}**")
    st.caption(f"Current activity · {ROBOT_STATES.get(robot.status, 'Working')}")
    st.metric("Battery", f"{robot.battery:.0f}%")
    st.write(f"**Communication:** {'Independent' if disconnected else 'Connected'}")
    st.write(f"**Destination:** {destination_text}")
    if disconnected:
        st.info("This robot cannot receive updates from the other group. It is using the jobs and messages it already has.", icon=":material/wifi_off:")
    if robot.current_task:
        st.write("**Why this robot chose the job**")
        st.write("It had the best bid among the robots it could reach, based on distance, battery and job priority.")
    else:
        st.write("**Why it is waiting**")
        st.write("It has no unclaimed job in its current local list, or it is restoring its battery.")

    with st.expander("Technical details"):
        st.write("**What this robot currently knows**")
        st.json({
            "position": robot.pos_tuple,
            "battery": round(robot.battery, 1),
            "nearby_robots": [f"Robot {rid+1:02d}" for rid in robot.nearby_agents],
            "local_task_queue": robot.local_task_queue[-12:],
            "current_task": getattr(robot.current_task, "task_id", None),
            "most_recent_decision": robot.last_decision,
            "decision_explanation": robot.last_decision_reason,
            "known_tasks": robot.local_task_knowledge,
        })
        sent = [message.as_dict() for message in model.network.activity_log
                if message.sender == f"Robot-{robot_id}"]
        received = [message.as_dict() for message in model.network.activity_log
                    if message.recipient == f"Robot-{robot_id}"]
        st.caption(f"Messages sent: {len(sent)} · received: {len(received)}")
        st.json({"recent_sent": sent[-8:], "recent_received": received[-8:]})


def render_activity_panel() -> None:
    with st.container(border=True):
        st.subheader("What's happening")
        if not st.session_state.activity:
            st.caption("Updates will appear here as the warehouse runs.")
        for item in reversed(st.session_state.activity[-7:]):
            st.markdown(f"<div class='hm-event'><span class='hm-event-time'>T{item['tick']}</span>{escape(item['text'])}</div>", unsafe_allow_html=True)
        st.caption("Plain-language updates from the live simulation")


def render_network_groups() -> None:
    groups = sorted(model.network.robot_components(), key=lambda group: min(group))
    st.write("**Who can talk right now**")
    with st.container(horizontal=True):
        for index, group in enumerate(groups):
            names = ", ".join(f"Robot {int(node.split('-')[1])+1:02d}" for node in sorted(group))
            with st.container(border=True):
                st.markdown(f"**{'Connected group' if len(groups) > 1 else 'All robots connected'} {index+1 if len(groups) > 1 else ''}**")
                st.write(names)


def render_metrics() -> None:
    kpis = model.get_kpis()
    with st.container(horizontal=True):
        st.metric("Active robots", f"{sum(r.status not in ('IDLE', 'FAILED', 'CHARGING') for r in model.robots.values())} / 5", border=True)
        st.metric("Deliveries completed", kpis["orders_completed"], border=True)
        st.metric("Deliveries waiting", kpis["pending_tasks"], border=True)
        status = "Connected" if model.network.partition_count == 1 else "Working independently"
        st.metric("Communication", status, border=True)


@st.fragment(run_every=0.7 if st.session_state.running else None)
def home_live(selected_robot: int, top_down: bool, speed: int) -> None:
    if st.session_state.running:
        advance_model(speed)
    render_metrics()
    scene, side = st.columns([2.25, 1], gap="medium")
    with scene:
        with st.container(border=True):
            st.markdown("**Live warehouse**")
            st.caption("Drag to turn · scroll to zoom · right-drag to pan · use the chart toolbar to reset the camera")
            fig = build_warehouse_scene(model, selected_robot, top_down)
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": True, "responsive": True}, alt="Interactive 3D warehouse with live robot positions, routes, shelves and communication links")
    with side:
        render_activity_panel()
        st.write("")
        st.markdown("**Choose a robot to inspect**")
        with st.container(horizontal=True, vertical_alignment="center"):
            for rid, robot in model.robots.items():
                label = f"Robot {rid+1:02d} · {ROBOT_STATES.get(robot.status, robot.status.title())}"
                st.button(label, key=f"home_robot_{rid}", width="stretch", on_click=select_home_robot, args=(rid,))


@st.fragment(run_every=0.7 if st.session_state.running else None)
def explore_live(selected_robot: int, top_down: bool, speed: int) -> None:
    if st.session_state.running:
        advance_model(speed)
    render_metrics()
    scene, detail = st.columns([1.8, 1], gap="medium")
    with scene:
        with st.container(border=True):
            st.markdown("**Five robots, one shared goal**")
            fig = build_warehouse_scene(model, selected_robot, top_down)
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": True, "responsive": True}, alt="Three-dimensional warehouse showing the selected robot and its live route")
    with detail:
        with st.container(border=True):
            render_robot_detail(selected_robot)
    st.write("**Select a robot**")
    with st.container(horizontal=True, vertical_alignment="center"):
        for rid in model.robots:
            st.button(f"Robot {rid+1:02d}", key=f"explore_robot_{rid}", width="stretch",
                      on_click=lambda chosen=rid: st.session_state.update(selected_robot=chosen))
    render_activity_panel()


@st.fragment(run_every=0.7 if st.session_state.running else None)
def experiment_live(selected_robot: int, top_down: bool, speed: int) -> None:
    if st.session_state.running:
        advance_model(speed)
    render_metrics()
    scene, side = st.columns([2.1, 1], gap="medium")
    with scene:
        with st.container(border=True):
            st.markdown("**The warehouse during the communication test**")
            st.caption("Teal links are active. Red dashed links are interrupted. Each colour identifies a communication group.")
            fig = build_warehouse_scene(model, selected_robot, top_down)
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": True, "responsive": True}, alt="Live warehouse showing robot routes and links that are active or interrupted")
    with side:
        with st.container(border=True):
            st.subheader("Communication")
            st.markdown(f"<span class='hm-network'><i class='hm-dot' style='background:{PALETTE['green'] if model.network.partition_count == 1 else PALETTE['amber']}'></i>{escape(network_label())}</span>", unsafe_allow_html=True)
            render_network_groups()
            kpis = model.get_network_state()["metrics"]
            st.caption(f"{kpis['active_connections']} active links · {kpis['delivered']} messages delivered · {kpis['dropped']} could not get through")
        render_activity_panel()


def next_guided_stage() -> None:
    stage = min(5, st.session_state.guided_stage + 1)
    st.session_state.guided_stage = stage
    if stage in st.session_state.guided_actions:
        return
    if stage == 1:
        advance_model(8)
    elif stage == 2:
        st.session_state.guide_partition_baseline = {
            "completed": model.partition_tasks_completed,
            "decisions": model.partition_decisions,
        }
        network_partition(model, 2)
        st.session_state.running = True
        sync_activity()
    elif stage == 3:
        st.session_state.running = True
    elif stage == 4:
        restore_network(model)
        st.session_state.running = True
        advance_model(4)
    elif stage == 5:
        advance_model(8)
        st.session_state.running = False
    st.session_state.guided_actions.add(stage)


GUIDE_STAGES = [
    ("Normal operation", "Five autonomous robots are working together to fulfil warehouse orders."),
    ("Choosing a robot for each job", "Each robot scores the work it knows about and negotiates with robots it can reach."),
    ("Communication interrupted", "The connection is split into two groups. Messages cannot cross the broken link."),
    ("Working independently", "Both groups keep using their local task lists and continue making decisions."),
    ("Communication restored", "The robots exchange updates and compare any overlapping job claims."),
    ("Results from this run", "The figures below come from the live simulation, including work completed during the outage."),
]


def render_guided_demo() -> None:
    if not st.session_state.guided:
        if st.button("Show me how HiveMine works", type="primary", width="stretch"):
            st.session_state.guided = True
            st.session_state.guided_stage = 0
            st.session_state.guided_actions = set()
            st.session_state.guide_partition_baseline = {
                "completed": model.partition_tasks_completed,
                "decisions": model.partition_decisions,
            }
            st.session_state.running = True
            st.session_state.started = True
            st.rerun()
        return

    stage = st.session_state.guided_stage
    with st.container(border=True):
        st.markdown(f"<div class='hm-eyebrow'>Guided walkthrough · Step {stage+1} of 6</div><div class='hm-hero-title'>{escape(GUIDE_STAGES[stage][0])}</div><p class='hm-hero-copy'>{escape(GUIDE_STAGES[stage][1])}</p>", unsafe_allow_html=True)
        if stage == 3:
            if st.button("Continue for 20 simulation ticks", key="guide_continue", width="stretch"):
                advance_model(20)
        if stage == 5:
            base = st.session_state.guide_partition_baseline
            network_metrics = model.get_network_state()["metrics"]
            st.success(f"During communication failure, robots completed {model.partition_tasks_completed - base['completed']} deliveries and made {model.partition_decisions - base['decisions']} independent job choices.")
            st.caption(f"This run also observed {network_metrics['conflicts_detected']} overlapping job claims and {network_metrics['reconciliations']} local state updates after reconnection.")
        controls = st.columns(4)
        if controls[0].button("Previous", disabled=stage == 0, key="guide_previous", width="stretch"):
            st.session_state.guided_stage = max(0, stage - 1)
            st.rerun()
        if controls[1].button("Next", disabled=stage == 5, key="guide_next", type="primary", width="stretch"):
            next_guided_stage()
            st.rerun()
        if controls[2].button("Pause" if st.session_state.running else "Resume", key="guide_pause", width="stretch"):
            st.session_state.running = not st.session_state.running
            st.rerun()
        if controls[3].button("Exit walkthrough", key="guide_exit", width="stretch"):
            st.session_state.guided = False
            st.rerun()


def apply_network_action(result: Dict[str, Any], activity_text: str | None = None) -> None:
    sync_activity()
    if activity_text:
        add_activity(activity_text)
    if result.get("error"):
        st.error(result["error"])


def render_communication_popover() -> None:
    label = "Communication · Connected" if model.network.partition_count == 1 else "Communication · Groups separated"
    with st.popover(label, icon=":material/hub:"):
        st.caption(network_label())
        if st.button("Normal communication", key="popover_normal", width="stretch"):
            result = restore_network(model); apply_network_action(result, "Communication restored. The robots are comparing their updates."); st.session_state.running = True
        if st.button("Split robots into two groups", key="popover_split", width="stretch"):
            result = network_partition(model, 2); apply_network_action(result); st.session_state.running = True
        if st.button("Disconnect all robots", key="popover_disconnect_all", width="stretch"):
            result = disconnect_all_robots(model); apply_network_action(result); st.session_state.running = True
        if st.button("Unstable communication", key="popover_unstable", width="stretch"):
            result = set_network_conditions(model, 1, 0.3); apply_network_action(result, "Some messages may arrive late or not arrive at all."); st.session_state.running = True
        robot_id = st.selectbox("Robot to disconnect", list(model.robots), format_func=lambda rid: f"Robot {rid+1:02d}", key="popover_isolate_select")
        if st.button("Disconnect this robot", key="popover_isolate", width="stretch"):
            result = isolate_robot(model, robot_id); apply_network_action(result); st.session_state.running = True


# Header and simple three-area navigation.
top_left, top_right = st.columns([2.4, 1], vertical_alignment="center")
with top_left:
    st.markdown("<div class='hm-brand'>HiveMine</div><div class='hm-tagline'>Watch autonomous robots work together, even when they lose communication.</div>", unsafe_allow_html=True)
with top_right:
    st.markdown(f"<div style='text-align:right'><span class='hm-network'><i class='hm-dot' style='background:{PALETTE['green'] if model.network.partition_count == 1 else PALETTE['amber']}'></i>{escape(network_label())}</span></div>", unsafe_allow_html=True)

st.write("")
view = st.segmented_control("Main areas", ["Home", "Explore", "Experiment"],
                            key="main_navigation", label_visibility="collapsed", width="stretch")
if view:
    st.session_state.view = view

with st.container(horizontal=True, vertical_alignment="bottom"):
    if not st.session_state.started:
        if st.button("Start Simulation", type="primary", width="stretch", icon=":material/play_arrow:"):
            set_running(True); st.rerun()
    else:
        if st.button("Pause" if st.session_state.running else "Start", type="primary", width="stretch",
                     icon=":material/pause:" if st.session_state.running else ":material/play_arrow:"):
            set_running(not st.session_state.running)
            st.rerun()
    st.button("Reset", width="content", icon=":material/restart_alt:", on_click=reset_demo)
    st.slider("Simulation speed", 1, 4, key="speed", help="How many real simulation steps happen per update")
    render_communication_popover()
    st.button("Top-down" if not st.session_state.top_down else "Angled view", key="camera_toggle",
              on_click=lambda: st.session_state.update(top_down=not st.session_state.top_down),
              help="Switch between a top-down and angled camera")

selected_robot = st.session_state.selected_robot
top_down = st.session_state.top_down
speed = st.session_state.speed

if st.session_state.view == "Home":
    if not st.session_state.started:
        st.markdown("<section class='hm-hero'><div class='hm-eyebrow'>Autonomous warehouse, one team</div><div class='hm-hero-title'>Five robots. One shared goal.</div><p class='hm-hero-copy'>Start the live warehouse, then break communication and watch the robots keep working with what they know.</p></section>", unsafe_allow_html=True)
    render_guided_demo()
    home_live(selected_robot, top_down, speed)

elif st.session_state.view == "Explore":
    st.markdown("<section class='hm-hero'><div class='hm-eyebrow'>Explore the robots</div><div class='hm-hero-title'>Every robot makes its own choices.</div><p class='hm-hero-copy'>Choose a robot to see what it is doing, where it is going and what it currently knows.</p></section>", unsafe_allow_html=True)
    with st.container(horizontal=True, vertical_alignment="center"):
        for rid, robot in model.robots.items():
            st.button(f"Robot {rid+1:02d} · {ROBOT_STATES.get(robot.status, robot.status.title())}",
                      key=f"select_robot_{rid}", width="stretch",
                      on_click=lambda chosen=rid: st.session_state.update(selected_robot=chosen))
    explore_live(st.session_state.selected_robot, top_down, speed)

else:
    st.markdown("<section class='hm-hero'><div class='hm-eyebrow'>Experiment</div><div class='hm-hero-title'>What happens when robots lose contact?</div><p class='hm-hero-copy'>Break the connection, watch each group carry on, then restore communication to let the robots compare updates.</p></section>", unsafe_allow_html=True)
    controls = st.columns(3)
    if controls[0].button("Simulate Network Failure", type="primary", width="stretch", icon=":material/wifi_off:"):
        apply_partition()
    if controls[1].button("Restore Communication", width="stretch", icon=":material/wifi:"):
        apply_restore()
    if controls[2].button("Disconnect All Robots", width="stretch", icon=":material/portable_wifi_off:"):
        result = disconnect_all_robots(model); apply_network_action(result); st.session_state.running = True
    render_network_groups()
    exp_left, exp_right = st.columns(2)
    with exp_left:
        robot_to_isolate = st.selectbox("Disconnect one robot", list(model.robots), format_func=lambda rid: f"Robot {rid+1:02d}", key="experiment_isolate")
        if st.button("Disconnect selected robot", key="experiment_isolate_button", width="stretch"):
            result = isolate_robot(model, robot_to_isolate); apply_network_action(result); st.session_state.running = True
    with exp_right:
        if st.button("Simulate unstable communication", key="experiment_unstable", width="stretch"):
            result = set_network_conditions(model, 2, 0.25); apply_network_action(result, "Messages may now arrive late or get lost.")

    with st.expander("Advanced settings and other disruptions"):
        with st.form("network_settings"):
            latency = st.slider("Message delay (ticks)", 0, 8, model.network.latency)
            loss = st.slider("Messages lost", 0.0, 0.8, model.network.packet_loss, 0.05)
            split = st.slider("Robots in group A", 1, len(model.robots)-1, 2)
            submit, restore = st.columns(2)
            apply_settings = submit.form_submit_button("Apply settings", width="stretch")
            apply_custom_split = restore.form_submit_button("Use this group split", width="stretch")
        if apply_settings:
            result = set_network_conditions(model, latency, loss); apply_network_action(result)
        if apply_custom_split:
            result = network_partition(model, split); apply_network_action(result); st.session_state.running = True
        st.divider()
        st.markdown("**Other warehouse events**")
        shock_cols = st.columns(4)
        alive = [rid for rid, robot in model.robots.items() if robot.status != "FAILED"]
        failure_id = shock_cols[0].selectbox("Robot failure", alive or list(model.robots), format_func=lambda rid: f"Robot {rid+1:02d}", key="shock_failure")
        if shock_cols[0].button("Trigger", key="shock_failure_btn", width="stretch"):
            apply_network_action(kill_robot(model, failure_id), f"Robot {failure_id+1:02d} is out of service. Other robots are continuing.")
        bx, by = shock_cols[1].columns(2)
        x = bx.number_input("Blocked aisle X", 0, 19, 5); y = by.number_input("Y", 0, 19, 6)
        if shock_cols[1].button("Block aisle", key="shock_block_btn", width="stretch"):
            apply_network_action(block_cell(model, (int(x), int(y))), "An aisle is blocked. Robots are finding another route.")
        drain_id = shock_cols[2].selectbox("Low battery", alive or list(model.robots), format_func=lambda rid: f"Robot {rid+1:02d}", key="shock_battery")
        if shock_cols[2].button("Drain battery", key="shock_battery_btn", width="stretch"):
            apply_network_action(force_drain(model, drain_id), f"Robot {drain_id+1:02d} needs to recharge.")
        if shock_cols[3].button("Add urgent deliveries", key="shock_orders_btn", width="stretch"):
            apply_network_action(flood_urgent_orders(model, 8), "Several urgent deliveries just arrived.")
        if st.button("Create a traffic hold-up", key="shock_deadlock_btn"):
            apply_network_action(inject_deadlock(model), "Robots encountered a traffic hold-up and are trying to clear it.")
        st.divider()
        st.markdown("**Results from this run**")
        network_metrics = model.get_network_state()["metrics"]
        with st.container(horizontal=True):
            st.metric("Deliveries during outage", network_metrics["partition_tasks_completed"], border=True)
            st.metric("Independent choices", network_metrics["independent_decisions"], border=True)
            st.metric("Overlapping job claims", network_metrics["conflicts_detected"], border=True)
            st.metric("Disconnected ticks", network_metrics["disconnected_ticks"], border=True)
        phases = model.phase_metrics
        phase_names = list(phases)
        phase_rates = [phases[name]["tasks_completed"] / max(1, phases[name]["ticks"]) for name in phase_names]
        phase_figure = go.Figure(go.Bar(x=phase_names, y=phase_rates,
                                        marker_color=[PALETTE["blue"], PALETTE["purple"], PALETTE["green"]],
                                        text=[f"{phases[name]['tasks_completed']} deliveries / {phases[name]['ticks']} ticks" for name in phase_names],
                                        textposition="auto"))
        phase_figure.update_layout(title="Deliveries per tick across communication phases",
                                   yaxis_title="Completed deliveries per tick",
                                   paper_bgcolor="#111722", plot_bgcolor="#1A2230", font_color="#EDF1F7",
                                   margin={"l": 10, "r": 10, "t": 45, "b": 10})
        st.plotly_chart(phase_figure, width="stretch", alt="Observed delivery rate during normal, interrupted and restored communication")
        history = model.datacollector.get_model_vars_dataframe().reset_index()
        for name, value in network_metrics.items():
            if isinstance(value, (str, int, float, bool)):
                history[name] = value
        evidence = {"kpis": model.get_kpis(), "network": model.get_network_state(),
                    "history": history.to_dict(orient="records"), "robots": model.get_grid_state()["robots"],
                    "recovery_events": model.recovery_events}
        downloads = st.columns(2)
        downloads[0].download_button("Download run summary (JSON)", json.dumps(evidence, default=str, indent=2),
                                     file_name="hivemine-run.json", mime="application/json", width="stretch")
        downloads[1].download_button("Download run history (CSV)", history.to_csv(index=False),
                                     file_name="hivemine-history.csv", mime="text/csv", width="stretch")

    experiment_live(selected_robot, top_down, speed)

st.markdown("<div style='text-align:center;color:#7d899a;font-size:.78rem;padding:1.25rem 0 .35rem'>HiveMine · GreatUniHack Neptune North · A local simulation of distributed robot teamwork</div>", unsafe_allow_html=True)
