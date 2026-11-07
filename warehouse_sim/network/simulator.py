"""Seeded graph network with routed delivery, latency, loss and TTL."""

from __future__ import annotations

import random
from collections import deque
from typing import Any, Deque, Dict, Iterable, List, Optional, Set, Tuple

from .messages import AgentMessage, MessageType


class NetworkSimulator:
    """A deterministic message transport; agents only observe delivered envelopes."""

    def __init__(self, robot_ids: Iterable[int], seed: Optional[int] = None, ttl: int = 12) -> None:
        self.nodes = [f"Robot-{rid}" for rid in robot_ids] + ["OrderAgent"]
        self.adjacency: Dict[str, Set[str]] = {node: set() for node in self.nodes}
        # A line topology gives a real multi-hop peer network; OrderAgent seeds Robot-0.
        for left, right in zip(self.nodes[:len(self.nodes)-1], self.nodes[1:len(self.nodes)-1]):
            self.connect(left, right)
        if "Robot-0" in self.adjacency:
            self.connect("OrderAgent", "Robot-0")
        self.rng = random.Random(seed)
        self.default_ttl = ttl
        self.latency = 0
        self.packet_loss = 0.0
        self.tick = 0
        self._sequence = 0
        self._pending: List[AgentMessage] = []
        self.activity_log: List[AgentMessage] = []
        self.inboxes: Dict[str, Deque[AgentMessage]] = {node: deque() for node in self.nodes}
        self.robot_message_counts: Dict[int, Dict[str, int]] = {
            int(node.split("-")[1]): {"sent": 0, "received": 0}
            for node in self.nodes if node.startswith("Robot-")
        }
        self.counters = {"sent": 0, "delivered": 0, "dropped": 0, "delayed": 0}
        self.delivered_delay_ticks = 0
        self.state_sync_received = 0
        self.disconnected_ticks = 0
        self.reconciliation_count = 0
        self.conflicts_detected = 0
        self.conflicts_resolved = 0
        self.duplicate_claims_prevented = 0
        self._conflict_keys: Set[Tuple[int, Tuple[int, ...]]] = set()
        self._resolved_conflict_keys: Set[Tuple[int, Tuple[int, ...]]] = set()
        self._last_partitions = self.partition_count

    def connect(self, a: str, b: str) -> None:
        if a in self.adjacency and b in self.adjacency and a != b:
            self.adjacency[a].add(b)
            self.adjacency[b].add(a)

    def disconnect(self, a: str, b: str) -> None:
        self.adjacency.get(a, set()).discard(b)
        self.adjacency.get(b, set()).discard(a)

    def restore_all(self) -> None:
        for node in self.nodes:
            self.adjacency[node].clear()
        for left, right in zip(self.nodes[:len(self.nodes)-1], self.nodes[1:len(self.nodes)-1]):
            self.connect(left, right)
        self.connect("OrderAgent", "Robot-0")
        # Recovery is counted only after agents exchange and merge state.

    def set_partition(self, groups: List[List[int]]) -> None:
        for node in self.nodes:
            self.adjacency[node].clear()
        for group in groups:
            names = [f"Robot-{rid}" for rid in group if f"Robot-{rid}" in self.adjacency]
            for a, b in zip(names, names[1:]):
                self.connect(a, b)
        # Put OrderAgent with the first group's first peer only.
        if groups and groups[0]:
            self.connect("OrderAgent", f"Robot-{groups[0][0]}")

    def isolate(self, robot_id: int) -> None:
        node = f"Robot-{robot_id}"
        for peer in list(self.adjacency.get(node, ())):
            self.disconnect(node, peer)

    def set_conditions(self, latency: int = 0, packet_loss: float = 0.0) -> None:
        self.latency = max(0, int(latency))
        self.packet_loss = min(1.0, max(0.0, float(packet_loss)))

    def _route(self, sender: str, recipient: str) -> Optional[Tuple[str, ...]]:
        if sender == recipient:
            return (sender,)
        todo = deque([(sender, (sender,))])
        seen = {sender}
        while todo:
            node, path = todo.popleft()
            for neighbor in sorted(self.adjacency.get(node, ())):
                if neighbor == recipient:
                    return path + (neighbor,)
                if neighbor not in seen:
                    seen.add(neighbor)
                    todo.append((neighbor, path + (neighbor,)))
        return None

    def send(self, sender: str, recipient: str, message_type: MessageType, payload: Dict[str, Any], tick: int) -> Optional[AgentMessage]:
        route = self._route(sender, recipient)
        self._sequence += 1
        self.counters["sent"] += 1
        if sender.startswith("Robot-"):
            sender_id = int(sender.split("-")[1])
            if sender_id in self.robot_message_counts:
                self.robot_message_counts[sender_id]["sent"] += 1
        message = AgentMessage(f"m{self._sequence:08d}", sender, recipient, message_type,
                               dict(payload), tick, tick + self.default_ttl,
                               deliver_at=tick + self.latency + 1, path=route or ())
        if route is None or self.rng.random() < self.packet_loss:
            message.delivery_status = "dropped"
            self.counters["dropped"] += 1
            self.activity_log.append(message)
            if len(self.activity_log) > 2000:
                del self.activity_log[:-2000]
            return message
        if self.latency:
            self.counters["delayed"] += 1
        self._pending.append(message)
        self.activity_log.append(message)
        if len(self.activity_log) > 2000:
            del self.activity_log[:-2000]
        return message

    def broadcast(self, sender: str, message_type: MessageType, payload: Dict[str, Any], tick: int) -> List[AgentMessage]:
        # Resolve reachability over the current graph at transmission time.
        return [m for recipient in self.nodes if recipient != sender
                if (m := self.send(sender, recipient, message_type, payload, tick)) is not None]

    def advance(self, tick: int) -> None:
        self.tick = tick
        if len(self.robot_components()) > 1:
            self.disconnected_ticks += 1
        for message in list(self._pending):
            if tick > message.expires_tick:
                message.delivery_status = "expired"
                self._pending.remove(message)
                self.counters["dropped"] += 1
            elif tick >= message.deliver_at:
                # A link failure after transmission prevents delivery too.
                route_ok = all(b in self.adjacency.get(a, ()) for a, b in zip(message.path, message.path[1:]))
                if route_ok:
                    message.delivery_status = "delivered"
                    self.inboxes[message.recipient].append(message)
                    self.counters["delivered"] += 1
                    self.delivered_delay_ticks += max(0, tick - message.created_tick)
                    if message.recipient.startswith("Robot-"):
                        recipient_id = int(message.recipient.split("-")[1])
                        self.robot_message_counts[recipient_id]["received"] += 1
                else:
                    message.delivery_status = "dropped"
                    self.counters["dropped"] += 1
                self._pending.remove(message)
        self._last_partitions = self.partition_count

    def receive(self, recipient: str) -> List[AgentMessage]:
        inbox = self.inboxes.get(recipient)
        if inbox is None:
            return []
        messages = list(inbox)
        inbox.clear()
        return messages

    def record_claim_conflict(self, task_id: int, robot_ids: Iterable[int]) -> Tuple[Tuple[int, Tuple[int, ...]], bool]:
        """Count each distinct competing claim set once, despite repeated syncs."""
        key = (int(task_id), tuple(sorted({int(rid) for rid in robot_ids})))
        if key not in self._conflict_keys:
            self._conflict_keys.add(key)
            self.conflicts_detected += 1
            return key, True
        return key, False

    def record_claim_resolution(self, key: Tuple[int, Tuple[int, ...]]) -> bool:
        """Count one deterministic resolution for each observed conflict set."""
        if key in self._resolved_conflict_keys:
            return False
        self._resolved_conflict_keys.add(key)
        self.conflicts_resolved += 1
        return True

    def robot_components(self) -> List[Set[str]]:
        remaining = {n for n in self.nodes if n.startswith("Robot-")}
        groups = []
        while remaining:
            start = min(remaining)
            reached = {start}
            todo = [start]
            while todo:
                node = todo.pop()
                for nxt in self.adjacency[node]:
                    if nxt.startswith("Robot-") and nxt not in reached:
                        reached.add(nxt); todo.append(nxt)
            groups.append(reached); remaining -= reached
        return groups

    @property
    def partition_count(self) -> int:
        return len(self.robot_components())

    @property
    def active_connections(self) -> int:
        return sum(len(peers) for peers in self.adjacency.values()) // 2

    def neighbors(self, robot_id: int) -> List[int]:
        return sorted(int(node.split("-")[1]) for node in self.adjacency.get(f"Robot-{robot_id}", ()) if node.startswith("Robot-"))

    def connected_robot_ids(self, robot_id: int) -> Set[int]:
        component = next((g for g in self.robot_components() if f"Robot-{robot_id}" in g), set())
        return {int(node.split("-")[1]) for node in component}
