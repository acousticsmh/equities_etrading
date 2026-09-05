from datetime import datetime, timezone
from decimal import Decimal

import pytest

from research.book.events import BookEvent, BookEventType
from research.book.models import Side
from research.book.order_book import OrderBook


def test_add_order_registers_order_and_preserves_fifo_queue():
    book = OrderBook("AAPL")
    event_time = datetime(2026, 1, 5, tzinfo=timezone.utc)

    book.add_order(
        BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=1,
            event_time=event_time,
            order_id="buy-1",
            side=Side.BUY,
            price=Decimal("100.00"),
            quantity=300,
        )
    )

    order = book.orders.get("buy-1")
    level = book.bids.get(Decimal("100.00"))
    assert order is not None
    assert order.remaining_quantity == 300
    assert level is not None
    assert list(level.orders) == ["buy-1"]
    assert level.quantity(book.orders) == 300


def test_execute_order_reduces_remaining_quantity_and_removes_filled_order():
    book = OrderBook("AAPL")
    event_time = datetime(2026, 1, 5, tzinfo=timezone.utc)
    book.add_order(
        BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=1,
            event_time=event_time,
            order_id="buy-1",
            side=Side.BUY,
            price=Decimal("100.00"),
            quantity=300,
        )
    )

    book.execute_order(
        BookEvent(
            event_type=BookEventType.EXECUTE,
            symbol="AAPL",
            sequence=2,
            event_time=event_time,
            order_id="buy-1",
            side=None,
            price=None,
            quantity=100,
        )
    )
    order = book.orders.get("buy-1")
    assert order is not None
    assert order.remaining_quantity == 200

    book.execute_order(
        BookEvent(
            event_type=BookEventType.EXECUTE,
            symbol="AAPL",
            sequence=3,
            event_time=event_time,
            order_id="buy-1",
            side=None,
            price=None,
            quantity=200,
        )
    )
    assert book.orders.get("buy-1") is None
    assert book.bids.get(Decimal("100.00")) is None


def test_cancel_order_supports_partial_cancellation():
    book = OrderBook("AAPL")
    event_time = datetime(2026, 1, 5, tzinfo=timezone.utc)
    book.add_order(
        BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=1,
            event_time=event_time,
            order_id="sell-1",
            side=Side.SELL,
            price=Decimal("100.01"),
            quantity=300,
        )
    )

    book.cancel_order(
        BookEvent(
            event_type=BookEventType.CANCEL,
            symbol="AAPL",
            sequence=2,
            event_time=event_time,
            order_id="sell-1",
            side=None,
            price=None,
            quantity=100,
        )
    )

    order = book.orders.get("sell-1")
    assert order is not None
    assert order.remaining_quantity == 200
    level = book.asks.get(Decimal("100.01"))
    assert level is not None
    assert level.quantity(book.orders) == 200


def test_depth_returns_ordered_levels_and_aggregated_quantity():
    book = OrderBook("AAPL")
    event_time = datetime(2026, 1, 5, tzinfo=timezone.utc)

    for sequence, order_id, side, price, quantity in (
        (1, "bid-1", Side.BUY, Decimal("100.00"), 300),
        (2, "bid-2", Side.BUY, Decimal("99.99"), 200),
        (3, "ask-1", Side.SELL, Decimal("100.01"), 150),
    ):
        book.add_order(
            BookEvent(
                event_type=BookEventType.ADD,
                symbol="AAPL",
                sequence=sequence,
                event_time=event_time,
                order_id=order_id,
                side=side,
                price=price,
                quantity=quantity,
            )
        )

    snapshot = book.depth(levels=5)

    assert [(level.price, level.quantity, level.order_count) for level in snapshot.bids] == [
        (Decimal("100.00"), 300, 1),
        (Decimal("99.99"), 200, 1),
    ]
    assert [(level.price, level.quantity, level.order_count) for level in snapshot.asks] == [
        (Decimal("100.01"), 150, 1),
    ]
    assert snapshot.sequence == 3


def test_replace_removes_old_level_and_updates_order_size():
    book = OrderBook("AAPL")
    first_time = datetime(2026, 1, 5, tzinfo=timezone.utc)
    second_time = datetime(2026, 1, 5, 0, 0, 1, tzinfo=timezone.utc)
    book.add_order(
        BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=1,
            event_time=first_time,
            order_id="buy-1",
            side=Side.BUY,
            price=Decimal("100.00"),
            quantity=300,
        )
    )

    book.replace_order(
        BookEvent(
            event_type=BookEventType.REPLACE,
            symbol="AAPL",
            sequence=2,
            event_time=second_time,
            order_id="buy-1",
            side=None,
            price=None,
            quantity=500,
            new_price=Decimal("100.01"),
        )
    )

    order = book.orders.get("buy-1")
    assert order is not None
    assert order.price == Decimal("100.01")
    assert order.quantity == 500
    assert order.remaining_quantity == 500
    assert book.bids.get(Decimal("100.00")) is None
    assert book.bids.get(Decimal("100.01")) is not None


def test_clear_removes_book_state_but_preserves_snapshot_metadata():
    book = OrderBook("AAPL")
    first_time = datetime(2026, 1, 5, tzinfo=timezone.utc)
    clear_time = datetime(2026, 1, 5, 0, 0, 1, tzinfo=timezone.utc)
    book.apply(
        BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=1,
            event_time=first_time,
            order_id="buy-1",
            side=Side.BUY,
            price=Decimal("100.00"),
            quantity=100,
        )
    )
    book.apply(
        BookEvent(
            event_type=BookEventType.CLEAR,
            symbol="AAPL",
            sequence=2,
            event_time=clear_time,
            order_id=None,
            side=None,
            price=None,
            quantity=None,
        )
    )

    snapshot = book.depth()
    assert snapshot.bids == ()
    assert snapshot.asks == ()
    assert snapshot.sequence == 2
    assert snapshot.event_time == clear_time


def test_sequence_gaps_are_rejected_without_mutating_book():
    book = OrderBook("AAPL")
    event_time = datetime(2026, 1, 5, tzinfo=timezone.utc)
    book.apply(
        BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=1,
            event_time=event_time,
            order_id="buy-1",
            side=Side.BUY,
            price=Decimal("100.00"),
            quantity=100,
        )
    )

    with pytest.raises(ValueError, match="Expected sequence 2, got 3"):
        book.apply(
            BookEvent(
                event_type=BookEventType.CANCEL,
                symbol="AAPL",
                sequence=3,
                event_time=event_time,
                order_id="buy-1",
                side=None,
                price=None,
                quantity=100,
            )
        )

    order = book.orders.get("buy-1")
    assert order is not None
    assert order.remaining_quantity == 100
    assert book.last_sequence == 1


def test_size_reduction_preserves_queue_priority():
    book = OrderBook("AAPL")
    event_time = datetime(2026, 1, 5, tzinfo=timezone.utc)
    for sequence, order_id, quantity in ((1, "buy-1", 300), (2, "buy-2", 200)):
        book.add_order(
            BookEvent(
                event_type=BookEventType.ADD,
                symbol="AAPL",
                sequence=sequence,
                event_time=event_time,
                order_id=order_id,
                side=Side.BUY,
                price=Decimal("100.00"),
                quantity=quantity,
            )
        )

    book.modify_order(
        BookEvent(
            event_type=BookEventType.MODIFY,
            symbol="AAPL",
            sequence=3,
            event_time=event_time,
            order_id="buy-1",
            side=None,
            price=None,
            quantity=100,
        )
    )

    level = book.bids.get(Decimal("100.00"))
    assert level is not None
    assert list(level.orders) == ["buy-1", "buy-2"]