"""HiveMine: a simple live 3D warehouse and multi-robot demonstration."""

from __future__ import annotations

import json
import os
import sys
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
from warehouse_sim.robot_perspective import local_knowledge_snapshot, simulation_comparison
from warehouse_sim.visualization.warehouse_3d import PALETTE, build_warehouse_scene


st.set_page_config(page_title="HiveMine", page_icon="H", layout="wide", initial_sidebar_state="collapsed")

st.html("""
<style>
:root { --hm-bg:#080D19; --hm-panel:#111C2D; --hm-raised:#19283C; --hm-cyan:#48C8EF; --hm-violet:#A78BFA; --hm-green:#34D399; --hm-amber:#FBBF24; --hm-red:#FB7185; --hm-text:#F1F5F9; --hm-muted:#94A3B8; --hm-line:#26364B; }
.stApp { background:var(--hm-bg); color:var(--hm-text); }
[data-testid="stHeader"] { background:transparent; }
.block-container { max-width:1720px; padding-top:1.05rem; padding-bottom:1.5rem; }
h1,h2,h3 { font-family:'Segoe UI',Arial,sans-serif !important; letter-spacing:-.035em; }
p,div,label,button { font-family:'Segoe UI',Arial,sans-serif; }
.hm-topbar { display:flex; align-items:center; gap:.8rem; }
.hm-mark { width:2.65rem;height:2.65rem;display:grid;place-items:center;border-radius:12px;background:#10283A;border:1px solid #245069;color:var(--hm-cyan);font-weight:800;font-size:1.35rem; }
.hm-brand { color:var(--hm-text);font-size:1.7rem;font-weight:800;letter-spacing:-.055em;line-height:1.1; }
.hm-tagline { color:var(--hm-muted);font-size:.88rem;margin-top:.15rem; }
.hm-eyebrow { color:var(--hm-cyan);font-size:.69rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase; }
.hm-hero { border:1px solid var(--hm-line);border-radius:18px;padding:1.2rem 1.4rem;background:var(--hm-panel);margin:.35rem 0 1rem; }
.hm-hero-title { color:var(--hm-text);font:700 clamp(1.25rem,2.3vw,2rem) 'Segoe UI',Arial,sans-serif;letter-spacing:-.045em;margin:.22rem 0; }
.hm-hero-copy { color:#B7C4D5;font-size:.96rem;line-height:1.5;margin:0;max-width:860px; }
.hm-section-head { display:flex;align-items:center;justify-content:space-between;gap:.6rem;color:var(--hm-text);font-weight:700; }
.hm-event { padding:.62rem 0;border-bottom:1px solid rgba(148,163,184,.13);color:#D8E2ED;line-height:1.4;font-size:.84rem; }
.hm-event-time { color:var(--hm-cyan);font-size:.72rem;font-weight:700;margin-right:.5rem;white-space:nowrap; }
.hm-event-tag { display:inline-block;color:var(--hm-muted);font-size:.62rem;font-weight:700;letter-spacing:.08em;margin-right:.45rem; }
.hm-event-tag.network,.hm-event-tag.alert { color:var(--hm-red); }.hm-event-tag.decision{color:var(--hm-violet)}.hm-event-tag.complete,.hm-event-tag.sync{color:var(--hm-green)}
.hm-timeline-row { padding:.65rem .75rem;margin:.32rem 0;border-left:2px solid #41516a;border-radius:0 9px 9px 0;background:var(--hm-panel);color:#D4DBE5;line-height:1.45;font-size:.86rem; }
.hm-timeline-row.partitioned { border-left-color:var(--hm-violet);background:#211D37; }
.hm-network { display:inline-flex;align-items:center;gap:.5rem;border:1px solid var(--hm-line);border-radius:999px;padding:.42rem .75rem;color:#DCE3EC;background:var(--hm-panel);font-size:.82rem; }
.hm-dot { width:.48rem;height:.48rem;border-radius:50%;display:inline-block;background:var(--hm-green); }
.hm-status-dot { width:.55rem;height:.55rem;border-radius:50%;display:inline-block;margin-right:.55rem;background:var(--hm-green);animation:hm-pulse 1.8s ease-out infinite; }
.hm-status-dot.warning { background:var(--hm-amber); }.hm-status-dot.danger { background:var(--hm-red); }
@keyframes hm-pulse { 70% { box-shadow:0 0 0 .42rem rgba(72,200,239,0); } 100% { box-shadow:0 0 0 0 rgba(72,200,239,0); } }
div[data-testid="stMetric"] { border-radius:13px;border-color:var(--hm-line);background:var(--hm-panel);padding:.7rem .85rem; }
div[data-testid="stMetricValue"] { font-family:'Segoe UI',Arial,sans-serif;color:var(--hm-text); }
.stButton>button { min-height:2.45rem;border-radius:10px;transition:border-color .16s ease,background-color .16s ease; }
.stButton>button:hover { border-color:var(--hm-cyan);background:#14263A; }
.stButton>button:focus-visible { outline:2px solid var(--hm-cyan);outline-offset:2px; }
div[role="radiogroup"] label,div[data-testid="stSegmentedControl"] label { border-radius:10px!important; }
[data-testid="stExpander"] { border-radius:13px;border-color:var(--hm-line); }
@media(max-width:900px) { .block-container{padding-left:1rem;padding-right:1rem}.hm-tagline{font-size:.8rem} }
@media(max-width:620px) { .hm-topbar{align-items:flex-start}.hm-brand{font-size:1.45rem}.hm-hero{padding:1rem}.hm-tagline{max-width:38rem} }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after { animation-duration:.01ms!important;transition-duration:.01ms!important;scroll-behavior:auto!important; } }
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
    "EN_ROUTE_TO_CHARGE": "Travelling to charge",
    "WAITING_FOR_CHARGE": "Waiting for a charging dock",
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
    st.session_state.presentation_mode = False
    st.session_state.selected_robot = 0
    st.session_state.explore_mode = "Robot Perspective"
    st.session_state.top_down = False
    st.session_state.show_network_layer = True
    st.session_state.show_routes_layer = True
    st.session_state.show_tasks_layer = True
    st.session_state.activity = [{"tick": 0, "text": "The warehouse is ready. Start the simulation to see the robots at work."}]
    st.session_state.activity_cursor = 0
    st.session_state.last_status = {rid: robot.status for rid, robot in st.session_state.model.robots.items()}
    st.session_state.guided = False
    st.session_state.guided_stage = 0
    st.session_state.guided_actions = set()
    st.session_state.guide_partition_baseline = {"completed": 0, "decisions": 0}
    st.session_state.comparison_results = None
    st.session_state.chaos_baseline = None
    st.session_state.chaos_actions = []
    st.session_state.chaos_last_action = "No disruption yet"
    st.session_state.judge_demo_active = False
    st.session_state.judge_demo_complete = False
    st.session_state.judge_demo_phase = "ready"
    st.session_state.judge_demo_start_tick = 0
    st.session_state.judge_demo_reconciliation_baseline = 0


if "model" not in st.session_state:
    fresh_state()
for _key in ("show_network_layer", "show_routes_layer", "show_tasks_layer"):
    if _key not in st.session_state:
        st.session_state[_key] = True
if "comparison_results" not in st.session_state:
    st.session_state.comparison_results = None
if "explore_mode" not in st.session_state:
    st.session_state.explore_mode = "Robot Perspective"
if "presentation_mode" not in st.session_state:
    st.session_state.presentation_mode = False
if "speed" not in st.session_state:
    st.session_state.speed = 1
for _key, _value in (
    ("chaos_baseline", None), ("chaos_actions", []),
    ("chaos_last_action", "No disruption yet"),
    ("judge_demo_active", False), ("judge_demo_complete", False),
    ("judge_demo_phase", "ready"), ("judge_demo_start_tick", 0),
    ("judge_demo_reconciliation_baseline", 0),
):
    if _key not in st.session_state:
        st.session_state[_key] = _value

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
        return f"{robot or 'A robot'} won delivery {payload.get('task_id')} with a bid of {float(payload.get('bid', 0)):.2f}."
    if action == "auction_bid_calculated":
        return f"{robot or 'A robot'} submitted a bid of {float(payload.get('score', 0)):.2f} for delivery {payload.get('task_id')}."
    if action == "task_complete":
        return f"{robot or 'A robot'} completed a delivery."
    if action == "state_reconciled":
        return f"{robot or 'A robot'} compared notes and updated what it knows."
    if action == "task_conflict_reconciled":
        return f"Robots had overlapping claims on delivery {payload.get('task_id')}. Robot {int(payload.get('winner', 0))+1:02d} kept it by lowest bid, then robot ID."
    if action == "duplicate_claim_detected":
        return "Two disconnected teams chose the same job. HiveMine recorded the overlap for later reconciliation."
    if action == "reconnection_reconciliation_started":
        return "Communication is back. Robots are exchanging updates and checking their job lists."
    if action == "state_sync_completed":
        return f"Robots finished exchanging state updates in {payload.get('duration_ticks', '—')} ticks."
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
    cursor = st.session_state.activity_cursor
    for item in messages:
        if item.get("event_id", 0) <= cursor:
            continue
        text = friendly_message(item)
        if text:
            add_activity(text, int(item.get("tick", model.current_tick)))
    st.session_state.activity_cursor = model._message_log_sequence
    for rid, robot in model.robots.items():
        before = st.session_state.last_status.get(rid)
        if before != robot.status:
            if robot.status == "EN_ROUTE_TO_SHELF":
                add_activity(f"Robot {rid+1:02d} chose a new delivery and is heading to a shelf.")
            elif robot.status == "EN_ROUTE_TO_PACKING":
                add_activity(f"Robot {rid+1:02d} picked its item and is delivering it to packing.")
            elif robot.status == "CHARGING":
                add_activity(f"Robot {rid+1:02d} is charging so it can keep working safely.")
            elif robot.status == "EN_ROUTE_TO_CHARGE":
                add_activity(f"Robot {rid+1:02d} is travelling to its reserved charging dock.")
            elif robot.status == "WAITING_FOR_CHARGE":
                add_activity(f"Robot {rid+1:02d} is waiting for a free charging dock.")
            elif robot.status == "IDLE" and before not in (None, "IDLE"):
                add_activity(f"Robot {rid+1:02d} is ready for another delivery.")
            st.session_state.last_status[rid] = robot.status


def chaos_counter_snapshot(source: WarehouseModel) -> Dict[str, int]:
    metrics = source.get_network_state()["metrics"]
    return {
        "tick": source.current_tick,
        "message_sequence": source._message_log_sequence,
        "partition_tasks_completed": metrics["partition_tasks_completed"],
        "independent_decisions": metrics["independent_decisions"],
        "messages_delayed": metrics["delayed"],
        "messages_dropped": metrics["dropped"],
        "state_sync_received": source.network.state_sync_received,
        "reconciliation_updates": metrics["reconciliations"],
        "reconciliation_runs": len(source.reconciliation_durations),
        "tasks_completed": len(source.completed_task_ids),
    }


def capture_chaos_baseline(source: WarehouseModel | None = None) -> None:
    st.session_state.chaos_baseline = chaos_counter_snapshot(source or model)
    st.session_state.chaos_actions = []
    st.session_state.chaos_last_action = "Experiment started"


def record_chaos_action(label: str, event: Dict[str, Any]) -> None:
    if event.get("error"):
        return
    action = {
        "label": label, "tick": model.current_tick,
        "event_sequence": model._message_log_sequence, "event": event,
    }
    st.session_state.chaos_actions.append(action)
    st.session_state.chaos_last_action = label
    sync_activity()


def update_judge_demo() -> None:
    if not st.session_state.judge_demo_active:
        return
    elapsed = model.current_tick - st.session_state.judge_demo_start_tick
    phase = st.session_state.judge_demo_phase
    if elapsed >= 8 and phase == "normal":
        st.session_state.judge_demo_phase = "negotiation"
        phase = "negotiation"
    if elapsed >= 20 and phase == "negotiation":
        event = network_partition(model, 2)
        record_chaos_action("Judge demo: network partition", event)
        st.session_state.judge_demo_phase = "partition"
        phase = "partition"
    if elapsed >= 45 and phase == "partition":
        event = restore_network(model)
        record_chaos_action("Judge demo: restore network", event)
        st.session_state.judge_demo_phase = "reconciliation"
        phase = "reconciliation"
    if (
        phase == "reconciliation"
        and model.network.partition_count == 1
        and not model._reconciliation_active
        and not model._reconciliation_force_start
        and len(model.reconciliation_durations) > st.session_state.judge_demo_reconciliation_baseline
    ):
        st.session_state.judge_demo_phase = "results"
        st.session_state.judge_demo_active = False
        st.session_state.judge_demo_complete = True
        st.session_state.running = False
        st.rerun()


def advance_model(count: int = 1) -> None:
    for _ in range(count):
        model.step()
        sync_activity()
        update_judge_demo()


def network_label() -> str:
    partition_count = model.network.partition_count
    if partition_count >= len(model.robots):
        label = "Fully disconnected · every robot is isolated"
    elif partition_count > 1:
        label = f"Partitioned · {partition_count} groups working separately"
    else:
        label = "Connected · robots can exchange messages"
    if model.network.latency or model.network.packet_loss:
        label += f" · unstable ({model.network.latency} tick delay, {model.network.packet_loss:.0%} loss)"
    return label


def network_condition() -> tuple[str, str]:
    count = model.network.partition_count
    if count >= len(model.robots):
        return "fully disconnected", "danger"
    if count > 1:
        return "partitioned", "warning"
    if model.network.latency or model.network.packet_loss:
        return "connected · unstable transport", "warning"
    return "connected", "healthy"


def select_home_robot(robot_id: int) -> None:
    st.session_state.selected_robot = robot_id
    st.session_state.view = "Explore"
    st.session_state.main_navigation = "Robot Intelligence"


def set_running(running: bool) -> None:
    st.session_state.running = running
    if running:
        st.session_state.started = True


def add_delivery() -> None:
    stocked_skus = sorted({sku for shelf in model.inventory_agent.shelf_state.values()
                           for sku, quantity in shelf["skus"].items() if quantity > 0})
    if not stocked_skus:
        st.error("There are no stocked products available to add.")
        return
    sku = model.random.choice(stocked_skus)
    model.order_agent.receive_order(sku, 1, "normal")
    model.log_message("CustomerAgent", "OrderAgent", {
        "action": "place_order", "sku": sku, "qty": 1, "priority": "normal"})
    sync_activity()
    st.session_state.started = True
    st.session_state.running = True


def reset_demo() -> None:
    st.session_state.main_navigation = "Mission Control"
    fresh_state()


def navigate_to_chaos_lab() -> None:
    st.session_state.main_navigation = "Chaos Lab"
    st.session_state.view = "Chaos Lab"


def render_robot_detail(robot_id: int) -> None:
    """Compact local-only inspector kept beside the alternate 3D view."""
    robot = model.robots[robot_id]
    local = local_knowledge_snapshot(robot)
    st.markdown(f"### Robot {robot_id+1:02d} ? local state")
    st.write(f"**Position:** {local['position']} ? **Battery:** {local['battery_percent']:.0f}%")
    current = local["current_task"]
    st.write(f"**Current task:** Delivery {current['task_id']}" if current else "**Current task:** None")
    st.write(f"**Tasks in local memory:** {len(local['known_tasks'])}")
    neighbours = local["direct_neighbours"]
    st.write("**Direct neighbours:** " + (
        ", ".join(f"Robot {rid+1:02d}" for rid in neighbours) if neighbours else "None"
    ))
    st.caption("This summary uses the selected robot's state only. Choose Robot Perspective for local/global comparison and its event timeline.")


def _robot_timeline(robot_id: int) -> List[Dict[str, Any]]:
    """Build a timeline from this robot's locally recorded events and receives."""
    robot = model.robots[robot_id]
    timeline: List[Dict[str, Any]] = []
    local_titles = {
        "bid_calculated": "Bid calculated",
        "bid_broadcast": "Bid broadcast attempted",
        "task_selected": "Task selected",
        "state_synchronised": "Local state synchronised",
    }
    for event in robot.local_decision_history:
        kind = event.get("event_type")
        if kind == "communication_neighbors_changed":
            title = "Connection lost" if event.get("lost_neighbors") else "Direct connection changed"
            lost = event.get("lost_neighbors", [])
            added = event.get("added_neighbors", [])
            details = (
                f"Lost direct links to {', '.join(f'Robot {rid+1:02d}' for rid in lost)}"
                if lost else
                f"Direct links now include {', '.join(f'Robot {rid+1:02d}' for rid in added)}"
                if added else "The directly connected peer set changed."
            )
        elif kind == "bid_calculated":
            title = local_titles[kind]
            details = f"Task {event['task_id']} · score {float(event['score']):.3f}"
        elif kind == "bid_broadcast":
            title = local_titles[kind]
            recipients = event.get("recipients", [])
            details = (
                f"Task {event['task_id']} · broadcast addressed to "
                f"{', '.join(f'Robot {rid+1:02d}' for rid in recipients) or 'no robot peers'}"
            )
            details += " · delivery outcome is shown only in the simulator view"
        elif kind == "task_selected":
            title = local_titles[kind]
            details = f"Task {event['task_id']} · local bid {float(event['bid']):.3f}"
        elif kind == "state_synchronised":
            title = local_titles[kind]
            details = f"{event['changes']} local changes · {event['tasks_known']} tasks known"
        else:
            continue
        timeline.append({
            "tick": int(event.get("tick", 0)),
            "sequence": int(event.get("local_sequence", 0)),
            "title": title,
            "details": details,
            "during_partition": bool(event.get("partitioned")),
            "source": "Robot-local event",
        })

    received_titles = {
        "task_announcement": "Task discovered",
        "task_bid": "Bid received",
        "task_claim": "Claim received",
        "task_complete": "Completion update received",
        "task_abandon": "Task release received",
        "state_sync": "State-sync message received",
    }
    for message in robot.local_event_memory:
        message_type = str(message.get("message_type", "")).lower()
        if message_type.startswith("messagetype."):
            message_type = message_type.split(".", 1)[1]
        title = received_titles.get(message_type)
        if title is None:
            continue
        payload = message.get("payload", {})
        task_id = payload.get("task_id")
        details = f"Task {task_id}" if task_id is not None else "Message received and stored locally"
        if message_type == "task_bid" and payload.get("score") is not None:
            details += f" · bid {float(payload['score']):.3f}"
        elif message_type == "task_claim":
            sender_id = payload.get("robot_id")
            if sender_id is not None:
                details += f" · claim from Robot {int(sender_id)+1:02d}"
        timeline.append({
            "tick": int(message.get("received_tick", message.get("created_tick", 0))),
            "sequence": int(message.get("local_sequence", 0)),
            "title": title,
            "details": details,
            "during_partition": bool(message.get("received_during_partition")),
            "source": "Message delivered to this robot",
        })
    for event in model.recovery_events:
        kind = event.get("shock_type")
        if kind not in ("network_partition", "robot_isolation", "network_recovery"):
            continue
        groups = event.get("groups", [])
        if not any(robot_id in group for group in groups):
            continue
        if kind == "network_recovery":
            title = "Network restored"
            details = "The simulator restored peer links; local state-sync messages follow through the network."
            during_partition = False
        else:
            title = "Connection lost"
            group = next((group for group in groups if robot_id in group), [])
            group_names = ", ".join(f"Robot {rid+1:02d}" for rid in group)
            details = (
                f"The simulator graph split into groups. This robot's reachable group: {group_names}. "
                "This is observer-side topology evidence, not an out-of-band message to the robot."
            )
            during_partition = True
        timeline.append({
            "tick": int(event.get("tick", 0)),
            "sequence": -1,
            "title": title,
            "details": details,
            "during_partition": during_partition,
            "source": "Simulator-observed topology event",
        })
    return sorted(timeline, key=lambda item: (item["tick"], item["sequence"]))[-40:]


def robot_network_figure(robot_id: int) -> go.Figure:
    """Small observer-side topology view; node labels include local-memory counts."""
    robot_ids = list(model.robots)
    reachable = model.network.connected_robot_ids(robot_id)
    x_pos = {rid: float(rid) for rid in robot_ids}
    fig = go.Figure()
    for rid in range(len(robot_ids) - 1):
        x0, x1 = x_pos[rid], x_pos[rid + 1]
        if rid + 1 in model.network.neighbors(rid):
            color, dash, width = "#63CEC4", "solid", 4
            status = "Active peer link"
        else:
            color, dash, width = "#EF7884", "dash", 2
            status = "Interrupted peer link"
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[0, 0], mode="lines",
            line={"color": color, "dash": dash, "width": width},
            hovertemplate=f"{status}<extra></extra>", showlegend=False,
        ))
    node_colors = [
        "#B5A0FF" if rid == robot_id else
        "#68D8A2" if rid in reachable else
        "#EF7884"
        for rid in robot_ids
    ]
    task_counts = [len(model.robots[rid].local_task_knowledge) for rid in robot_ids]
    labels = [f"Robot {rid+1:02d}" for rid in robot_ids]
    fig.add_trace(go.Scatter(
        x=[x_pos[rid] for rid in robot_ids], y=[0 for _ in robot_ids],
        mode="markers+text", text=labels, textposition="top center",
        marker={"size": [25 if rid == robot_id else 18 for rid in robot_ids],
                "color": node_colors, "line": {"color": "#F4F6FA", "width": 1}},
        customdata=[[task_counts[rid], "reachable" if rid in reachable else "unreachable"]
                    for rid in robot_ids],
        hovertemplate="%{text}<br>%{customdata[1]} from selected robot"
                      "<br>%{customdata[0]} tasks in this robot's local memory"
                      "<extra>Simulator observer view</extra>",
        showlegend=False,
    ))
    fig.update_layout(
        height=210, margin={"l": 20, "r": 20, "t": 35, "b": 8},
        paper_bgcolor="#111722", plot_bgcolor="#111722",
        font_color="#EDF1F7", xaxis={"visible": False, "range": [-0.5, 4.5]},
        yaxis={"visible": False, "range": [-0.6, 0.7]},
        title="Current robot communication topology",
    )
    return fig


