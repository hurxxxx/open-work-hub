from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from typing import Any, Literal

from aidoo_api.domains.ai.runtime.contracts import (
    EvidenceCoverage,
    EvidenceItem,
    EvidencePacket,
    QueryPlan,
)
from aidoo_api.domains.ai.runtime.routing import RuntimeRoutingDecision


GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID = "graph_instructed_single_loop_v0"
GRAPH_NODE_RUNNER_ADAPTER_ID = "graph_node_runner_v0"
GRAPH_VERIFIER_AGENT_ID = "verifier.grounding"
GRAPH_WRITER_AGENT_ID = "writer.template"

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
GraphVerifierFailurePolicy = Literal[
    "not_required",
    "passed",
    "not_run_continue_with_gap_disclaimer",
    "failed_continue_with_gap_disclaimer",
]

SUPPORTED_GRAPH_NODE_RUNNER_INTENTS = ("report",)
SUPPORTED_GRAPH_NODE_RUNNER_OUTPUT_KINDS = ("answer", "artifact")


@dataclass(frozen=True)
class GraphNodeOutput:
    agent_id: str
    status: str
    text: str = ""
    tool_results: tuple[str, ...] = ()
    error: str | None = None


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
    if not isinstance(schedule_summary, dict) or schedule_summary.get("state") != "planned":
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
        graph_schedule_summary=_mark_schedule_execution_enabled(schedule_summary),
        graph_execution_status="adapter_selected",
        graph_execution_fallback_reason=None,
        graph_execution_fallback_policy=None,
        graph_execution_adapter=GRAPH_NODE_RUNNER_ADAPTER_ID,
    )


def build_graph_execution_system_prompt(decision: RuntimeRoutingDecision) -> str:
    candidate_summary = decision.graph_candidate_summary or {}
    schedule_summary = decision.graph_schedule_summary or {}
    planned_agent_ids = _string_list(schedule_summary.get("planned_agent_ids"))
    steps = schedule_summary.get("steps")
    step_lines: list[str] = []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            agent_id = step.get("agent_id")
            if not isinstance(agent_id, str) or not agent_id:
                continue
            depends_on = ", ".join(_string_list(step.get("depends_on_agent_ids")))
            suffix = f" after [{depends_on}]" if depends_on else ""
            step_lines.append(f"- {agent_id}{suffix}")

    graph_lines = "\n".join(step_lines) if step_lines else "- " + "\n- ".join(planned_agent_ids)
    domains = ", ".join(_string_list(candidate_summary.get("domains"))) or "unknown"
    adapter_id = decision.graph_execution_adapter or GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID
    return (
        f"Graph execution adapter: {adapter_id}.\n"
        "Follow the accepted execution graph as the control plan for this turn. "
        "Use only the tools exposed in this request and do not invent workspace facts. "
        "Treat domain/search nodes as evidence collection work, verifier nodes as coverage "
        "checks, and writer nodes as final response rendering.\n"
        f"Intent: {candidate_summary.get('intent') or 'unknown'}\n"
        f"Domains: {domains}\n"
        f"Risk: {candidate_summary.get('risk') or 'unknown'}\n"
        f"Output kind: {candidate_summary.get('output_kind') or 'answer'}\n"
        "Planned graph steps:\n"
        f"{graph_lines}\n"
        "If the available tools or context cannot satisfy an evidence step, state the gap "
        "explicitly instead of filling it from assumption. For grounded reports, put the "
        "substantive output in a document artifact when it is longer than a short answer."
    )


def build_graph_node_system_prompt(agent_id: str) -> str:
    return (
        f"Execute graph node `{agent_id}` only. "
        "Do not write the final answer. Use available read-only tools when they help. "
        "Return concise Korean evidence notes with source/tool context. "
        "If this node cannot collect evidence, state the gap explicitly."
    )


