import json
from datetime import datetime, timezone

from research.ingest import DataKind, IngestionPipeline, IngestionRequest, JsonlEventSink
from research.ingest.providers import LocalFileProvider, UnsupportedDataKind


def test_local_provider_filters_basket_and_interval(tmp_path):
    path = tmp_path / "trades.jsonl"
    records = [
        {"symbol": "aapl", "t": "2026-01-05T14:30:00Z", "p": 100, "s": 10},
        {"symbol": "MSFT", "t": "2026-01-05T14:31:00Z", "p": 200, "s": 5},
        {"symbol": "TSLA", "t": "2026-01-05T14:31:00Z", "p": 300, "s": 2},
        {"symbol": "AAPL", "t": "2026-01-06T14:30:00Z", "p": 101, "s": 4},
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    request = IngestionRequest(
        symbols=("AAPL", "MSFT"),
        start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        end=datetime(2026, 1, 6, tzinfo=timezone.utc),
    )

    events = list(LocalFileProvider({DataKind.TRADES: path}).fetch(DataKind.TRADES, request))

    assert [event.symbol for event in events] == ["AAPL", "MSFT"]
    assert events[0].payload["p"] == 100


def test_pipeline_partitions_events_by_kind_symbol_and_date(tmp_path):
    path = tmp_path / "quotes.csv"
    path.write_text(
        "symbol,event_time,bid_price\nAAPL,2026-01-05T14:30:00Z,100\n",
        encoding="utf-8",
    )
    request = IngestionRequest(
        symbols=("AAPL",),
        start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        end=datetime(2026, 1, 6, tzinfo=timezone.utc),
    )

    counts = IngestionPipeline(
        LocalFileProvider({DataKind.QUOTES: path}), JsonlEventSink(tmp_path / "raw")
    ).run(request, (DataKind.QUOTES,))

    output = tmp_path / "raw/quotes/AAPL/2026-01-05.jsonl"
    assert counts[DataKind.QUOTES] == 1
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["kind"] == "quotes"


def test_request_requires_timezone_aware_bounds():
    try:
        IngestionRequest(
            symbols=("AAPL",),
            start=datetime(2026, 1, 5),
            end=datetime(2026, 1, 6, tzinfo=timezone.utc),
        )
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:
        raise AssertionError("expected naive timestamps to be rejected")


def test_alpaca_depth_is_explicitly_unsupported():
    from research.ingest.providers import AlpacaHistoricalProvider

    provider = object.__new__(AlpacaHistoricalProvider)
    try:
        list(provider.fetch(DataKind.DEPTH, None))
    except UnsupportedDataKind as error:
        assert "venue-specific" in str(error)
    else:
        raise AssertionError("expected Alpaca depth to be unsupported")