from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from open_work_hub_api.domains.ai.runtime.contracts import RuntimeProfile
from open_work_hub_api.domains.ai.runtime.manager_candidate import (
    supports_deterministic_manager_candidate,
)
from open_work_hub_api.domains.ai.runtime.manager_validation import ManagerGraphValidationResult
from open_work_hub_api.domains.ai.runtime.routing_signals import select_runtime_profile_signal

GraphGateDecision = Literal["disabled", "eligible", "ineligible"]
GraphFallbackReason = Literal[
    "feature_disabled",
    "runtime_profile_ineligible",
    "graph_runtime_not_implemented",
]
GraphValidationStatus = Literal[
    "not_applicable",
    "candidate_unavailable",
    "accepted",
    "rejected",
]


@dataclass(frozen=True)
class RuntimeRoutingDecision:
    runtime_profile: RuntimeProfile
    reason_codes: tuple[str, ...]
    graph_gate: GraphGateDecision
    graph_fallback_reason: GraphFallbackReason | None
    graph_used: bool = False
    graph_validation_status: GraphValidationStatus = "not_applicable"
    graph_validation_fallback_reason: str | None = None
    graph_registry_agent_count: int = 0
    graph_write_agent_count: int = 0
    graph_candidate_summary: dict[str, Any] | None = None
    graph_schedule_summary: dict[str, Any] | None = None
    external_egress_summary: dict[str, Any] | None = None
    external_planner_summary: dict[str, Any] | None = None
    external_search_summary: dict[str, Any] | None = None
    external_planner_execution_summary: dict[str, Any] | None = None
    external_search_execution_summary: dict[str, Any] | None = None
    graph_execution_status: str = "not_applicable"
    graph_execution_fallback_reason: str | None = None
    graph_execution_fallback_policy: dict[str, Any] | None = None
    graph_execution_adapter: str | None = None


def attach_trace_only_graph_validation(
    decision: RuntimeRoutingDecision,
    *,
    registry_agent_count: int,
    write_agent_count: int,
) -> RuntimeRoutingDecision:
    if decision.graph_gate != "eligible":
        return decision
    return replace(
        decision,
        graph_validation_status="candidate_unavailable",
        graph_validation_fallback_reason=decision.graph_fallback_reason,
        graph_registry_agent_count=max(registry_agent_count, 0),
        graph_write_agent_count=max(write_agent_count, 0),
    )


def attach_manager_graph_validation_result(
    decision: RuntimeRoutingDecision,
    *,
    validation: ManagerGraphValidationResult,
    registry_agent_count: int,
    write_agent_count: int,
    graph_candidate_summary: dict[str, Any] | None = None,
    graph_schedule_summary: dict[str, Any] | None = None,
) -> RuntimeRoutingDecision:
    if decision.graph_gate != "eligible":
        return decision
    return replace(
        decision,
        graph_validation_status="accepted" if validation.accepted else "rejected",
        graph_validation_fallback_reason=validation.fallback_reason,
        graph_registry_agent_count=max(registry_agent_count, 0),
        graph_write_agent_count=max(write_agent_count, 0),
        graph_candidate_summary=graph_candidate_summary if validation.accepted else None,
        graph_schedule_summary=graph_schedule_summary if validation.accepted else None,
    )


def select_runtime_profile(
    *,
    messages: list[dict[str, str]],
    allowed_app_ids: list[str] | None,
    max_tokens: int | None,
    graph_enabled: bool,
) -> RuntimeRoutingDecision:
    signal = select_runtime_profile_signal(
        messages=messages,
        allowed_app_ids=allowed_app_ids,
        max_tokens=max_tokens,
    )
    return _decision(
        signal.runtime_profile,
        signal.reason_codes,
        graph_enabled=graph_enabled,
    )


def _decision(
    runtime_profile: RuntimeProfile,
    reason_codes: tuple[str, ...],
    *,
    graph_enabled: bool,
) -> RuntimeRoutingDecision:
    graph_gate: GraphGateDecision = "disabled"
    graph_fallback_reason: GraphFallbackReason = "feature_disabled"
    if graph_enabled:
        graph_gate = (
            "eligible"
            if supports_deterministic_manager_candidate(runtime_profile)
            else "ineligible"
        )
        graph_fallback_reason = (
            "graph_runtime_not_implemented"
            if graph_gate == "eligible"
            else "runtime_profile_ineligible"
        )
    return RuntimeRoutingDecision(
        runtime_profile=runtime_profile,
        reason_codes=tuple(reason_codes),
        graph_gate=graph_gate,
        graph_fallback_reason=graph_fallback_reason,
        graph_used=False,
    )


__all__ = [
    "RuntimeRoutingDecision",
    "attach_manager_graph_validation_result",
    "attach_trace_only_graph_validation",
    "select_runtime_profile",
]
