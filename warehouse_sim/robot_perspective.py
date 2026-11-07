"""Read-only view data for explaining one robot's local perspective."""

from __future__ import annotations

from typing import Any, Dict


def local_knowledge_snapshot(robot: Any) -> Dict[str, Any]:
    """Return only state stored on the selected robot."""
    known_tasks = []
    for task_id, task in sorted(robot.local_task_knowledge.items()):
        known_tasks.append({
            "task_id": int(task_id),
            "sku": task.get("sku"),
            "quantity": task.get("qty"),
            "priority": task.get("priority"),
            "completed": bool(task.get("completed", False)),
            "owner_robot_id": task.get("owner"),
            "bids": {int(rid): float(score) for rid, score in task.get("bids", {}).items()},
            "claims": {int(rid): float(score) for rid, score in task.get("claims", {}).items()},
            "bid_exclusions": dict(task.get("bid_exclusions", {})),
        })
    current = robot.current_task
    return {
        "robot_id": robot.robot_id,
        "position": tuple(robot.pos_tuple),
        "battery_percent": float(robot.battery),
        "status": robot.status,
        "current_task": ({
            "task_id": int(current.task_id),
            "sku": current.sku,
            "quantity": current.qty,
            "priority": current.priority,
        } if current is not None else None),
        "known_tasks": known_tasks,
        "direct_neighbours": list(robot.nearby_agents),
        "communication_status": robot.communication_status,
        "last_decision": robot.last_decision,
        "last_decision_reason": robot.last_decision_reason,
        "received_messages": [dict(message) for message in robot.local_event_memory[-12:]],
        "decision_history": [dict(event) for event in robot.local_decision_history[-80:]],
    }


def simulation_comparison(model: Any, robot: Any, local: Dict[str, Any]) -> Dict[str, Any]:
    """Return observer-only global facts, kept separate from the local snapshot."""
    local_task_ids = {task["task_id"] for task in local["known_tasks"]}
    global_tasks = [{
        "task_id": int(task.task_id),
        "sku": task.sku,
        "quantity": task.qty,
        "priority": task.priority,
        "global_status": task.status,
        "assigned_robot_id": task.assigned_robot,
        "in_selected_robot_memory": task.task_id in local_task_ids,
    } for task in model.order_agent.all_tasks]
    recipient = f"Robot-{robot.robot_id}"
    in_transit = [{
        "message_id": message.message_id,
        "type": message.message_type.value,
        "sender": message.sender,
        "created_tick": message.created_tick,
        "expected_delivery_tick": message.deliver_at,
    } for message in model.network._pending
        if message.recipient == recipient]
    delivered_pending_sense = [{
        "message_id": message.message_id,
        "type": message.message_type.value,
        "sender": message.sender,
        "created_tick": message.created_tick,
    } for message in model.network.inboxes.get(recipient, ())]
    unavailable_messages = [{
        "message_id": message.message_id,
        "type": message.message_type.value,
        "sender": message.sender,
        "created_tick": message.created_tick,
        "delivery_status": message.delivery_status,
        "task_id": message.payload.get("task_id"),
    } for message in model.network.activity_log
        if message.recipient == recipient
        and message.delivery_status in ("dropped", "expired")]
    reachable = sorted(model.network.connected_robot_ids(robot.robot_id))
    return {
        "global_tasks": global_tasks,
        "global_tasks_not_in_local_memory": [
            task for task in global_tasks if not task["in_selected_robot_memory"]
        ],
        "messages_in_transit": in_transit[-12:],
        "delivered_pending_sense": delivered_pending_sense[-12:],
        "unavailable_messages": unavailable_messages[-12:],
        "reachable_robot_ids": reachable,
        "unreachable_robot_ids": [
            rid for rid in model.robots if rid not in reachable
        ],
        "operating_independently_of_full_fleet": model.network.partition_count > 1,
        "communication_group_size": len(reachable),
    }
