"""
Inventory Management Agent — Tracks shelf stock and handles reservations.

Owner: Kalyan (cb.sc.u4cse23060) — Warehouse Intelligence
Responsibility: Maintains ground-truth shelf state (SKU, quantity, reserved flag),
resolves SKU lookups to shelf locations, and manages reservations that directly
impact Traffic Controller's routing decisions (cross-agent causality).

PEAS Formulation:
    Performance: Correct shelf resolution, stock accuracy, zero false "in-stock" reports.
    Environment: Shelf/stock ground-truth table, warehouse map.
    Actuators: reserve_stock(), update_shelf_state().
    Sensors: Shelf occupancy, incoming task requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import mesa

if TYPE_CHECKING:
    from ..model import WarehouseModel


class InventoryAgent(mesa.Agent):
    """
    Manages warehouse shelf inventory and stock reservations.

    The reservation mechanism is the key causal link: when a shelf is
    reserved by the Fleet Manager, it changes the Traffic Controller's
    view of active corridors, affecting A* path costs for other robots.
    """

    def __init__(
        self,
        model: WarehouseModel,
        shelf_locations: List[Tuple[int, int]],
    ) -> None:
        """Initialize inventory with SKUs distributed across shelves."""
        super().__init__(model)
        self.shelf_state: Dict[Tuple[int, int], Dict] = {}

        # Distribute SKUs across shelves
        skus = [f"SKU-{i:03d}" for i in range(1, 21)]
        for i, loc in enumerate(shelf_locations):
            # Each shelf holds 2 SKUs with random quantity
            second_index = i + 7
            if second_index < len(shelf_locations):
                second_index += len(shelf_locations)
            assigned_skus = [skus[i % len(skus)], skus[second_index % len(skus)]]
            self.shelf_state[loc] = {
                "skus": {sku: model.random.randint(5, 15) for sku in assigned_skus},
                "reserved": False,
                "reserved_by": None,
            }

    def locate(self, sku: str) -> Optional[Tuple[int, int]]:
        """
        Find the nearest shelf with the given SKU in stock and not reserved.

        Args:
            sku: The product SKU to look up.

        Returns:
            Shelf location (x, y) or None if not available.
        """
        candidates = []
        for loc, state in self.shelf_state.items():
            if sku in state["skus"] and state["skus"][sku] > 0 and not state["reserved"]:
                candidates.append(loc)

        if not candidates:
            # Fall back: any shelf with stock, even if reserved
            for loc, state in self.shelf_state.items():
                if sku in state["skus"] and state["skus"][sku] > 0:
                    candidates.append(loc)

        return candidates[0] if candidates else None

    def reserve(self, shelf_id: Tuple[int, int], robot_id: int, sku: Optional[str] = None, qty: int = 1) -> bool:
        """
        Reserve a shelf for a robot pickup.

        This is the causal link from Section 2.8: reservation changes what
        the Traffic Controller sees as active reservation corridors.

        Args:
            shelf_id: The shelf location to reserve.
            robot_id: The robot that will pick from this shelf.

        Returns:
            True if reservation succeeded, False if already reserved.
        """
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            return False
        if robot_id not in self.model.robots or shelf_id not in self.shelf_state:
            return False
        if self.shelf_state[shelf_id]["reserved"]:
            return False
        if sku is not None and self.shelf_state[shelf_id]["skus"].get(sku, 0) < qty:
            return False

        self.shelf_state[shelf_id]["reserved"] = True
        self.shelf_state[shelf_id]["reserved_by"] = robot_id

        self.model.log_message(
            from_agent="InventoryAgent",
            to_agent="TrafficController",
            payload={
                "action": "shelf_reserved",
                "shelf_id": shelf_id,
                "robot_id": robot_id,
            },
        )
        return True

    def release(self, shelf_id: Tuple[int, int], robot_id: Optional[int] = None) -> None:
        """Release a shelf reservation after pickup is complete."""
        if shelf_id in self.shelf_state:
            current_owner = self.shelf_state[shelf_id]["reserved_by"]
            if robot_id is not None and current_owner not in (None, robot_id):
                return
            self.shelf_state[shelf_id]["reserved"] = False
            self.shelf_state[shelf_id]["reserved_by"] = None

    def decrement_stock(self, shelf_id: Tuple[int, int], sku: str, qty: int) -> bool:
        """
        Decrement stock for a SKU at a shelf after pickup.

        Args:
            shelf_id: Shelf location.
            sku: Product SKU.
            qty: Quantity to remove.

        Returns:
            True if stock was sufficient, False otherwise.
        """
        if isinstance(qty, bool) or not isinstance(qty, int) or qty <= 0:
            return False
        if shelf_id not in self.shelf_state:
            return False
        if sku not in self.shelf_state[shelf_id]["skus"]:
            return False

        current = self.shelf_state[shelf_id]["skus"][sku]
        if current < qty:
            return False

        self.shelf_state[shelf_id]["skus"][sku] = current - qty
        return True

    def sense(self) -> None:
        """Observe current shelf states."""
        pass

    def decide(self) -> None:
        """No autonomous decisions — reactive to requests."""
        pass

    def act(self) -> None:
        """No autonomous actions — reactive to method calls."""
        pass
