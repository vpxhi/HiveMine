"""Deterministic in-process peer network used by HiveMine agents."""

from .messages import AgentMessage, MessageType
from .simulator import NetworkSimulator

__all__ = ["AgentMessage", "MessageType", "NetworkSimulator"]