def build_graph_node_messages(
    messages: list[dict[str, Any]],
    *,
    agent_id: str,
    step: dict[str, Any],
    prior_outputs: list[GraphNodeOutput],
    candidate_summary: dict[str, Any] | None,
    external_planner_execution_summary: dict[str, Any] | None = None,
    external_search_execution_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    node_input = _graph_node_input_text(
        messages=messages,
        agent_id=agent_id,
        step=step,
        prior_outputs=prior_outputs,
        candidate_summary=candidate_summary,
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    )
    return [
        *[dict(message) for message in messages],
        {
            "role": "user",
            "content": node_input,
        },
    ]


def build_graph_writer_system_prompt(
    *,
    messages: list[dict[str, Any]],
    node_outputs: list[GraphNodeOutput],
    candidate_summary: dict[str, Any] | None,
    external_planner_execution_summary: dict[str, Any] | None = None,
    external_search_execution_summary: dict[str, Any] | None = None,
) -> str:
    evidence_packet = materialize_graph_evidence_packet(
        messages=messages,
        node_outputs=node_outputs,
        candidate_summary=candidate_summary,
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    )
    verifier_policy = graph_verifier_failure_policy(
        node_outputs,
        requires_verifier=bool(
            isinstance(candidate_summary, dict)
            and candidate_summary.get("requires_verifier") is True
        ),
    )
    return (
        "You are the writer.template graph node. Use this EvidencePacket JSON as "
        "the only collected evidence for this graph run. Do not claim facts that "
        "are missing from the evidence. If evidence is thin, say so. "
        "If ready_for_grounded_write is false, write a limited answer that makes "
        "the verification gap explicit instead of presenting the report as fully "
        "verified.\n\n"
        f"verifier_failure_policy: {verifier_policy}\n"
        f"{render_evidence_packet(evidence_packet)}"
    )


def materialize_graph_evidence_packet(
    *,
    messages: list[dict[str, Any]],
    node_outputs: list[GraphNodeOutput],
    candidate_summary: dict[str, Any] | None,
    external_planner_execution_summary: dict[str, Any] | None = None,
    external_search_execution_summary: dict[str, Any] | None = None,
) -> EvidencePacket:
    failed_outputs = [output for output in node_outputs if output.status == "failed"]
    completed_outputs = [
        output
        for output in node_outputs
        if output.status == "completed" and (output.text or output.tool_results)
    ]
    provider_source_agent_ids = _external_provider_source_agent_ids(
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    )
    source_agent_ids = [output.agent_id for output in node_outputs]
    source_agent_ids.extend(provider_source_agent_ids)
    tool_result_count = sum(len(output.tool_results) for output in node_outputs)
    node_items = _evidence_items_from_node_outputs(node_outputs)
    provider_items = _external_provider_evidence_items(
        external_search_execution_summary=external_search_execution_summary,
    )
    items = [*node_items, *provider_items]
    verifier_status = _verifier_status(node_outputs)
    requires_verifier = bool(
        isinstance(candidate_summary, dict)
        and candidate_summary.get("requires_verifier") is True
    )
    ready_for_grounded_write = bool(node_items) and (
        verifier_status == "completed" if requires_verifier else verifier_status != "failed"
    )
    source_kinds = sorted({item.source_kind for item in items})
    sources_used = [item.ref for item in items[:12]]
    covered = [output.agent_id for output in completed_outputs]
    missed = [output.agent_id for output in failed_outputs]
    gaps = _evidence_gaps(node_outputs, verifier_status=verifier_status)
    return EvidencePacket(
        intent=_candidate_string(candidate_summary, "intent"),
        output_kind=_candidate_string(candidate_summary, "output_kind"),
        source_agent_ids=source_agent_ids,
        query_plan=QueryPlan(
            keywords=_extract_query_keywords(messages),
            source_kinds=source_kinds,
            sources_used=sources_used,
            candidate_top_k=len(items),
            rerank_top_k=min(len(items), 8),
            final_evidence_token_budget=2048,
            external_search_used=_external_search_used(
                external_search_execution_summary
            ),
            external_search_provider=_external_search_provider(
                external_search_execution_summary
            ),
            sanitized_query_ref=_external_search_query_ref(
                external_search_execution_summary
            ),
        ),
        items=items,
        coverage=EvidenceCoverage(
            intents_covered=covered,
            intents_missed=missed,
        ),
        quality={
            "verifier_status": verifier_status,
            "ready_for_grounded_write": ready_for_grounded_write,
            "failed_node_count": len(failed_outputs),
            "evidence_item_count": len(items),
            "tool_result_count": tool_result_count,
        },
        gaps=gaps,
    )


def summarize_graph_evidence_packet(packet: EvidencePacket) -> dict[str, Any]:
    return {
        "packet_version": packet.packet_version,
        "intent": packet.intent,
        "output_kind": packet.output_kind,
        "source_agent_count": len(packet.source_agent_ids),
        "source_kinds": list(packet.query_plan.source_kinds),
        "evidence_item_count": len(packet.items),
        "gap_count": len(packet.gaps),
        "verifier_status": packet.quality.verifier_status,
        "ready_for_grounded_write": packet.quality.ready_for_grounded_write,
        "failed_node_count": packet.quality.failed_node_count,
        "tool_result_count": packet.quality.tool_result_count,
    }


def render_evidence_packet(packet: EvidencePacket) -> str:
    return "EvidencePacket JSON:\n" + json.dumps(
        packet.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def graph_verifier_failure_policy(
    node_outputs: list[GraphNodeOutput],
    *,
    requires_verifier: bool,
) -> GraphVerifierFailurePolicy:
    if not requires_verifier:
        return "not_required"
    verifier_status = _verifier_status(node_outputs)
    if verifier_status == "completed":
        return "passed"
    if verifier_status == "failed":
        return "failed_continue_with_gap_disclaimer"
    return "not_run_continue_with_gap_disclaimer"


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
    schedule_state = _graph_schedule_state(decision.graph_schedule_summary)
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


def _graph_schedule_state(schedule_summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(schedule_summary, dict):
        return {}
    return {
        key: schedule_summary.get(key)
        for key in ("state", "execution_enabled", "step_count")
        if key in schedule_summary
    }


def _mark_schedule_execution_enabled(
    schedule_summary: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(schedule_summary)
    updated["execution_enabled"] = True
    return updated


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _graph_node_input_text(
    *,
    messages: list[dict[str, Any]],
    agent_id: str,
    step: dict[str, Any],
    prior_outputs: list[GraphNodeOutput],
    candidate_summary: dict[str, Any] | None,
    external_planner_execution_summary: dict[str, Any] | None,
    external_search_execution_summary: dict[str, Any] | None,
) -> str:
    depends_on = _string_list(step.get("depends_on_agent_ids"))
    node_kind = _node_kind(agent_id)
    evidence_packet = materialize_graph_evidence_packet(
        messages=messages,
        node_outputs=prior_outputs,
        candidate_summary=candidate_summary,
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    )
    return (
        "Deterministic graph node input\n"
        f"agent_id: {agent_id}\n"
        f"node_kind: {node_kind}\n"
        f"depends_on_agent_ids: {depends_on}\n"
        f"intent: {_candidate_string(candidate_summary, 'intent') or 'unknown'}\n"
        f"output_kind: {_candidate_string(candidate_summary, 'output_kind') or 'unknown'}\n"
        f"user_task: {_latest_user_text(messages)}\n\n"
        f"{render_evidence_packet(evidence_packet)}\n\n"
        "Node output requirements:\n"
        "- Return only evidence notes for this node.\n"
        "- Include source/tool context for every concrete fact.\n"
        "- Use 'gap:' lines for missing evidence or unavailable tools.\n"
        "- Do not produce the final report."
    )


def _evidence_items_from_node_outputs(
    node_outputs: list[GraphNodeOutput],
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for output in node_outputs:
        source_kind = _source_kind_for_agent(output.agent_id)
        authority_class = _authority_class_for_source_kind(source_kind)
        trust_level = "trusted" if source_kind != "verifier" else "mixed"
        if output.text:
            items.append(
                EvidenceItem(
                    ref=f"graph-node:{output.agent_id}#note",
                    source_kind=source_kind,
                    excerpt=_trim_graph_text(output.text, limit=1200),
                    provenance=output.agent_id,
                    trust_level=trust_level,
                    authority_class=authority_class,
                )
            )
        for index, result in enumerate(output.tool_results, start=1):
            items.append(
                EvidenceItem(
                    ref=f"graph-node:{output.agent_id}#tool-{index}",
                    source_kind=source_kind,
                    excerpt=_trim_graph_text(result, limit=900),
                    provenance=output.agent_id,
                    trust_level=trust_level,
                    authority_class=authority_class,
                )
            )
    return items


def _external_provider_source_agent_ids(
    *,
    external_planner_execution_summary: dict[str, Any] | None,
    external_search_execution_summary: dict[str, Any] | None,
) -> list[str]:
    agent_ids: list[str] = []
    if _execution_status(external_planner_execution_summary) == "completed":
        adapter_id = _summary_string(external_planner_execution_summary, "adapter_id")
        if adapter_id:
            agent_ids.append(adapter_id)
    if _external_search_used(external_search_execution_summary):
        adapter_id = _summary_string(external_search_execution_summary, "adapter_id")
        if adapter_id:
            agent_ids.append(adapter_id)
    return agent_ids


def _external_provider_evidence_items(
    *,
    external_search_execution_summary: dict[str, Any] | None,
) -> list[EvidenceItem]:
    if not _external_search_used(external_search_execution_summary):
        return []
    query_ref = _external_search_query_ref(external_search_execution_summary)
    if not query_ref:
        return []
    provider = _external_search_provider(external_search_execution_summary) or "unknown"
    adapter_id = _summary_string(
        external_search_execution_summary,
        "adapter_id",
    ) or "external_search"
    execution_provider = _summary_string(
        external_search_execution_summary,
        "execution_provider",
    ) or "unknown"
    source_kinds = _string_list(
        external_search_execution_summary.get("source_kinds")
        if isinstance(external_search_execution_summary, dict)
        else None
    )
    source_kind = source_kinds[0] if source_kinds else "external_web"
    result_count = _summary_int(external_search_execution_summary, "result_count")
    result_refs = _external_search_result_refs(
        external_search_execution_summary,
        query_ref=query_ref,
        result_count=result_count,
    )
    items: list[EvidenceItem] = []
    for index, result_ref in enumerate(result_refs, start=1):
        excerpt = (
            "Mock external search normalized result metadata only; "
            f"sanitized_query_ref={query_ref}; "
            f"result_index={index}; "
            f"normalized_result_count={result_count}; "
            f"source_kinds={source_kinds or [source_kind]}."
        )
        items.append(
            EvidenceItem(
                ref=result_ref,
                source_kind=source_kind,
                excerpt=excerpt,
                provenance=f"{adapter_id}:{execution_provider}:{provider}",
                trust_level="untrusted",
                authority_class="public_web",
            )
        )
    return items


def _external_search_result_refs(
    summary: dict[str, Any] | None,
    *,
    query_ref: str,
    result_count: int,
) -> list[str]:
    result_refs = _string_list(
        summary.get("result_refs") if isinstance(summary, dict) else None
    )
    if result_refs:
        return result_refs
    fallback_count = max(result_count, 1)
    return [
        f"external-search:{query_ref}:result-{index}"
        for index in range(1, fallback_count + 1)
    ]


def _evidence_gaps(
    node_outputs: list[GraphNodeOutput],
    *,
    verifier_status: str | None,
) -> list[str]:
    gaps: list[str] = []
    for output in node_outputs:
        if output.status == "failed":
            error = _trim_graph_text(output.error or "node failed without detail", limit=240)
            gaps.append(f"{output.agent_id}: {error}")
        elif not output.text and not output.tool_results:
            gaps.append(f"{output.agent_id}: no evidence returned")
    if verifier_status == "failed":
        gaps.append("verifier.grounding: grounding verification failed")
    return _dedupe(gaps)


def _verifier_status(node_outputs: list[GraphNodeOutput]) -> str | None:
    for output in node_outputs:
        if output.agent_id == GRAPH_VERIFIER_AGENT_ID:
            return output.status
    return None


def _source_kind_for_agent(agent_id: str) -> str:
    if agent_id.startswith("domain."):
        return agent_id.removeprefix("domain.")
    if agent_id.startswith("search."):
        return "rag"
    if agent_id == GRAPH_VERIFIER_AGENT_ID:
        return "verifier"
    return "runtime"


def _authority_class_for_source_kind(source_kind: str) -> str:
    if source_kind in {"pms", "meeting", "docs", "planner", "rag"}:
        return "internal_system_of_record"
    if source_kind in {"external_web", "public_web_mock"}:
        return "public_web"
    return "unknown"


def _node_kind(agent_id: str) -> str:
    if agent_id.startswith("domain."):
        return "domain_evidence"
    if agent_id.startswith("search."):
        return "search_evidence"
    if agent_id == GRAPH_VERIFIER_AGENT_ID:
        return "evidence_verifier"
    if agent_id == GRAPH_WRITER_AGENT_ID:
        return "writer"
    return "runtime_node"


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return _trim_graph_text(content, limit=1400)
    return ""


def _extract_query_keywords(messages: list[dict[str, Any]]) -> list[str]:
    text = _latest_user_text(messages)
    tokens = [
        token.strip(" \t\n\r.,!?;:()[]{}'\"`")
        for token in re.split(r"\s+", text)
        if token.strip()
    ]
    selected: list[str] = []
    for token in tokens:
        if len(token) < 2 or token in selected:
            continue
        selected.append(token[:40])
        if len(selected) >= 8:
            break
    return selected


def _candidate_string(candidate_summary: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(candidate_summary, dict):
        return None
    value = candidate_summary.get(key)
    return value if isinstance(value, str) and value else None


def _external_search_used(summary: dict[str, Any] | None) -> bool:
    return _execution_status(summary) == "completed" and _summary_int(
        summary,
        "result_count",
    ) > 0


def _external_search_provider(summary: dict[str, Any] | None) -> str | None:
    if not _external_search_used(summary):
        return None
    return _summary_string(summary, "provider")


def _external_search_query_ref(summary: dict[str, Any] | None) -> str | None:
    if not _external_search_used(summary):
        return None
    query_digest = _summary_string(summary, "query_digest")
    return f"sha256:{query_digest}" if query_digest else None


def _execution_status(summary: dict[str, Any] | None) -> str | None:
    return _summary_string(summary, "status")


def _summary_string(summary: dict[str, Any] | None, key: str) -> str | None:
    if not isinstance(summary, dict):
        return None
    value = summary.get(key)
    return value if isinstance(value, str) and value else None


def _summary_int(summary: dict[str, Any] | None, key: str) -> int:
    if not isinstance(summary, dict):
        return 0
    try:
        return int(summary.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _trim_graph_text(value: str, *, limit: int) -> str:
    collapsed = " ".join(value.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 1]}…"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        out.append(value)
        seen.add(value)
    return out


__all__ = [
    "GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID",
    "GRAPH_NODE_RUNNER_ADAPTER_ID",
    "GRAPH_VERIFIER_AGENT_ID",
    "GRAPH_WRITER_AGENT_ID",
    "GraphNodeOutput",
    "GraphExecutionStatus",
    "GraphExecutionFallbackReason",
    "GraphVerifierFailurePolicy",
    "attach_graph_execution_adapter_decision",
    "build_graph_node_messages",
    "build_graph_node_system_prompt",
    "build_graph_writer_system_prompt",
    "build_graph_execution_system_prompt",
    "graph_verifier_failure_policy",
    "materialize_graph_evidence_packet",
    "render_evidence_packet",
    "summarize_graph_evidence_packet",
]
