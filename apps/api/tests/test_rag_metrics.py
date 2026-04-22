from __future__ import annotations

import aidoo_api.domains.rag.metrics as rag_metrics_module
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from aidoo_api.domains.rag.contracts import RagAnswerMode, RagProjection, RagQueryRequest
from aidoo_api.domains.rag.metrics import build_rag_metrics
from aidoo_api.domains.rag.providers.fake import (
    FakeEmbeddingClient,
    FakeOcrClient,
    FakeRerankClient,
    FakeVectorIndexClient,
)
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.service import RagService


def _metric_map(reader: InMemoryMetricReader) -> dict[str, object]:
    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    return {
        metric.name: metric
        for resource_metric in metrics_data.resource_metrics
        for scope_metric in resource_metric.scope_metrics
        for metric in scope_metric.metrics
    }


def test_rag_metrics_emit_full_phase5a_baseline() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    rag_metrics = build_rag_metrics(provider.get_meter("tests.rag"))

    rag_metrics.record_sync_queue_depth(
        depth=3,
        workspace_id="ws-1",
        job_lane="realtime",
        job_kind="resource_sync",
    )
    rag_metrics.record_query_latency(
        workspace_id="ws-1",
        answer_mode="search-only",
        latency_ms=17,
    )
    rag_metrics.record_ingest_latency(
        workspace_id="ws-1",
        resource_type="doc",
        source_kind="docs",
        provider_name="qdrant",
        latency_ms=23,
    )
    rag_metrics.record_sync_job_lag(
        lag_ms=41,
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        operation="upsert",
        job_lane="realtime",
        job_kind="resource_sync",
    )
    rag_metrics.record_vector_query_latency(
        workspace_id="ws-1",
        provider_name="qdrant",
        latency_ms=9,
        source_kind="docs",
    )
    rag_metrics.record_embedding_latency(
        provider_name="fake-embedding",
        operation="query_embedding",
        latency_ms=7,
        workspace_id="ws-1",
        source_kind="docs",
    )
    rag_metrics.record_ocr_latency(
        provider_name="fake-ocr",
        latency_ms=5,
        workspace_id="ws-1",
        resource_type="doc",
        source_kind="docs",
    )
    rag_metrics.record_rerank_latency(
        provider_name="fake-rerank",
        latency_ms=4,
        workspace_id="ws-1",
        source_kind="docs",
    )
    rag_metrics.record_grounded_answer_latency(
        provider_name="default-grounded-answer",
        latency_ms=6,
        workspace_id="ws-1",
        source_kind="docs",
    )
    rag_metrics.record_sync_job_result(
        status="disabled",
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        operation="upsert",
        job_lane="realtime",
        job_kind="resource_sync",
    )
    rag_metrics.record_provider_error(
        provider_name="qdrant",
        operation="vector_query",
        workspace_id="ws-1",
        source_kind="docs",
        error_type="RuntimeError",
    )
    rag_metrics.record_provider_timeout(
        provider_name="qdrant",
        operation="vector_query",
        workspace_id="ws-1",
        source_kind="docs",
        error_type="TimeoutError",
    )

    metric_map = _metric_map(reader)

    queue_points = metric_map["rag_sync_queue_depth"].data.data_points
    assert len(queue_points) == 1
    assert queue_points[0].sum == 3
    assert queue_points[0].attributes["rag.job.lane"] == "realtime"

    query_points = metric_map["rag_query_latency_ms"].data.data_points
    assert len(query_points) == 1
    assert query_points[0].sum == 17

    ingest_points = metric_map["rag_ingest_latency_ms"].data.data_points
    assert len(ingest_points) == 1
    assert ingest_points[0].sum == 23
    assert ingest_points[0].attributes["provider_name"] == "qdrant"

    vector_points = metric_map["qdrant_query_latency_ms"].data.data_points
    assert len(vector_points) == 1
    assert vector_points[0].sum == 9

    embedding_points = metric_map["embedding_latency_ms"].data.data_points
    assert len(embedding_points) == 1
    assert embedding_points[0].sum == 7

    ocr_points = metric_map["ocr_latency_ms"].data.data_points
    assert len(ocr_points) == 1
    assert ocr_points[0].sum == 5

    rerank_points = metric_map["rerank_latency_ms"].data.data_points
    assert len(rerank_points) == 1
    assert rerank_points[0].sum == 4

    grounded_points = metric_map["grounded_answer_latency_ms"].data.data_points
    assert len(grounded_points) == 1
    assert grounded_points[0].sum == 6

    result_points = metric_map["rag_sync_jobs_total"].data.data_points
    assert len(result_points) == 1
    assert result_points[0].value == 1
    assert result_points[0].attributes["status"] == "disabled"

    error_points = metric_map["rag_provider_errors_total"].data.data_points
    assert len(error_points) == 1
    assert error_points[0].value == 1
    assert error_points[0].attributes["error_type"] == "RuntimeError"

    timeout_points = metric_map["rag_provider_timeouts_total"].data.data_points
    assert len(timeout_points) == 1
    assert timeout_points[0].value == 1
    assert timeout_points[0].attributes["error_type"] == "TimeoutError"


