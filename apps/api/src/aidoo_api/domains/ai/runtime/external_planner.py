from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aidoo_api.domains.ai.runtime.contracts import RuntimeProfile
from aidoo_api.domains.ai.runtime.external_egress import ExternalEgressDecision


EXTERNAL_PLANNER_ADAPTER_ID = "external_planner_v0"

ExternalPlannerStatus = Literal["disabled", "ready"]
ExternalPlannerDisabledReason = Literal[
    "capability_mismatch",
    "egress_denied",
    "sanitized_empty",
]
ExternalPlannerExecutionStatus = Literal["disabled", "skipped", "completed", "failed"]
ExternalPlannerExecutionDisabledReason = Literal[
    "execution_flag_disabled",
    "request_not_ready",
]


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
    execution_provider: Literal["mock"] = "mock"
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
    if egress_decision.capability != "planning":
        return ExternalPlannerRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="capability_mismatch",
            egress_reason=egress_decision.reason,
        )
    if not egress_decision.allow_external:
        return ExternalPlannerRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="egress_denied",
            egress_reason=egress_decision.reason,
        )
    sanitized_prompt = egress_decision.sanitized_prompt.strip()
    if not sanitized_prompt:
        return ExternalPlannerRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="sanitized_empty",
            egress_reason=egress_decision.reason,
        )
    return ExternalPlannerRequest(
        status="ready",
        provider=egress_decision.provider,
        egress_reason=egress_decision.reason,
        messages=_planner_messages(
            sanitized_prompt=sanitized_prompt,
            runtime_profile=runtime_profile,
            agent_ids=agent_ids,
        ),
    )


def summarize_external_planner_request(
    request: ExternalPlannerRequest,
) -> dict[str, Any]:
    return {
        "adapter_id": request.adapter_id,
        "status": request.status,
        "provider": request.provider,
        "disabled_reason": request.disabled_reason,
        "egress_reason": request.egress_reason,
        "message_count": len(request.messages),
    }


def execute_mock_external_planner(
    request: ExternalPlannerRequest,
    *,
    execution_enabled: bool,
    force_error_class: str | None = None,
) -> ExternalPlannerExecutionResult:
    if not execution_enabled:
        return ExternalPlannerExecutionResult(
            status="disabled",
            provider=request.provider,
            disabled_reason="execution_flag_disabled",
        )
    if request.status != "ready":
        return ExternalPlannerExecutionResult(
            status="skipped",
            provider=request.provider,
            disabled_reason="request_not_ready",
        )
    if force_error_class:
        return ExternalPlannerExecutionResult(
            status="failed",
            provider=request.provider,
            error_class=force_error_class,
        )
    planner_input = _planner_input_from_request(request)
    runtime_profile = str(planner_input.get("runtime_profile") or "")
    return ExternalPlannerExecutionResult(
        status="completed",
        provider=request.provider,
        planned_agent_ids=_string_list(planner_input.get("available_agent_ids")),
        intent_hint=_intent_hint(runtime_profile),
        output_kind_hint=_output_kind_hint(runtime_profile),
        raw_output_persisted=False,
    )


def summarize_external_planner_execution(
    result: ExternalPlannerExecutionResult,
) -> dict[str, Any]:
    return {
        "adapter_id": result.adapter_id,
        "execution_provider": result.execution_provider,
        "status": result.status,
        "provider": result.provider,
        "disabled_reason": result.disabled_reason,
        "planned_agent_count": len(result.planned_agent_ids),
        "intent_hint": result.intent_hint,
        "output_kind_hint": result.output_kind_hint,
        "latency_ms": result.latency_ms,
        "retry_count": result.retry_count,
        "error_class": result.error_class,
        "estimated_cost_microunits": result.estimated_cost_microunits,
        "raw_output_persisted": result.raw_output_persisted,
    }


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


def _intent_hint(runtime_profile: str) -> str:
    if runtime_profile == "grounded_report":
        return "report"
    if runtime_profile == "high_risk_action":
        return "write"
    return "read"


def _output_kind_hint(runtime_profile: str) -> str:
    if runtime_profile == "grounded_report":
        return "artifact"
    if runtime_profile == "high_risk_action":
        return "approval_preview"
    return "answer"


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
