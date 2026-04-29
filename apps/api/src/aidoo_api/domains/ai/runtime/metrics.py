from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
import logging

from opentelemetry.metrics import Meter

from aidoo_api.core.telemetry import get_meter


logger = logging.getLogger(__name__)


class RuntimeMetrics:
    def __init__(self, meter: Meter) -> None:
        self._trace_events_total = meter.create_counter(
            "ai_runtime_trace_events_total",
            unit="1",
            description="Total AI runtime trace events written.",
        )
        self._trace_payload_truncated_total = meter.create_counter(
            "ai_runtime_trace_payload_truncated_total",
            unit="1",
            description="Total AI runtime trace payloads truncated before persistence.",
        )
        self._shadow_write_failures_total = meter.create_counter(
            "ai_runtime_shadow_write_failures_total",
            unit="1",
            description="Total AI runtime shadow-write failures swallowed by compatibility paths.",
        )
        self._inspection_requests_total = meter.create_counter(
            "ai_runtime_inspection_requests_total",
            unit="1",
            description="Total AI runtime inspection requests.",
        )
        self._external_executions_total = meter.create_counter(
            "ai_runtime_external_executions_total",
            unit="1",
            description="Total AI runtime external planner/search execution outcomes.",
        )

    def record_trace_event(self, *, event_type: str, result: str) -> None:
        self._trace_events_total.add(
            1,
            attributes={
                "event_type": event_type,
                "result": result,
            },
        )

    def record_trace_payload_truncated(self, *, event_type: str) -> None:
        self._trace_payload_truncated_total.add(
            1,
            attributes={"event_type": event_type},
        )

    def record_shadow_write_failure(self, *, operation: str) -> None:
        self._shadow_write_failures_total.add(
            1,
            attributes={"operation": operation},
        )

    def record_inspection_request(self, *, result: str) -> None:
        self._inspection_requests_total.add(
            1,
            attributes={"result": result},
        )

    def record_external_execution(
        self,
        *,
        capability: str,
        adapter_id: str,
        execution_provider: str,
        status: str,
        error_class: str | None = None,
    ) -> None:
        self._external_executions_total.add(
            1,
            attributes={
                "capability": capability,
                "adapter_id": adapter_id,
                "execution_provider": execution_provider,
                "status": status,
                "error_class": error_class or "none",
            },
        )


def build_runtime_metrics(meter: Meter) -> RuntimeMetrics:
    return RuntimeMetrics(meter)


@lru_cache(maxsize=1)
def _default_runtime_metrics() -> RuntimeMetrics:
    return build_runtime_metrics(get_meter("aidoo_api.ai_runtime"))


def record_trace_event(*, event_type: str, result: str) -> None:
    _safe_record(
        lambda: _default_runtime_metrics().record_trace_event(
            event_type=event_type,
            result=result,
        )
    )


def record_trace_payload_truncated(*, event_type: str) -> None:
    _safe_record(
        lambda: _default_runtime_metrics().record_trace_payload_truncated(event_type=event_type)
    )


def record_shadow_write_failure(*, operation: str) -> None:
    _safe_record(
        lambda: _default_runtime_metrics().record_shadow_write_failure(operation=operation)
    )


def record_inspection_request(*, result: str) -> None:
    _safe_record(lambda: _default_runtime_metrics().record_inspection_request(result=result))


def record_external_execution(
    *,
    capability: str,
    adapter_id: str,
    execution_provider: str,
    status: str,
    error_class: str | None = None,
) -> None:
    _safe_record(
        lambda: _default_runtime_metrics().record_external_execution(
            capability=capability,
            adapter_id=adapter_id,
            execution_provider=execution_provider,
            status=status,
            error_class=error_class,
        )
    )


def _safe_record(callback: Callable[[], None]) -> None:
    try:
        callback()
    except Exception:
        logger.exception("ai_runtime.metric_record_failed")


__all__ = [
    "RuntimeMetrics",
    "build_runtime_metrics",
    "record_external_execution",
    "record_inspection_request",
    "record_shadow_write_failure",
    "record_trace_event",
    "record_trace_payload_truncated",
]
