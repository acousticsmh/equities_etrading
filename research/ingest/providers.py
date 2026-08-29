"""Market-data providers.

The providers deliberately return raw normalized envelopes instead of pandas objects. This
keeps timestamps, sequence numbers, venue identifiers, and the untouched source payload
available for later validation and order-book reconstruction.
"""

import csv
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import DataKind, IngestionRequest, RawMarketEvent


class UnsupportedDataKind(ValueError):
    """Raised when a provider cannot supply a requested market-data layer."""


class MarketDataProvider(Protocol):
    def fetch(self, kind: DataKind, request: IngestionRequest) -> Iterator[RawMarketEvent]: ...


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class AlpacaHistoricalProvider:
    """Fetch historical trades and quotes from Alpaca's stock data REST API.

    Set ``APCA_API_KEY_ID`` and ``APCA_API_SECRET_KEY`` in the environment, or pass keys
    explicitly. Alpaca's historical endpoints are multi-symbol and paginated. Depth and
    order-level events intentionally raise ``UnsupportedDataKind`` because those require a
    venue-specific full-depth/order-event feed such as Nasdaq TotalView-ITCH.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = "https://data.alpaca.markets",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("APCA_API_KEY_ID")
        self.api_secret = api_secret or os.environ.get("APCA_API_SECRET_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if not self.api_key or not self.api_secret:
            raise ValueError("Alpaca credentials are required via arguments or environment")

    def fetch(self, kind: DataKind, request: IngestionRequest) -> Iterator[RawMarketEvent]:
        if kind not in (DataKind.TRADES, DataKind.QUOTES):
            raise UnsupportedDataKind(
                f"AlpacaHistoricalProvider does not supply {kind.value}; "
                "use a venue-specific depth/order-event adapter or LocalFileProvider"
            )
        endpoint = f"{self.base_url}/v2/stocks/{kind.value}"
        page_token: str | None = None
        while True:
            params: dict[str, str] = {
                "symbols": ",".join(request.symbols),
                "start": request.start.isoformat().replace("+00:00", "Z"),
                "end": request.end.isoformat().replace("+00:00", "Z"),
                "feed": request.feed,
                "sort": "asc",
                "limit": "10000",
            }
            if page_token:
                params["page_token"] = page_token
            response = self._get_json(f"{endpoint}?{urlencode(params)}")
            records_key = kind.value
            for symbol, records in response.get(records_key, {}).items():
                for record in records:
                    timestamp_key = "t"
                    yield RawMarketEvent(
                        symbol=symbol,
                        kind=kind,
                        event_time=_parse_time(record[timestamp_key]),
                        venue=record.get("x") or record.get("bx") or record.get("ax"),
                        payload=record,
                        source="alpaca",
                    )
            page_token = response.get("next_page_token")
            if not page_token:
                break

    def _get_json(self, url: str) -> Mapping[str, Any]:
        request = Request(
            url,
            headers={
                "APCA-API-KEY-ID": self.api_key or "",
                "APCA-API-SECRET-KEY": self.api_secret or "",
                "Accept": "application/json",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)


class LocalFileProvider:
    """Load normalized or provider-shaped records from JSONL, JSON, or CSV files.

    ``paths`` maps each data kind to a file. Files must contain ``symbol`` and a timestamp
    under ``event_time`` or ``t``. All remaining fields are preserved as the payload.
    """

    def __init__(self, paths: Mapping[DataKind, str | Path], source: str = "local") -> None:
        self.paths = {kind: Path(path) for kind, path in paths.items()}
        self.source = source

    def fetch(self, kind: DataKind, request: IngestionRequest) -> Iterator[RawMarketEvent]:
        path = self.paths.get(kind)
        if path is None:
            return
        for record in self._records(path):
            symbol = str(record.get("symbol", "")).upper()
            if symbol not in request.symbols:
                continue
            event_time = _parse_time(str(record.get("event_time", record.get("t"))))
            if not request.start <= event_time < request.end:
                continue
            yield RawMarketEvent(
                symbol=symbol,
                kind=kind,
                event_time=event_time,
                received_time=_parse_time(str(record["received_time"]))
                if record.get("received_time")
                else None,
                sequence=int(record["sequence"]) if record.get("sequence") not in (None, "") else None,
                venue=record.get("venue") or record.get("x"),
                payload=record,
                source=self.source,
            )

    @staticmethod
    def _records(path: Path) -> Sequence[Mapping[str, Any]]:
        if path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]
        if path.suffix == ".json":
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else data.get("records", [])
        if path.suffix == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                return list(csv.DictReader(handle))
        raise ValueError(f"unsupported input format: {path.suffix}")