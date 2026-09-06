"""Execution-domain types and data structures.

Provides immutable views and results for fill simulation, queue position tracking,
and execution diagnostics.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto


class FillType(Enum):
    """Categorizes the type of execution result."""

    PASSIVE_FILL = auto()
    """Order was at front of queue when trade occurred; passive fill."""

    POSITION_MISS = auto()
    """Order was not at front of queue; missed fill opportunity."""

    NO_POSITION = auto()
    """Order does not exist at the price level."""


@dataclass(frozen=True)
class QueuePosition:
    """Immutable queue position snapshot for an order at a price level."""

    order_id: str
    """Unique order identifier."""

    sequence_position: int
    """0-based position in FIFO queue (0 = front, n-1 = back)."""

    orders_ahead: tuple[str, ...]
    """Order IDs ahead of this order in the queue (front to back)."""

    total_orders_at_level: int
    """Total number of orders at this price level."""

    @property
    def is_at_front(self) -> bool:
        """True if this order is at the front of the queue."""
        return self.sequence_position == 0

    def __repr__(self) -> str:
        return (
            f"QueuePosition(order_id={self.order_id}, "
            f"sequence_position={self.sequence_position}, "
            f"orders_ahead={self.orders_ahead}, "
            f"total_orders_at_level={self.total_orders_at_level})"
        )


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable result of a fill simulation for a trade event."""

    trade_symbol: str
    """Symbol of the trade that triggered the evaluation."""

    trade_quantity: Decimal
    """Quantity of the trade (remaining liquidity to fill)."""

    order_id: str
    """Order ID being evaluated for passive fill."""

    fill_type: FillType
    """Categorization of the result (passive fill, miss, or no position)."""

    queue_position: QueuePosition | None
    """Queue position snapshot if order exists at the price level; else None."""

    fill_quantity: Decimal
    """Quantity filled from the trade (0.0 if no fill)."""

    remaining_quantity: Decimal
    """Remaining order quantity after fill (0.0 if fully filled)."""

    def __repr__(self) -> str:
        return (
            f"ExecutionResult(trade_symbol={self.trade_symbol}, "
            f"trade_quantity={self.trade_quantity}, "
            f"order_id={self.order_id}, "
            f"fill_type={self.fill_type.name}, "
            f"queue_position={self.queue_position}, "
            f"fill_quantity={self.fill_quantity}, "
            f"remaining_quantity={self.remaining_quantity})"
        )


@dataclass(frozen=True)
class FillEvent:
    """Immutable record of a fill execution for audit/analytics."""

    symbol: str
    """Symbol of the filled order."""

    order_id: str
    """Order ID that was filled."""

    trade_price: Decimal
    """Price at which the fill occurred."""

    fill_quantity: Decimal
    """Quantity filled in this execution."""

    remaining_quantity: Decimal
    """Remaining quantity on the order after this fill."""

    sequence: int
    """Event sequence number from the trade."""

    event_time: datetime
    """Timestamp of the source book event."""

    queue_position_at_fill: int
    """Queue position when fill occurred (0 = front of queue)."""

    def __repr__(self) -> str:
        return (
            f"FillEvent(symbol={self.symbol}, "
            f"order_id={self.order_id}, "
            f"trade_price={self.trade_price}, "
            f"fill_quantity={self.fill_quantity}, "
            f"remaining_quantity={self.remaining_quantity}, "
            f"sequence={self.sequence}, "
            f"event_time={self.event_time}, "
            f"queue_position_at_fill={self.queue_position_at_fill})"
        )
        
