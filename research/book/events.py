
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from .models import Side


class BookEventType(StrEnum):
    ADD = "add"
    MODIFY = "modify"
    CANCEL = "cancel"
    EXECUTE = "execute"
    REPLACE = "replace"
    CLEAR = "clear"


@dataclass(frozen=True)
class BookEvent:
    event_type: BookEventType
    symbol: str
    sequence: int
    event_time: datetime
    order_id: str | None
    side: Side | None
    price: Decimal | None
    quantity: Decimal | None
    new_price: Decimal | None = None
    venue: str | None = None
    # Local receipt time, carried through from the ingest layer alongside
    # exchange event_time and the monotonic sequence number.
    received_time: datetime | None = None