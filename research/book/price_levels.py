from collections import deque
from collections.abc import Iterable
from decimal import Decimal
from typing import cast

from sortedcontainers import SortedDict


class PriceLevel:
    """A single price level holding a FIFO queue of resting order IDs.

    The aggregate resting quantity is tracked incrementally as orders are
    appended, removed, or reduced, so reading it is O(1) rather than a walk of
    the queue with a store lookup per order.
    """

    price: Decimal
    orders: deque[str]

    def __init__(self, price: Decimal):
        self.price = price
        self.orders = deque()
        self._quantity = Decimal("0")

    def append(self, order_id: str, quantity: Decimal) -> None:
        self.orders.append(order_id)
        self._quantity += quantity

    def remove(self, order_id: str, quantity: Decimal) -> None:
        self.orders.remove(order_id)
        self._quantity -= quantity

    def reduce(self, quantity: Decimal) -> None:
        """Adjust the level total for a partial cancel, execution, or modify."""
        self._quantity -= quantity

    def quantity(self) -> Decimal:
        return self._quantity


class PriceLadder:
    def __init__(self, is_bid: bool):
        self.is_bid = is_bid
        # Maps Decimal price -> PriceLevel, kept in ascending price order.
        self._levels = SortedDict()

    def get_or_create(self, price: Decimal) -> PriceLevel:
        level = self._levels.get(price)
        if level is None:
            level = PriceLevel(price)
            self._levels[price] = level
        return level

    def get(self, price: Decimal) -> PriceLevel | None:
        return self._levels.get(price)

    def remove_if_empty(self, price: Decimal) -> None:
        level = self._levels.get(price)
        if level is not None and not level.orders:
            del self._levels[price]

    def clear(self) -> None:
        self._levels.clear()

    def best_price(self) -> Decimal | None:
        if not self._levels:
            return None
        # SortedDict keeps prices ascending: best bid is the last key, best ask the first.
        index = -1 if self.is_bid else 0
        return cast(Decimal, self._levels.peekitem(index)[0])

    def levels(self) -> Iterable[PriceLevel]:
        prices = reversed(self._levels) if self.is_bid else self._levels
        return (self._levels[price] for price in prices)
