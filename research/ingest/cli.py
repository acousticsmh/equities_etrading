"""Command-line entry point for Alpaca basket ingestion."""

import argparse
from datetime import datetime, timezone

from .models import DataKind, IngestionRequest
from .pipeline import IngestionPipeline
from .providers import AlpacaHistoricalProvider
from .storage import JsonlEventSink


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Alpaca historical equity trades and quotes")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start", required=True, help="RFC-3339 timestamp, inclusive")
    parser.add_argument("--end", required=True, help="RFC-3339 timestamp, exclusive")
    parser.add_argument("--output", default="data/raw")
    parser.add_argument("--feed", default="sip", choices=("sip", "iex", "otc", "boats"))
    parser.add_argument("--kinds", nargs="+", choices=[kind.value for kind in DataKind], default=["trades", "quotes"])
    args = parser.parse_args()
    request = IngestionRequest(
        symbols=tuple(args.symbols),
        start=_timestamp(args.start),
        end=_timestamp(args.end),
        feed=args.feed,
    )
    counts = IngestionPipeline(AlpacaHistoricalProvider(), JsonlEventSink(args.output)).run(
        request, (DataKind(kind) for kind in args.kinds)
    )
    for kind, count in counts.items():
        print(f"{kind.value}: {count}")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


if __name__ == "__main__":
    main()