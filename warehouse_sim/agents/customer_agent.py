"""
Customer Agent — Generates realistic order streams for the warehouse.

Owner: Kalyan (cb.sc.u4cse23060) — Warehouse Intelligence
Responsibility: Simulates customer demand by generating orders on a
Poisson-distributed random interval with configurable priority mix.

PEAS Formulation:
    Performance: Order-generation realism, sustained arrival rate, priority mix.
    Environment: Warehouse order queue, customer priority tiers (normal/urgent).
    Actuators: place_order(sku, quantity, priority).
    Sensors: Current queue length, delivery-time feedback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import mesa

if TYPE_CHECKING:
    from ..model import WarehouseModel


# Available SKUs in the warehouse
AVAILABLE_SKUS = [f"SKU-{i:03d}" for i in range(1, 21)]

# Probability of generating an urgent order
URGENT_PROBABILITY = 0.15

# Average ticks between orders (Poisson lambda parameter)
ORDER_INTERVAL_LAMBDA = 8


class CustomerAgent(mesa.Agent):
    """
    Simulates customer demand by placing orders at random intervals.

    Orders are generated on a Poisson-distributed schedule with a 15%
    chance of being urgent. This creates the realistic demand patterns
    that drive the rest of the warehouse simulation.
    """

    def __init__(self, model: WarehouseModel) -> None:
        """Initialize the customer agent."""
        super().__init__(model)
        self.orders_placed: int = 0
        self._ticks_until_next_order: int = self._sample_interval()

    def _sample_interval(self) -> int:
        """Sample the next order interval from a Poisson distribution."""
        return max(1, int(self.model.random.expovariate(1.0 / ORDER_INTERVAL_LAMBDA)))

    def sense(self) -> None:
        """Observe the current order queue length."""
        self.current_queue_length = len(self.model.order_agent.task_queue)

    def decide(self) -> None:
        """Decide whether to place an order this tick."""
        self._ticks_until_next_order -= 1
        self.should_place_order = self._ticks_until_next_order <= 0

    def act(self) -> None:
        """Place an order if the decision was to do so."""
        if not self.should_place_order:
            return

        sku = self.model.random.choice(AVAILABLE_SKUS)
        qty = self.model.random.randint(1, 3)
        priority = "urgent" if self.model.random.random() < URGENT_PROBABILITY else "normal"

        self.model.order_agent.receive_order(sku, qty, priority)
        self.orders_placed += 1

        # Log the inter-agent message
        self.model.log_message(
            from_agent="CustomerAgent",
            to_agent="OrderAgent",
            payload={
                "action": "place_order",
                "sku": sku,
                "qty": qty,
                "priority": priority,
            },
        )

        # Reset timer
        self._ticks_until_next_order = self._sample_interval()
