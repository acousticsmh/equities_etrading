"""Execution simulation module for passive fill tracking and queue verification.

This module provides tools for simulating fills based on queue position in an
order book, validating that passive orders would be executed when they reach
the front of the FIFO queue at their price level.

Key Components:
    FillSimulator: Evaluates passive fills using queue position verification.
    ExecutionResult: Immutable result of a fill simulation.
    FillEvent: Immutable audit record of a fill execution.
    QueuePosition: FIFO position snapshot for an order at a price level.
    ExecutionValidator: Diagnostic checks on fill results (non-blocking).

Example:
    >>> from research.book.order_book import OrderBook
    >>> from research.book.events import BookEvent, BookEventType
    >>> from research.execution.fill_simulator import FillSimulator
    >>>
    >>> book = OrderBook(symbol="AAPL")
    >>> simulator = FillSimulator(book=book)
    >>>
    >>> # After replaying events to build book state...
    >>> trade_event = BookEvent(
    ...     event_type=BookEventType.EXECUTE,
    ...     symbol="AAPL",
    ...     sequence=1000,
    ...     event_time=1234567890,
    ...     order_id="TRADE_1",
    ...     side=Side.BUY,
    ...     price=150.5,
    ...     quantity=100.0,
    ... )
    >>>
    >>> result = simulator.evaluate_fill(order_id="MY_SELL_ORDER", trade_event=trade_event)
    >>> print(result.fill_type, result.fill_quantity)
"""

from research.execution.fill_simulator import FillSimulator
from research.execution.models import (ExecutionResult, FillEvent, FillType,
                                       QueuePosition)
from research.execution.validators import (ExecutionDiagnostic,
                                           ExecutionValidator)

__all__ = [
    "FillSimulator",
    "ExecutionResult",
    "FillEvent",
    "FillType",
    "QueuePosition",
    "ExecutionValidator",
    "ExecutionDiagnostic",
]
