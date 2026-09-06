from collections.abc import Iterable
from decimal import Decimal

from .models import BookOrder


class OrderStore:
    def __init__(self):
        self._orders: dict[str, BookOrder] = {}

    def add(self, order: BookOrder) -> None:
        self._orders[order.order_id] = order

    def get(self, order_id: str) -> BookOrder | None:
        return self._orders.get(order_id)

    def values(self) -> Iterable[BookOrder]:
        return self._orders.values()

    def clear(self) -> None:
        self._orders.clear()

    def remove(self, order_id: str) -> BookOrder | None:
        return self._orders.pop(order_id, None)

    def update_quantity(self, order_id: str, quantity: Decimal) -> None:
        self._orders[order_id].remaining_quantity = quantity