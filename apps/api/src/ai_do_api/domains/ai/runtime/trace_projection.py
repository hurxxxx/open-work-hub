from __future__ import annotations

from typing import Any

from ai_do_api.domains.ai.runtime.routing_metadata import (
    runtime_graph_candidate_validation_trace_fields,
    runtime_graph_execution_trace_fields,
    runtime_present_external_trace_summaries,
)

_ADAPTER_NOT_PROVIDED = object()


def graph_candidate_trace_payloads(
    runtime_metadata: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    graph_gate = runtime_metadata.get("graph_gate")
    if graph_gate != "eligible":
        return []

    payloads: list[tuple[str, dict[str, Any]]] = []
    candidate_summary = runtime_metadata.get("graph_candidate_summary")
    if isinstance(candidate_summary, dict):
        generated_payload = {
            "runtime_profile": runtime_metadata.get("runtime_profile"),
            "graph_gate": graph_gate,
            "graph_candidate_summary": candidate_summary,
        }
        generated_payload.update(runtime_present_external_trace_summaries(runtime_metadata))
        payloads.append(("graph_candidate_generated", generated_payload))

    validated_payload = {
        **runtime_graph_candidate_validation_trace_fields(runtime_metadata),
        "graph_candidate_summary": candidate_summary
        if isinstance(candidate_summary, dict)
        else None,
    }
    validated_payload.update(runtime_present_external_trace_summaries(runtime_metadata))
    payloads.append(("graph_candidate_validated", validated_payload))
    return payloads


def single_loop_run_created_payload(
    *,
    runtime_profile: str,
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": "single_loop_fallback_shadow",
        "runtime_profile": runtime_profile,
        "graph_gate": runtime_metadata.get("graph_gate"),
        "graph_fallback_reason": runtime_metadata.get("graph_fallback_reason"),
    }


def graph_execution_run_created_payload(
    *,
    runtime_profile: str,
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": "graph_execution_shadow",
        "runtime_profile": runtime_profile,
        "graph_gate": runtime_metadata.get("graph_gate"),
        "graph_execution_adapter": runtime_metadata.get("graph_execution_adapter"),
    }


def invocation_started_payload(
    *,
    agent_id: str,
    adapter: str | None | object = _ADAPTER_NOT_PROVIDED,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"agent_id": agent_id}
    if adapter is not _ADAPTER_NOT_PROVIDED:
        payload["adapter"] = adapter
    return payload


def terminal_invocation_payload(
    *,
    agent_id: str,
    finish_reason: str | None,
    response_status: str,
    adapter: str | None | object = _ADAPTER_NOT_PROVIDED,
) -> dict[str, Any]:
    payload = invocation_started_payload(agent_id=agent_id, adapter=adapter)
    payload.update(
        {
            "finish_reason": finish_reason,
            "response_status": response_status,
        }
    )
    return payload


def terminal_run_payload(
    *,
    finish_reason: str | None,
    response_status: str,
) -> dict[str, Any]:
    return {
        "finish_reason": finish_reason,
        "response_status": response_status,
    }


def graph_node_planned_payload(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "invocation_seq": step.get("invocation_seq"),
        "agent_id": step.get("agent_id"),
        "state": step.get("state"),
        "depends_on_agent_ids": step.get("depends_on_agent_ids") or [],
    }


def graph_execution_gate_payload(runtime_metadata: dict[str, Any]) -> dict[str, Any]:
    return runtime_graph_execution_trace_fields(runtime_metadata)
