from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
import logging

from opentelemetry.metrics import Meter

from open_alm_api.core.telemetry import get_meter


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeCounterDefinition:
    key: str
    name: str
    description: str
    unit: str = "1"


TRACE_EVENTS_COUNTER = RuntimeCounterDefinition(
    key="trace_events",
    name="ai_runtime_trace_events_total",
    description="Total AI runtime trace events written.",
)
TRACE_PAYLOAD_TRUNCATED_COUNTER = RuntimeCounterDefinition(
    key="trace_payload_truncated",
    name="ai_runtime_trace_payload_truncated_total",
    description="Total AI runtime trace payloads truncated before persistence.",
)
SHADOW_WRITE_FAILURES_COUNTER = RuntimeCounterDefinition(
    key="shadow_write_failures",
    name="ai_runtime_shadow_write_failures_total",
    description="Total AI runtime shadow-write failures swallowed by compatibility paths.",
)
INSPECTION_REQUESTS_COUNTER = RuntimeCounterDefinition(
    key="inspection_requests",
    name="ai_runtime_inspection_requests_total",
    description="Total AI runtime inspection requests.",
)
EXTERNAL_EXECUTIONS_COUNTER = RuntimeCounterDefinition(
    key="external_executions",
    name="ai_runtime_external_executions_total",
    description="Total AI runtime external planner/search execution outcomes.",
)

RUNTIME_COUNTER_DEFINITIONS = (
    TRACE_EVENTS_COUNTER,
    TRACE_PAYLOAD_TRUNCATED_COUNTER,
    SHADOW_WRITE_FAILURES_COUNTER,
    INSPECTION_REQUESTS_COUNTER,
    EXTERNAL_EXECUTIONS_COUNTER,
)


class RuntimeMetrics:
    def __init__(self, meter: Meter) -> None:
        self._counters = {
            definition.key: meter.create_counter(
                definition.name,
                unit=definition.unit,
                description=definition.description,
            )
            for definition in RUNTIME_COUNTER_DEFINITIONS
        }

    def _add_counter(
        self,
        key: str,
        attributes: Mapping[str, object],
    ) -> None:
        self._counters[key].add(1, attributes=dict(attributes))

    def record_trace_event(self, *, event_type: str, result: str) -> None:
        self._add_counter(
            TRACE_EVENTS_COUNTER.key,
            {
                "event_type": event_type,
                "result": result,
            },
        )

    def record_trace_payload_truncated(self, *, event_type: str) -> None:
        self._add_counter(
            TRACE_PAYLOAD_TRUNCATED_COUNTER.key,
            {"event_type": event_type},
        )

    def record_shadow_write_failure(self, *, operation: str) -> None:
        self._add_counter(
            SHADOW_WRITE_FAILURES_COUNTER.key,
            {"operation": operation},
        )

    def record_inspection_request(self, *, result: str) -> None:
        self._add_counter(
            INSPECTION_REQUESTS_COUNTER.key,
            {"result": result},
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
        self._add_counter(
            EXTERNAL_EXECUTIONS_COUNTER.key,
            {
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
    return build_runtime_metrics(get_meter("open_alm_api.ai_runtime"))


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
