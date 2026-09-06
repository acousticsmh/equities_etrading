"""Comprehensive test for FillSimulator and ExecutionValidator."""

from decimal import Decimal

from research.book.events import BookEvent, BookEventType
from research.book.models import Side
from research.book.order_book import OrderBook
from research.execution import ExecutionValidator, FillSimulator, FillType


def test_passive_fill_at_front():
    """Test: Order at front of queue gets filled."""
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Build book: 2 BUY orders at $150, 1 SELL order at $151 (establish bid/ask)
    events = [
        ("A", Side.BUY, Decimal("150.00"), 100),
        ("B", Side.BUY, Decimal("150.00"), 50),
        ("SELL_1", Side.SELL, Decimal("151.00"), 100),
    ]
    for i, (order_id, side, price, qty) in enumerate(events, 1):
        event = BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=i,
            event_time=i * 1000,
            order_id=order_id,
            side=side,
            price=price,
            quantity=qty,
        )
        book.apply(event)
    
    # Trade event: SELL at $150.00 (at bid, aggressor SELL side hitting BUY orders)
    trade_event = BookEvent(
        event_type=BookEventType.EXECUTE,
        symbol="AAPL",
        sequence=4,
        event_time=4000,
        order_id="TRADE_1",
        side=None,
        price=Decimal("150.00"),
        quantity=75.0,
    )
    
    # Evaluate ORDER_A (at front)
    result = simulator.evaluate_fill("A", trade_event)
    assert result.fill_type == FillType.PASSIVE_FILL, f"Expected PASSIVE_FILL, got {result.fill_type}"
    assert result.fill_quantity == 75.0, f"Expected fill_qty=75, got {result.fill_quantity}"
    assert result.remaining_quantity == 25.0, f"Expected remaining=25, got {result.remaining_quantity}"
    assert result.queue_position is not None
    assert result.queue_position.is_at_front == True
    print(f"✓ ORDER_A passive fill: {result}")
    
    # Validate result
    diags = ExecutionValidator.validate_result(result)
    assert all(diag.passed for diag in diags), f"Validation failed: {diags}"
    print(f"✓ ORDER_A validation: {len([d for d in diags if d.passed])}/3 passed")


def test_position_miss():
    """Test: Order not at front doesn't get filled."""
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Build book: 3 BUY orders at $150, 1 SELL at $151
    events = [
        ("A", Side.BUY, Decimal("150.00"), 100),
        ("B", Side.BUY, Decimal("150.00"), 50),
        ("C", Side.BUY, Decimal("150.00"), 75),
        ("SELL_1", Side.SELL, Decimal("151.00"), 100),
    ]
    for i, (order_id, side, price, qty) in enumerate(events, 1):
        event = BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=i,
            event_time=i * 1000,
            order_id=order_id,
            side=side,
            price=price,
            quantity=qty,
        )
        book.apply(event)
    
    # Trade event: SELL at $150.00
    trade_event = BookEvent(
        event_type=BookEventType.EXECUTE,
        symbol="AAPL",
        sequence=5,
        event_time=5000,
        order_id="TRADE_1",
        side=None,
        price=Decimal("150.00"),
        quantity=100.0,
    )
    
    # Evaluate ORDER_B (not at front)
    result = simulator.evaluate_fill("B", trade_event)
    assert result.fill_type == FillType.POSITION_MISS, f"Expected POSITION_MISS, got {result.fill_type}"
    assert result.fill_quantity == 0.0
    assert result.queue_position is not None
    assert result.queue_position.is_at_front == False
    assert result.queue_position.sequence_position == 1
    print(f"✓ ORDER_B position miss: {result}")
    
    # Validate result
    diags = ExecutionValidator.validate_result(result)
    assert all(diag.passed for diag in diags), f"Validation failed: {diags}"


def test_no_position():
    """Test: Non-existent order returns NO_POSITION."""
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Add one order and establish spread
    events = [
        ("A", Side.BUY, Decimal("150.00"), 100),
        ("SELL_1", Side.SELL, Decimal("151.00"), 100),
    ]
    for i, (order_id, side, price, qty) in enumerate(events, 1):
        event = BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=i,
            event_time=i * 1000,
            order_id=order_id,
            side=side,
            price=price,
            quantity=qty,
        )
        book.apply(event)
    
    # Trade event
    trade_event = BookEvent(
        event_type=BookEventType.EXECUTE,
        symbol="AAPL",
        sequence=3,
        event_time=3000,
        order_id="TRADE_1",
        side=None,
        price=Decimal("150.00"),
        quantity=50.0,
    )
    
    # Evaluate non-existent order
    result = simulator.evaluate_fill("FAKE", trade_event)
    assert result.fill_type == FillType.NO_POSITION
    assert result.fill_quantity == 0.0
    assert result.queue_position is None
    print(f"✓ Non-existent order: {result}")


