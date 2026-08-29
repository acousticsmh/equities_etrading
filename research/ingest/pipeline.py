"""Orchestration for basket ingestion."""

from collections import Counter
from collections.abc import Iterable

from .models import DataKind, IngestionRequest
from .providers import MarketDataProvider
from .storage import JsonlEventSink


class IngestionPipeline:
    """Fetch each requested data layer and persist raw events without reordering them."""

    def __init__(self, provider: MarketDataProvider, sink: JsonlEventSink) -> None:
        self.provider = provider
        self.sink = sink

    def run(self, request: IngestionRequest, kinds: Iterable[DataKind]) -> Counter[DataKind]:
        counts: Counter[DataKind] = Counter()
        for kind in kinds:
            for event in self.provider.fetch(kind, request):
                self.sink.write(event)
                counts[kind] += 1
        return counts