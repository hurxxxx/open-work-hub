from __future__ import annotations

from typing import Any

from open_work_hub_api.domains.ai.runtime.graph_evidence_packet import (
    graph_verifier_failure_policy,
    materialize_graph_evidence_packet,
    summarize_graph_evidence_packet,
)
from open_work_hub_api.domains.ai.runtime.graph_node_output import GraphNodeOutput
from open_work_hub_api.domains.ai.runtime.graph_projection_values import trim_graph_text


GraphNodeSummary = dict[str, Any]


def graph_node_execution_summary(
    *,
    adapter: str,
    node_outputs: list[GraphNodeOutput],
    planned_steps: list[dict[str, Any]],
    writer_status: str,
    messages: list[dict[str, Any]],
    candidate_summary: dict[str, Any] | None,
    external_planner_execution_summary: dict[str, Any] | None = None,
    external_search_execution_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    nodes = [_node_summary(output) for output in node_outputs]
    planned_agent_ids = _planned_agent_ids(planned_steps)
    covered_agent_ids = {node["agent_id"] for node in nodes}
    if "writer.template" in planned_agent_ids:
        nodes.append(_writer_node_summary(writer_status))
        covered_agent_ids.add("writer.template")
    return _graph_execution_summary(
        adapter=adapter,
        planned_agent_ids=planned_agent_ids,
        covered_node_count=len(covered_agent_ids),
        nodes=nodes,
        messages=messages,
        node_outputs=node_outputs,
        candidate_summary=candidate_summary,
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    )


def graph_execution_adapter_error_summary(
    *,
    adapter: str,
    planned_steps: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    error_class: str,
    candidate_summary: dict[str, Any] | None,
    external_planner_execution_summary: dict[str, Any] | None = None,
    external_search_execution_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    planned_agent_ids = _planned_agent_ids(planned_steps)
    nodes = [_adapter_error_node_summary(agent_id, error_class) for agent_id in planned_agent_ids]
    return _graph_execution_summary(
        adapter=adapter,
        adapter_error_class=error_class,
        planned_agent_ids=planned_agent_ids,
        covered_node_count=len(planned_agent_ids),
        nodes=nodes,
        messages=messages,
        node_outputs=[],
        candidate_summary=candidate_summary,
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    )


def _graph_execution_summary(
    *,
    adapter: str,
    planned_agent_ids: list[str],
    covered_node_count: int,
    nodes: list[GraphNodeSummary],
    messages: list[dict[str, Any]],
    node_outputs: list[GraphNodeOutput],
    candidate_summary: dict[str, Any] | None,
    adapter_error_class: str | None = None,
    external_planner_execution_summary: dict[str, Any] | None = None,
    external_search_execution_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_packet = materialize_graph_evidence_packet(
        messages=messages,
        node_outputs=node_outputs,
        candidate_summary=candidate_summary,
        external_planner_execution_summary=external_planner_execution_summary,
        external_search_execution_summary=external_search_execution_summary,
    )
    summary = {
        "adapter": adapter,
    }
    if adapter_error_class is not None:
        summary["adapter_error_class"] = adapter_error_class
    summary.update(
        {
            "planned_node_count": len(planned_agent_ids),
            "covered_node_count": covered_node_count,
            "failed_node_count": _failed_node_count(nodes),
            "verifier_failure_policy": graph_verifier_failure_policy(
                node_outputs,
                requires_verifier=_requires_verifier(candidate_summary),
            ),
            "evidence_packet_summary": summarize_graph_evidence_packet(evidence_packet),
            "nodes": nodes,
        }
    )
    return summary


def _planned_agent_ids(planned_steps: list[dict[str, Any]]) -> list[str]:
    return [
        step["agent_id"] for step in planned_steps if isinstance(step.get("agent_id"), str)
    ]


def _node_summary(output: GraphNodeOutput) -> GraphNodeSummary:
    return {
        "agent_id": output.agent_id,
        "status": output.status,
        "has_text": bool(output.text),
        "tool_result_count": len(output.tool_results),
        "error": trim_graph_text(output.error or "", limit=240) or None,
    }


def _writer_node_summary(writer_status: str) -> GraphNodeSummary:
    return {
        "agent_id": "writer.template",
        "status": writer_status,
        "has_text": writer_status == "completed",
        "tool_result_count": 0,
        "error": None,
    }


def _adapter_error_node_summary(agent_id: str, error_class: str) -> GraphNodeSummary:
    return {
        "agent_id": agent_id,
        "status": "failed",
        "has_text": False,
        "tool_result_count": 0,
        "error": error_class,
    }


def _failed_node_count(nodes: list[GraphNodeSummary]) -> int:
    return sum(1 for node in nodes if node["status"] == "failed")


def _requires_verifier(candidate_summary: dict[str, Any] | None) -> bool:
    return bool(
        isinstance(candidate_summary, dict)
        and candidate_summary.get("requires_verifier") is True
    )


__all__ = [
    "graph_execution_adapter_error_summary",
    "graph_node_execution_summary",
]
