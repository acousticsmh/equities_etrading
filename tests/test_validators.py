from datetime import datetime, timezone
from decimal import Decimal

import pytest

from research.book.events import BookEvent, BookEventType
from research.book.models import Side
from research.book.order_book import OrderBook
from research.book.validators import BookValidator


def event(event_type: BookEventType, **kwargs) -> BookEvent:
    return BookEvent(
        event_type=event_type,
        symbol="AAPL",
        sequence=kwargs.pop("sequence", 1),
        event_time=datetime(2026, 1, 5, tzinfo=timezone.utc),
        **kwargs,
    )


def test_validate_event_accepts_lifecycle_events():
    validator = BookValidator()

    validator.validate_event(
        event(
            BookEventType.ADD,
            order_id="order-1",
            side=Side.BUY,
            price=Decimal("100.00"),
            quantity=100,
        )
    )
    validator.validate_event(
        event(BookEventType.CANCEL, order_id="order-1", side=None, price=None, quantity=10)
    )
    validator.validate_event(
        event(BookEventType.REPLACE, order_id="order-1", side=None, price=None, quantity=90, new_price=Decimal("100.01"))
    )


def test_validate_state_accepts_consistent_book():
    book = OrderBook("AAPL")
    book.add_order(
        event(
            BookEventType.ADD,
            order_id="order-1",
            side=Side.BUY,
            price=Decimal("100.00"),
            quantity=100,
        )
    )

    BookValidator().validate_state(book)


def test_validate_state_rejects_missing_order_reference():
    book = OrderBook("AAPL")
    level = book.bids.get_or_create(Decimal("100.00"))
    level.append("missing")

    with pytest.raises(ValueError, match="missing order"):
        BookValidator().validate_state(book)