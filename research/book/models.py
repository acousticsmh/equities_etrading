from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"

@dataclass
class BookOrder:
    order_id: str
    symbol: str
    side: Side
    price: Decimal
    quantity: Decimal
    remaining_quantity: Decimal
    sequence: int
    timestamp: datetime
    venue: str | None = None
    received_time: datetime | None = None