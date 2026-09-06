"""Quick test for get_queue_position logic."""

from decimal import Decimal

from research.book.events import BookEvent, BookEventType
from research.book.models import Side
from research.book.order_book import OrderBook
from research.execution.fill_simulator import FillSimulator


def test_get_queue_position():
    """Test queue position retrieval for orders at a price level."""
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Build book state: add 3 BUY orders at $150.00
    add_event_1 = BookEvent(
        event_type=BookEventType.ADD,
        symbol="AAPL",
        sequence=1,
        event_time=1000,
        order_id="ORDER_A",
        side=Side.BUY,
        price=Decimal("150.00"),
        quantity=100.0,
    )
    book.apply(add_event_1)
    
    add_event_2 = BookEvent(
        event_type=BookEventType.ADD,
        symbol="AAPL",
        sequence=2,
        event_time=2000,
        order_id="ORDER_B",
        side=Side.BUY,
        price=Decimal("150.00"),
        quantity=50.0,
    )
    book.apply(add_event_2)
    
    add_event_3 = BookEvent(
        event_type=BookEventType.ADD,
        symbol="AAPL",
        sequence=3,
        event_time=3000,
        order_id="ORDER_C",
        side=Side.BUY,
        price=Decimal("150.00"),
        quantity=75.0,
    )
    book.apply(add_event_3)
    
    # Test: ORDER_A should be at position 0 (front)
    pos_a = simulator.get_queue_position("ORDER_A", Decimal("150.00"))
    assert pos_a is not None, "ORDER_A should exist"
    assert pos_a.order_id == "ORDER_A"
    assert pos_a.sequence_position == 0, f"ORDER_A should be at position 0, got {pos_a.sequence_position}"
    assert pos_a.is_at_front == True
    assert pos_a.orders_ahead == (), f"ORDER_A should have no orders ahead, got {pos_a.orders_ahead}"
    assert pos_a.total_orders_at_level == 3
    print(f"✓ ORDER_A: {pos_a}")
    
    # Test: ORDER_B should be at position 1
    pos_b = simulator.get_queue_position("ORDER_B", Decimal("150.00"))
    assert pos_b is not None
    assert pos_b.order_id == "ORDER_B"
    assert pos_b.sequence_position == 1, f"ORDER_B should be at position 1, got {pos_b.sequence_position}"
    assert pos_b.is_at_front == False
    assert pos_b.orders_ahead == ("ORDER_A",), f"ORDER_B should have ORDER_A ahead, got {pos_b.orders_ahead}"
    assert pos_b.total_orders_at_level == 3
    print(f"✓ ORDER_B: {pos_b}")
    
    # Test: ORDER_C should be at position 2 (back)
    pos_c = simulator.get_queue_position("ORDER_C", Decimal("150.00"))
    assert pos_c is not None
    assert pos_c.order_id == "ORDER_C"
    assert pos_c.sequence_position == 2, f"ORDER_C should be at position 2, got {pos_c.sequence_position}"
    assert pos_c.is_at_front == False
    assert pos_c.orders_ahead == ("ORDER_A", "ORDER_B"), f"ORDER_C should have A,B ahead, got {pos_c.orders_ahead}"
    assert pos_c.total_orders_at_level == 3
    print(f"✓ ORDER_C: {pos_c}")
    
    # Test: Non-existent order returns None
    pos_none = simulator.get_queue_position("FAKE_ORDER", Decimal("150.00"))
    assert pos_none is None, "Non-existent order should return None"
    print("✓ Non-existent order: None")
    
    # Test: Order at wrong price returns None
    pos_wrong = simulator.get_queue_position("ORDER_A", Decimal("151.00"))
    assert pos_wrong is None, "Order at wrong price should return None"
    print("✓ Wrong price: None")
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_get_queue_position()
