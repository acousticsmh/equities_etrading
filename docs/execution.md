# Execution Module

**Purpose:** Simulate passive fills for orders in a reconstructed order book using FIFO queue-position verification.

The execution module answers the question: **"Would my order have been filled?"** by checking whether the order was at the front of its price level's FIFO queue when a trade occurred at or through that price.

---

## Architecture

### Component Ownership

| Component | Purpose | Dependencies |
|-----------|---------|--------------|
| **FillSimulator** | Passive fill evaluation and queue position lookup | OrderBook (read-only) |
| **ExecutionResult** | Immutable fill evaluation result | – |
| **FillEvent** | Audit record of a fill execution | ExecutionResult |
| **QueuePosition** | FIFO queue snapshot for an order at a price level | – |
| **ExecutionValidator** | Diagnostic checks on results (non-blocking) | ExecutionResult |

### Data Flow

```
OrderBook (state)
     ↓
FillSimulator.evaluate_fill(order_id, trade_event)
     ↓
ExecutionResult (fill_type, queue_position, quantity)
     ↓
[Optional] ExecutionValidator.validate_result(result)
     ↓
FillEvent (audit record)
```

---

## Core Concepts

### Passive Fill

A **passive fill** occurs when:
1. A resting order exists in the order book at a price level
2. A trade occurs at or through that price
3. The resting order is **at the front of the FIFO queue** at that price level

Example:
```
Book state at $150.00 (BID):
  Order A (100 shares) ← front of queue
  Order B (50 shares)
  Order C (75 shares)

Trade event: 100 shares sold at $150.00

Result for Order A: PASSIVE_FILL (100 shares filled)
Result for Order B: POSITION_MISS (not at front)
Result for Order C: POSITION_MISS (not at front)
```

### Position Miss

A **position miss** occurs when an order exists at the correct price but is not at the front of the queue, so it doesn't get filled despite liquidity available.

### No Position

**No position** indicates the order doesn't exist in the book at the evaluated price level, or doesn't exist at all.

---

## Usage

### Basic Fill Simulation

```python
from datetime import datetime
from decimal import Decimal

from research.book.order_book import OrderBook
from research.book.events import BookEvent, BookEventType
from research.book.models import Side
from research.execution import FillSimulator

# Initialize order book and simulator
book = OrderBook(symbol="AAPL")
simulator = FillSimulator(book=book)

# Replay events to build state...
for event in events:
    book.apply(event)

# Evaluate if your order would be filled by a trade
trade_event = BookEvent(
    event_type=BookEventType.EXECUTE,
    symbol="AAPL",
    sequence=1000,
    event_time=datetime.now(),
    order_id="MARKET_BUY",  # not our order
    side=Side.BUY,
    price=Decimal("150.50"),
    quantity=Decimal("200.0"),
)

result = simulator.evaluate_fill(order_id="MY_SELL_001", trade_event=trade_event)

print(f"Fill type: {result.fill_type.name}")
print(f"Filled quantity: {result.fill_quantity}")
print(f"Queue position: {result.queue_position}")
```

### Checking Queue Position

```python
# Get the queue position of an order at a price level
queue_pos = simulator.get_queue_position(
    order_id="MY_ORDER", price=Decimal("150.50")
)

if queue_pos and queue_pos.is_at_front:
    print(f"Order is at front of {queue_pos.total_orders_at_level} orders at $150.50")
    print(f"Orders ahead: {queue_pos.orders_ahead}")
else:
    print("Order not at front or doesn't exist at price")
```

### Creating Audit Records

```python
# Convert fill result to immutable audit record
if result.fill_type == FillType.PASSIVE_FILL:
    fill_event = simulator.create_fill_event(result, trade_event)
    print(f"Filled {fill_event.fill_quantity} shares at ${fill_event.trade_price}")
    print(f"Remaining: {fill_event.remaining_quantity} shares")
```

### Diagnostic Validation

```python
from research.execution import ExecutionValidator

# Run all diagnostics on a result (non-blocking, for logging/warnings)
diagnostics = ExecutionValidator.validate_result(result)

for diag in diagnostics:
    if not diag.passed:
        print(f"[{diag.severity}] {diag.warning}")
```

