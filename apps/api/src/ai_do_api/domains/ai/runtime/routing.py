from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from ai_do_api.domains.ai.runtime.contracts import RuntimeProfile
from ai_do_api.domains.ai.runtime.manager_validation import ManagerGraphValidationResult


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

LONG_DOC_CHAR_THRESHOLD = 12_000
LONG_DOC_MAX_TOKENS_THRESHOLD = 32_768
REPORT_KEYWORDS = (
    "보고서",
    "리포트",
    "비교",
    "분석",
    "종합",
    "근거",
    "출처",
    "citation",
    "evidence",
    "template",
    "템플릿",
)
LONG_DOC_KEYWORDS = (
    "장문",
    "전체 문서",
    "전문",
    "긴 문서",
    "batch",
    "일괄",
)
HIGH_RISK_KEYWORDS = (
    "등록",
    "수정",
    "삭제",
    "승인",
    "예약",
    "전송",
    "생성해줘",
    "만들어줘",
    "create",
    "update",
    "delete",
    "send",
    "approve",
)


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
    text = _message_text(messages)
    lowered = text.lower()
    reason_codes: list[str] = []

    if allowed_app_ids == []:
        reason_codes.append("text_only_scope")

    if max_tokens is not None and max_tokens >= LONG_DOC_MAX_TOKENS_THRESHOLD:
        reason_codes.append("large_output_budget")
        return _decision("long_doc", reason_codes, graph_enabled=graph_enabled)

    if len(text) >= LONG_DOC_CHAR_THRESHOLD or _contains_any(lowered, LONG_DOC_KEYWORDS):
        reason_codes.append("long_doc_signal")
        return _decision("long_doc", reason_codes, graph_enabled=graph_enabled)

    if _contains_any(lowered, REPORT_KEYWORDS) or _has_multiple_app_scope(allowed_app_ids):
        reason_codes.append("grounded_report_signal")
        return _decision("grounded_report", reason_codes, graph_enabled=graph_enabled)

    if _contains_any(lowered, HIGH_RISK_KEYWORDS) and allowed_app_ids != []:
        reason_codes.append("write_or_external_action_signal")
        return _decision("high_risk_action", reason_codes, graph_enabled=graph_enabled)

    reason_codes.append("default_interactive_read")
    return _decision("interactive_read", reason_codes, graph_enabled=graph_enabled)


def _decision(
    runtime_profile: RuntimeProfile,
    reason_codes: list[str],
    *,
    graph_enabled: bool,
) -> RuntimeRoutingDecision:
    graph_gate: GraphGateDecision = "disabled"
    graph_fallback_reason: GraphFallbackReason = "feature_disabled"
    if graph_enabled:
        graph_gate = (
            "eligible"
            if runtime_profile in {"grounded_report", "high_risk_action"}
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


def _message_text(messages: list[dict[str, str]]) -> str:
    return "\n".join(str(message.get("content") or "") for message in messages)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _has_multiple_app_scope(allowed_app_ids: list[str] | None) -> bool:
    return allowed_app_ids is not None and len(set(allowed_app_ids)) > 1


__all__ = [
    "RuntimeRoutingDecision",
    "attach_manager_graph_validation_result",
    "attach_trace_only_graph_validation",
    "select_runtime_profile",
]