def test_default_rag_metrics_wrapper_emits_after_lazy_meter_lookup(monkeypatch) -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(
        rag_metrics_module,
        "get_meter",
        lambda name: provider.get_meter(name),
    )
    rag_metrics_module._default_rag_metrics.cache_clear()
    try:
        rag_metrics_module.record_query_latency(
            workspace_id="ws-2",
            answer_mode="grounded-answer",
            latency_ms=9,
            source_kind="docs",
        )
        rag_metrics_module.record_sync_queue_depth(
            depth=2,
            workspace_id="ws-2",
            job_lane="backfill",
            job_kind="backfill_sync",
        )
        rag_metrics_module.record_provider_timeout(
            provider_name="fake-embedding",
            operation="embed_query",
            workspace_id="ws-2",
            source_kind="docs",
            error_type="TimeoutError",
        )
    finally:
        rag_metrics_module._default_rag_metrics.cache_clear()

    metric_map = _metric_map(reader)
    assert metric_map["rag_query_latency_ms"].data.data_points[0].attributes["workspace_id"] == "ws-2"
    assert metric_map["rag_sync_queue_depth"].data.data_points[0].attributes["rag.job.lane"] == "backfill"
    assert metric_map["rag_provider_timeouts_total"].data.data_points[0].value == 1


class _RecordingSynthesizer:
    provider_name = "stub-grounded-answer"

    def synthesize(self, *, query: str, hits):
        from aidoo_api.domains.rag.contracts import RagGroundedAnswer, RagGroundedCitation

        return RagGroundedAnswer(
            text=f"answer for {query}",
            citations=[
                RagGroundedCitation(
                    resource_id=hit.resource_id,
                    source_kind=hit.source_kind,
                    quote=hit.summary or hit.resource_id,
                )
                for hit in hits[:1]
            ],
            sources_used=sorted({hit.source_kind for hit in hits}),
        )


def test_rag_service_and_query_emit_runtime_metrics(monkeypatch) -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(rag_metrics_module, "get_meter", lambda name: provider.get_meter(name))
    rag_metrics_module._default_rag_metrics.cache_clear()
    try:
        vector_index = FakeVectorIndexClient()
        rag_service = RagService(
            vector_index=vector_index,
            embedding_client=FakeEmbeddingClient(),
            ocr_client=FakeOcrClient(),
        )
        rag_query = RagQueryService(
            vector_index=vector_index,
            embedding_client=FakeEmbeddingClient(),
            rerank_client=FakeRerankClient(),
            grounded_answer_synthesizer=_RecordingSynthesizer(),
        )

        rag_service.sync_projection(
            RagProjection(
                workspace_id="ws-1",
                resource_type="doc",
                resource_id="doc-1",
                source_kind="docs",
                title="Budget Review",
                summary="Quarterly budget risk and spending review",
                text_content="Budget review for Q2 and risk tracking.",
                visibility_refs=["owner:user-1", "workspace:ws-1"],
                metadata={"origin_ref": "docs:doc-1"},
            ),
            collection="rag-metrics",
        )
        rag_service.extract_text(
            content=b"hello world",
            content_type="text/plain",
            workspace_id="ws-1",
            resource_type="doc",
            source_kind="docs",
        )
        response = rag_query.query(
            RagQueryRequest(
                collection="rag-metrics",
                workspace_id="ws-1",
                query="budget risk",
                source_kinds=["docs"],
                answer_mode=RagAnswerMode.GROUNDED_ANSWER,
                top_k=5,
            )
        )
        assert response.grounded_answer is not None
    finally:
        rag_metrics_module._default_rag_metrics.cache_clear()

    metric_map = _metric_map(reader)
    for metric_name in (
        "rag_ingest_latency_ms",
        "embedding_latency_ms",
        "ocr_latency_ms",
        "rerank_latency_ms",
        "grounded_answer_latency_ms",
        "rag_query_latency_ms",
    ):
        assert metric_name in metric_map
        assert metric_map[metric_name].data.data_points


class _TimeoutEmbeddingClient:
    provider_name = "timeout-embedding"

    def healthcheck(self):
        raise NotImplementedError

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise TimeoutError("embedding timeout")

    def embed_query(self, text: str) -> list[float]:
        raise TimeoutError("embedding timeout")


class _ErrorOcrClient:
    provider_name = "error-ocr"

    def healthcheck(self):
        raise NotImplementedError

    def extract_text(self, *, content: bytes, content_type: str | None = None) -> str:
        raise RuntimeError("ocr failed")


def test_provider_failures_emit_error_and_timeout_counters(monkeypatch) -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    monkeypatch.setattr(rag_metrics_module, "get_meter", lambda name: provider.get_meter(name))
    rag_metrics_module._default_rag_metrics.cache_clear()
    try:
        timeout_service = RagService(
            vector_index=FakeVectorIndexClient(),
            embedding_client=_TimeoutEmbeddingClient(),
        )
        with pytest.raises(TimeoutError):
            timeout_service.sync_projection(
                RagProjection(
                    workspace_id="ws-err",
                    resource_type="doc",
                    resource_id="doc-timeout",
                    source_kind="docs",
                    text_content="timeout",
                ),
                collection="rag-errors",
            )

        ocr_service = RagService(
            vector_index=FakeVectorIndexClient(),
            embedding_client=FakeEmbeddingClient(),
            ocr_client=_ErrorOcrClient(),
        )
        with pytest.raises(RuntimeError):
            ocr_service.extract_text(
                content=b"boom",
                content_type="text/plain",
                workspace_id="ws-err",
                resource_type="doc",
                source_kind="docs",
            )
    finally:
        rag_metrics_module._default_rag_metrics.cache_clear()

    metric_map = _metric_map(reader)
    timeout_points = metric_map["rag_provider_timeouts_total"].data.data_points
    error_points = metric_map["rag_provider_errors_total"].data.data_points
    assert any(point.attributes["provider_name"] == "timeout-embedding" for point in timeout_points)
    assert any(point.attributes["provider_name"] == "error-ocr" for point in error_points)
