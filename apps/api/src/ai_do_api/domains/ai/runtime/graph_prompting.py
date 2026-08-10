from __future__ import annotations

from typing import Any

from ai_do_api.domains.ai.runtime.graph_schedule_summary import (
    graph_schedule_step_descriptions,
)
from ai_do_api.domains.ai.runtime.graph_execution_fallback_policy import (
    GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID,
)
from ai_do_api.domains.ai.runtime.graph_evidence_packet import (
    GRAPH_VERIFIER_AGENT_ID,
    GRAPH_WRITER_AGENT_ID,
    candidate_requires_graph_verifier,
    graph_verifier_failure_policy,
    materialize_graph_evidence_packet,
    render_evidence_packet,
)
from ai_do_api.domains.ai.runtime.graph_node_output import GraphNodeOutput
from ai_do_api.domains.ai.runtime.graph_projection_values import (
    graph_candidate_string,
    graph_latest_user_text,
    graph_string_list,
)
from ai_do_api.domains.ai.runtime.routing import RuntimeRoutingDecision


def build_graph_execution_system_prompt(decision: RuntimeRoutingDecision) -> str:
    candidate_summary = decision.graph_candidate_summary or {}
    schedule_summary = decision.graph_schedule_summary or {}
    step_descriptions = graph_schedule_step_descriptions(schedule_summary)
    graph_lines = (
        "\n".join(f"- {description}" for description in step_descriptions)
        if step_descriptions
        else "-"
    )
    domains = ", ".join(graph_string_list(candidate_summary.get("domains"))) or "unknown"
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
        requires_verifier=candidate_requires_graph_verifier(candidate_summary),
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


def graph_execution_scope_prompt(
    *,
    scope_system_prompt: str | None,
    runtime_routing: RuntimeRoutingDecision,
) -> str | None:
    return merge_system_prompts(
        scope_system_prompt,
        build_graph_execution_system_prompt(runtime_routing),
    )


def graph_node_scope_prompt(
    *,
    scope_system_prompt: str | None,
    runtime_routing: RuntimeRoutingDecision,
    agent_id: str,
) -> str | None:
    return merge_system_prompts(
        scope_system_prompt,
        build_graph_execution_system_prompt(runtime_routing),
        build_graph_node_system_prompt(agent_id),
    )


def graph_writer_scope_prompt(
    *,
    scope_system_prompt: str | None,
    runtime_routing: RuntimeRoutingDecision,
    messages: list[dict[str, Any]],
    node_outputs: list[GraphNodeOutput],
) -> str | None:
    return merge_system_prompts(
        scope_system_prompt,
        build_graph_execution_system_prompt(runtime_routing),
        build_graph_writer_system_prompt(
            messages=messages,
            node_outputs=node_outputs,
            candidate_summary=runtime_routing.graph_candidate_summary,
            external_planner_execution_summary=(
                runtime_routing.external_planner_execution_summary
            ),
            external_search_execution_summary=(
                runtime_routing.external_search_execution_summary
            ),
        ),
    )


def merge_system_prompts(*prompts: str | None) -> str | None:
    parts = [
        prompt.strip()
        for prompt in prompts
        if isinstance(prompt, str) and prompt.strip()
    ]
    return "\n\n".join(parts) if parts else None


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
    depends_on = graph_string_list(step.get("depends_on_agent_ids"))
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
        f"intent: {graph_candidate_string(candidate_summary, 'intent') or 'unknown'}\n"
        f"output_kind: {graph_candidate_string(candidate_summary, 'output_kind') or 'unknown'}\n"
        f"user_task: {graph_latest_user_text(messages)}\n\n"
        f"{render_evidence_packet(evidence_packet)}\n\n"
        "Node output requirements:\n"
        "- Return only evidence notes for this node.\n"
        "- Include source/tool context for every concrete fact.\n"
        "- Use 'gap:' lines for missing evidence or unavailable tools.\n"
        "- Do not produce the final report."
    )


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


__all__ = [
    "build_graph_execution_system_prompt",
    "build_graph_node_messages",
    "build_graph_node_system_prompt",
    "build_graph_writer_system_prompt",
    "graph_execution_scope_prompt",
    "graph_node_scope_prompt",
    "graph_writer_scope_prompt",
    "merge_system_prompts",
]
