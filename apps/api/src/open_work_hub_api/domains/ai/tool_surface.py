from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import (
    AiCapabilityDescriptor,
    AiCapabilityRegistry,
    build_workspace_context,
    get_ai_capability_registry,
    resolve_workspace_entitlement_view,
)
from open_work_hub_api.domains.ai.tool_surface_projection import (
    build_tool_manifest,
    build_tool_openapi_export,
)
from open_work_hub_api.domains.ai.tool_contracts import AgentToolSpec, agent_tool_names
from open_work_hub_api.domains.auth.models import Workspace


@dataclass(frozen=True)
class FilteredCapabilityTool:
    descriptor: AiCapabilityDescriptor
    mcp_tool: Mapping[str, Any]
    tool_spec: AgentToolSpec


@dataclass(frozen=True)
class AgentToolSurface:
    tool_specs: list[AgentToolSpec]
    capability_tools: list[FilteredCapabilityTool]
    tool_names: list[str]
    approval_required_tool_names: list[str]
    has_approval_required_tools: bool


def descriptor_owner_app_enabled(
    descriptor: AiCapabilityDescriptor,
    *,
    enabled_app_ids: frozenset[str],
) -> bool:
    """Require the descriptor owner before domain-specific narrowing rules."""

    return descriptor.workspace_app_id in enabled_app_ids


def resolve_filtered_capability_tools(
    db: Session,
    *,
    registry: AiCapabilityRegistry,
    workspace: Workspace,
    principal: CallerPrincipal,
    app_id: str | None = None,
    app_ids: Iterable[str] | None = None,
    include_meta: bool = False,
    include_approval_required: bool = True,
) -> list[FilteredCapabilityTool]:
    # ``app_id`` (single) and ``app_ids`` (multi-select) compose: when both are
    # given the descriptor must match the single id AND be part of the
    # multi-select set. The multi-select is user-driven scope narrowing; it can
    # never expand the workspace entitlement and discoverability checks below.
    scope_set: frozenset[str] | None = (
        frozenset(app_ids) if app_ids is not None else None
    )
    workspace_context = build_workspace_context(workspace)
    entitlements = resolve_workspace_entitlement_view(db, workspace=workspace)
    filtered: list[FilteredCapabilityTool] = []
    for tool_name, descriptor in sorted(registry.descriptors.items()):
        if descriptor.kind != "tool":
            continue
        if app_id is not None and not descriptor_matches_app(descriptor, app_id=app_id):
            continue
        if scope_set is not None and descriptor.workspace_app_id not in scope_set:
            continue
        if not include_approval_required and descriptor.approval_policy == "required":
            continue
        if not descriptor_owner_app_enabled(
            descriptor,
            enabled_app_ids=entitlements.effective_enabled_app_ids,
        ):
            continue
        predicate = registry.resolve_discoverability_predicate(
            descriptor.discoverability_predicate_id
        )
        if predicate is None:
            continue
        if not predicate(principal, workspace_context, entitlements):
            continue
        compiled = registry.get_compiled_schemas(tool_name)
        if compiled is None:
            continue
        filtered.append(
            FilteredCapabilityTool(
                descriptor=descriptor,
                mcp_tool=compiled.mcp_tool_definition(
                    descriptor=descriptor,
                    include_meta=include_meta,
                ),
                tool_spec=AgentToolSpec(
                    name=descriptor.name,
                    description=descriptor.description,
                    input_schema=compiled.strict_input_schema,
                ),
            )
        )
    return filtered


def descriptor_matches_app(descriptor: AiCapabilityDescriptor, *, app_id: str) -> bool:
    return descriptor.workspace_app_id == app_id


def workspace_app_id_for_tool(
    tool_name: str,
    *,
    registry: AiCapabilityRegistry | None = None,
) -> str | None:
    resolved_registry = registry or get_ai_capability_registry()
    descriptor = resolved_registry.descriptors.get(tool_name)
    if descriptor is None:
        return None
    return descriptor.workspace_app_id


def resolve_agent_tool_surface(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    messages: list[dict[str, Any]] | None = None,
    allowed_app_ids: list[str] | None = None,
    registry: AiCapabilityRegistry | None = None,
) -> AgentToolSurface:
    settings = get_settings()
    resolved_registry = registry or get_ai_capability_registry()
    _ = messages

    # ``allowed_app_ids`` is a user-driven owner-app scope. An empty list means
    # text-only; ``None`` exposes every entitled and discoverable owner app.
    if allowed_app_ids is not None and not allowed_app_ids:
        return AgentToolSurface(
            tool_specs=[],
            capability_tools=[],
            tool_names=[],
            approval_required_tool_names=[],
            has_approval_required_tools=False,
        )

    scope_filter = list(allowed_app_ids) if allowed_app_ids else None
    filtered_tools = resolve_filtered_capability_tools(
        db,
        registry=resolved_registry,
        workspace=workspace,
        principal=principal,
        app_ids=scope_filter,
        include_meta=False,
        include_approval_required=settings.ai_write_tools_enabled,
    )
    tool_names = sorted(item.descriptor.name for item in filtered_tools)
    approval_required_tool_names = sorted(
        item.descriptor.name
        for item in filtered_tools
        if item.descriptor.approval_policy == "required"
    )
    return AgentToolSurface(
        tool_specs=[item.tool_spec for item in filtered_tools],
        capability_tools=filtered_tools if settings.ai_mcp_bridge_enabled else [],
        tool_names=tool_names,
        approval_required_tool_names=approval_required_tool_names,
        has_approval_required_tools=bool(approval_required_tool_names),
    )


def tool_names_from_specs(tool_specs: Sequence[AgentToolSpec]) -> list[str]:
    return sorted(set(agent_tool_names(tool_specs)))


def approval_required_tool_names_from_specs(
    tool_specs: Sequence[AgentToolSpec],
    *,
    registry: AiCapabilityRegistry | None = None,
) -> list[str]:
    return approval_required_tool_names_from_tool_names(
        tool_names_from_specs(tool_specs),
        registry=registry,
    )


def approval_required_tool_names_from_tool_names(
    tool_names: Iterable[str],
    *,
    registry: AiCapabilityRegistry | None = None,
) -> list[str]:
    resolved_registry = registry or get_ai_capability_registry()
    approval_required: list[str] = []
    for name in sorted(set(str(tool_name).strip() for tool_name in tool_names)):
        if not name:
            continue
        definition = resolved_registry.tools.get(name)
        descriptor = resolved_registry.descriptors.get(name)
        if definition is not None and definition.approval_required:
            approval_required.append(name)
            continue
        if descriptor is not None and descriptor.approval_policy == "required":
            approval_required.append(name)
    return approval_required


__all__ = [
    "AgentToolSurface",
    "FilteredCapabilityTool",
    "approval_required_tool_names_from_specs",
    "approval_required_tool_names_from_tool_names",
    "build_tool_manifest",
    "build_tool_openapi_export",
    "descriptor_matches_app",
    "resolve_agent_tool_surface",
    "resolve_filtered_capability_tools",
    "tool_names_from_specs",
    "workspace_app_id_for_tool",
]