def render_robot_perspective(robot_id: int) -> None:
    robot = model.robots[robot_id]
    local = local_knowledge_snapshot(robot)
    observer = simulation_comparison(model, robot, local)
    local_col, global_col = st.columns(2, gap="medium")
    with local_col:
        with st.container(border=True):
            st.markdown(f"<div class='hm-eyebrow'>Robot-local memory · only what it has received</div><h3>What Robot {robot_id+1:02d} Knows</h3>", unsafe_allow_html=True)
            metrics = st.columns(2)
            metrics[0].metric("Current position", str(local["position"]))
            metrics[1].metric("Battery", f"{local['battery_percent']:.0f}%")
            current = local["current_task"]
            st.write("**Current task:** " + (
                f"Delivery {current['task_id']} · {current['sku']} × {current['quantity']}"
                if current else "None"
            ))
            st.write(f"**Robot status:** {ROBOT_STATES.get(local['status'], local['status'].replace('_', ' ').title())}")
            st.write(f"**Most recent local decision:** {local['last_decision']}")
            st.caption(local["last_decision_reason"])
            neighbours = local["direct_neighbours"]
            st.write("**Direct communication neighbours:** " + (
                ", ".join(f"Robot {rid+1:02d}" for rid in neighbours) if neighbours else "None"
            ))
            st.write(f"**Communication status from its last sensing tick:** {local['communication_status']}")
            st.write(f"**Tasks in this robot's local memory:** {len(local['known_tasks'])}")
            if local["known_tasks"]:
                rows = []
                for task in local["known_tasks"]:
                    bid_text = ", ".join(
                        f"R{rid+1:02d}: {score:.2f}" for rid, score in sorted(task["bids"].items())
                    ) or "—"
                    claim_text = ", ".join(
                        f"R{rid+1:02d}: {score:.2f}" for rid, score in sorted(task["claims"].items())
                    ) or "—"
                    rows.append({
                        "Task": task["task_id"], "SKU": task["sku"],
                        "Qty": task["quantity"], "Priority": task["priority"],
                        "Bids in memory": bid_text, "Claims in memory": claim_text,
                        "Local owner": (f"Robot {task['owner_robot_id']+1:02d}"
                                        if task["owner_robot_id"] is not None else "—"),
                        "Completed locally": task["completed"],
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            else:
                st.caption("No task announcements have reached this robot yet.")
            st.caption(
                "The robot has no direct neighbours right now."
                if not neighbours else
                f"The robot can directly message {len(neighbours)} peer(s); other robots may still be reachable through multi-hop routes."
            )
            with st.expander("Most recent messages received by this robot"):
                messages = local["received_messages"][-8:]
                if not messages:
                    st.caption("No messages have been delivered to this robot yet.")
                else:
                    rows = []
                    for message in reversed(messages):
                        payload = message.get("payload", {})
                        rows.append({
                            "Received at tick": message.get("received_tick", message.get("created_tick")),
                            "From": message.get("sender"),
                            "Type": str(message.get("message_type", "")).replace("_", " ").title(),
                            "Task": str(payload["task_id"]) if payload.get("task_id") is not None else "Not applicable",
                            "Bid": (f"{float(payload['score']):.2f}" if isinstance(payload.get("score"), (int, float)) else "Not applicable"),
                        })
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with global_col:
        with st.container(border=True):
            st.markdown(
                f"<div class='hm-eyebrow'>Simulator observer view · not available to Robot {robot_id+1:02d}</div>"
                f"<h3>What the Simulation Knows</h3>",
                unsafe_allow_html=True,
            )
            st.warning(
                "This global view is for comparison only. It is not copied into the robot's local memory or used by its decisions.",
                icon=":material/visibility:",
            )
            st.write(
                f"**Operating independently of the full fleet:** "
                f"{'Yes' if observer['operating_independently_of_full_fleet'] else 'No'} · "
                f"reachable group size {observer['communication_group_size']}."
            )
            st.write(f"**Robots this robot cannot currently reach:** " + (
                ", ".join(f"Robot {rid+1:02d}" for rid in observer["unreachable_robot_ids"])
                if observer["unreachable_robot_ids"] else "None"
            ))
            st.markdown("**Global task registry**")
            if observer["global_tasks"]:
                st.dataframe(pd.DataFrame([
                    {key: task[key] for key in (
                        "task_id", "sku", "quantity", "priority", "global_status",
                        "assigned_robot_id", "in_selected_robot_memory",
                    )}
                    for task in observer["global_tasks"]
                ]).rename(columns={
                    "task_id": "Global task", "sku": "SKU", "quantity": "Qty",
                    "priority": "Priority", "global_status": "Global status",
                    "assigned_robot_id": "Global assignment",
                    "in_selected_robot_memory": "In robot memory?",
                }), hide_index=True, width="stretch")
                missing_ids = [task["task_id"] for task in observer["global_tasks_not_in_local_memory"]]
                if missing_ids:
                    st.caption(
                        "Global-only task IDs: " + ", ".join(map(str, missing_ids))
                        + ". These offers are not in the robot's local task table; this view does not infer why."
                    )
            else:
                st.caption("The simulation currently has no tasks.")
            if observer["messages_in_transit"]:
                st.markdown("**Messages in transit to this robot**")
                st.dataframe(pd.DataFrame(observer["messages_in_transit"]), hide_index=True, width="stretch")
            if observer["delivered_pending_sense"]:
                st.markdown("**Delivered to its inbox, not yet processed**")
                st.dataframe(pd.DataFrame(observer["delivered_pending_sense"]),
                             hide_index=True, width="stretch")
            if observer["unavailable_messages"]:
                st.markdown("**Updates dropped before reaching it**")
                st.dataframe(pd.DataFrame(observer["unavailable_messages"]), hide_index=True, width="stretch")

    st.markdown("### WHY DID THIS ROBOT CHOOSE THIS TASK?")
    selections = [event for event in local["decision_history"]
                  if event.get("event_type") == "task_selected"]
    if not selections:
        st.info(
            "No task-selection event is recorded in this robot's local decision history, "
            "so there is no supported explanation to show."
        )
    else:
        selection = selections[-1]
        calculation = selection.get("bid_calculation")
        if not calculation:
            st.info(
                f"The robot recorded selecting Task {selection['task_id']}, but this run has no saved "
                "bid-factor record for that selection. No score explanation is inferred."
            )
        else:
            distance = float(calculation["distance"])
            battery_adjustment = float(calculation["battery_adjustment"])
            urgency_adjustment = float(calculation["urgency_adjustment"])
            score = float(calculation["score"])
            computed_score = round(distance + battery_adjustment + urgency_adjustment, 6)
            available_bids = selection.get("available_bids", {})
            eligible = {int(rid): float(value) for rid, value in available_bids.items()}
            if eligible:
                winner = min(eligible, key=lambda rid: (eligible[rid], rid))
                if winner == robot_id:
                    st.success(
                        f"At tick {selection['tick']}, Robot {robot_id+1:02d} selected Task "
                        f"{selection['task_id']}. Its bid was the lowest of {len(eligible)} "
                        "scores available in its local view at selection time."
                    )
                else:
                    st.info("The recorded local bids do not show this robot as the lowest bidder; the score list is shown without claiming a winner.")
            factors = st.columns(4)
            factors[0].metric("Manhattan distance", f"{distance:.2f}")
            factors[1].metric("Battery adjustment", f"+{battery_adjustment:.2f}")
            factors[2].metric("Urgency adjustment", f"{urgency_adjustment:+.2f}")
            factors[3].metric("Recorded bid", f"{score:.3f}")
            st.caption(
                f"Recorded calculation: {distance:.2f} distance + {battery_adjustment:.2f} battery cost "
                f"{urgency_adjustment:+.2f} urgency = {computed_score:.3f}."
            )
            if eligible:
                st.markdown("**Competing bids available to this robot at selection time**")
                st.dataframe(pd.DataFrame([
                    {"Robot": f"Robot {rid+1:02d}", "Bid known locally": score_value,
                     "Selected robot": rid == robot_id}
                    for rid, score_value in sorted(eligible.items())
                ]), hide_index=True, width="stretch")

    lower_left, lower_right = st.columns([1, 1.5], gap="medium")
    with lower_left:
        st.markdown("### Communication reachability")
        st.caption("Simulator observer view. Hover labels show each robot's own local task count; those counts are not shared with the selected robot.")
        st.plotly_chart(robot_network_figure(robot_id), width="stretch",
                        config={"displayModeBar": False},
                        alt="Robot peer topology with active and interrupted links and per-robot local task counts")
    with lower_right:
        st.markdown("### Live decision timeline")
        st.caption("Events come from this robot's received-message memory and local decision trace. Purple marks an event during a simulator-observed partition.")
        timeline = _robot_timeline(robot_id)
        if not timeline:
            st.caption("No received-message or decision events have been captured yet.")
        for event in reversed(timeline):
            partition_class = " partitioned" if event["during_partition"] else ""
            marker = " · PARTITION" if event["during_partition"] else ""
            st.markdown(
                f"<div class='hm-timeline-row{partition_class}'>"
                f"<span class='hm-event-time'>T{event['tick']}</span>"
                f"<b>{escape(event['title'])}{marker}</b><br>"
                f"<span>{escape(event['details'])}</span><br>"
                f"<small>{escape(event['source'])}</small></div>",
                unsafe_allow_html=True,
            )


@st.fragment(run_every=0.7 if st.session_state.running else None)
def robot_perspective_live(robot_id: int, speed: int) -> None:
    if st.session_state.running:
        advance_model(speed)
    render_robot_perspective(robot_id)


def _activity_kind(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("restor", "reconnect", "synchron", "compared notes", "state update")):
        return "sync"
    if any(word in lowered for word in ("completed", "handed over")):
        return "complete"
    if any(word in lowered for word in ("bid", "chose a new delivery", "won delivery", "independent")):
        return "decision"
    if any(word in lowered for word in ("network", "connection", "disconnected", "communication", "partition", "isolated")):
        return "network"
    if any(word in lowered for word in ("conflict", "overlap", "failed", "could not")):
        return "alert"
    return "activity"


def render_activity_panel(limit: int = 6, title: str = "Live intelligence") -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if not st.session_state.activity:
            st.caption("Updates will appear here as the warehouse runs.")
        for item in reversed(st.session_state.activity[-limit:]):
            kind = _activity_kind(item["text"])
            st.markdown(
                f"<div class='hm-event'><span class='hm-event-time'>T{item['tick']}</span>"
                f"<span class='hm-event-tag {kind}'>{kind.upper()}</span>{escape(item['text'])}</div>",
                unsafe_allow_html=True,
            )


def render_network_groups() -> None:
    groups = sorted(model.network.robot_components(), key=lambda group: min(group))
    st.write("**Who can talk right now**")
    with st.container(horizontal=True):
        for index, group in enumerate(groups):
            names = ", ".join(f"Robot {int(node.split('-')[1])+1:02d}" for node in sorted(group))
            with st.container(border=True):
                st.markdown(f"**{'Connected group' if len(groups) > 1 else 'All robots connected'} {index+1 if len(groups) > 1 else ''}**")
                st.write(names)


def render_conflict_history() -> None:
    entries = [entry for entry in model.message_log
               if entry.get("payload", {}).get("action") == "task_conflict_reconciled"]
    if not entries:
        st.caption("No overlapping claims have been recorded in this run.")
        return
    rows = []
    for entry in entries:
        payload = entry["payload"]
        claims = ", ".join(
            f"Robot {int(robot_id)+1:02d}: {float(score):.2f}"
            for robot_id, score in payload.get("claims", {}).items())
        rows.append({"Tick": entry["tick"], "Delivery": payload.get("task_id"),
                     "Competing bids": claims, "Rule": payload.get("rule", "lowest bid, then robot ID"),
                     "Final owner": f"Robot {int(payload.get('winner', 0))+1:02d}"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_metrics(presentation: bool = False) -> None:
    kpis = model.get_kpis()
    with st.container(horizontal=True):
        st.metric("Deliveries completed", kpis["orders_completed"], border=True)
        groups = model.network.robot_components()
        connected = sum(
            1 for rid, robot in model.robots.items()
            if robot.status != "FAILED" and any(len(group) > 1 and f"Robot-{rid}" in group for group in groups)
        )
        st.metric("Connected fleet", f"{connected} / {len(model.robots)}", border=True)
        condition, _ = network_condition()
        st.metric("Network", condition.title(), border=True)


def current_experiment_label() -> str:
    if st.session_state.get("judge_demo_active"):
        return f"Judge demo / {st.session_state.get('judge_demo_phase', 'running').replace('_', ' ')}"
    if st.session_state.get("chaos_actions"):
        return st.session_state.get("chaos_last_action", "Chaos Lab experiment")
    return "Normal operations"


@st.fragment(run_every=0.7 if st.session_state.running else None)
def render_topbar() -> None:
    top_left, top_right = st.columns([2.2, 1], vertical_alignment="center")
    with top_left:
        st.markdown(
            "<div class='hm-topbar'><div class='hm-mark'>H</div><div><div class='hm-brand'>HiveMine</div>"
            "<div class='hm-tagline'>Five robots. One collective intelligence.</div>"
            "<div class='hm-tagline'>When the network breaks, the work continues.</div></div></div>",
            unsafe_allow_html=True,
        )
    with top_right:
        condition, tone = network_condition()
        color = {"healthy": PALETTE["green"], "warning": PALETTE["amber"], "danger": PALETTE["red"]}[tone]
        running_label = "Running" if st.session_state.running else "Paused" if st.session_state.started else "Ready"
        components = model.network.robot_components()
        connected_count = sum(
            1 for rid, robot in model.robots.items()
            if robot.status != "FAILED" and any(f"Robot-{rid}" in group and len(group) > 1 for group in components)
        )
        st.markdown(
            f"<div style='text-align:right'><div><span class='hm-network'><i class='hm-dot' style='background:{color}'></i>{escape(condition.title())}</span></div>"
            f"<div class='hm-tagline' style='margin-top:.45rem'>{running_label} | Tick {model.current_tick} | {connected_count}/{len(model.robots)} connected</div>"
            f"<div class='hm-tagline'>Experiment: {escape(current_experiment_label())}</div></div>",
            unsafe_allow_html=True,
        )


def render_fleet_panel() -> None:
    with st.container(border=True):
        st.markdown("**Robot fleet**")
        groups = model.network.robot_components()
        for rid, robot in model.robots.items():
            peers = model.network.neighbors(rid)
            peer_names = list(peers)
            online = robot.status != "FAILED" and bool(peer_names)
            if robot.status == "FAILED":
                connection = "Offline"
            elif online:
                group = next((component for component in groups if f"Robot-{rid}" in component), set())
                connection = f"Connected / group {min((int(node.split('-')[1]) for node in group if node.startswith('Robot-')), default=rid)+1}"
            else:
                connection = "Isolated"
            task = getattr(robot, "current_task", None)
            task_id = getattr(task, "task_id", None) if task is not None else None
            task_text = f"Delivery {task_id}" if task_id is not None else "No active delivery"
            battery = float(getattr(robot, "battery", 0))
            tone = "danger" if robot.status == "FAILED" else "warning" if not online else "healthy"
            with st.container(border=True):
                st.markdown(
                    f"<span class='hm-status-dot {tone}'></span><b>Robot {rid+1:02d}</b>"
                    f"<span style='float:right;color:#94A3B8'>{battery:.0f}% battery</span>",
                    unsafe_allow_html=True,
                )
                st.caption(f"{task_text}  |  {connection}")
                st.caption(ROBOT_STATES.get(robot.status, robot.status.replace("_", " ").title()))
                st.button("Inspect robot", key=f"fleet_inspect_{rid}", width="stretch",
                          on_click=select_home_robot, args=(rid,))


def render_scene_layers(presentation: bool = False) -> None:
    """Offer simple toggles for the dynamic layers in the warehouse view."""
    if presentation:
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.checkbox("Robot routes", key="show_routes_layer")
        st.checkbox("Network links", key="show_network_layer")
        st.checkbox("Delivery tasks", key="show_tasks_layer")


def warehouse_figure(selected_robot: int, top_down: bool) -> go.Figure:
    return build_warehouse_scene(
        model, selected_robot, top_down,
        show_network=st.session_state.show_network_layer,
        show_routes=st.session_state.show_routes_layer,
        show_tasks=st.session_state.show_tasks_layer)


def run_comparison_scenarios(seed: int = 42, ticks: int = 120) -> Dict[str, Dict[str, Any]]:
    """Run identical seeded demand for normal, outage, and recovery scenarios."""
    results: Dict[str, Dict[str, Any]] = {}
    reference_workload = None
    for scenario in ("Normal network", "Network partition", "After recovery"):
        comparison_model = WarehouseModel(seed=seed, persist_log=False)
        for tick in range(1, ticks + 1):
            if tick == 41 and scenario != "Normal network":
                network_partition(comparison_model, 2)
            if tick == 81 and scenario == "After recovery":
                restore_network(comparison_model)
            comparison_model.step()
        kpis = comparison_model.get_kpis()
        workload = [(task.arrival_tick, task.sku, task.qty, task.priority)
                    for task in comparison_model.order_agent.all_tasks]
        if reference_workload is None:
            reference_workload = workload
        elif workload != reference_workload:
            raise RuntimeError("Seeded comparison generated different customer workloads")
        network_metrics = comparison_model.get_network_state()["metrics"]
        results[scenario] = {
            "Tasks created": kpis["total_tasks_created"],
            "Tasks completed": kpis["orders_completed"],
            "Tasks remaining": kpis["tasks_remaining"],
            "Active robot utilization (%)": kpis["average_active_robot_utilisation_pct"],
            "Avg completion time (ticks)": kpis["average_task_time"],
            "Completed during partition": network_metrics["partition_tasks_completed"],
            "Independent decisions": network_metrics["independent_decisions"],
            "Messages dropped": network_metrics["dropped"],
            "Avg message delay (ticks)": network_metrics["average_message_delay_ticks"],
            "Reconciliation duration (ticks)": (comparison_model.reconciliation_durations[-1]
                                                 if comparison_model.reconciliation_durations else None),
        }
    return results


def render_comparison() -> None:
    with st.expander("Compare the same seeded workload across network conditions"):
        st.caption("Runs three independent 120-tick simulations with seed 42 and identical generated customer demand. The partition starts at tick 41; recovery starts at tick 81. Outcomes are measured, not prefilled.")
        if st.button("Run comparable scenarios", key="run_comparison"):
            with st.spinner("Running three seeded simulation scenarios…"):
                st.session_state.comparison_results = run_comparison_scenarios(seed=42, ticks=120)
        results = st.session_state.comparison_results
        if results:
            table = pd.DataFrame(results).T
            st.dataframe(table, width="stretch")
            chart = go.Figure(go.Bar(
                x=list(results),
                y=[results[name]["Tasks completed"] for name in results],
                marker_color=[PALETTE["blue"], PALETTE["purple"], PALETTE["green"]],
                text=[f"{results[name]['Tasks completed']} completed · {results[name]['Tasks remaining']} remaining"
                      for name in results], textposition="auto"))
            chart.update_layout(title="Observed completed deliveries after 120 ticks",
                                yaxis_title="Deliveries", paper_bgcolor="#111722",
                                plot_bgcolor="#1A2230", font_color="#EDF1F7",
                                margin={"l": 10, "r": 10, "t": 45, "b": 10})
            st.plotly_chart(chart, width="stretch",
                            alt="Measured completed deliveries under normal, partitioned, and recovered network scenarios")


@st.fragment(run_every=0.7 if st.session_state.running else None)
def home_live(selected_robot: int, top_down: bool, speed: int, presentation: bool = False) -> None:
    if st.session_state.running:
        advance_model(speed)
    render_metrics(presentation=presentation)
    scene, side = st.columns([2.35, 1], gap="medium")
    with scene:
        with st.container(border=True):
            st.markdown("**Mission Control / live fleet view**" if presentation else "**Live warehouse**")
            if not presentation:
                st.caption("Drag to rotate. Scroll to zoom. Right-drag to pan.")
            render_scene_layers(presentation=presentation)
            fig = warehouse_figure(selected_robot, top_down)
            if presentation:
                fig.update_layout(height=690)
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": True, "responsive": True}, alt="Interactive 3D warehouse with live robot positions, routes, shelves and communication links")
    with side:
        if presentation:
            render_activity_panel(limit=4, title="Recent activity")
            with st.container(border=True):
                st.markdown("**Network resilience controls**")
                st.caption("Open Chaos Lab for live failure and restoration controls.")
                st.button("Open Chaos Lab", key="presentation_open_chaos", width="stretch",
                          icon=":material/hub:", on_click=navigate_to_chaos_lab)
        else:
            render_fleet_panel()
            render_activity_panel()


@st.fragment(run_every=0.7 if st.session_state.running else None)
def explore_live(selected_robot: int, top_down: bool, speed: int) -> None:
    if st.session_state.running:
        advance_model(speed)
    render_metrics()
    scene, detail = st.columns([1.8, 1], gap="medium")
    with scene:
        with st.container(border=True):
            st.markdown("**Five robots, one shared goal**")
            render_scene_layers()
            fig = warehouse_figure(selected_robot, top_down)
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": True, "responsive": True}, alt="Three-dimensional warehouse showing the selected robot and its live route")
    with detail:
        with st.container(border=True):
            render_robot_detail(selected_robot)
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
            st.caption("Teal links are healthy. Amber links have unstable delivery. Red dashed links are interrupted; partitioned groups use distinct colours.")
            render_scene_layers()
            fig = warehouse_figure(selected_robot, top_down)
            st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "scrollZoom": True, "responsive": True}, alt="Live warehouse showing robot routes and links that are active or interrupted")
    with side:
        with st.container(border=True):
            st.subheader("Communication")
            condition, tone = network_condition()
            color = {"healthy": PALETTE["green"], "warning": PALETTE["amber"], "danger": PALETTE["red"]}[tone]
            st.markdown(f"<span class='hm-network'><i class='hm-dot' style='background:{color}'></i>{escape(condition.title())}</span>", unsafe_allow_html=True)
            render_network_groups()
            kpis = model.get_network_state()["metrics"]
            st.caption(f"{kpis['active_connections']} active links · {kpis['delivered']} messages delivered · {kpis['dropped']} could not get through")
        render_activity_panel()


def next_guided_stage() -> None:
    stage = min(6, st.session_state.guided_stage + 1)
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
    elif stage == 5:
        restore_network(model)
        st.session_state.running = True
        advance_model(4)
    elif stage == 6:
        advance_model(8)
        st.session_state.running = False
    st.session_state.guided_actions.add(stage)


GUIDE_STAGES = [
    ("Normal operation", "Five autonomous robots are working together to fulfil warehouse orders."),
    ("Choosing a robot for each job", "Each robot scores the work it knows about and negotiates with robots it can reach."),
    ("Communication interrupted", "The connection is split into two groups. Messages cannot cross the broken link."),
    ("Working independently", "Both groups keep using their local task lists and continue making decisions."),
    ("Conflicting information", "Inspect any overlapping claims observed in this run. If none occurred, HiveMine reports that rather than creating a fake conflict."),
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
        st.markdown(f"<div class='hm-eyebrow'>Guided walkthrough · Step {stage+1} of {len(GUIDE_STAGES)}</div><div class='hm-hero-title'>{escape(GUIDE_STAGES[stage][0])}</div><p class='hm-hero-copy'>{escape(GUIDE_STAGES[stage][1])}</p>", unsafe_allow_html=True)
        if stage == 3:
            if st.button("Continue for 20 simulation ticks", key="guide_continue", width="stretch"):
                advance_model(20)
        if stage == 4:
            st.markdown("**Observed claim conflicts**")
            render_conflict_history()
        if stage == 6:
            base = st.session_state.guide_partition_baseline
            network_metrics = model.get_network_state()["metrics"]
            st.success(f"During communication failure, robots completed {model.partition_tasks_completed - base['completed']} deliveries and made {model.partition_decisions - base['decisions']} independent job choices.")
            st.caption(f"This run also observed {network_metrics['conflicts_detected']} overlapping job claims and {network_metrics['reconciliations']} local state updates after reconnection.")
        controls = st.columns(4)
        if controls[0].button("Previous", disabled=stage == 0, key="guide_previous", width="stretch"):
            st.session_state.guided_stage = max(0, stage - 1)
            st.rerun()
        if controls[1].button("Next", disabled=stage == 6, key="guide_next", type="primary", width="stretch"):
            next_guided_stage()
            st.rerun()
        if controls[2].button("Pause" if st.session_state.running else "Resume", key="guide_pause", width="stretch"):
            st.session_state.running = not st.session_state.running
            st.rerun()
        if controls[3].button("Exit walkthrough", key="guide_exit", width="stretch"):
            st.session_state.guided = False
            st.rerun()


def start_judge_demo() -> None:
    """Start a repeatable, tick-driven demo without sleeping or blocking."""
    demo_model = WarehouseModel(seed=42, persist_log=False)
    st.session_state.model = demo_model
    st.session_state.activity = [{
        "tick": 0, "text": "Judge demo started: normal warehouse operation is live."
    }]
    st.session_state.activity_cursor = 0
    st.session_state.last_status = {rid: robot.status for rid, robot in demo_model.robots.items()}
    st.session_state.started = True
    st.session_state.running = True
    st.session_state.judge_demo_start_tick = 0
    st.session_state.judge_demo_phase = "normal"
    st.session_state.judge_demo_active = True
    st.session_state.judge_demo_complete = False
    st.session_state.judge_demo_reconciliation_baseline = len(demo_model.reconciliation_durations)
    st.session_state.chaos_actions = []
    st.session_state.chaos_last_action = "Judge demo started"
    st.session_state.chaos_baseline = chaos_counter_snapshot(demo_model)


def demo_phase_copy() -> tuple[str, str, str]:
    phase = st.session_state.judge_demo_phase
    labels = {
        "ready": ("Ready", "A fixed-seed run will walk through normal work, network failure and recovery.", "healthy"),
        "normal": ("Normal operation", "Five robots are receiving work and moving through the warehouse.", "healthy"),
        "negotiation": ("Robots negotiating", "Robots are exchanging task announcements and bids.", "healthy"),
        "partition": ("Network partition", "The network is split. Robots continue with their local task knowledge.", "warning"),
        "reconciliation": ("Restoring and synchronising", "The network is back. Waiting for actual state-sync messages to arrive.", "warning"),
        "results": ("Measured results", "The run ended after state reconciliation completed or the network returned to one group.", "healthy"),
    }
    return labels.get(phase, labels["ready"])


def render_judge_demo() -> None:
    title, description, tone = demo_phase_copy()
    demo_running = st.session_state.judge_demo_active and st.session_state.running
    state_label = "LIVE" if demo_running else "PAUSED" if st.session_state.judge_demo_active else "COMPLETE" if st.session_state.judge_demo_complete else "READY"
    with st.container(border=True):
        left, right = st.columns([2.3, 1], vertical_alignment="center")
        with left:
            st.markdown(f"<div class='hm-eyebrow'>Judge sabotage mode · {state_label}</div><div class='hm-hero-title'>{escape(title)}</div><p class='hm-hero-copy'>{escape(description)}</p>", unsafe_allow_html=True)
        with right:
            if not st.session_state.judge_demo_active and not st.session_state.judge_demo_complete:
                if st.button("START 60-SECOND JUDGE DEMO", key="judge_demo_start", type="primary", width="stretch", icon=":material/bolt:"):
                    start_judge_demo()
                    st.rerun()
            else:
                controls = st.columns(2)
                if st.session_state.judge_demo_active:
                    if controls[0].button("Pause demo" if demo_running else "Continue demo",
                                           key="judge_demo_pause", width="stretch"):
                        st.session_state.running = not st.session_state.running
                        st.rerun()
                if controls[1 if st.session_state.judge_demo_active else 0].button(
                    "Replay demo", key="judge_demo_replay", width="stretch"
                ):
                    start_judge_demo()
                    st.rerun()
        if st.session_state.judge_demo_active or st.session_state.judge_demo_complete:
            state_text = f"<span class='hm-status-dot {tone}'></span><b>{escape(title)}</b> · simulation tick {model.current_tick}"
            st.markdown(state_text, unsafe_allow_html=True)
            demo_metrics = model.get_network_state()["metrics"]
            st.caption(
                f"Observed so far: {model.partition_tasks_completed} deliveries completed while disconnected · "
                f"{demo_metrics['independent_decisions']} independent decisions · "
                f"{model.network.state_sync_received} state-sync messages received."
            )


def _experiment_values() -> Dict[str, int]:
    current = chaos_counter_snapshot(model)
    baseline = st.session_state.chaos_baseline or current
    return {
        "tasks_outage": max(0, current["partition_tasks_completed"] - baseline["partition_tasks_completed"]),
        "independent": max(0, current["independent_decisions"] - baseline["independent_decisions"]),
        "messages": max(0, current["messages_delayed"] - baseline["messages_delayed"])
                    + max(0, current["messages_dropped"] - baseline["messages_dropped"]),
        "sync": max(0, current["state_sync_received"] - baseline["state_sync_received"]),
        "reconciliations": max(0, current["reconciliation_updates"] - baseline["reconciliation_updates"]),
    }


def render_chaos_metrics() -> None:
    metrics = model.get_network_state()["metrics"]
    current = chaos_counter_snapshot(model)
    baseline = st.session_state.chaos_baseline or current
    delta = _experiment_values()
    cumulative_messages = metrics["delayed"] + metrics["dropped"]
    cols = st.columns(4)
    cols[0].metric("Tasks completed during outage", delta["tasks_outage"],
                   delta=f"Experiment · {metrics['partition_tasks_completed']} cumulative")
    cols[1].metric("Independent decisions", delta["independent"],
                   delta=f"Experiment · {metrics['independent_decisions']} cumulative")
    cols[2].metric("Messages delayed or dropped", delta["messages"],
                   delta=f"Experiment · {cumulative_messages} cumulative")
    cols[3].metric("Reconciliation updates completed", delta["sync"],
                   delta=f"Experiment · {current['state_sync_received']} cumulative syncs")
    st.caption(
        f"Experiment baseline captured at tick {baseline['tick']}. "
        f"State merges with observed changes: {delta['reconciliations']} in this experiment "
        f"({metrics['reconciliations']} cumulative). Counts are taken from the live model and network."
    )


def build_chaos_report() -> Dict[str, Any]:
    """Build an evidence report from recorded shocks and actual task/network state."""
    baseline = st.session_state.chaos_baseline or chaos_counter_snapshot(model)
    actions = list(st.session_state.chaos_actions)
    intervals: List[tuple[int, int, int, int]] = []
    open_outage: tuple[int, int] | None = None
    affected: set[int] = set()
    failures: List[Dict[str, Any]] = []
    for action in actions:
        event = action["event"]
        kind = event.get("shock_type")
        tick = int(action.get("tick", event.get("tick", 0)))
        event_sequence = int(action.get("event_sequence", 0))
        if kind in ("network_partition", "robot_isolation"):
            if open_outage is None:
                open_outage = (tick, event_sequence)
        elif kind == "network_recovery" and open_outage is not None:
            intervals.append((open_outage[0], tick, open_outage[1], event_sequence))
            open_outage = None
        if kind in ("network_partition", "robot_isolation", "network_recovery"):
            for group in event.get("groups", []):
                affected.update(int(rid) for rid in group)
            if "robot_id" in event:
                affected.add(int(event["robot_id"]))
        elif kind == "network_conditions":
            affected.update(model.robots)
        elif kind == "blocked_aisle":
            affected.update(int(rid) for rid in event.get("affected_robots", [])
                            if isinstance(rid, int))
        elif kind == "robot_failure":
            affected.add(int(event["robot_id"]))
        failures.append({
            "action": action["label"],
            "tick": tick,
            "shock_type": kind,
            "details": {key: value for key, value in event.items() if key != "shock_type"},
        })
    if open_outage is not None:
        intervals.append((open_outage[0], model.current_tick, open_outage[1],
                          model._message_log_sequence))

    completed_in_outage = []
    completed_since_start = []
    unresolved = []
    continued: Dict[int, Dict[str, Any]] = {}
    for entry in model.message_log:
        payload = entry.get("payload", {})
        event_sequence = int(entry.get("event_id", 0))
        tick = int(entry.get("tick", -1))
        action_name = payload.get("action")
        if (
            action_name == "task_complete"
            and int(payload.get("task_id", -1)) in model.completed_task_ids
        ):
            task_id = int(payload["task_id"])
            record = {"task_id": task_id, "completed_tick": tick}
            if event_sequence > int(baseline.get("message_sequence", 0)):
                completed_since_start.append(record)
            if any(start_tick <= tick <= end_tick and start_seq < event_sequence <= end_seq
                   for start_tick, end_tick, start_seq, end_seq in intervals):
                completed_in_outage.append(record)
                task = next((item for item in model.order_agent.all_tasks if item.task_id == task_id), None)
                continued.setdefault(task_id, {
                    "task_id": task_id,
                    "robot_id": int(payload["robot_id"]) if "robot_id" in payload else (
                        task.assigned_robot if task and task.assigned_robot >= 0 else None
                    ),
                    "claim_tick": None,
                    "completed_during_outage": True,
                })
                continued[task_id]["completed_during_outage"] = True
        if (
            action_name == "distributed_task_claim"
            and any(start_tick <= tick <= end_tick and start_seq < event_sequence <= end_seq
                    for start_tick, end_tick, start_seq, end_seq in intervals)
        ):
            task_id = int(payload["task_id"])
            continued[task_id] = {
                "task_id": task_id,
                "robot_id": int(payload["robot_id"]),
                "claim_tick": tick,
                "completed_during_outage": False,
            }
    for task in model.order_agent.all_tasks:
        if task.task_id in model.completed_task_ids:
            continue
        unresolved.append({
            "task_id": task.task_id,
            "status": task.status,
            "assigned_robot": task.assigned_robot,
            "arrival_tick": task.arrival_tick,
        })

    values = _experiment_values()
    reconciliation_updates = []
    for entry in model.message_log:
        payload = entry.get("payload", {})
        if (
            payload.get("action") != "state_reconciled"
            or int(entry.get("event_id", 0)) <= int(baseline.get("message_sequence", 0))
        ):
            continue
        sender = str(entry.get("from_agent", ""))
        robot_id = int(sender.split("-")[1]) if sender.startswith("Robot-") else None
        reconciliation_updates.append({
            "tick": int(entry["tick"]),
            "robot_id": robot_id,
            "changes": int(payload.get("changes", 0)),
            "tasks_known": int(payload.get("tasks_known", 0)),
        })
    had_network_outage = bool(intervals)
    network_ready = (
        model.network.partition_count == 1
        and not model._reconciliation_active
        and not model._reconciliation_force_start
        and (
            not had_network_outage
            or len(model.reconciliation_durations) > int(baseline.get("reconciliation_runs", 0))
        )
    )
    return {
        "seed": model.seed,
        "generated_at_tick": model.current_tick,
        "experiment_started_at_tick": baseline["tick"],
        "what_failed": failures,
        "affected_robots": sorted(affected),
        "tasks_completed_during_outage": completed_in_outage,
        "tasks_continued_during_outage": sorted(continued.values(), key=lambda item: item["task_id"]),
        "tasks_completed_since_experiment_start": completed_since_start,
        "tasks_still_open": unresolved[:30],
        "additional_open_tasks_omitted": max(0, len(unresolved) - 30),
        "network_recovered_and_reconciled": network_ready,
        "state_sync_messages_received_this_experiment": values["sync"],
        "state_sync_messages_received_cumulative": model.network.state_sync_received,
        "state_merges_with_changes_this_experiment": values["reconciliations"],
        "state_merges_with_changes_cumulative": model.network.reconciliation_count,
        "reconciliation_updates": reconciliation_updates,
        "information_synchronized": [
            "Locally learned task announcements and completion state",
            "Peer bids and claims attached to those tasks",
        ] if values["sync"] else [],
        "messages_delayed_or_dropped_this_experiment": values["messages"],
        "messages_delayed_or_dropped_cumulative": (
            model.network.counters["delayed"] + model.network.counters["dropped"]
        ),
    }


def start_chaos_action(label: str, event: Dict[str, Any]) -> None:
    if event.get("error"):
        st.error(event["error"])
        return
    record_chaos_action(label, event)
    st.session_state.started = True
    st.session_state.running = True
    st.rerun()


def render_chaos_controls() -> None:
    st.markdown("### Break something")
    st.caption("Each control changes the running model. Physical safety and inventory remain shared services.")
    split, isolate, blackout, restore = st.columns(4)
    split_size = split.selectbox("Group A size", range(1, len(model.robots)), index=1, key="chaos_split_size")
    if split.button("Split Network", key="chaos_split", width="stretch"):
        start_chaos_action("Split Network", network_partition(model, split_size))
    isolate_id = isolate.selectbox("Robot to isolate", list(model.robots),
                                   format_func=lambda rid: f"Robot {rid+1:02d}", key="chaos_isolate_id")
    if isolate.button("Isolate Robot", key="chaos_isolate", width="stretch"):
        start_chaos_action("Isolate Robot", isolate_robot(model, isolate_id))
    if blackout.button("Total Blackout", key="chaos_blackout", type="primary", width="stretch"):
        start_chaos_action("Total Blackout", disconnect_all_robots(model))
    if restore.button("Restore Network", key="chaos_restore", width="stretch"):
        start_chaos_action("Restore Network", restore_network(model))

    latency_col, loss_col, unstable_col = st.columns([1, 1, 1.4])
    latency = latency_col.slider("Latency (ticks)", 0, 8, model.network.latency, key="chaos_latency")
    loss = loss_col.slider("Packet loss", 0.0, 0.8, model.network.packet_loss, 0.05, key="chaos_loss")
    if unstable_col.button("Apply Unstable Network", key="chaos_unstable", width="stretch"):
        start_chaos_action("Unstable Network", set_network_conditions(model, latency, loss))

    aisle_col, failure_col, reserved_col = st.columns([1.4, 1, 1])
    unavailable = set(model.shelf_locations) | {model.packing_station, *model.charging_docks} | model.blocked_cells
    free_cells = [(x, y) for x in range(model.grid_width) for y in range(model.grid_height)
                  if (x, y) not in unavailable]
    aisle_cell = aisle_col.selectbox(
        "Aisle cell to block", free_cells,
        index=min(125, len(free_cells) - 1) if free_cells else None,
        format_func=lambda pos: f"Cell ({pos[0]}, {pos[1]})",
        key="chaos_aisle_cell", disabled=not free_cells,
    )
    if aisle_col.button("Block Aisle", key="chaos_block_aisle", width="stretch",
                        disabled=not free_cells):
        start_chaos_action("Block Aisle", block_cell(model, aisle_cell))
    available_robots = [rid for rid, robot in model.robots.items() if robot.status != "FAILED"]
    failure_id = failure_col.selectbox("Robot to fail", available_robots or list(model.robots),
                                       format_func=lambda rid: f"Robot {rid+1:02d}", key="chaos_failure_id",
                                       disabled=not available_robots)
    if failure_col.button("Robot Failure", key="chaos_robot_failure", width="stretch",
                          disabled=not available_robots):
        start_chaos_action("Robot Failure", kill_robot(model, failure_id))
    reserved_col.markdown("**Live experiment**")
    reserved_col.caption(f"Last action: {st.session_state.chaos_last_action}")
    if reserved_col.button("Start new measurement", key="chaos_new_measurement", width="stretch"):
        capture_chaos_baseline()
        st.rerun()


def render_after_action_report() -> None:
    report = build_chaos_report()
    with st.expander("After-action report", expanded=bool(st.session_state.chaos_actions)):
        if not report["what_failed"]:
            st.info("No disruption has been injected yet. Trigger a control above to create an evidence-based report.")
        else:
            st.markdown(f"**What failed:** {len(report['what_failed'])} recorded disruption action(s).")
            st.write(", ".join(dict.fromkeys(item["action"] for item in report["what_failed"])))
            affected = report["affected_robots"]
            st.markdown("**Robots affected:** " + (
                ", ".join(f"Robot {rid+1:02d}" for rid in affected) if affected else "No robot IDs recorded."
            ))
            outage_tasks = report["tasks_completed_during_outage"]
            continued = report["tasks_continued_during_outage"]
            st.markdown(
                f"**Tasks continued during communication outages:** {len(continued)} observed claims; "
                f"{len(outage_tasks)} deliveries completed."
            )
            if continued:
                st.caption("Delivery IDs: " + ", ".join(str(item["task_id"]) for item in continued))
            st.markdown(f"**Still open:** {len(report['tasks_still_open'])} tasks at tick {model.current_tick}; statuses are included in the JSON report.")
            st.markdown(
                f"**Synchronised after recovery:** {report['state_sync_messages_received_this_experiment']} "
                f"state-sync messages received and {report['state_merges_with_changes_this_experiment']} "
                f"state merges with changes during this experiment."
            )
            if report["information_synchronized"]:
                st.caption("Sync payload categories: " + "; ".join(report["information_synchronized"]))
            if report["reconciliation_updates"]:
                merged = ", ".join(
                    f"Robot {item['robot_id']+1:02d} +{item['changes']} changes"
                    for item in report["reconciliation_updates"]
                    if item["robot_id"] is not None
                )
                if merged:
                    st.caption("Robots that merged new local state: " + merged)
            st.caption("Recovery status: " + ("network connected and reconciliation finished" if report["network_recovered_and_reconciled"]
                                               else "a disruption or reconciliation is still in progress"))
        st.download_button(
            "Download after-action JSON",
            json.dumps(report, default=str, indent=2),
            file_name="hivemine-chaos-report.json",
            mime="application/json",
            key="chaos_report_download",
            width="stretch",
        )


def render_chaos_lab(selected_robot: int, top_down: bool, speed: int) -> None:
    if st.session_state.chaos_baseline is None:
        capture_chaos_baseline()
    status, tone = network_condition()
    st.markdown(
        "<section class='hm-hero'><div class='hm-eyebrow'>HiveMine · Chaos Lab</div>"
        "<div class='hm-hero-title'>Try to break our network. Watch the robots keep working.</div>"
        "<p class='hm-hero-copy'>Disrupt communications or the warehouse itself, then inspect what the robots actually did and what they synchronised after recovery.</p></section>",
        unsafe_allow_html=True,
    )
    render_judge_demo()
    render_chaos_metrics()
    status_label = status.upper()
    st.markdown(
        f"<div class='hm-network'><span class='hm-status-dot {tone}'></span>"
        f"<b>Simulation status · {status_label}</b> · {escape(network_label())}</div>",
        unsafe_allow_html=True,
    )
    selected_robot = st.selectbox(
        "Highlight robot in the 3D view", list(model.robots),
        index=min(st.session_state.selected_robot, len(model.robots) - 1),
        format_func=lambda rid: f"Robot {rid+1:02d}",
        key="chaos_view_robot",
    )
    st.session_state.selected_robot = selected_robot
    st.write("")
    render_chaos_controls()
    render_after_action_report()
    with st.expander("Additional disruptions and scenario analysis"):
        optional = st.columns(3)
        alive = [rid for rid, robot in model.robots.items() if robot.status != "FAILED"]
        optional_id = optional[0].selectbox("Force low battery", alive or list(model.robots),
                                            format_func=lambda rid: f"Robot {rid+1:02d}",
                                            key="chaos_optional_battery", disabled=not alive)
        if optional[0].button("Drain battery", key="chaos_optional_battery_btn", disabled=not alive):
            start_chaos_action("Battery drain", force_drain(model, optional_id))
        if optional[1].button("Add urgent deliveries", key="chaos_optional_orders"):
            start_chaos_action("Urgent order flood", flood_urgent_orders(model, 8))
        if optional[2].button("Create a traffic hold-up", key="chaos_optional_deadlock"):
            start_chaos_action("Traffic hold-up", inject_deadlock(model))
        render_comparison()
        network_metrics = model.get_network_state()["metrics"]
        kpis = model.get_kpis()
        st.markdown("**Cumulative simulation and network detail**")
        detail_cols = st.columns(4)
        detail_cols[0].metric("Deliveries completed", kpis["orders_completed"])
        detail_cols[1].metric("Deliveries open", kpis["tasks_remaining"])
        detail_cols[2].metric("Active peer links", network_metrics["active_connections"])
        detail_cols[3].metric("Observed state merges", network_metrics["reconciliations"])
        st.caption(
            f"{network_metrics['delivered']} messages delivered · "
            f"{network_metrics['dropped']} dropped · {network_metrics['delayed']} delayed · "
            f"{network_metrics['conflicts_detected']} overlapping claims observed · "
            f"{network_metrics['conflicts_resolved']} resolved."
        )
        with st.expander("Observed claim conflicts"):
            render_conflict_history()
        phases = model.phase_metrics
        phase_names = list(phases)
        phase_figure = go.Figure(go.Bar(
            x=phase_names,
            y=[phases[name]["tasks_completed"] / max(1, phases[name]["ticks"]) for name in phase_names],
            marker_color=[PALETTE["blue"], PALETTE["purple"], PALETTE["green"]],
            text=[f"{phases[name]['tasks_completed']} deliveries / {phases[name]['ticks']} ticks"
                  for name in phase_names],
            textposition="auto",
        ))
        phase_figure.update_layout(
            title="Observed deliveries per tick across network phases",
            yaxis_title="Deliveries per tick", paper_bgcolor="#111722",
            plot_bgcolor="#1A2230", font_color="#EDF1F7",
            margin={"l": 10, "r": 10, "t": 45, "b": 10},
        )
        st.plotly_chart(phase_figure, width="stretch",
                        alt="Measured deliveries per tick during normal, interrupted and restored communication")
        history = model.datacollector.get_model_vars_dataframe().reset_index()
        for name, value in network_metrics.items():
            if isinstance(value, (str, int, float, bool)):
                history[name] = value
        evidence = {"chaos_report": build_chaos_report(), "kpis": model.get_kpis(),
                    "network": model.get_network_state(), "history": history.to_dict(orient="records"),
                    "robots": model.get_grid_state()["robots"], "recovery_events": model.recovery_events}
        export_cols = st.columns(2)
        export_cols[0].download_button(
            "Download full run evidence (JSON)", json.dumps(evidence, default=str, indent=2),
            file_name="hivemine-run-evidence.json", mime="application/json",
            key="chaos_full_evidence", width="stretch",
        )
        export_cols[1].download_button(
            "Download run history (CSV)", history.to_csv(index=False),
            file_name="hivemine-history.csv", mime="text/csv",
            key="chaos_history_csv", width="stretch",
        )
    experiment_live(selected_robot, top_down, speed)


def render_communication_popover() -> None:
    condition, _ = network_condition()
    label = f"Communication · {condition.title()}"
    with st.popover(label, icon=":material/hub:"):
        st.caption(network_label())
        st.caption("Use the Chaos Lab for network disruptions, warehouse shocks and recovery controls.")
        st.button("Open Chaos Lab", key="popover_open_chaos", width="stretch",
                  on_click=navigate_to_chaos_lab)


# Header and persistent three-area navigation.
nav_aliases = {"Home": "Mission Control", "Explore": "Robot Intelligence", "Experiment": "Chaos Lab",
               "Mission Control": "Mission Control", "Robot Intelligence": "Robot Intelligence", "Chaos Lab": "Chaos Lab"}
st.session_state.main_navigation = nav_aliases.get(st.session_state.get("main_navigation", "Mission Control"), "Mission Control")
render_topbar()

st.write("")
view = st.segmented_control("Main areas", ["Mission Control", "Robot Intelligence", "Chaos Lab"],
                            key="main_navigation", label_visibility="collapsed", width="stretch")
if view:
    st.session_state.view = {"Mission Control": "Home", "Robot Intelligence": "Explore", "Chaos Lab": "Chaos Lab"}[view]

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
    if not st.session_state.presentation_mode:
        if st.button("Add a delivery", width="content", icon=":material/add_box:",
                     help="Create a real order from a product that is currently in stock"):
            add_delivery()
            st.rerun()
        st.slider("Simulation speed", 1, 4, key="speed", help="How many real simulation steps happen per update")
    render_communication_popover()
    if not st.session_state.presentation_mode:
        st.button("Top-down" if not st.session_state.top_down else "Angled view", key="camera_toggle",
                  on_click=lambda: st.session_state.update(top_down=not st.session_state.top_down),
                  help="Switch between a top-down and angled camera")
    st.toggle("Presentation mode", key="presentation_mode", help="Emphasise the live warehouse and key outcomes")

selected_robot = st.session_state.selected_robot
top_down = st.session_state.top_down
speed = st.session_state.speed

if st.session_state.view == "Home":
    if not st.session_state.started and not st.session_state.presentation_mode:
        st.markdown("<section class='hm-hero'><div class='hm-eyebrow'>Autonomous warehouse, one team</div><div class='hm-hero-title'>Five robots. One collective intelligence.</div><p class='hm-hero-copy'>Start the live warehouse, then break communication and watch the robots keep working with what they know.</p></section>", unsafe_allow_html=True)
    if not st.session_state.presentation_mode:
        render_guided_demo()
    home_live(selected_robot, top_down, speed, st.session_state.presentation_mode)

elif st.session_state.view == "Explore":
    st.markdown("<section class='hm-hero'><div class='hm-eyebrow'>INSIDE THE ROBOT'S MIND</div><div class='hm-hero-title'>Every robot decides from its own local view.</div><p class='hm-hero-copy'>Compare one robot's actual memory with the simulator's global state, then inspect the bids and messages behind its choices.</p></section>", unsafe_allow_html=True)
    mode = st.segmented_control(
        "Explore mode", ["Robot Perspective", "3D Warehouse"],
        key="explore_mode", label_visibility="collapsed", width="stretch",
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        for rid, robot in model.robots.items():
            st.button(
                f"{'[SELECTED] ' if rid == st.session_state.selected_robot else ''}Robot {rid+1:02d} | {ROBOT_STATES.get(robot.status, robot.status.title())}",
                key=f"perspective_robot_{rid}", width="stretch",
                on_click=lambda chosen=rid: st.session_state.update(selected_robot=chosen),
            )
    if mode == "3D Warehouse":
        explore_live(st.session_state.selected_robot, top_down, speed)
    else:
        robot_perspective_live(st.session_state.selected_robot, speed)

else:
    render_chaos_lab(selected_robot, top_down, speed)