def test_price_rejection():
    """Test: Order is rejected only if trade price is worse than order price."""
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Add BUY order at $150 and establish spread
    events = [
        ("A", Side.BUY, Decimal("150.00"), 100),
        ("SELL_1", Side.SELL, Decimal("151.00"), 100),
    ]
    for i, (order_id, side, price, qty) in enumerate(events, 1):
        event = BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=i,
            event_time=i * 1000,
            order_id=order_id,
            side=side,
            price=price,
            quantity=qty,
        )
        book.apply(event)
    
    # Trade event at $152 (worse price for buyer - above the order price)
    trade_event = BookEvent(
        event_type=BookEventType.EXECUTE,
        symbol="AAPL",
        sequence=3,
        event_time=3000,
        order_id="TRADE_1",
        side=None,
        price=Decimal("152.00"),
        quantity=50.0,
    )
    
    result = simulator.evaluate_fill("A", trade_event)
    # BUY order at $150 should reject trade at $152 (worse price for buyer)
    assert result.fill_type == FillType.NO_POSITION, f"Expected NO_POSITION, got {result.fill_type}"
    print(f"✓ Price rejection (worse price): {result}")


def test_sell_side():
    """Test: SELL orders work correctly."""
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Add 2 SELL orders at $150, establish spread with BUY at $149
    events = [
        ("BUY_1", Side.BUY, Decimal("149.00"), 100),
        ("A", Side.SELL, Decimal("150.00"), 100),
        ("B", Side.SELL, Decimal("150.00"), 50),
    ]
    for i, (order_id, side, price, qty) in enumerate(events, 1):
        event = BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=i,
            event_time=i * 1000,
            order_id=order_id,
            side=side,
            price=price,
            quantity=qty,
        )
        book.apply(event)
    
    # Trade event: BUY at $150.00
    trade_event = BookEvent(
        event_type=BookEventType.EXECUTE,
        symbol="AAPL",
        sequence=4,
        event_time=4000,
        order_id="TRADE_1",
        side=None,
        price=Decimal("150.00"),
        quantity=60.0,
    )
    
    # Evaluate ORDER_A (at front)
    result = simulator.evaluate_fill("A", trade_event)
    assert result.fill_type == FillType.PASSIVE_FILL
    assert result.fill_quantity == 60.0
    print(f"✓ SELL order passive fill: {result}")


def test_create_fill_event():
    """Test: FillEvent creation from ExecutionResult."""
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Add order and establish spread
    events = [
        ("A", Side.BUY, Decimal("150.00"), 100),
        ("SELL_1", Side.SELL, Decimal("151.00"), 100),
    ]
    for i, (order_id, side, price, qty) in enumerate(events, 1):
        event = BookEvent(
            event_type=BookEventType.ADD,
            symbol="AAPL",
            sequence=i,
            event_time=i * 1000,
            order_id=order_id,
            side=side,
            price=price,
            quantity=qty,
        )
        book.apply(event)
    
    # Trade
    trade_event = BookEvent(
        event_type=BookEventType.EXECUTE,
        symbol="AAPL",
        sequence=3,
        event_time=3000,
        order_id="TRADE_1",
        side=None,
        price=Decimal("150.00"),
        quantity=50.0,
    )
    
    result = simulator.evaluate_fill("A", trade_event)
    fill_event = simulator.create_fill_event(result, trade_event)
    
    assert fill_event is not None
    assert fill_event.symbol == "AAPL"
    assert fill_event.order_id == "A"
    assert fill_event.trade_price == Decimal("150.00")
    assert fill_event.fill_quantity == 50.0
    assert fill_event.remaining_quantity == 50.0
    assert fill_event.sequence == 3
    assert fill_event.event_time == 3000
    print(f"✓ FillEvent: {fill_event}")


if __name__ == "__main__":
    test_passive_fill_at_front()
    test_position_miss()
    test_no_position()
    test_price_rejection()
    test_sell_side()
    test_create_fill_event()
    print("\n✅ All tests passed!")
