from collections import deque
from collections.abc import Iterable
from decimal import Decimal

from .orders import OrderStore


class PriceLevel:
    price: Decimal
    orders: deque[str]

    def __init__(self, price: Decimal):
        self.price = price
        self.orders = deque()

    def append(self, order_id: str) -> None:
        self.orders.append(order_id)
    def remove(self, order_id: str) -> None:
        self.orders.remove(order_id)
    def quantity(self, orders: OrderStore) -> Decimal:
        return sum(
            (
                order.remaining_quantity
                for order_id in self.orders
                if (order := orders.get(order_id)) is not None
            ),
            Decimal("0"),
        )


class PriceLadder:
    def __init__(self, is_bid: bool):
        self.is_bid = is_bid
        self._levels: dict[Decimal, PriceLevel] = {}

    def get_or_create(self, price: Decimal) -> PriceLevel:
        if price not in self._levels:
            self._levels[price] = PriceLevel(price)
        return self._levels[price]

    def get(self, price: Decimal) -> PriceLevel | None:
        return self._levels.get(price)

    def remove_if_empty(self, price: Decimal, orders: OrderStore) -> None:
        level = self._levels.get(price)
        if level is not None and level.quantity(orders) == 0:
            del self._levels[price]

    def clear(self) -> None:
        self._levels.clear()

    def best_price(self) -> Decimal | None:
        if not self._levels:
            return None
        return max(self._levels) if self.is_bid else min(self._levels)

    def levels(self) -> Iterable[PriceLevel]:
        prices = sorted(self._levels, reverse=self.is_bid)
        return (self._levels[price] for price in prices)