---

## Fill Simulation Rules

### Fill Eligibility

An order is eligible for a passive fill if:

| Condition | Rule |
|-----------|------|
| **Order exists** | Order must be in the order book's OrderStore |
| **Symbol matches** | Order symbol must equal trade symbol |
| **Side opposition** | Order side must be opposite to trade direction |
| **Price crossing** | Order price must be at or better than trade price |
| **Queue position** | Order must be at the front (position 0) of its price level |

### Trade Direction Inference

The FillSimulator infers trade direction from the EXECUTE event:

- If `event.price >= book.top_of_book().ask_price`: **BUY** (aggressor hitting the ask)
- If `event.price <= book.top_of_book().bid_price`: **SELL** (aggressor hitting the bid)
- Otherwise: **Indeterminate** (no fill)

*Note:* This logic can be overridden or enhanced for venue-specific trade indicators.

### Fill Quantity

Fill quantity is determined by:
```python
fill_qty = min(order.remaining_quantity, trade_event.quantity)
```

If the trade quantity is less than the remaining order quantity, only a partial fill occurs. The order remains in the book with updated `remaining_quantity`.

---

## Immutable Data Structures

### QueuePosition

Captures the FIFO position of an order at a price level:

```python
@dataclass(frozen=True)
class QueuePosition:
    order_id: str              # The order being positioned
    sequence_position: int     # 0-based position (0 = front)
    orders_ahead: tuple[str]   # Order IDs ahead in FIFO order
    total_orders_at_level: int # Total orders at this price
    
    @property
    def is_at_front(self) -> bool:
        return self.sequence_position == 0
```

### ExecutionResult

Captures the full result of a fill evaluation:

```python
@dataclass(frozen=True)
class ExecutionResult:
    trade_symbol: str                    # Trade's symbol
    trade_quantity: Decimal              # Trade's quantity
    order_id: str                        # Order evaluated
    fill_type: FillType                  # PASSIVE_FILL, POSITION_MISS, or NO_POSITION
    queue_position: QueuePosition | None # Queue snapshot (if order exists)
    fill_quantity: Decimal               # Qty filled (0 if no fill)
    remaining_quantity: Decimal          # Order qty after fill
```

### FillEvent

Audit record for a fill execution:

```python
@dataclass(frozen=True)
class FillEvent:
    symbol: str                  # Symbol of filled order
    order_id: str                # Order ID
    trade_price: Decimal         # Price at which filled
    fill_quantity: Decimal       # Quantity filled
    remaining_quantity: Decimal  # Remaining after fill
    sequence: int                # Event sequence number
    event_time: datetime         # Source event timestamp
    queue_position_at_fill: int  # Queue position when filled
```

---

## Validation & Diagnostics

The `ExecutionValidator` provides non-blocking diagnostic checks:

| Check | Purpose |
|-------|---------|
| `validate_fill_quantity()` | Ensures fill qty is consistent with order and trade size |
| `validate_queue_position()` | Verifies queue position matches fill type |
| `validate_remaining_quantity()` | Checks remaining qty is valid (non-negative) |

**Key Difference from BookValidator:**
- `BookValidator` (in book module) **rejects** invalid events before state mutation
- `ExecutionValidator` **logs warnings** without blocking, for diagnostics only

Example:
```python
diags = ExecutionValidator.validate_result(result)
for diag in diags:
    if diag.severity == "error":
        logger.error(diag.warning)
```

---

## Integration with Order Book

The FillSimulator is a **read-only consumer** of the OrderBook. It does not mutate state. To apply fills to the order book, downstream code should:

1. Call `simulator.evaluate_fill()` to get the ExecutionResult
2. Verify `result.fill_type == FillType.PASSIVE_FILL`
3. Call `book.execute_order()` with the appropriate quantity to mutate the book

