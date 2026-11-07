"""
Order Management Agent — Prioritizes and decomposes incoming orders into tasks.

Owner: Kalyan (cb.sc.u4cse23060) — Warehouse Intelligence
Responsibility: Maintains a priority queue of orders, decomposes multi-item
orders into per-shelf sub-tasks, and dispatches them to the Inventory Agent.

PEAS Formulation:
    Performance: Correct prioritization, task decomposition latency, zero dropped orders.
    Environment: Incoming order stream, current task backlog.
    Actuators: create_task(), set_priority(), dispatch_to_inventory_agent().
    Sensors: Order queue, task-completion acknowledgements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

import mesa

if TYPE_CHECKING:
    from ..model import WarehouseModel


@dataclass(order=True)
class Task:
    """A single fulfillment task (one SKU from one shelf)."""

    priority_rank: int = field(compare=True)  # 0 = urgent, 1 = normal
    arrival_tick: int = field(compare=True)
    task_id: int = field(compare=False)
    sku: str = field(compare=False)
    qty: int = field(compare=False)
    priority: str = field(compare=False)
    status: str = field(default="PENDING", compare=False)
    assigned_robot: int = field(default=-1, compare=False)
    shelf_location: tuple = field(default=(0, 0), compare=False)
    completion_tick: int = field(default=-1, compare=False)


class OrderAgent(mesa.Agent):
    """
    Manages incoming orders by prioritizing and decomposing them into tasks.

    Urgent orders are always processed before normal ones. Within the same
    priority tier, orders are processed in FIFO order.
    """

    def __init__(self, model: WarehouseModel) -> None:
        """Initialize the order management agent."""
        super().__init__(model)
        self.task_queue: List[Task] = []
        self.completed_tasks: List[Task] = []
        self.all_tasks: List[Task] = []
        self._next_task_id: int = 0
        self.total_orders_received: int = 0

    def receive_order(self, sku: str, qty: int, priority: str) -> None:
        """
        Receive a new order and create a task for it.

        Args:
            sku: The product SKU to fulfill.
            qty: Quantity requested.
            priority: "urgent" or "normal".
        """
        self.total_orders_received += 1
        priority_rank = 0 if priority == "urgent" else 1

        task = Task(
            priority_rank=priority_rank,
            arrival_tick=self.model.current_tick,
            task_id=self._next_task_id,
            sku=sku,
            qty=qty,
            priority=priority,
        )
        self._next_task_id += 1

        # Insert maintaining sorted order (heapq-style, but using sorted list)
        self.task_queue.append(task)
        self.task_queue.sort()
        self.all_tasks.append(task)

    def sense(self) -> None:
        """Check for completed task acknowledgements."""
        pass  # Completions are handled via mark_task_completed()

    def decide(self) -> None:
        """Determine if there are tasks ready to dispatch."""
        self.tasks_to_dispatch: List[Task] = []
        for task in self.task_queue:
            if task.status == "PENDING":
                self.tasks_to_dispatch.append(task)

    def act(self) -> None:
        """Dispatch pending tasks to the inventory agent (max 2 per tick)."""
        dispatched = 0
        for task in self.tasks_to_dispatch:
            if dispatched >= 2:
                break

            shelf_location = self.model.inventory_agent.locate(task.sku)
            if shelf_location is not None:
                task.shelf_location = shelf_location
                task.status = "DISPATCHED"

                self.model.log_message(
                    from_agent="OrderAgent",
                    to_agent="InventoryAgent",
                    payload={
                        "action": "locate_sku",
                        "task_id": task.task_id,
                        "sku": task.sku,
                        "shelf_location": shelf_location,
                    },
                )

                # The Order Agent publishes an offer. Robots independently bid
                # and agree with reachable peers; FleetManager is not the allocator.
                self.model.announce_task(task)

                dispatched += 1

    def mark_task_completed(self, task_id: int) -> None:
        """Mark a task as completed and move it to the completed list."""
        for task in self.task_queue:
            if task.task_id == task_id:
                task.status = "COMPLETED"
                self.completed_tasks.append(task)
                self.task_queue.remove(task)
                break

    def get_pending_count(self) -> int:
        """Return the number of pending tasks."""
        return sum(1 for t in self.task_queue if t.status == "PENDING")

    def get_active_count(self) -> int:
        """Return the number of in-progress tasks."""
        return sum(
            1 for t in self.task_queue if t.status in ("DISPATCHED", "IN_PROGRESS")
        )
