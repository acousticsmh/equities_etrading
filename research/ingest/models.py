"""Common types shared by data providers and storage."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class DataKind(StrEnum):
    """The market-data layers consumed by the research pipeline."""

    TRADES = "trades"
    QUOTES = "quotes"
    DEPTH = "depth"
    ORDERS = "orders"


@dataclass(frozen=True, slots=True)
class IngestionRequest:
    """A bounded request for one basket and one time interval."""

    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    feed: str = "sip"

    def __post_init__(self) -> None:
        normalized = tuple(dict.fromkeys(symbol.upper().strip() for symbol in self.symbols))
        if not normalized or any(not symbol for symbol in normalized):
            raise ValueError("symbols must contain at least one non-empty ticker")
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if self.start >= self.end:
            raise ValueError("start must be before end")
        object.__setattr__(self, "symbols", normalized)


@dataclass(frozen=True, slots=True)
class RawMarketEvent:
    """A normalized envelope that retains the provider payload unchanged."""

    symbol: str
    kind: DataKind
    event_time: datetime
    payload: Mapping[str, Any]
    source: str
    received_time: datetime | None = None
    sequence: int | None = None
    venue: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")
        if self.received_time is not None and self.received_time.tzinfo is None:
            raise ValueError("received_time must be timezone-aware")
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")