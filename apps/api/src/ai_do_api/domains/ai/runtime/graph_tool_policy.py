from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai_do_api.domains.ai.registry import get_ai_capability_registry
from ai_do_api.domains.ai.runtime.agent_catalog import (
    AgentDefinition,
    get_agent_definition_registry,
)
from ai_do_api.domains.ai.tool_contracts import AgentToolSpec


def read_only_tool_specs(
    tool_specs: Sequence[AgentToolSpec],
    *,
    registry: Any | None = None,
) -> list[AgentToolSpec]:
    capability_registry = registry or get_ai_capability_registry()
    read_only_specs: list[AgentToolSpec] = []
    for spec in tool_specs:
        tool_name = spec.name
        descriptor = capability_registry.descriptors.get(tool_name)
        if descriptor is None or descriptor.mode == "read":
            read_only_specs.append(spec)
    return read_only_specs


def graph_node_tool_specs(
    agent_id: str,
    tool_specs: Sequence[AgentToolSpec],
    *,
    tools_enabled: bool,
    registry: Any | None = None,
) -> list[AgentToolSpec]:
    if not tools_enabled:
        return []
    capability_registry = registry or get_ai_capability_registry()
    allowed_app_id = workspace_app_id_for_graph_agent(agent_id)
    allowed_tool_names = tool_names_for_graph_agent(agent_id)
    selected: list[AgentToolSpec] = []
    for spec in tool_specs:
        tool_name = spec.name
        descriptor = capability_registry.descriptors.get(tool_name)
        if descriptor is not None and descriptor.mode != "read":
            continue
        if allowed_tool_names and tool_name not in allowed_tool_names:
            continue
        if allowed_app_id is not None:
            if descriptor is None or descriptor.workspace_app_id != allowed_app_id:
                continue
        selected.append(spec)
    return selected


def workspace_app_id_for_graph_agent(agent_id: str) -> str | None:
    definition = _agent_definition(agent_id)
    if definition is None or len(definition.workspace_app_ids) != 1:
        return None
    return next(iter(definition.workspace_app_ids))


def tool_names_for_graph_agent(agent_id: str) -> set[str]:
    definition = _agent_definition(agent_id)
    if definition is None:
        return set()
    return set(definition.graph_tool_names)


def _agent_definition(agent_id: str) -> AgentDefinition | None:
    return get_agent_definition_registry().by_id(agent_id)


__all__ = [
    "graph_node_tool_specs",
    "read_only_tool_specs",
    "tool_names_for_graph_agent",
    "workspace_app_id_for_graph_agent",
]
