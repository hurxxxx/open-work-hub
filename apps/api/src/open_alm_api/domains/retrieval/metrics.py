from __future__ import annotations

from functools import lru_cache

from opentelemetry.metrics import Meter

from open_alm_api.core.telemetry import get_meter


class RetrievalMetrics:
    def __init__(self, meter: Meter) -> None:
        self._query_latency = meter.create_histogram(
            "retrieval_query_latency_ms",
            unit="ms",
            description="End-to-end Retrieval Module query latency.",
        )
        self._result_count = meter.create_histogram(
            "retrieval_result_count",
            unit="1",
            description="Returned Retrieval resources by strategy.",
        )
        self._degraded_total = meter.create_counter(
            "retrieval_degraded_total",
            unit="1",
            description="Retrieval backend, rerank, or grounding degradation events.",
        )

    def record_query(self, *, strategy: str, latency_ms: int, result_count: int) -> None:
        attributes = {"strategy": strategy}
        self._query_latency.record(max(latency_ms, 0), attributes=attributes)
        self._result_count.record(max(result_count, 0), attributes=attributes)

    def record_degraded(self, *, strategy: str, reason: str) -> None:
        self._degraded_total.add(1, attributes={"strategy": strategy, "reason": reason[:80]})


@lru_cache(maxsize=1)
def _metrics() -> RetrievalMetrics:
    return RetrievalMetrics(get_meter("open_alm_api.retrieval"))


def record_retrieval_query(*, strategy: str, latency_ms: int, result_count: int) -> None:
    _metrics().record_query(strategy=strategy, latency_ms=latency_ms, result_count=result_count)


def record_retrieval_degraded(*, strategy: str, reason: str) -> None:
    _metrics().record_degraded(strategy=strategy, reason=reason)
