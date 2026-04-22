from __future__ import annotations

from starlette.datastructures import Headers

from aidoo_api.core.telemetry import (
    bootstrap_telemetry,
    serialize_current_trace_context,
    start_as_current_span,
)


def test_extract_trace_context_preserves_http_baggage_header() -> None:
    bootstrap_telemetry(service_name="aidoo-api-test")

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
    assert trace_context["traceparent"].startswith(
        "00-4bf92f3577b34da6a3ce929d0e0e4736-"
    )
    assert trace_context["baggage"] == {
        "tenant": "delivery-hub",
        "locale": "ko-KR",
        "feature": "rag sync",
    }
