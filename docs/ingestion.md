# Data Ingestion Pipeline

## Purpose

The ingestion layer is the controlled boundary between market-data sources and the research codebase. It loads a basket of symbols, preserves the source records, normalizes only the envelope needed by downstream modules, and writes append-only raw partitions that can be replayed later.

The pipeline supports four data layers:

| Layer | Meaning | Initial source |
| --- | --- | --- |
| `trades` | Completed transactions, price, size, conditions, timestamp, and venue | Alpaca historical stock trades |
| `quotes` | Best bid/ask prices, sizes, conditions, timestamp, and venues | Alpaca historical stock quotes |
| `depth` | Multi-level displayed book updates or snapshots | Local file now; venue-specific adapter later |
| `orders` | Add, modify, execute, cancel, and replace events with order references | Local file now; ITCH/order-feed adapter later |

The last two layers are intentionally not fabricated from top-of-book quotes. A quote is not an order event, and a depth snapshot cannot provide exact queue history. Use a licensed venue-level feed for book reconstruction research.

## Alpaca Historical API

`AlpacaHistoricalProvider` uses the official Market Data API:

- `GET https://data.alpaca.markets/v2/stocks/trades`
- `GET https://data.alpaca.markets/v2/stocks/quotes`

Both endpoints accept a comma-separated symbol basket, an inclusive `start`, an inclusive `end`, `feed`, `limit`, `sort`, and `page_token`. The provider follows `next_page_token` until all pages are consumed. Alpaca records retain exchange timestamps and venue fields in the raw payload.

Set credentials in the shell rather than committing them:

```bash
export APCA_API_KEY_ID="..."
export APCA_API_SECRET_KEY="..."
```

The `sip` feed is the appropriate starting point for consolidated U.S. equity research when the subscription permits it. `iex` is a venue feed and may be useful for development, but it is not a substitute for consolidated market coverage. Check the subscription, historical availability, rate limits, and current vendor terms before a run.

Example:

```bash
PYTHONPATH=. python3 -m research.ingest.cli \
  --symbols AAPL MSFT NVDA \
  --start 2026-01-05T14:30:00Z \
  --end 2026-01-06T21:00:00Z \
  --feed sip \
  --output data/raw
```

The command writes records under:

```text
data/raw/
  trades/AAPL/2026-01-05.jsonl
  quotes/AAPL/2026-01-05.jsonl
  ...
```

The output is raw event storage, not an adjusted bar dataset. Do not overwrite it with corporate-action adjustments or inferred trade signs. Those transformations belong in later, versioned stages.

## Local Depth and Order-Level Files

`LocalFileProvider` is the adapter for captured or licensed venue files. It accepts `.jsonl`, `.json`, and `.csv` paths, one path per `DataKind`. Every record must contain:

- `symbol`;
- `event_time` or `t` as an RFC-3339 timestamp;
- optional `received_time`, `sequence`, and `venue` fields.

All other columns remain in `payload`, so feed-specific fields are not discarded. Example wiring:

```python
from datetime import datetime, timezone

from research.ingest import DataKind, IngestionPipeline, IngestionRequest
from research.ingest.providers import LocalFileProvider
from research.ingest.storage import JsonlEventSink

request = IngestionRequest(
    symbols=("AAPL", "MSFT"),
    start=datetime(2026, 1, 5, tzinfo=timezone.utc),
    end=datetime(2026, 1, 6, tzinfo=timezone.utc),
)
provider = LocalFileProvider({
    DataKind.DEPTH: "captures/depth.jsonl",
    DataKind.ORDERS: "captures/orders.jsonl",
})
counts = IngestionPipeline(provider, JsonlEventSink("data/raw")).run(
    request, (DataKind.DEPTH, DataKind.ORDERS)
)
print(counts)
```

For Nasdaq TotalView-ITCH-style data, retain the feed sequence number and exchange timestamp. Packet-gap detection and retransmission handling belong in the feed adapter before events enter `RawMarketEvent`; never silently sort around a sequence gap.

## Normalized Event Contract

Each `RawMarketEvent` contains:

| Field | Rule |
| --- | --- |
| `symbol` | Uppercase ticker used for partitioning and basket filtering |
| `kind` | `trades`, `quotes`, `depth`, or `orders` |
| `event_time` | Time assigned by the source; timezone-aware |
| `received_time` | Optional local capture time; never substitute it for event time |
| `sequence` | Optional source sequence or order-event sequence |
| `venue` | Optional exchange or market center identifier |
| `payload` | Untouched provider record |
| `source` | Provider or capture identifier |

The event envelope is deliberately provider-neutral. Downstream book reconstruction can depend on `sequence` and `payload` without knowing whether the event came from a REST response, a CSV capture, or a binary-feed decoder.

## Data-Quality Rules

Before data is used by a backtest, add validation for:

1. missing or duplicate records;
2. sequence gaps and out-of-order events;
3. timestamps outside the requested interval;
4. invalid prices, sizes, symbols, or venue codes;
5. stale, crossed, or locked quote states where the feed rules do not explain them;
6. halts, early closes, daylight-saving transitions, and auction periods;
7. vendor corrections, cancellations, and trade conditions.

The current ingestion layer preserves records and filters local files by interval. It does not claim to provide full feed-quality validation yet; that is the next implementation milestone before book reconstruction.

## Source References

- [Alpaca historical trades](https://docs.alpaca.markets/reference/stocktrades-1)
- [Alpaca historical quotes](https://docs.alpaca.markets/reference/stockquotes-1)
- [Nasdaq TotalView-ITCH specifications](https://www.nasdaqtrader.com/Trader.aspx?id=ITCH)

Vendor access, redistribution rights, and exchange licensing must be reviewed before storing or sharing market data outside the permitted use.