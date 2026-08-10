from __future__ import annotations

from opentelemetry import baggage

from ai_do_api.core.telemetry import bootstrap_telemetry, get_tracer
from ai_do_api.core.trace_context import (
    serialize_current_trace_context,
    start_span_with_trace_context,
)


def test_start_span_with_trace_context_preserves_mapping_baggage() -> None:
    bootstrap_telemetry(service_name="ai-do-api-test")
    tracer = get_tracer("tests.trace_context")

    with start_span_with_trace_context(
        tracer=tracer,
        span_name="tests.mapping_baggage",
        parent_trace_context={
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "baggage": {
                "tenant": "delivery hub",
                "locale": "ko-KR",
                "ignored": 123,
            },
        },
    ) as span:
        assert baggage.get_baggage("tenant") == "delivery hub"
        assert baggage.get_baggage("locale") == "ko-KR"
        assert baggage.get_baggage("ignored") is None
        trace_context = serialize_current_trace_context()
        parent = span.parent

    assert parent is not None
    assert format(parent.trace_id, "032x") == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert baggage.get_baggage("tenant") is None
    assert trace_context is not None
    assert trace_context["traceparent"].startswith(
        "00-4bf92f3577b34da6a3ce929d0e0e4736-"
    )
    assert trace_context["baggage"] == {
        "tenant": "delivery hub",
        "locale": "ko-KR",
    }
