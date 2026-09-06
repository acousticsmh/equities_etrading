"""Passive fill simulation using queue-position verification.

The FillSimulator evaluates whether an order at a given price level would be
filled by an observed trade, based on FIFO queue position. Passive fills occur
only when the order is at the front of the queue when the trade occurs.
"""

from dataclasses import dataclass
from decimal import Decimal

from research.book.events import BookEvent
from research.book.models import Side
from research.book.order_book import OrderBook
from research.execution.models import (ExecutionResult, FillEvent, FillType,
                                       QueuePosition)


@dataclass
class FillSimulator:
    """Evaluates passive fills for orders in an order book.

    Given a trade event (market order or execution) and an order book state,
    determines whether a passive resting order would be filled based on its
    queue position at the price level.

    Attributes:
        book: The OrderBook instance to query for position and state.
    """

    book: OrderBook

    def get_queue_position(self, order_id: str, price: Decimal) -> QueuePosition | None:
        """Retrieve the queue position of an order at a given price level.

        Args:
            order_id: Order ID to locate in the queue.
            price: Price level to check.

        Returns:
            QueuePosition snapshot if order exists at the level; None otherwise.
        """
        order = self.book.orders.get(order_id)
        if order is None:
            return None
        if order.side == Side.BUY:
            level = self.book.bids.get(price)
        elif order.side == Side.SELL:
            level = self.book.asks.get(price)
        else:
            return None
        if level is None or order_id not in level.orders:
            return None
        orders_ahead: list[str] = []
        sequence_position = None
        for position, queued_order_id in enumerate(level.orders):
            if queued_order_id == order_id:
                sequence_position = position
                break
            orders_ahead.append(queued_order_id)

        if sequence_position is None:
            return None

        return QueuePosition(
            order_id=order_id,
            sequence_position=sequence_position,
            orders_ahead=tuple(orders_ahead),
            total_orders_at_level=len(level.orders),
        )



    def evaluate_fill(
        self, order_id: str, trade_event: BookEvent
    ) -> ExecutionResult:
        """Evaluate whether an order would be passively filled by a trade event.

        For a passive fill to occur:
        1. Order must exist in the order book
        2. Order side must be opposite to trade direction
        3. Order price must be at or better than trade price
        4. Order must be at the front of its price level's FIFO queue

        Args:
            order_id: Order ID to evaluate for fill.
            trade_event: BookEvent representing a trade (EXECUTE or market fill).

        Returns:
            ExecutionResult with fill type, queue position, and quantity details.
        """
        # Step 1: Retrieve order from book
        order = self.book.orders.get(order_id)
        trade_quantity = (
            Decimal(str(trade_event.quantity))
            if trade_event.quantity is not None
            else Decimal("0")
        )
        if order is None:
            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.NO_POSITION,
                queue_position=None,
                fill_quantity=Decimal("0"),
                remaining_quantity=Decimal("0"),
            )

        # Step 2: Check that symbols match
        if order.symbol != trade_event.symbol:
            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.NO_POSITION,
                queue_position=None,
                fill_quantity=Decimal("0"),
                remaining_quantity=order.remaining_quantity,
            )

        if trade_event.price is None:
            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.NO_POSITION,
                queue_position=None,
                fill_quantity=Decimal("0"),
                remaining_quantity=order.remaining_quantity,
            )

        # Step 3: Infer trade direction from event
        trade_side = self._infer_trade_side(trade_event)

        # Step 4: Order can only be passively filled if its side is opposite to trade
        if trade_side is None or order.side == trade_side:
            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.NO_POSITION,
                queue_position=None,
                fill_quantity=Decimal("0"),
                remaining_quantity=order.remaining_quantity,
            )

        # Step 5: Check if order price is at or better than trade price
        if not self._is_price_acceptable(order.side, order.price, trade_event.price):
            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.NO_POSITION,
                queue_position=None,
                fill_quantity=Decimal("0"),
                remaining_quantity=order.remaining_quantity,
            )

        # Step 6: Get queue position at the order's price level
        queue_pos = self.get_queue_position(order_id, order.price)
        if queue_pos is None:
            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.NO_POSITION,
                queue_position=None,
                fill_quantity=Decimal("0"),
                remaining_quantity=order.remaining_quantity,
            )

        # Step 7: Determine fill type based on queue position
        if queue_pos.is_at_front:
            # Passive fill: order is at front of queue
            fill_qty = min(order.remaining_quantity, trade_quantity)
            remaining_qty = order.remaining_quantity - fill_qty

            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.PASSIVE_FILL,
                queue_position=queue_pos,
                fill_quantity=fill_qty,
                remaining_quantity=remaining_qty,
            )
        else:
            # Position miss: order exists but not at front
            return ExecutionResult(
                trade_symbol=trade_event.symbol,
                trade_quantity=trade_quantity,
                order_id=order_id,
                fill_type=FillType.POSITION_MISS,
                queue_position=queue_pos,
                fill_quantity=Decimal("0"),
                remaining_quantity=order.remaining_quantity,
            )

    def create_fill_event(
        self, result: ExecutionResult, trade_event: BookEvent
    ) -> FillEvent | None:
        """Create an immutable FillEvent record from an ExecutionResult.

        Returns None if the result indicates no fill occurred.

        Args:
            result: ExecutionResult from evaluate_fill().
            trade_event: Original BookEvent that was evaluated.

        Returns:
            FillEvent if fill_quantity > 0; else None.
        """
        if result.fill_quantity <= Decimal("0"):
            return None

        if result.queue_position is None:
            return None

        if trade_event.price is None:
            return None

        return FillEvent(
            symbol=result.trade_symbol,
            order_id=result.order_id,
            trade_price=trade_event.price,
            fill_quantity=result.fill_quantity,
            remaining_quantity=result.remaining_quantity,
            sequence=trade_event.sequence,
            event_time=trade_event.event_time,
            queue_position_at_fill=result.queue_position.sequence_position,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _infer_trade_side(self, event: BookEvent) -> Side | None:
        """Infer the aggressor side from an execution event.

        For an EXECUTE event, we assume the aggressor determines the direction.
        In a market reconstruction:
        - If price >= best_ask, likely BUY (aggressor hitting the ask)
        - If price <= best_bid, likely SELL (aggressor hitting the bid)

        Args:
            event: BookEvent to infer trade side from.

        Returns:
            Side (BUY or SELL) of the aggressor; None if indeterminate.
        """
        # Event must have a price to infer direction
        if event.price is None:
            return None

        best_bid = self.book.bids.best_price()
        best_ask = self.book.asks.best_price()

        # If no bid/ask, can't infer direction
        if best_bid is None or best_ask is None:
            return None

        # Trade at or above best ask: BUY (aggressor buying)
        if event.price >= best_ask:
            return Side.BUY

        # Trade at or below best bid: SELL (aggressor selling)
        if event.price <= best_bid:
            return Side.SELL

        # Trade between bid and ask: indeterminate
        return None

    def _is_price_acceptable(self, order_side: Side, order_price: Decimal, trade_price: Decimal) -> bool:
        """Check if trade price is at or better than order price.

        Args:
            order_side: Side of the resting order (BUY or SELL).
            order_price: Price of the resting order.
            trade_price: Price of the trade.

        Returns:
            True if the trade would fill the order; False otherwise.
        """
        if order_side == Side.BUY:
            # Buy order filled if trade price <= order price
            return trade_price <= order_price
        else:  # SELL
            # Sell order filled if trade price >= order price
            return trade_price >= order_price
