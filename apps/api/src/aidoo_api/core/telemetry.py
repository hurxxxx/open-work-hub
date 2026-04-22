from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import logging
import urllib.parse

from opentelemetry import metrics, propagate, trace
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.context import Context, attach, detach
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.textmap import default_getter, default_setter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


logger = logging.getLogger(__name__)

_CONSOLE_EXPORTER_ENABLED = False
_OTLP_TRACE_EXPORTER_ENABLED = False


def bootstrap_telemetry(
    *,
    service_name: str,
    service_version: str = "0.1.0",
    enabled: bool = True,
    enable_console_exporter: bool = False,
    enable_otlp_exporter: bool = False,
    metrics_export_interval_ms: int = 60000,
) -> bool:
    global _CONSOLE_EXPORTER_ENABLED, _OTLP_TRACE_EXPORTER_ENABLED

    if not enabled:
        return False

    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
        }
    )
    trace_provider = trace.get_tracer_provider()
    if not isinstance(trace_provider, TracerProvider):
        trace_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(trace_provider)

    if enable_console_exporter and not _CONSOLE_EXPORTER_ENABLED:
        trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        _CONSOLE_EXPORTER_ENABLED = True
    if enable_otlp_exporter and not _OTLP_TRACE_EXPORTER_ENABLED:
        trace_provider.add_span_processor(BatchSpanProcessor(_build_otlp_span_exporter()))
        _OTLP_TRACE_EXPORTER_ENABLED = True

    meter_provider = metrics.get_meter_provider()
    if not isinstance(meter_provider, MeterProvider):
        metric_readers = []
        if enable_console_exporter:
            metric_readers.append(
                PeriodicExportingMetricReader(
                    ConsoleMetricExporter(),
                    export_interval_millis=metrics_export_interval_ms,
                )
            )
        if enable_otlp_exporter:
            metric_readers.append(
                PeriodicExportingMetricReader(
                    _build_otlp_metric_exporter(),
                    export_interval_millis=metrics_export_interval_ms,
                )
            )
        metrics.set_meter_provider(
            MeterProvider(resource=resource, metric_readers=metric_readers)
        )

    propagate.set_global_textmap(
        CompositePropagator(
            [
                TraceContextTextMapPropagator(),
                W3CBaggagePropagator(),
            ]
        )
    )
    return True


def get_tracer(name: str):
    return trace.get_tracer(name)


def get_meter(name: str):
    return metrics.get_meter(name)


def get_meter_provider() -> MeterProvider | None:
    provider = metrics.get_meter_provider()
    if isinstance(provider, MeterProvider):
        return provider
    return None


def get_tracer_provider() -> TracerProvider | None:
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        return provider
    return None


def current_trace_id() -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


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
def start_as_current_span(
    *,
    tracer_name: str,
    span_name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    parent_trace_context: Mapping[str, object] | None = None,
    attributes: Mapping[str, object] | None = None,
) -> Iterator[Span]:
    tracer = get_tracer(tracer_name)
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


def _build_otlp_span_exporter():
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter()


def _build_otlp_metric_exporter():
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

    return OTLPMetricExporter()
