from __future__ import annotations

from starlette.datastructures import Headers

from open_work_hub_api.core.telemetry import (
    _build_otlp_metric_exporter,
    _build_otlp_span_exporter,
    bootstrap_telemetry,
    serialize_current_trace_context,
    start_as_current_span,
)


def test_extract_trace_context_preserves_http_baggage_header() -> None:
    bootstrap_telemetry(service_name="open-work-hub-api-test")

    headers = Headers(
        {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "baggage": "tenant=delivery-hub,locale=ko-KR,feature=rag%20sync",
        }
    )

    with start_as_current_span(
        tracer_name="tests.telemetry",
        span_name="tests.http_baggage",
        parent_trace_context=headers,
    ):
        trace_context = serialize_current_trace_context()

    assert trace_context is not None
    assert trace_context["traceparent"].startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
    assert trace_context["baggage"] == {
        "tenant": "delivery-hub",
        "locale": "ko-KR",
        "feature": "rag sync",
    }


def test_start_as_current_span_preserves_ambient_parent_when_no_explicit_context() -> None:
    bootstrap_telemetry(service_name="open-work-hub-api-test")

    with start_as_current_span(
        tracer_name="tests.telemetry",
        span_name="tests.outer",
    ) as outer_span:
        outer_context = outer_span.get_span_context()
        with start_as_current_span(
            tracer_name="tests.telemetry",
            span_name="tests.inner",
        ) as inner_span:
            inner_parent = inner_span.parent

    assert inner_parent is not None
    assert inner_parent.span_id == outer_context.span_id
    assert inner_span.get_span_context().trace_id == outer_context.trace_id


def test_otlp_exporter_builders_follow_protocol_env(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
    span_exporter = _build_otlp_span_exporter()
    metric_exporter = _build_otlp_metric_exporter()
    assert span_exporter.__class__.__module__.endswith("proto.grpc.trace_exporter")
    assert metric_exporter.__class__.__module__.endswith("proto.grpc.metric_exporter")

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "http/protobuf")
    span_exporter = _build_otlp_span_exporter()
    metric_exporter = _build_otlp_metric_exporter()
    assert span_exporter.__class__.__module__.endswith("proto.http.trace_exporter")
    assert metric_exporter.__class__.__module__.endswith("proto.http.metric_exporter")
