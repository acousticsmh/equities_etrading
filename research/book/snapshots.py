
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    quantity: Decimal
    order_count: int

@dataclass(frozen=True)
class TopOfBook:
    bid_price: Decimal | None
    bid_size: Decimal
    ask_price: Decimal | None
    ask_size: Decimal


@dataclass(frozen=True)
class BookSnapshot:
    symbol: str
    event_time: datetime
    sequence: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]

    @property
    def best_bid(self) -> BookLevel | None:
        if not self.bids:
            return None
        return max(self.bids, key=lambda level: level.price)
    @property
    def best_ask(self) -> BookLevel | None:
        if not self.asks:
            return None
        return min(self.asks, key=lambda level: level.price)