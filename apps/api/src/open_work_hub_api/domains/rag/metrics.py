from __future__ import annotations

from functools import lru_cache
from typing import Any

from opentelemetry.metrics import Meter

from open_work_hub_api.core.telemetry import get_meter
from open_work_hub_api.domains.rag.telemetry import rag_span_attributes


class RagMetrics:
    def __init__(self, meter: Meter) -> None:
        self._sync_queue_depth = meter.create_histogram(
            "rag_sync_queue_depth",
            unit="1",
            description="Pending RAG queue depth snapshots by lane.",
        )
        self._sync_oldest_pending_age_ms = meter.create_histogram(
            "rag_sync_oldest_pending_age_ms",
            unit="ms",
            description="Age of the oldest pending RAG job by lane.",
        )
        self._sync_stale_processing_jobs = meter.create_histogram(
            "rag_sync_stale_processing_jobs",
            unit="1",
            description="RAG processing jobs whose claim lease has expired.",
        )
        self._sync_overdue_pending_jobs = meter.create_histogram(
            "rag_sync_overdue_pending_jobs",
            unit="1",
            description="Due RAG jobs left pending longer than one processing lease.",
        )
        self._query_latency_ms = meter.create_histogram(
            "rag_query_latency_ms",
            unit="ms",
            description="Latency for synchronous RAG query execution.",
        )
        self._ingest_latency_ms = meter.create_histogram(
            "rag_ingest_latency_ms",
            unit="ms",
            description="Latency for RAG ingest and vector upsert operations.",
        )
        self._sync_job_lag_ms = meter.create_histogram(
            "rag_sync_job_lag_ms",
            unit="ms",
            description="Queue lag from job creation until worker pickup.",
        )
        self._vector_query_latency_ms = meter.create_histogram(
            "qdrant_query_latency_ms",
            unit="ms",
            description="Latency for vector index query execution.",
        )
        self._embedding_latency_ms = meter.create_histogram(
            "embedding_latency_ms",
            unit="ms",
            description="Latency for embedding provider calls.",
        )
        self._ocr_latency_ms = meter.create_histogram(
            "ocr_latency_ms",
            unit="ms",
            description="Latency for OCR provider calls.",
        )
        self._rerank_latency_ms = meter.create_histogram(
            "rerank_latency_ms",
            unit="ms",
            description="Latency for rerank provider calls.",
        )
        self._grounded_answer_latency_ms = meter.create_histogram(
            "grounded_answer_latency_ms",
            unit="ms",
            description="Latency for grounded-answer synthesis.",
        )
        self._sync_jobs_total = meter.create_counter(
            "rag_sync_jobs_total",
            unit="1",
            description="Total number of RAG sync jobs observed by workers.",
        )
        self._provider_errors_total = meter.create_counter(
            "rag_provider_errors_total",
            unit="1",
            description="Total number of provider errors observed by the RAG pipeline.",
        )
        self._provider_timeouts_total = meter.create_counter(
            "rag_provider_timeouts_total",
            unit="1",
            description="Total number of provider timeouts observed by the RAG pipeline.",
        )

    def _record_histogram(
        self,
        instrument: Any,
        value: int,
        *,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        source_kind: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        operation: str | None = None,
        provider_name: str | None = None,
        job_lane: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        instrument.record(
            value,
            attributes=rag_span_attributes(
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                source_kind=source_kind,
                scope_type=scope_type,
                scope_id=scope_id,
                operation=operation,
                provider_name=provider_name,
                job_lane=job_lane,
                extra=extra,
            ),
        )

    def _add_counter(
        self,
        instrument: Any,
        *,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        source_kind: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        operation: str | None = None,
        provider_name: str | None = None,
        job_lane: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        instrument.add(
            1,
            attributes=rag_span_attributes(
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
                source_kind=source_kind,
                scope_type=scope_type,
                scope_id=scope_id,
                operation=operation,
                provider_name=provider_name,
                job_lane=job_lane,
                extra=extra,
            ),
        )

    def record_sync_queue_depth(
        self,
        *,
        depth: int,
        workspace_id: str | None = None,
        job_lane: str | None = None,
        job_kind: str,
    ) -> None:
        self._record_histogram(
            self._sync_queue_depth,
            max(depth, 0),
            workspace_id=workspace_id,
            job_lane=job_lane,
            extra={"job_kind": job_kind},
        )

    def record_sync_queue_health(
        self,
        *,
        oldest_pending_age_ms: int,
        stale_processing_jobs: int,
        overdue_pending_jobs: int,
        job_lane: str,
        job_kind: str,
    ) -> None:
        attributes = {"job_kind": job_kind}
        self._record_histogram(
            self._sync_oldest_pending_age_ms,
            max(oldest_pending_age_ms, 0),
            job_lane=job_lane,
            extra=attributes,
        )
        self._record_histogram(
            self._sync_stale_processing_jobs,
            max(stale_processing_jobs, 0),
            job_lane=job_lane,
            extra=attributes,
        )
        self._record_histogram(
            self._sync_overdue_pending_jobs,
            max(overdue_pending_jobs, 0),
            job_lane=job_lane,
            extra=attributes,
        )

    def record_query_latency(
        self,
        *,
        workspace_id: str | None,
        answer_mode: str,
        latency_ms: int,
        source_kind: str | None = None,
    ) -> None:
        self._record_histogram(
            self._query_latency_ms,
            latency_ms,
            workspace_id=workspace_id,
            source_kind=source_kind,
            operation="query",
            extra={"answer_mode": answer_mode},
        )

    def record_ingest_latency(
        self,
        *,
        workspace_id: str | None,
        resource_type: str,
        source_kind: str,
        provider_name: str | None,
        latency_ms: int,
    ) -> None:
        self._record_histogram(
            self._ingest_latency_ms,
            latency_ms,
            workspace_id=workspace_id,
            resource_type=resource_type,
            source_kind=source_kind,
            operation="ingest",
            provider_name=provider_name,
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
        self._record_histogram(
            self._sync_job_lag_ms,
            lag_ms,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            scope_type=scope_type,
            scope_id=scope_id,
            operation=operation,
            job_lane=job_lane,
            extra={"job_kind": job_kind},
        )

    def record_vector_query_latency(
        self,
        *,
        workspace_id: str | None,
        provider_name: str | None,
        latency_ms: int,
        source_kind: str | None = None,
    ) -> None:
        self._record_histogram(
            self._vector_query_latency_ms,
            latency_ms,
            workspace_id=workspace_id,
            source_kind=source_kind,
            operation="vector_query",
            provider_name=provider_name,
        )

    def record_embedding_latency(
        self,
        *,
        provider_name: str | None,
        operation: str,
        latency_ms: int,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        source_kind: str | None = None,
    ) -> None:
        self._record_histogram(
            self._embedding_latency_ms,
            latency_ms,
            workspace_id=workspace_id,
            resource_type=resource_type,
            source_kind=source_kind,
            operation=operation,
            provider_name=provider_name,
        )

    def record_ocr_latency(
        self,
        *,
        provider_name: str | None,
        latency_ms: int,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        source_kind: str | None = None,
    ) -> None:
        self._record_histogram(
            self._ocr_latency_ms,
            latency_ms,
            workspace_id=workspace_id,
            resource_type=resource_type,
            source_kind=source_kind,
            operation="ocr",
            provider_name=provider_name,
        )

    def record_rerank_latency(
        self,
        *,
        provider_name: str | None,
        latency_ms: int,
        workspace_id: str | None = None,
        source_kind: str | None = None,
    ) -> None:
        self._record_histogram(
            self._rerank_latency_ms,
            latency_ms,
            workspace_id=workspace_id,
            source_kind=source_kind,
            operation="rerank",
            provider_name=provider_name,
        )

    def record_grounded_answer_latency(
        self,
        *,
        provider_name: str | None,
        latency_ms: int,
        workspace_id: str | None = None,
        source_kind: str | None = None,
    ) -> None:
        self._record_histogram(
            self._grounded_answer_latency_ms,
            latency_ms,
            workspace_id=workspace_id,
            source_kind=source_kind,
            operation="grounded_answer",
            provider_name=provider_name,
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
        self._add_counter(
            self._sync_jobs_total,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            scope_type=scope_type,
            scope_id=scope_id,
            operation=operation,
            job_lane=job_lane,
            extra={"job_kind": job_kind, "status": status},
        )

    def record_provider_error(
        self,
        *,
        provider_name: str | None,
        operation: str,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        source_kind: str | None = None,
        error_type: str | None = None,
    ) -> None:
        self._add_counter(
            self._provider_errors_total,
            workspace_id=workspace_id,
            resource_type=resource_type,
            source_kind=source_kind,
            operation=operation,
            provider_name=provider_name,
            extra={"error_type": error_type or "unknown"},
        )

    def record_provider_timeout(
        self,
        *,
        provider_name: str | None,
        operation: str,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        source_kind: str | None = None,
        error_type: str | None = None,
    ) -> None:
        self._add_counter(
            self._provider_timeouts_total,
            workspace_id=workspace_id,
            resource_type=resource_type,
            source_kind=source_kind,
            operation=operation,
            provider_name=provider_name,
            extra={"error_type": error_type or "timeout"},
        )


def build_rag_metrics(meter: Meter) -> RagMetrics:
    return RagMetrics(meter)


@lru_cache(maxsize=1)
def _default_rag_metrics() -> RagMetrics:
    return build_rag_metrics(get_meter("open_work_hub_api.rag"))


def reset_default_rag_metrics() -> None:
    _default_rag_metrics.cache_clear()


def record_sync_queue_depth(
    *,
    depth: int,
    workspace_id: str | None = None,
    job_lane: str | None = None,
    job_kind: str,
) -> None:
    _default_rag_metrics().record_sync_queue_depth(
        depth=depth,
        workspace_id=workspace_id,
        job_lane=job_lane,
        job_kind=job_kind,
    )


def record_sync_queue_health(
    *,
    oldest_pending_age_ms: int,
    stale_processing_jobs: int,
    overdue_pending_jobs: int,
    job_lane: str,
    job_kind: str,
) -> None:
    _default_rag_metrics().record_sync_queue_health(
        oldest_pending_age_ms=oldest_pending_age_ms,
        stale_processing_jobs=stale_processing_jobs,
        overdue_pending_jobs=overdue_pending_jobs,
        job_lane=job_lane,
        job_kind=job_kind,
    )


def record_query_latency(
    *,
    workspace_id: str | None,
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


def record_ingest_latency(
    *,
    workspace_id: str | None,
    resource_type: str,
    source_kind: str,
    provider_name: str | None,
    latency_ms: int,
) -> None:
    _default_rag_metrics().record_ingest_latency(
        workspace_id=workspace_id,
        resource_type=resource_type,
        source_kind=source_kind,
        provider_name=provider_name,
        latency_ms=latency_ms,
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


def record_vector_query_latency(
    *,
    workspace_id: str | None,
    provider_name: str | None,
    latency_ms: int,
    source_kind: str | None = None,
) -> None:
    _default_rag_metrics().record_vector_query_latency(
        workspace_id=workspace_id,
        provider_name=provider_name,
        latency_ms=latency_ms,
        source_kind=source_kind,
    )


def record_embedding_latency(
    *,
    provider_name: str | None,
    operation: str,
    latency_ms: int,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    source_kind: str | None = None,
) -> None:
    _default_rag_metrics().record_embedding_latency(
        provider_name=provider_name,
        operation=operation,
        latency_ms=latency_ms,
        workspace_id=workspace_id,
        resource_type=resource_type,
        source_kind=source_kind,
    )


def record_ocr_latency(
    *,
    provider_name: str | None,
    latency_ms: int,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    source_kind: str | None = None,
) -> None:
    _default_rag_metrics().record_ocr_latency(
        provider_name=provider_name,
        latency_ms=latency_ms,
        workspace_id=workspace_id,
        resource_type=resource_type,
        source_kind=source_kind,
    )


def record_rerank_latency(
    *,
    provider_name: str | None,
    latency_ms: int,
    workspace_id: str | None = None,
    source_kind: str | None = None,
) -> None:
    _default_rag_metrics().record_rerank_latency(
        provider_name=provider_name,
        latency_ms=latency_ms,
        workspace_id=workspace_id,
        source_kind=source_kind,
    )


def record_grounded_answer_latency(
    *,
    provider_name: str | None,
    latency_ms: int,
    workspace_id: str | None = None,
    source_kind: str | None = None,
) -> None:
    _default_rag_metrics().record_grounded_answer_latency(
        provider_name=provider_name,
        latency_ms=latency_ms,
        workspace_id=workspace_id,
        source_kind=source_kind,
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


def record_provider_error(
    *,
    provider_name: str | None,
    operation: str,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    source_kind: str | None = None,
    error_type: str | None = None,
) -> None:
    _default_rag_metrics().record_provider_error(
        provider_name=provider_name,
        operation=operation,
        workspace_id=workspace_id,
        resource_type=resource_type,
        source_kind=source_kind,
        error_type=error_type,
    )


def record_provider_timeout(
    *,
    provider_name: str | None,
    operation: str,
    workspace_id: str | None = None,
    resource_type: str | None = None,
    source_kind: str | None = None,
    error_type: str | None = None,
) -> None:
    _default_rag_metrics().record_provider_timeout(
        provider_name=provider_name,
        operation=operation,
        workspace_id=workspace_id,
        resource_type=resource_type,
        source_kind=source_kind,
        error_type=error_type,
    )
