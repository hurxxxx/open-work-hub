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
GraphVerifierFailurePolicy = Literal[
    "not_required",
    "passed",
    "not_run_continue_with_gap_disclaimer",
    "failed_continue_with_gap_disclaimer",
]


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
            graph_execution_adapter=None,
        )
    schedule_summary = decision.graph_schedule_summary
    if not isinstance(schedule_summary, dict) or schedule_summary.get("state") != "planned":
        return replace(
            decision,
            graph_execution_status="not_applicable",
            graph_execution_fallback_reason="graph_schedule_unavailable",
            graph_execution_adapter=None,
        )
    if not graph_execution_enabled:
        return replace(
            decision,
            graph_execution_status="disabled",
            graph_execution_fallback_reason="graph_execution_disabled",
            graph_execution_adapter=None,
        )
    candidate_summary = decision.graph_candidate_summary
    if not _is_supported_by_graph_node_runner(candidate_summary):
        return replace(
            decision,
            graph_execution_status="adapter_unavailable",
            graph_execution_fallback_reason="graph_execution_adapter_unsupported",
            graph_execution_adapter=None,
        )
    return replace(
        decision,
        graph_used=True,
        graph_fallback_reason=None,
        graph_schedule_summary=_mark_schedule_execution_enabled(schedule_summary),
        graph_execution_status="adapter_selected",
        graph_execution_fallback_reason=None,
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
) -> list[dict[str, Any]]:
    node_input = _graph_node_input_text(
        messages=messages,
        agent_id=agent_id,
        step=step,
        prior_outputs=prior_outputs,
        candidate_summary=candidate_summary,
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
) -> str:
    evidence_packet = materialize_graph_evidence_packet(
        messages=messages,
        node_outputs=node_outputs,
        candidate_summary=candidate_summary,
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
) -> EvidencePacket:
    failed_outputs = [output for output in node_outputs if output.status == "failed"]
    completed_outputs = [
        output
        for output in node_outputs
        if output.status == "completed" and (output.text or output.tool_results)
    ]
    source_agent_ids = [output.agent_id for output in node_outputs]
    tool_result_count = sum(len(output.tool_results) for output in node_outputs)
    items = _evidence_items_from_node_outputs(node_outputs)
    verifier_status = _verifier_status(node_outputs)
    requires_verifier = bool(
        isinstance(candidate_summary, dict)
        and candidate_summary.get("requires_verifier") is True
    )
    ready_for_grounded_write = bool(items) and (
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
    if not isinstance(candidate_summary, dict):
        return False
    if candidate_summary.get("intent") != "report":
        return False
    if candidate_summary.get("requires_approval_preview") is True:
        return False
    if candidate_summary.get("risk") == "high":
        return False
    return candidate_summary.get("output_kind") in {"answer", "artifact"}


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
) -> str:
    depends_on = _string_list(step.get("depends_on_agent_ids"))
    node_kind = _node_kind(agent_id)
    evidence_packet = materialize_graph_evidence_packet(
        messages=messages,
        node_outputs=prior_outputs,
        candidate_summary=candidate_summary,
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
