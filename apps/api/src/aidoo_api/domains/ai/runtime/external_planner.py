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


class ExternalPlannerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: Literal["external_planner_v0"] = EXTERNAL_PLANNER_ADAPTER_ID
    status: ExternalPlannerStatus
    provider: str | None = None
    disabled_reason: ExternalPlannerDisabledReason | None = None
    egress_reason: str | None = None
    messages: list[dict[str, str]] = Field(default_factory=list)


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


__all__ = [
    "EXTERNAL_PLANNER_ADAPTER_ID",
    "ExternalPlannerDisabledReason",
    "ExternalPlannerRequest",
    "ExternalPlannerStatus",
    "build_external_planner_request",
    "summarize_external_planner_request",
]
