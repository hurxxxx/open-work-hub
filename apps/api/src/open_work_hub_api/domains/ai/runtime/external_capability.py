from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Literal, TypeVar

from open_work_hub_api.domains.ai.runtime.external_egress import (
    ExternalCapability,
    ExternalEgressDecision,
    ExternalEgressReason,
    ExternalProvider,
)


ExternalCapabilityRequestStatus = Literal["disabled", "ready"]
ExternalCapabilityDisabledReason = Literal[
    "capability_mismatch",
    "egress_denied",
    "sanitized_empty",
]
ExternalCapabilityExecutionStatus = Literal["disabled", "skipped", "completed", "failed"]
ExternalCapabilityExecutionDisabledReason = Literal[
    "execution_flag_disabled",
    "request_not_ready",
]
ExternalCapabilityBlockedExecutionStatus = Literal["disabled", "skipped"]
RedactedSummaryCodec = Literal["value", "count", "presence", "list"]
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class ExternalCapabilityRequestDecision:
    status: ExternalCapabilityRequestStatus
    provider: ExternalProvider | None
    disabled_reason: ExternalCapabilityDisabledReason | None
    egress_reason: ExternalEgressReason
    sanitized_payload: str = ""


@dataclass(frozen=True)
class ExternalCapabilityExecutionGate:
    should_execute: bool
    status: ExternalCapabilityBlockedExecutionStatus | None = None
    disabled_reason: ExternalCapabilityExecutionDisabledReason | None = None


@dataclass(frozen=True)
class RedactedSummaryField:
    output_key: str
    source_attr: str | None = None
    codec: RedactedSummaryCodec = "value"


@dataclass(frozen=True)
class RedactedExternalSummaryProjection:
    fields: tuple[RedactedSummaryField, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields))

    def build(self, source: object) -> dict[str, Any]:
        return build_redacted_external_summary(source, self.fields)


def external_request_summary_projection(
    extra_fields: tuple[RedactedSummaryField, ...],
) -> RedactedExternalSummaryProjection:
    return RedactedExternalSummaryProjection(
        (
            RedactedSummaryField("adapter_id"),
            RedactedSummaryField("status"),
            RedactedSummaryField("provider"),
            RedactedSummaryField("disabled_reason"),
            RedactedSummaryField("egress_reason"),
            *extra_fields,
        )
    )


def external_execution_summary_projection(
    capability_fields: tuple[RedactedSummaryField, ...],
) -> RedactedExternalSummaryProjection:
    return RedactedExternalSummaryProjection(
        (
            RedactedSummaryField("adapter_id"),
            RedactedSummaryField("execution_provider"),
            RedactedSummaryField("status"),
            RedactedSummaryField("provider"),
            RedactedSummaryField("disabled_reason"),
            *capability_fields,
            RedactedSummaryField("latency_ms"),
            RedactedSummaryField("retry_count"),
            RedactedSummaryField("error_class"),
            RedactedSummaryField("estimated_cost_microunits"),
            RedactedSummaryField("raw_output_persisted"),
        )
    )


def external_request_fields_from_decision(
    decision: ExternalCapabilityRequestDecision,
) -> dict[str, Any]:
    return {
        "status": decision.status,
        "provider": decision.provider,
        "disabled_reason": decision.disabled_reason,
        "egress_reason": decision.egress_reason,
    }


def blocked_external_execution_result(
    result_factory: Callable[..., ResultT],
    *,
    gate: ExternalCapabilityExecutionGate,
    provider: ExternalProvider | None,
) -> ResultT:
    if gate.status is None or gate.disabled_reason is None:
        raise ValueError("blocked external execution requires blocked gate details")
    return result_factory(
        status=gate.status,
        provider=provider,
        disabled_reason=gate.disabled_reason,
    )


def failed_external_execution_result(
    result_factory: Callable[..., ResultT],
    *,
    provider: ExternalProvider | None,
    error_class: str,
    extra_fields: dict[str, Any] | None = None,
) -> ResultT:
    return result_factory(
        status="failed",
        provider=provider,
        error_class=error_class,
        **(extra_fields or {}),
    )


def decide_external_capability_request(
    *,
    egress_decision: ExternalEgressDecision,
    expected_capability: ExternalCapability,
    sanitized_payload: str,
) -> ExternalCapabilityRequestDecision:
    if egress_decision.capability != expected_capability:
        return _disabled_request_decision(
            egress_decision=egress_decision,
            disabled_reason="capability_mismatch",
        )
    if not egress_decision.allow_external:
        return _disabled_request_decision(
            egress_decision=egress_decision,
            disabled_reason="egress_denied",
        )

    stripped_payload = sanitized_payload.strip()
    if not stripped_payload:
        return _disabled_request_decision(
            egress_decision=egress_decision,
            disabled_reason="sanitized_empty",
        )

    return ExternalCapabilityRequestDecision(
        status="ready",
        provider=egress_decision.provider,
        disabled_reason=None,
        egress_reason=egress_decision.reason,
        sanitized_payload=stripped_payload,
    )


def gate_mock_external_execution(
    *,
    execution_enabled: bool,
    request_status: ExternalCapabilityRequestStatus,
) -> ExternalCapabilityExecutionGate:
    if not execution_enabled:
        return ExternalCapabilityExecutionGate(
            should_execute=False,
            status="disabled",
            disabled_reason="execution_flag_disabled",
        )
    if request_status != "ready":
        return ExternalCapabilityExecutionGate(
            should_execute=False,
            status="skipped",
            disabled_reason="request_not_ready",
        )
    return ExternalCapabilityExecutionGate(should_execute=True)


def build_redacted_external_summary(
    source: object,
    fields: tuple[RedactedSummaryField, ...],
) -> dict[str, Any]:
    return {
        field.output_key: _summary_value(
            getattr(source, field.source_attr or field.output_key),
            codec=field.codec,
        )
        for field in fields
    }


def _disabled_request_decision(
    *,
    egress_decision: ExternalEgressDecision,
    disabled_reason: ExternalCapabilityDisabledReason,
) -> ExternalCapabilityRequestDecision:
    return ExternalCapabilityRequestDecision(
        status="disabled",
        provider=egress_decision.provider,
        disabled_reason=disabled_reason,
        egress_reason=egress_decision.reason,
    )


def _summary_value(value: Any, *, codec: RedactedSummaryCodec) -> Any:
    if codec == "count":
        return len(value)
    if codec == "presence":
        return bool(value)
    if codec == "list":
        return list(value)
    return value


__all__ = [
    "ExternalCapabilityBlockedExecutionStatus",
    "ExternalCapabilityDisabledReason",
    "ExternalCapabilityExecutionDisabledReason",
    "ExternalCapabilityExecutionGate",
    "ExternalCapabilityExecutionStatus",
    "ExternalCapabilityRequestDecision",
    "ExternalCapabilityRequestStatus",
    "RedactedExternalSummaryProjection",
    "RedactedSummaryCodec",
    "RedactedSummaryField",
    "blocked_external_execution_result",
    "build_redacted_external_summary",
    "decide_external_capability_request",
    "external_execution_summary_projection",
    "external_request_fields_from_decision",
    "external_request_summary_projection",
    "failed_external_execution_result",
    "gate_mock_external_execution",
]
