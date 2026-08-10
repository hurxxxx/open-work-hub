from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from open_work_hub_api.domains.ai.runtime.contracts import RUNTIME_PROFILE_VALUES, RuntimeProfile
from open_work_hub_api.domains.ai.runtime.routing_metadata import (
    runtime_shadow_meta_from_mapping,
)


@dataclass(frozen=True)
class RuntimeShadowContext:
    agent_run_id: str
    workspace_id: str
    conversation_id: str
    requested_by_user_id: str
    runtime_metadata: dict[str, Any]
    finish_reason: str | None
    response_status: str
    status: str

    @property
    def terminal_event(self) -> str:
        return terminal_trace_event_prefix(self.status)


def build_runtime_shadow_context(
    *,
    agent_run_id: str,
    workspace_id: str,
    conversation_id: str,
    requested_by_user_id: str,
    runtime_metadata: dict[str, Any],
    finish_reason: str | None,
    response_status: str,
) -> RuntimeShadowContext:
    return RuntimeShadowContext(
        agent_run_id=agent_run_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        requested_by_user_id=requested_by_user_id,
        runtime_metadata=runtime_metadata,
        finish_reason=finish_reason,
        response_status=response_status,
        status=terminal_runtime_status(
            finish_reason=finish_reason,
            response_status=response_status,
        ),
    )


def terminal_runtime_status(*, finish_reason: str | None, response_status: str) -> str:
    if response_status == "cancelled" or finish_reason == "cancelled":
        return "cancelled"
    if response_status == "error" or finish_reason == "error":
        return "failed"
    return "completed"


def terminal_trace_event_prefix(status: str) -> str:
    if status == "failed":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    return "completed"


def runtime_profile_from_metadata(runtime_metadata: dict[str, Any]) -> RuntimeProfile:
    runtime_profile = runtime_metadata.get("runtime_profile")
    if runtime_profile in RUNTIME_PROFILE_VALUES:
        return cast(RuntimeProfile, runtime_profile)
    return "interactive_read"


def runtime_shadow_metadata_json(
    *,
    source: str,
    runtime_metadata: dict[str, Any],
) -> dict[str, Any]:
    metadata = {
        "source": source,
    }
    metadata.update(runtime_shadow_meta_from_mapping(runtime_metadata))
    return metadata


def graph_node_status_by_agent_id(runtime_metadata: dict[str, Any]) -> dict[str, str]:
    summary = runtime_metadata.get("graph_node_execution_summary")
    if not isinstance(summary, dict):
        return {}
    nodes = summary.get("nodes")
    if not isinstance(nodes, list):
        return {}
    statuses: dict[str, str] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        agent_id = node.get("agent_id")
        raw_status = node.get("status")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        if raw_status in {"completed", "failed", "cancelled"}:
            statuses[agent_id] = raw_status
    return statuses


__all__ = [
    "RuntimeShadowContext",
    "build_runtime_shadow_context",
    "graph_node_status_by_agent_id",
    "runtime_profile_from_metadata",
    "runtime_shadow_metadata_json",
    "terminal_runtime_status",
    "terminal_trace_event_prefix",
]
