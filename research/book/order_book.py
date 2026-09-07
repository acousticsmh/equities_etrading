
from datetime import datetime, timezone
from decimal import Decimal

from .events import BookEvent, BookEventType
from .models import BookOrder, Side
from .orders import OrderStore
from .price_levels import PriceLadder
from .snapshots import BookLevel, BookSnapshot, TopOfBook
from .validators import BookValidator


class OrderBook:

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.orders = OrderStore()
        self.bids = PriceLadder(is_bid=True)
        self.asks = PriceLadder(is_bid=False)
        self.validator = BookValidator()
        self.last_sequence: int | None = None
        self.last_event_time: datetime | None = None
        self.last_received_time: datetime | None = None

    def _check_symbol(self, event: BookEvent) -> None:
        if event.symbol != self.symbol:
            raise ValueError(f"Event symbol {event.symbol} does not match {self.symbol}")

    def _check_sequence(self, event: BookEvent) -> None:
        if self.last_sequence is not None and event.sequence != self.last_sequence + 1:
            raise ValueError(
                f"Expected sequence {self.last_sequence + 1}, got {event.sequence}"
            )

    def _prepare_event(self, event: BookEvent) -> None:
        self.validator.validate_event(event)
        self._check_symbol(event)
        self._check_sequence(event)

    def _record_event(self, event: BookEvent) -> None:
        self.last_sequence = event.sequence
        self.last_event_time = event.event_time
        self.last_received_time = event.received_time

    def apply(self, event: BookEvent) -> None:
        if event.event_type is BookEventType.ADD:
            self.add_order(event)
        elif event.event_type is BookEventType.CANCEL:
            self.cancel_order(event)
        elif event.event_type is BookEventType.EXECUTE:
            self.execute_order(event)
        elif event.event_type is BookEventType.MODIFY:
            self.modify_order(event)
        elif event.event_type is BookEventType.REPLACE:
            self.replace_order(event)
        elif event.event_type is BookEventType.CLEAR:
            self.clear_order(event)
        else:
            raise ValueError(f"Unknown event type: {event.event_type}")

    def add_order(self, event: BookEvent) -> None:
        self._prepare_event(event)
        order_id, side, price, quantity = self.validator.add_values(event)
        if self.orders.get(order_id) is not None:
            raise ValueError(f"Order already exists: {order_id}")
        if side is Side.BUY:
            level = self.bids.get_or_create(price)
        elif side is Side.SELL:
            level = self.asks.get_or_create(price)
        else:
            raise ValueError(f"Unknown side: {side}")
        self.orders.add(
            BookOrder(
                order_id=order_id,
                symbol=event.symbol,
                side=side,
                price=price,
                quantity=quantity,
                remaining_quantity=quantity,
                sequence=event.sequence,
                timestamp=event.event_time,
                venue=event.venue,
                received_time=event.received_time,
            )
        )
        level.append(order_id, quantity)
        self._record_event(event)

    def cancel_order(self, event: BookEvent) -> None:
        self._prepare_event(event)
        order_id = self.validator.order_id(event, "Cancel")
        quantity = self.validator.quantity(event, "Cancel")
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")
        if quantity > order.remaining_quantity:
            raise ValueError(
                f"Cancel quantity {quantity} exceeds "
                f"remaining quantity {order.remaining_quantity}"
            )
        if order.side is Side.BUY:
            level = self.bids.get(order.price)
        elif order.side is Side.SELL:
            level = self.asks.get(order.price)
        else:
            raise ValueError(f"Unknown side: {order.side}")
        if level is None:
            raise ValueError(f"Price level not found: {order.price}")

        order.remaining_quantity -= quantity
        if order.remaining_quantity == 0:
            level.remove(order_id, quantity)
            self.orders.remove(order_id)
            if order.side is Side.BUY:
                self.bids.remove_if_empty(order.price)
            else:
                self.asks.remove_if_empty(order.price)
        else:
            level.reduce(quantity)
        self._record_event(event)

    def execute_order(self, event: BookEvent) -> None:
        self._prepare_event(event)
        order_id = self.validator.order_id(event, "Execute")
        quantity = self.validator.quantity(event, "Execute")

        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")
        if quantity > order.remaining_quantity:
            raise ValueError(
                f"Execute quantity {quantity} exceeds "
                f"remaining quantity {order.remaining_quantity}"
            )

        if order.side is Side.BUY:
            level = self.bids.get(order.price)
        elif order.side is Side.SELL:
            level = self.asks.get(order.price)
        else:
            raise ValueError(f"Unknown side: {order.side}")
        if level is None:
            raise ValueError(f"Price level not found: {order.price}")

        order.remaining_quantity -= quantity
        if order.remaining_quantity == 0:
            level.remove(order_id, quantity)
            self.orders.remove(order_id)
            if order.side is Side.BUY:
                self.bids.remove_if_empty(order.price)
            else:
                self.asks.remove_if_empty(order.price)
        else:
            level.reduce(quantity)
        self._record_event(event)

    def modify_order(self, event: BookEvent) -> None:
        self._prepare_event(event)
        order_id = self.validator.order_id(event, "Modify")
        quantity = self.validator.quantity(event, "Modify")

        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")

        if quantity > order.remaining_quantity:
            raise ValueError(
                f"Modify quantity {quantity} exceeds "
                f"remaining quantity {order.remaining_quantity}"
            )

        if order.side is Side.BUY:
            level = self.bids.get(order.price)
        elif order.side is Side.SELL:
            level = self.asks.get(order.price)
        else:
            raise ValueError(f"Unknown side: {order.side}")
        if level is None:
            raise ValueError(f"Price level not found: {order.price}")

        level.reduce(order.remaining_quantity - quantity)
        order.remaining_quantity = quantity
        self._record_event(event)


    def replace_order(self, event: BookEvent) -> None:
        self._prepare_event(event)
        order_id = self.validator.order_id(event, "Replace")
        new_price = event.new_price
        quantity = self.validator.quantity(event, "Replace")
        if new_price is None or new_price <= 0:
            raise ValueError("Replace event requires a positive price")

        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"Order not found: {order_id}")

        if order.side is Side.BUY:
            old_level = self.bids.get(order.price)
            new_level = self.bids.get_or_create(new_price)
        elif order.side is Side.SELL:
            old_level = self.asks.get(order.price)
            new_level = self.asks.get_or_create(new_price)
        else:
            raise ValueError(f"Unknown side: {order.side}")

        if old_level is None:
            raise ValueError(f"Old price level not found: {order.price}")

        old_level.remove(order_id, order.remaining_quantity)
        new_level.append(order_id, quantity)
        if old_level is not new_level:
            self._remove_empty_level(order)

        order.price = new_price
        order.quantity = quantity
        order.remaining_quantity = quantity
        self._record_event(event)

    def clear_order(self, event: BookEvent) -> None:
        self._prepare_event(event)
        self.orders.clear()
        self.bids.clear()
        self.asks.clear()
        self._record_event(event)

    def _remove_empty_level(self, order: BookOrder) -> None:
        if order.side is Side.BUY:
            self.bids.remove_if_empty(order.price)
        else:
            self.asks.remove_if_empty(order.price)

    def top_of_book(self) -> TopOfBook:
        best_bid_price = self.bids.best_price()
        best_ask_price = self.asks.best_price()

        best_bid_level = (
            self.bids.get(best_bid_price) if best_bid_price is not None else None
        )
        best_ask_level = (
            self.asks.get(best_ask_price) if best_ask_price is not None else None
        )

        return TopOfBook(
            bid_price=best_bid_price,
            bid_size=(best_bid_level.quantity() if best_bid_level else Decimal("0")),
            ask_price=best_ask_price,
            ask_size=(best_ask_level.quantity() if best_ask_level else Decimal("0")),
        )

    def depth(self, levels: int = 5) -> BookSnapshot:
        bid_levels = list(self.bids.levels())[:levels]
        ask_levels = list(self.asks.levels())[:levels]

        bid_snapshots = tuple(
            BookLevel(
                price=level.price,
                quantity=level.quantity(),
                order_count=len(level.orders),
            )
            for level in bid_levels
        )

        ask_snapshots = tuple(
            BookLevel(
                price=level.price,
                quantity=level.quantity(),
                order_count=len(level.orders),
            )
            for level in ask_levels
        )

        return BookSnapshot(
            symbol=self.symbol,
            event_time=self.last_event_time or datetime.now(timezone.utc),
            sequence=self.last_sequence or 0,
            bids=bid_snapshots,
            asks=ask_snapshots,
        )