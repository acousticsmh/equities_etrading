from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from .events import BookEvent, BookEventType
from .models import Side

if TYPE_CHECKING:
    from .order_book import OrderBook


class BookValidator:
    def validate_event(self, event: BookEvent) -> None:
        if not event.symbol.strip():
            raise ValueError("Event requires a symbol")

        if event.event_type is BookEventType.ADD:
            self._validate_add_event(event)
        elif event.event_type is BookEventType.CANCEL:
            self._validate_quantity_event(event, "Cancel")
        elif event.event_type is BookEventType.MODIFY:
            self._validate_modify_event(event)
        elif event.event_type is BookEventType.EXECUTE:
            self._validate_quantity_event(event, "Execute")
        elif event.event_type is BookEventType.REPLACE:
            self._validate_replace_event(event)
        elif event.event_type is BookEventType.CLEAR:
            self._validate_clear_event(event)
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")

    def validate_state(self, book: OrderBook) -> None:
        active_order_ids: set[str] = set()

        for level in book.bids.levels():
            self._validate_level_membership(book, level, Side.BUY, active_order_ids)
            if level.quantity(book.orders) <= 0:
                raise ValueError(f"Bid level {level.price} has no remaining quantity")

        for level in book.asks.levels():
            self._validate_level_membership(book, level, Side.SELL, active_order_ids)
            if level.quantity(book.orders) <= 0:
                raise ValueError(f"Ask level {level.price} has no remaining quantity")

        stored_orders = list(book.orders.values())
        if len(active_order_ids) != len(stored_orders):
            raise ValueError("Every stored order must appear exactly once in the book")

        for order in stored_orders:
            if order.symbol != book.symbol:
                raise ValueError(f"Order {order.order_id} has the wrong symbol")
            if order.quantity <= 0:
                raise ValueError(f"Order {order.order_id} has invalid original quantity")
            if not 0 < order.remaining_quantity <= order.quantity:
                raise ValueError(f"Order {order.order_id} has invalid remaining quantity")

        best_bid = book.bids.best_price()
        best_ask = book.asks.best_price()
        if best_bid is not None and best_ask is not None and best_bid >= best_ask:
            raise ValueError(f"Book is crossed: bid {best_bid} >= ask {best_ask}")

    @staticmethod
    def order_id(event: BookEvent, name: str) -> str:
        BookValidator._require_order_id(event, name)
        assert event.order_id is not None
        return event.order_id

    @staticmethod
    def quantity(event: BookEvent, name: str) -> int:
        BookValidator._require_positive_quantity(event.quantity, name)
        assert event.quantity is not None
        return event.quantity

    @staticmethod
    def add_values(event: BookEvent) -> tuple[str, Side, Decimal, int]:
        BookValidator._validate_add_event(event)
        assert event.order_id is not None
        assert event.side is not None
        assert event.price is not None
        assert event.quantity is not None
        return event.order_id, event.side, event.price, event.quantity

    @staticmethod
    def _validate_add_event(event: BookEvent) -> None:
        BookValidator._require_order_id(event, "Add")
        BookValidator._require_side(event, "Add")
        BookValidator._require_price(event.price, "Add")
        BookValidator._require_positive_quantity(event.quantity, "Add")

    @staticmethod
    def _validate_quantity_event(event: BookEvent, name: str) -> None:
        BookValidator._require_order_id(event, name)
        BookValidator._require_positive_quantity(event.quantity, name)

    @staticmethod
    def _validate_modify_event(event: BookEvent) -> None:
        BookValidator._validate_quantity_event(event, "Modify")

    @staticmethod
    def _validate_replace_event(event: BookEvent) -> None:
        BookValidator._require_order_id(event, "Replace")
        BookValidator._require_price(event.new_price, "Replace")
        BookValidator._require_positive_quantity(event.quantity, "Replace")

    @staticmethod
    def _validate_clear_event(event: BookEvent) -> None:
        if any(value is not None for value in (event.order_id, event.side, event.price, event.quantity)):
            raise ValueError("Clear event cannot contain order fields")

    @staticmethod
    def _require_order_id(event: BookEvent, name: str) -> None:
        if event.order_id is None or not event.order_id.strip():
            raise ValueError(f"{name} event requires an order_id")

    @staticmethod
    def _require_side(event: BookEvent, name: str) -> None:
        if event.side not in (Side.BUY, Side.SELL):
            raise ValueError(f"{name} event requires a valid side")

    @staticmethod
    def _require_price(price: Decimal | None, name: str) -> None:
        if price is None or price <= 0:
            raise ValueError(f"{name} event requires a positive price")

    @staticmethod
    def _require_positive_quantity(quantity: int | None, name: str) -> None:
        if quantity is None or quantity <= 0:
            raise ValueError(f"{name} event requires a positive quantity")

    @staticmethod
    def _validate_level_membership(book, level, side: Side, active_order_ids: set[str]) -> None:
        for order_id in level.orders:
            if order_id in active_order_ids:
                raise ValueError(f"Order {order_id} appears more than once in the book")
            order = book.orders.get(order_id)
            if order is None:
                raise ValueError(f"Level {level.price} references missing order {order_id}")
            if order.side is not side or order.price != level.price:
                raise ValueError(f"Order {order_id} does not match its price level")
            active_order_ids.add(order_id)