from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from opentelemetry import metrics, propagate, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span, SpanKind

from open_work_hub_api.core.trace_context import (
    build_trace_context_propagator,
    start_span_with_trace_context,
)
from open_work_hub_api.core.trace_context import (
    extract_trace_context as extract_trace_context,
)
from open_work_hub_api.core.trace_context import (
    serialize_current_trace_context as serialize_current_trace_context,
)
from open_work_hub_api.version import VERSION as APP_VERSION

logger = logging.getLogger(__name__)

_CONSOLE_EXPORTER_ENABLED = False
_OTLP_TRACE_EXPORTER_ENABLED = False
_BOOTSTRAP_SIGNATURE: tuple[str, bool, bool, int] | None = None
_BOOTSTRAP_MISMATCH_WARNED = False


def bootstrap_telemetry(
    *,
    service_name: str,
    service_version: str = APP_VERSION,
    enabled: bool = True,
    enable_console_exporter: bool = False,
    enable_otlp_exporter: bool = False,
    metrics_export_interval_ms: int = 60000,
) -> bool:
    global _CONSOLE_EXPORTER_ENABLED, _OTLP_TRACE_EXPORTER_ENABLED
    global _BOOTSTRAP_MISMATCH_WARNED, _BOOTSTRAP_SIGNATURE

    if not enabled:
        return False

    requested_signature = (
        service_name,
        enable_console_exporter,
        enable_otlp_exporter,
        metrics_export_interval_ms,
    )
    if _BOOTSTRAP_SIGNATURE is None:
        _BOOTSTRAP_SIGNATURE = requested_signature
    elif _BOOTSTRAP_SIGNATURE != requested_signature and not _BOOTSTRAP_MISMATCH_WARNED:
        logger.warning(
            "bootstrap_telemetry is process-global; retaining initial config %s and ignoring later request %s",
            _BOOTSTRAP_SIGNATURE,
            requested_signature,
        )
        _BOOTSTRAP_MISMATCH_WARNED = True

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
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=metric_readers))

    propagate.set_global_textmap(build_trace_context_propagator())
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
    with start_span_with_trace_context(
        tracer=tracer,
        span_name=span_name,
        kind=kind,
        parent_trace_context=parent_trace_context,
        attributes=attributes,
    ) as span:
        yield span


def _build_otlp_span_exporter():
    protocol = _resolve_otlp_protocol("traces")
    if protocol in {"http", "http/protobuf"}:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter()
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        return OTLPSpanExporter()
    raise RuntimeError(f"Unsupported OTLP traces protocol: {protocol}")


def _build_otlp_metric_exporter():
    protocol = _resolve_otlp_protocol("metrics")
    if protocol in {"http", "http/protobuf"}:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        return OTLPMetricExporter()
    if protocol == "grpc":
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

        return OTLPMetricExporter()
    raise RuntimeError(f"Unsupported OTLP metrics protocol: {protocol}")


def _resolve_otlp_protocol(signal: str) -> str:
    normalized_signal = signal.strip().lower()
    if normalized_signal not in {"traces", "metrics"}:
        raise RuntimeError(f"Unsupported OTLP signal: {signal}")
    signal_env = f"OTEL_EXPORTER_OTLP_{normalized_signal.upper()}_PROTOCOL"
    return (
        (os.getenv(signal_env) or os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") or "http/protobuf")
        .strip()
        .lower()
    )
