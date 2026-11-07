"""Typed envelopes for simulated agent communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class MessageType(str, Enum):
    TASK_ANNOUNCEMENT = "task_announcement"
    TASK_BID = "task_bid"
    TASK_CLAIM = "task_claim"
    TASK_COMPLETE = "task_complete"
    TASK_ABANDON = "task_abandon"
    ROBOT_STATUS = "robot_status"
    STATE_SYNC = "state_sync"


@dataclass
class AgentMessage:
    message_id: str
    sender: str
    recipient: str
    message_type: MessageType
    payload: Dict[str, Any]
    created_tick: int
    expires_tick: int
    delivery_status: str = "queued"
    deliver_at: int = 0
    path: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type.value,
            "payload": dict(self.payload),
            "created_tick": self.created_tick,
            "expires_tick": self.expires_tick,
            "delivery_status": self.delivery_status,
            "deliver_at": self.deliver_at,
            "path": list(self.path),
        }
