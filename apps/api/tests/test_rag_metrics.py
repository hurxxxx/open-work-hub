from __future__ import annotations

import aidoo_api.domains.rag.metrics as rag_metrics_module
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from aidoo_api.domains.rag.metrics import build_rag_metrics


def test_rag_metrics_emit_query_latency_and_sync_lag() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    rag_metrics = build_rag_metrics(provider.get_meter("tests.rag"))

    rag_metrics.record_query_latency(
        workspace_id="ws-1",
        answer_mode="search-only",
        latency_ms=17,
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
    rag_metrics.record_sync_job_result(
        status="disabled",
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        operation="upsert",
        job_lane="realtime",
        job_kind="resource_sync",
    )

    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None

    metric_map = {
        metric.name: metric
        for resource_metric in metrics_data.resource_metrics
        for scope_metric in resource_metric.scope_metrics
        for metric in scope_metric.metrics
    }

    query_points = metric_map["rag_query_latency_ms"].data.data_points
    assert len(query_points) == 1
    assert query_points[0].sum == 17
    assert query_points[0].attributes["workspace_id"] == "ws-1"
    assert query_points[0].attributes["answer_mode"] == "search-only"

    lag_points = metric_map["rag_sync_job_lag_ms"].data.data_points
    assert len(lag_points) == 1
    assert lag_points[0].sum == 41
    assert lag_points[0].attributes["job_kind"] == "resource_sync"
    assert lag_points[0].attributes["rag.job.lane"] == "realtime"

    result_points = metric_map["rag_sync_jobs_total"].data.data_points
    assert len(result_points) == 1
    assert result_points[0].value == 1
    assert result_points[0].attributes["status"] == "disabled"


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
        rag_metrics_module.record_sync_job_result(
            status="disabled",
            workspace_id="ws-2",
            resource_type="docs_native_doc",
            resource_id="doc-9",
            operation="upsert",
            job_lane="realtime",
            job_kind="resource_sync",
        )
    finally:
        rag_metrics_module._default_rag_metrics.cache_clear()

    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None

    metric_map = {
        metric.name: metric
        for resource_metric in metrics_data.resource_metrics
        for scope_metric in resource_metric.scope_metrics
        for metric in scope_metric.metrics
    }

    query_points = metric_map["rag_query_latency_ms"].data.data_points
    assert len(query_points) == 1
    assert query_points[0].sum == 9
    assert query_points[0].attributes["workspace_id"] == "ws-2"
    assert query_points[0].attributes["source_kind"] == "docs"

    result_points = metric_map["rag_sync_jobs_total"].data.data_points
    assert len(result_points) == 1
    assert result_points[0].value == 1
    assert result_points[0].attributes["resource_type"] == "docs_native_doc"
