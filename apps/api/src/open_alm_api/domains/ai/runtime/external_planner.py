from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from open_alm_api.domains.ai.runtime.contracts import RuntimeProfile
from open_alm_api.domains.ai.runtime.external_capability import (
    ExternalCapabilityDisabledReason,
    ExternalCapabilityExecutionDisabledReason,
    ExternalCapabilityExecutionStatus,
    ExternalCapabilityRequestStatus,
    RedactedSummaryField,
    blocked_external_execution_result,
    decide_external_capability_request,
    external_execution_summary_projection,
    external_request_fields_from_decision,
    external_request_summary_projection,
    failed_external_execution_result,
    gate_mock_external_execution,
)
from open_alm_api.domains.ai.runtime.external_egress import ExternalEgressDecision
from open_alm_api.domains.ai.runtime.external_planner_hints import (
    external_planner_hint_for_runtime_profile,
)


EXTERNAL_PLANNER_ADAPTER_ID = "external_planner_v0"

ExternalPlannerStatus = ExternalCapabilityRequestStatus
ExternalPlannerDisabledReason = ExternalCapabilityDisabledReason
ExternalPlannerExecutionStatus = ExternalCapabilityExecutionStatus
ExternalPlannerExecutionDisabledReason = ExternalCapabilityExecutionDisabledReason

_PLANNER_REQUEST_SUMMARY_PROJECTION = external_request_summary_projection(
    (
        RedactedSummaryField("message_count", source_attr="messages", codec="count"),
    )
)
_PLANNER_EXECUTION_SUMMARY_PROJECTION = external_execution_summary_projection(
    (
        RedactedSummaryField(
            "planned_agent_count",
            source_attr="planned_agent_ids",
            codec="count",
        ),
        RedactedSummaryField("intent_hint"),
        RedactedSummaryField("output_kind_hint"),
    )
)


class ExternalPlannerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: Literal["external_planner_v0"] = EXTERNAL_PLANNER_ADAPTER_ID
    status: ExternalPlannerStatus
    provider: str | None = None
    disabled_reason: ExternalPlannerDisabledReason | None = None
    egress_reason: str | None = None
    messages: list[dict[str, str]] = Field(default_factory=list)


class ExternalPlannerExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: Literal["external_planner_v0"] = EXTERNAL_PLANNER_ADAPTER_ID
    execution_provider: str = "mock"
    status: ExternalPlannerExecutionStatus
    provider: str | None = None
    disabled_reason: ExternalPlannerExecutionDisabledReason | None = None
    planned_agent_ids: list[str] = Field(default_factory=list)
    intent_hint: str | None = None
    output_kind_hint: str | None = None
    latency_ms: int = 0
    retry_count: int = 0
    error_class: str | None = None
    estimated_cost_microunits: int = 0
    raw_output_persisted: bool = False


class MockExternalPlannerAdapter:
    adapter_id = EXTERNAL_PLANNER_ADAPTER_ID
    execution_provider = "mock"

    def __init__(
        self,
        *,
        execution_enabled: bool,
        force_error_class: str | None = None,
    ) -> None:
        self._execution_enabled = execution_enabled
        self._force_error_class = force_error_class

    def execute(self, request: ExternalPlannerRequest) -> ExternalPlannerExecutionResult:
        return execute_mock_external_planner(
            request,
            execution_enabled=self._execution_enabled,
            force_error_class=self._force_error_class,
        )


def build_external_planner_request(
    *,
    egress_decision: ExternalEgressDecision,
    runtime_profile: RuntimeProfile,
    agent_ids: list[str],
) -> ExternalPlannerRequest:
    decision = decide_external_capability_request(
        egress_decision=egress_decision,
        expected_capability="planning",
        sanitized_payload=egress_decision.sanitized_prompt,
    )
    if decision.status == "disabled":
        return ExternalPlannerRequest(**external_request_fields_from_decision(decision))
    return ExternalPlannerRequest(
        **external_request_fields_from_decision(decision),
        messages=_planner_messages(
            sanitized_prompt=decision.sanitized_payload,
            runtime_profile=runtime_profile,
            agent_ids=agent_ids,
        ),
    )


def summarize_external_planner_request(
    request: ExternalPlannerRequest,
) -> dict[str, Any]:
    return _PLANNER_REQUEST_SUMMARY_PROJECTION.build(request)


def execute_mock_external_planner(
    request: ExternalPlannerRequest,
    *,
    execution_enabled: bool,
    force_error_class: str | None = None,
) -> ExternalPlannerExecutionResult:
    gate = gate_mock_external_execution(
        execution_enabled=execution_enabled,
        request_status=request.status,
    )
    if not gate.should_execute:
        return blocked_external_execution_result(
            ExternalPlannerExecutionResult,
            gate=gate,
            provider=request.provider,
        )
    if force_error_class:
        return failed_external_execution_result(
            ExternalPlannerExecutionResult,
            provider=request.provider,
            error_class=force_error_class,
        )
    planner_input = _planner_input_from_request(request)
    runtime_profile = str(planner_input.get("runtime_profile") or "")
    hint = external_planner_hint_for_runtime_profile(runtime_profile)
    return ExternalPlannerExecutionResult(
        status="completed",
        provider=request.provider,
        planned_agent_ids=_string_list(planner_input.get("available_agent_ids")),
        intent_hint=hint.intent,
        output_kind_hint=hint.output_kind,
        raw_output_persisted=False,
    )


def summarize_external_planner_execution(
    result: ExternalPlannerExecutionResult,
) -> dict[str, Any]:
    return _PLANNER_EXECUTION_SUMMARY_PROJECTION.build(result)


def _planner_messages(
    *,
    sanitized_prompt: str,
    runtime_profile: RuntimeProfile,
    agent_ids: list[str],
) -> list[dict[str, str]]:
    planner_input = {
        "runtime_profile": runtime_profile,
        "available_agent_ids": [agent_id for agent_id in agent_ids if agent_id],
        "sanitized_user_prompt": sanitized_prompt,
    }
    return [
        {
            "role": "system",
            "content": (
                "You are an external graph planner. Use only the sanitized "
                "user prompt and listed agent ids. Do not infer private "
                "workspace facts or request raw user content."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                planner_input,
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    ]


def _planner_input_from_request(request: ExternalPlannerRequest) -> dict[str, Any]:
    if len(request.messages) < 2:
        return {}
    try:
        parsed = json.loads(request.messages[1].get("content") or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


__all__ = [
    "EXTERNAL_PLANNER_ADAPTER_ID",
    "ExternalPlannerDisabledReason",
    "ExternalPlannerExecutionDisabledReason",
    "ExternalPlannerExecutionResult",
    "ExternalPlannerExecutionStatus",
    "ExternalPlannerRequest",
    "ExternalPlannerStatus",
    "MockExternalPlannerAdapter",
    "build_external_planner_request",
    "execute_mock_external_planner",
    "summarize_external_planner_execution",
    "summarize_external_planner_request",
]