Example:
```python
result = simulator.evaluate_fill(order_id="MY_ORDER", trade_event=trade_event)

if result.fill_type == FillType.PASSIVE_FILL:
    # Apply the fill to the book
    execute_event = BookEvent(
        event_type=BookEventType.EXECUTE,
        symbol=result.trade_symbol,
        sequence=trade_event.sequence + 1,  # Increment sequence
        event_time=trade_event.event_time,
        order_id=result.order_id,
        side=None,  # EXECUTE doesn't require side
        price=trade_event.price,  # Price at which filled
        quantity=result.fill_quantity,  # Fill quantity
    )
    book.apply(execute_event)
```

---

## Design Rationale

### Why Queue Position Matters

In electronic markets, fills are allocated by **exchange matching rules**, typically:
- **FIFO at price:** Orders at the same price are filled in the sequence received
- **Price/time priority:** Orders at better prices are prioritized, then FIFO within price

The FillSimulator models the **FIFO at price** model, which is the most common for equities.

### Why Not Accept All Trades?

Without queue-position checking, a simple simulation might:
- Fill all orders at a price when any trade occurs (unrealistic)
- Overfill orders (fill more than trade quantity allows)
- Ignore liquidity aggregation (orders at better prices)

Queue-position verification ensures fills match realistic venue behavior.

### Passive vs. Aggressive

- **Passive fill:** Resting order that gets filled by an incoming aggressive order
- **Aggressive order:** Market order or aggressive limit order that initiates the fill

This module simulates fills for **passive orders** (already in the book). Matching engines and aggressive execution logic belong in a future trading simulator module.

---

## Future Extensions

### 1. Trade Direction Inference Refinement
Currently, trade direction is inferred from price vs. best bid/ask. Future enhancements:
- Accept `trade_side` as an explicit parameter from the event stream
- Use venue-specific indicators (e.g., ITCH trade flags)
- Implement more sophisticated aggressor detection

### 2. ProRata Allocation
For venues with **pro-rata** (size-weighted) fills instead of pure FIFO:
- Implement `get_allocation_ratio()` based on order size and level size
- Calculate `fill_quantity = trade_quantity * allocation_ratio`

### 3. Partial Fill Tracking
Currently, a partial fill reduces `remaining_quantity` but doesn't re-position the order in the queue. Future:
- Option to re-sort queues after partial fills (for certain exchange rules)
- Track fill history per order

### 4. Multi-Leg Order Support
Extend to handle:
- Spread orders (simultaneous buy/sell at different prices)
- Conditional orders (fill one leg only if other fills)
- Options orders (complex position sizing)

### 5. Performance Optimization
For high-frequency simulation:
- Cache queue position lookup results
- Index orders by (symbol, price, order_id) for O(1) access
- Batch-evaluate multiple orders at once

---

## Testing

See `test_execution_complete.py` and `test_get_queue_position.py` for:
- Queue position retrieval (existing, non-existing orders)
- Passive fill evaluation (eligible fills, position misses)
- Fill event creation (audit records)
- Diagnostic validation (consistency checks)

Example test:
```python
def test_passive_fill_when_at_front():
    book = OrderBook(symbol="AAPL")
    simulator = FillSimulator(book=book)
    
    # Build book state with order at front of queue
    add_event = BookEvent(...)
    book.apply(add_event)
    
    # Evaluate fill from a trade at that price
    trade_event = BookEvent(...)
    result = simulator.evaluate_fill(order_id="MY_ORDER", trade_event=trade_event)
    
    assert result.fill_type == FillType.PASSIVE_FILL
    assert result.queue_position.is_at_front
    assert result.fill_quantity > 0
```

---

## References

- **Order Book Module:** `research/book/` — Provides order state and FIFO queues
- **Book Event Types:** `research/book/events.py` — Event definitions for replay
- **Order Models:** `research/book/models.py` — Side, BookOrder, etc.

---

## Summary

The execution module provides a **read-only simulation layer** for passive fills in a reconstructed order book. By checking queue position at the moment a trade occurs, it enables realistic backtesting and strategy evaluation based on actual venue fill semantics.

**Key Takeaway:** Fills are not automatic; they depend on queue position. Orders not at the front of their queue don't get filled, even if liquidity is available. This module makes that explicit and auditable.
