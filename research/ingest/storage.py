"""Durable raw-event storage."""

import json
from dataclasses import asdict
from pathlib import Path

from .models import RawMarketEvent


class JsonlEventSink:
    """Write append-only JSONL partitions by data kind, symbol, and UTC date."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def write(self, event: RawMarketEvent) -> Path:
        path = self.root / event.kind.value / event.symbol / f"{event.event_time:%Y-%m-%d}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = asdict(event)
        record["kind"] = event.kind.value
        record["event_time"] = event.event_time.isoformat()
        if event.received_time:
            record["received_time"] = event.received_time.isoformat()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
        return path