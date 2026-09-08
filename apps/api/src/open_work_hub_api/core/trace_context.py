from __future__ import annotations

import urllib.parse
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from opentelemetry import propagate
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.context import Context, attach, detach
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.textmap import default_getter, default_setter
from opentelemetry.trace import Span, SpanKind, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


def build_trace_context_propagator() -> CompositePropagator:
    return CompositePropagator(
        [
            TraceContextTextMapPropagator(),
            W3CBaggagePropagator(),
        ]
    )


def serialize_current_trace_context() -> dict[str, object] | None:
    carrier: dict[str, str] = {}
    propagate.inject(carrier=carrier, setter=default_setter)
    traceparent = carrier.get("traceparent")
    if not traceparent:
        return None
    baggage_header = carrier.get("baggage")
    return {
        "traceparent": traceparent,
        "tracestate": carrier.get("tracestate"),
        "baggage": _decode_baggage_header(baggage_header),
    }


def extract_trace_context(trace_context: Mapping[str, object] | None) -> Context:
    if not trace_context:
        return Context()

    carrier: dict[str, str] = {}
    traceparent = trace_context.get("traceparent")
    tracestate = trace_context.get("tracestate")
    baggage_items = trace_context.get("baggage")
    if isinstance(traceparent, str) and traceparent:
        carrier["traceparent"] = traceparent
    if isinstance(tracestate, str) and tracestate:
        carrier["tracestate"] = tracestate
    if isinstance(baggage_items, str) and baggage_items:
        baggage_header = baggage_items
    else:
        baggage_header = _encode_baggage_header(baggage_items)
    if baggage_header:
        carrier["baggage"] = baggage_header
    return propagate.extract(carrier=carrier, getter=default_getter)


@contextmanager
def start_span_with_trace_context(
    *,
    tracer: Tracer,
    span_name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    parent_trace_context: Mapping[str, object] | None = None,
    attributes: Mapping[str, object] | None = None,
) -> Iterator[Span]:
    if parent_trace_context is None:
        with tracer.start_as_current_span(
            span_name,
            kind=kind,
            attributes=dict(attributes or {}),
        ) as span:
            yield span
        return

    context = extract_trace_context(parent_trace_context)
    token = attach(context)
    try:
        with tracer.start_as_current_span(
            span_name,
            context=context,
            kind=kind,
            attributes=dict(attributes or {}),
        ) as span:
            yield span
    finally:
        detach(token)


def _decode_baggage_header(header: str | None) -> dict[str, str]:
    if not header:
        return {}

    baggage: dict[str, str] = {}
    for item in header.split(","):
        member = item.strip()
        if not member or "=" not in member:
            continue
        key, value = member.split("=", 1)
        baggage[key.strip()] = urllib.parse.unquote_plus(value.strip())
    return baggage


def _encode_baggage_header(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    encoded_items = []
    for key, raw_value in value.items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(raw_value, str):
            continue
        encoded_items.append(f"{key}={urllib.parse.quote(raw_value, safe='')}")
    if not encoded_items:
        return None
    return ",".join(encoded_items)
