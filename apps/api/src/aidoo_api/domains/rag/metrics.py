from __future__ import annotations

from functools import lru_cache

from opentelemetry.metrics import Meter

from aidoo_api.core.telemetry import get_meter
from aidoo_api.domains.rag.telemetry import rag_span_attributes


class RagMetrics:
    def __init__(self, meter: Meter) -> None:
        self._query_latency_ms = meter.create_histogram(
            "rag_query_latency_ms",
            unit="ms",
            description="Latency for synchronous RAG query execution.",
        )
        self._sync_job_lag_ms = meter.create_histogram(
            "rag_sync_job_lag_ms",
            unit="ms",
            description="Queue lag from job creation until worker pickup.",
        )
        self._sync_jobs_total = meter.create_counter(
            "rag_sync_jobs_total",
            unit="1",
            description="Total number of RAG sync jobs observed by workers.",
        )

    def record_query_latency(
        self,
        *,
        workspace_id: str,
        answer_mode: str,
        latency_ms: int,
        source_kind: str | None = None,
    ) -> None:
        self._query_latency_ms.record(
            latency_ms,
            attributes=rag_span_attributes(
                workspace_id=workspace_id,
                source_kind=source_kind,
                operation="query",
                extra={"answer_mode": answer_mode},
            ),
        )

    def record_sync_job_lag(
        self,
        *,
        lag_ms: int,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        operation: str | None = None,
        job_lane: str | None = None,
        job_kind: str,
    ) -> None:
        self._sync_job_lag_ms.record(
            lag_ms,
            attributes=rag_span_attributes(
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                scope_type=scope_type,
                scope_id=scope_id,
                operation=operation,
                job_lane=job_lane,
                extra={"job_kind": job_kind},
            ),
        )

    def record_sync_job_result(
        self,
        *,
        status: str,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        operation: str | None = None,
        job_lane: str | None = None,
        job_kind: str,
    ) -> None:
        self._sync_jobs_total.add(
            1,
            attributes=rag_span_attributes(
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                scope_type=scope_type,
                scope_id=scope_id,
                operation=operation,
                job_lane=job_lane,
                extra={"job_kind": job_kind, "status": status},
            ),
        )


def build_rag_metrics(meter: Meter) -> RagMetrics:
    return RagMetrics(meter)


@lru_cache(maxsize=1)
def _default_rag_metrics() -> RagMetrics:
    return build_rag_metrics(get_meter("aidoo_api.rag"))


def record_query_latency(
    *,
    workspace_id: str,
    answer_mode: str,
    latency_ms: int,
    source_kind: str | None = None,
) -> None:
    _default_rag_metrics().record_query_latency(
        workspace_id=workspace_id,
        answer_mode=answer_mode,
        latency_ms=latency_ms,
        source_kind=source_kind,
    )


def record_sync_job_lag(
    *,
    lag_ms: int,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    operation: str | None = None,
    job_lane: str | None = None,
    job_kind: str,
) -> None:
    _default_rag_metrics().record_sync_job_lag(
        lag_ms=lag_ms,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        scope_type=scope_type,
        scope_id=scope_id,
        operation=operation,
        job_lane=job_lane,
        job_kind=job_kind,
    )


def record_sync_job_result(
    *,
    status: str,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    operation: str | None = None,
    job_lane: str | None = None,
    job_kind: str,
) -> None:
    _default_rag_metrics().record_sync_job_result(
        status=status,
        workspace_id=workspace_id,
        resource_type=resource_type,
        resource_id=resource_id,
        scope_type=scope_type,
        scope_id=scope_id,
        operation=operation,
        job_lane=job_lane,
        job_kind=job_kind,
    )
