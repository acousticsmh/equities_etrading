# Order-Book Reconstruction

## Purpose

The `research/book/` module replays normalized order-level events into a deterministic, venue-level limit order book. It is the source of truth for displayed liquidity used by later feature and execution modules.

The module maintains:

- individual active orders and their remaining quantities;
- FIFO order queues at each price level;
- price priority across bid and ask ladders;
- replay sequence and event-time metadata;
- read-only top-of-book and depth snapshots;
- validation of event shape and book-state invariants.

It does not infer trades, calculate signals, simulate fills, or connect to a venue.

## Component Ownership

| Component | Responsibility |
| --- | --- |
| `models.py` | `Side` and mutable `BookOrder` state |
| `events.py` | Immutable `BookEvent` and `BookEventType` definitions |
| `orders.py` | Lookup and storage of active orders by order ID |
| `price_levels.py` | FIFO queues at one price and bid/ask price ladders |
| `order_book.py` | Event dispatch, lifecycle mutation, replay metadata, and snapshots |
| `snapshots.py` | Immutable `BookLevel`, `TopOfBook`, and `BookSnapshot` views |
| `validators.py` | Event-shape checks and full book-state invariants |

The dependency direction is:

```text
BookEvent -> OrderBook -> OrderStore + PriceLadder -> BookSnapshot
                 |
                 +-> BookValidator
```

`PriceLevel` stores order IDs in arrival order. `OrderStore` stores the full mutable order objects. This separation preserves FIFO queue ordering while allowing executions and cancellations to update remaining quantity in one place.

`PriceLadder` keeps its levels in a `sortedcontainers.SortedDict` keyed by price, so the best price is an O(log n) lookup and a depth walk needs no re-sort. `PriceLevel` maintains its aggregate resting quantity incrementally as orders are appended, removed, or reduced, rather than summing the queue on every read.

## Event Lifecycle

`OrderBook.apply()` dispatches using `BookEventType` members. Each successful mutation records the event sequence, the exchange event time, and the local receipt time (`received_time`), which flows through `BookEvent` and `BookOrder` from the ingest layer rather than being collapsed into a single timestamp.

### Add

An add event requires an order ID, side, positive price, and positive quantity. The book creates a `BookOrder`, stores it in `OrderStore`, and appends its ID to the correct price-level queue.

### Execute

An execution reduces `remaining_quantity`. Partial executions leave the order in its FIFO position. When the remaining quantity reaches zero, the order and its empty price level are removed.

### Cancel

Cancellation uses the same quantity convention as execution: `event.quantity` is the number of shares removed. Partial cancellation reduces the live order size; a full cancellation removes the order and empty level.

### Modify

Modify is intentionally reduction-only. A size reduction updates `remaining_quantity` in place and preserves queue position. Increasing size, changing price, or otherwise re-entering the queue belongs to replace behavior.

### Replace

Replace changes price and quantity, removes the order from its old FIFO queue, and appends it to the new price queue. The replacement quantity becomes both the order's new original quantity and its remaining quantity. Empty old levels are removed.

### Clear

A clear event removes all active orders and all bid/ask levels while preserving the clear event's sequence and timestamp as replay metadata.

## Replay Contract

`OrderBook` tracks:

```python
last_sequence: int | None
last_event_time: datetime | None
```

After the first event, every next event must have exactly `last_sequence + 1`. Missing, duplicate, and out-of-order sequence numbers raise `ValueError` before book state changes. This makes packet loss visible instead of silently producing an incomplete book.

Snapshot metadata comes from the last successfully applied event, not from currently active orders or the local wall clock. Consequently, a snapshot remains correctly timestamped after the book becomes empty.

This strict policy assumes the input has already been scoped to one venue and one replay sequence. A feed adapter must handle session resets, packet retransmission, and stream boundaries before events reach `OrderBook`.

## Validation

`BookValidator` has two responsibilities:

1. `validate_event()` checks event shape: supported event type, symbol presence, required IDs, valid side, positive prices, and positive quantities.
2. `validate_state()` checks the reconstructed book: every stored order appears exactly once, each order matches its side and price level, quantities are valid, levels contain live liquidity, and the best bid is below the best ask.

`OrderBook` retains checks that require current state, including whether an order exists, whether a quantity exceeds its live size, whether a price level exists, and whether the event belongs to this symbol's book.

## Snapshot Views

`top_of_book()` returns the best bid and ask prices plus aggregate live size at each price. `depth(levels=5)` returns up to five bid and ask levels as immutable `BookLevel` values:

- bids are ordered from highest price to lowest;
- asks are ordered from lowest price to highest;
- quantity is the sum of each order's `remaining_quantity`;
- `order_count` counts active order IDs at the level.

These views do not expose mutable internal queues to downstream feature code.

## Testing Expectations

The book module should be tested with small, hand-verifiable event sequences before replaying production-sized captures. The current tests cover:

- add and FIFO queue placement;
- partial and complete execution;
- partial and complete cancellation;
- depth aggregation and price ordering;
- replacement cleanup and quantity updates;
- clear events and empty-book snapshot metadata;
- sequence-gap rejection;
- reduction-only modify behavior;
- event and state validation.

The next integration milestone is an adapter that maps one venue's raw order messages into `BookEvent` without losing exchange sequence numbers, timestamps, order IDs, or lifecycle semantics.