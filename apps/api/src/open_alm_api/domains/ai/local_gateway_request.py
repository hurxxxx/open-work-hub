from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from open_alm_api.domains.ai.internal_agent_contracts import LocalAgentTask
from open_alm_api.domains.ai.local_gateway_tool_catalog import (
    DEFAULT_TOOLS_BY_AGENT,
    QUERY_STOPWORDS,
    READ_GATEWAY_TOOL_BUILDERS,
    GatewayArgumentBuilder,
    default_gateway_tools_for_agent,
    docs_list_hub_args,
    meeting_list_args,
    normalize_query_token,
    planner_list_args,
    pms_search_tasks_args,
    rag_query_args,
    read_gateway_tool_builders,
    retrieval_search_args,
    search_query_from_objective,
)
from open_alm_api.domains.ai.registry import GatewayToolAdapter, get_ai_capability_registry


@dataclass(frozen=True, slots=True)
class GatewayToolRequest:
    tool_name: str
    arguments: Mapping[str, Any]


def build_gateway_tool_request(
    *,
    task: LocalAgentTask,
    available_tool_names: frozenset[str],
    approval_required_tool_names: frozenset[str] = frozenset(),
) -> GatewayToolRequest | None:
    tool_name = select_gateway_tool(
        task=task,
        available_tool_names=available_tool_names,
        approval_required_tool_names=approval_required_tool_names,
    )
    if tool_name is None:
        return None
    return GatewayToolRequest(
        tool_name=tool_name,
        arguments=MappingProxyType(
            gateway_tool_arguments(
                tool_name=tool_name,
                task=task,
                approval_required_tool_names=approval_required_tool_names,
            )
        ),
    )


def select_gateway_tool(
    *,
    task: LocalAgentTask,
    available_tool_names: frozenset[str],
    approval_required_tool_names: frozenset[str] = frozenset(),
) -> str | None:
    registry = get_ai_capability_registry()
    registered_adapters = {
        adapter.tool_name: adapter
        for adapter in registry.gateway_adapters_for_agent(task.agent_id)
    }
    approved_exact_tool_names = _approved_exact_tool_names(
        task=task,
        approval_required_tool_names=approval_required_tool_names,
    )
    read_builders = read_gateway_tool_builders()
    gateway_tool_names = (
        frozenset(read_builders)
        | frozenset(registered_adapters)
        | approved_exact_tool_names
    )
    requested = [
        name
        for name in task.allowed_tool_names
        if name in available_tool_names and name in gateway_tool_names
    ]
    if task.tool_arguments and requested:
        return requested[0]
    for name in requested:
        return name

    preferred = (
        *default_gateway_tools_for_agent(task.agent_id),
        *(
            adapter.tool_name
            for adapter in registry.gateway_adapters_for_agent(task.agent_id)
        ),
    )
    for name in preferred:
        if name in available_tool_names:
            return name
    return None


def gateway_tool_arguments(
    *,
    tool_name: str,
    task: LocalAgentTask,
    approval_required_tool_names: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if tool_name in _approved_exact_tool_names(
        task=task,
        approval_required_tool_names=approval_required_tool_names,
    ):
        return dict(task.tool_arguments)
    adapter = _registered_gateway_adapter(tool_name=tool_name, task=task)
    if adapter is not None:
        return {
            **dict(adapter.build_arguments(task)),
            **_gateway_passthrough_arguments(adapter=adapter, task=task),
        }
    builder = read_gateway_tool_builders().get(tool_name)
    if builder is not None:
        return builder(task)
    raise ValueError(f"unsupported local gateway tool: {tool_name}")


def _approved_exact_tool_names(
    *,
    task: LocalAgentTask,
    approval_required_tool_names: frozenset[str],
) -> frozenset[str]:
    if not task.approved_call_id or not task.tool_arguments:
        return frozenset()
    return frozenset(task.allowed_tool_names) & approval_required_tool_names


def _registered_gateway_adapter(
    *,
    tool_name: str,
    task: LocalAgentTask,
) -> GatewayToolAdapter | None:
    return get_ai_capability_registry().get_gateway_tool_adapter(
        agent_id=task.agent_id,
        tool_name=tool_name,
    )


def _gateway_passthrough_arguments(
    *,
    adapter: GatewayToolAdapter,
    task: LocalAgentTask,
) -> dict[str, Any]:
    return {
        key: value
        for key, value in task.tool_arguments.items()
        if key in adapter.passthrough_keys
    }


__all__ = [
    "DEFAULT_TOOLS_BY_AGENT",
    "GatewayArgumentBuilder",
    "GatewayToolRequest",
    "QUERY_STOPWORDS",
    "READ_GATEWAY_TOOL_BUILDERS",
    "build_gateway_tool_request",
    "default_gateway_tools_for_agent",
    "docs_list_hub_args",
    "gateway_tool_arguments",
    "meeting_list_args",
    "normalize_query_token",
    "planner_list_args",
    "pms_search_tasks_args",
    "rag_query_args",
    "read_gateway_tool_builders",
    "retrieval_search_args",
    "search_query_from_objective",
    "select_gateway_tool",
]
