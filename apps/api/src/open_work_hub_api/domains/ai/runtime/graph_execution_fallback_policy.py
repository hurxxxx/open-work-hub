from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal

from open_work_hub_api.domains.ai.runtime.graph_schedule_summary import (
    enable_graph_schedule_summary_execution,
    graph_schedule_is_planned,
    project_graph_schedule_state,
)
from open_work_hub_api.domains.ai.runtime.routing import RuntimeRoutingDecision


GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID = "graph_instructed_single_loop_v0"
GRAPH_NODE_RUNNER_ADAPTER_ID = "graph_node_runner_v0"

GraphExecutionStatus = Literal[
    "not_applicable",
    "disabled",
    "adapter_unavailable",
    "adapter_selected",
]
GraphExecutionFallbackReason = Literal[
    "graph_schedule_unavailable",
    "graph_execution_disabled",
    "graph_candidate_unavailable",
    "graph_intent_unsupported",
    "graph_approval_preview_required",
    "graph_risk_high_unsupported",
    "graph_output_kind_unsupported",
]

SUPPORTED_GRAPH_NODE_RUNNER_INTENTS = ("report",)
SUPPORTED_GRAPH_NODE_RUNNER_OUTPUT_KINDS = ("answer", "artifact")


def attach_graph_execution_adapter_decision(
    decision: RuntimeRoutingDecision,
    *,
    graph_execution_enabled: bool,
) -> RuntimeRoutingDecision:
    if decision.graph_gate != "eligible" or decision.graph_validation_status != "accepted":
        return replace(
            decision,
            graph_execution_status="not_applicable",
            graph_execution_fallback_reason=None,
            graph_execution_fallback_policy=None,
            graph_execution_adapter=None,
        )
    schedule_summary = decision.graph_schedule_summary
    if not graph_schedule_is_planned(schedule_summary):
        fallback_reason: GraphExecutionFallbackReason = "graph_schedule_unavailable"
        return replace(
            decision,
            graph_execution_status="not_applicable",
            graph_execution_fallback_reason=fallback_reason,
            graph_execution_fallback_policy=_build_graph_execution_fallback_policy(
                fallback_reason,
                decision=decision,
                graph_execution_enabled=graph_execution_enabled,
            ),
            graph_execution_adapter=None,
        )
    if not graph_execution_enabled:
        fallback_reason = "graph_execution_disabled"
        return replace(
            decision,
            graph_execution_status="disabled",
            graph_execution_fallback_reason=fallback_reason,
            graph_execution_fallback_policy=_build_graph_execution_fallback_policy(
                fallback_reason,
                decision=decision,
                graph_execution_enabled=graph_execution_enabled,
            ),
            graph_execution_adapter=None,
        )
    candidate_summary = decision.graph_candidate_summary
    fallback_reason = _graph_node_runner_fallback_reason(candidate_summary)
    if fallback_reason is not None:
        return replace(
            decision,
            graph_execution_status="adapter_unavailable",
            graph_execution_fallback_reason=fallback_reason,
            graph_execution_fallback_policy=_build_graph_execution_fallback_policy(
                fallback_reason,
                decision=decision,
                graph_execution_enabled=graph_execution_enabled,
            ),
            graph_execution_adapter=None,
        )
    return replace(
        decision,
        graph_used=True,
        graph_fallback_reason=None,
        graph_schedule_summary=enable_graph_schedule_summary_execution(
            schedule_summary,
        ),
        graph_execution_status="adapter_selected",
        graph_execution_fallback_reason=None,
        graph_execution_fallback_policy=None,
        graph_execution_adapter=GRAPH_NODE_RUNNER_ADAPTER_ID,
    )


def _is_supported_by_graph_node_runner(
    candidate_summary: dict[str, Any] | None,
) -> bool:
    return _graph_node_runner_fallback_reason(candidate_summary) is None


def _graph_node_runner_fallback_reason(
    candidate_summary: dict[str, Any] | None,
) -> GraphExecutionFallbackReason | None:
    if not isinstance(candidate_summary, dict) or not candidate_summary:
        return "graph_candidate_unavailable"
    if candidate_summary.get("requires_approval_preview") is True:
        return "graph_approval_preview_required"
    if candidate_summary.get("risk") == "high":
        return "graph_risk_high_unsupported"
    if candidate_summary.get("intent") not in SUPPORTED_GRAPH_NODE_RUNNER_INTENTS:
        return "graph_intent_unsupported"
    if candidate_summary.get("output_kind") not in SUPPORTED_GRAPH_NODE_RUNNER_OUTPUT_KINDS:
        return "graph_output_kind_unsupported"
    return None


def _build_graph_execution_fallback_policy(
    reason: GraphExecutionFallbackReason,
    *,
    decision: RuntimeRoutingDecision,
    graph_execution_enabled: bool,
) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "reason": reason,
        "blocked_adapter": GRAPH_NODE_RUNNER_ADAPTER_ID,
        "fallback_adapter": GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID,
        "fallback_path": "single_loop",
        "graph_execution_enabled": graph_execution_enabled,
        "supported_intents": list(SUPPORTED_GRAPH_NODE_RUNNER_INTENTS),
        "supported_output_kinds": list(SUPPORTED_GRAPH_NODE_RUNNER_OUTPUT_KINDS),
    }
    candidate_shape = _graph_candidate_shape(decision.graph_candidate_summary)
    if candidate_shape:
        policy["candidate_shape"] = candidate_shape
    schedule_state = project_graph_schedule_state(decision.graph_schedule_summary)
    if schedule_state:
        policy["schedule_state"] = schedule_state
    return policy


def _graph_candidate_shape(candidate_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(candidate_summary, dict):
        return {}
    return {
        key: candidate_summary.get(key)
        for key in (
            "intent",
            "risk",
            "output_kind",
            "requires_verifier",
            "requires_approval_preview",
        )
        if key in candidate_summary
    }


__all__ = [
    "GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID",
    "GRAPH_NODE_RUNNER_ADAPTER_ID",
    "GraphExecutionFallbackReason",
    "GraphExecutionStatus",
    "SUPPORTED_GRAPH_NODE_RUNNER_INTENTS",
    "SUPPORTED_GRAPH_NODE_RUNNER_OUTPUT_KINDS",
    "attach_graph_execution_adapter_decision",
]
