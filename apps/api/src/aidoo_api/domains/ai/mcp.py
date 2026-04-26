from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import (
    AiCapabilityDescriptor,
    AiCapabilityRegistry,
    WorkspaceContext,
    build_workspace_context,
    get_ai_capability_registry,
    resolve_workspace_entitlement_view,
)
from aidoo_api.domains.ai.tool_service import (
    ToolRequiresApproval,
    approval_required_http_exception,
    execute_tool,
)
from aidoo_api.domains.auth.models import User, Workspace


@dataclass(frozen=True)
class FilteredCapabilityTool:
    descriptor: AiCapabilityDescriptor
    mcp_tool: Mapping[str, Any]
    openai_tool: Mapping[str, Any]


class InProcTransport:
    def call_tool(
        self,
        db: Session,
        *,
        workspace: Workspace,
        principal: CallerPrincipal,
        user: User,
        tool_name: str,
        arguments: Mapping[str, Any],
        source: str,
        call_id: str | None = None,
        agent_run_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            return execute_tool(
                db,
                workspace=workspace,
                principal=principal,
                user=user,
                tool_name=tool_name,
                arguments=arguments,
                source=source,
                call_id=call_id,
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
        except ToolRequiresApproval as error:
            raise approval_required_http_exception(error) from error


class AiMcpClient:
    def __init__(
        self,
        *,
        registry: AiCapabilityRegistry | None = None,
        transport: InProcTransport | None = None,
    ) -> None:
        self._registry = registry or get_ai_capability_registry()
        self._transport = transport or InProcTransport()

    def list_tools(
        self,
        db: Session,
        *,
        workspace: Workspace,
        principal: CallerPrincipal,
        app_id: str | None = None,
        app_ids: Iterable[str] | None = None,
        include_meta: bool = False,
        include_approval_required: bool = True,
    ) -> list[FilteredCapabilityTool]:
        # ``app_id`` (single) and ``app_ids`` (multi-select) compose: when both
        # are given the descriptor must match the single id AND be part of the
        # multi-select set. The multi-select is the user-driven scope picker
        # narrowing — it can never expand the surface, only intersect with the
        # workspace-entitlement check that runs below.
        scope_set: frozenset[str] | None = (
            frozenset(app_ids) if app_ids is not None else None
        )
        workspace_context = build_workspace_context(workspace)
        entitlements = resolve_workspace_entitlement_view(db, workspace=workspace)
        filtered: list[FilteredCapabilityTool] = []
        for tool_name, descriptor in sorted(self._registry.descriptors.items()):
            if descriptor.kind != "tool":
                continue
            if app_id is not None and not _descriptor_matches_app(descriptor, app_id=app_id):
                continue
            if scope_set is not None and descriptor.workspace_app_id not in scope_set:
                continue
            if not include_approval_required and descriptor.approval_policy == "required":
                continue
            predicate = self._registry.resolve_discoverability_predicate(
                descriptor.discoverability_predicate_id
            )
            if predicate is None:
                continue
            if not predicate(principal, workspace_context, entitlements):
                continue
            compiled = self._registry.get_compiled_schemas(tool_name)
            if compiled is None:
                continue
            filtered.append(
                FilteredCapabilityTool(
                    descriptor=descriptor,
                    mcp_tool=compiled.mcp_tool_definition(
                        descriptor=descriptor,
                        include_meta=include_meta,
                    ),
                    openai_tool=compiled.openai_function_spec(
                        descriptor=descriptor,
                    ),
                )
            )
        return filtered

    def list_openai_function_specs(
        self,
        db: Session,
        *,
        workspace: Workspace,
        principal: CallerPrincipal,
        include_approval_required: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            dict(item.openai_tool)
            for item in self.list_tools(
                db,
                workspace=workspace,
                principal=principal,
                include_meta=False,
                include_approval_required=include_approval_required,
            )
        ]

    def build_manifest(
        self,
        db: Session,
        *,
        workspace: Workspace,
        principal: CallerPrincipal,
        app_id: str | None = None,
        include_meta: bool = True,
        include_approval_required: bool = False,
    ) -> dict[str, Any]:
        workspace_context = build_workspace_context(workspace)
        tools = self.list_tools(
            db,
            workspace=workspace,
            principal=principal,
            app_id=app_id,
            include_meta=include_meta,
            include_approval_required=include_approval_required,
        )
        return {
            "server": {
                "name": "doowon-ai-capabilities",
                "transport": "inproc",
                "capabilities": {"tools": {"listChanged": False}},
            },
            "workspace": {
                "id": workspace_context.workspace_id,
                "slug": workspace_context.workspace_slug,
                "display_name": workspace_context.display_name,
            },
            "app_id": app_id,
            "tools": [dict(item.mcp_tool) for item in tools],
        }

    def build_openapi_export(
        self,
        db: Session,
        *,
        workspace: Workspace,
        principal: CallerPrincipal,
        app_id: str | None = None,
        include_approval_required: bool = False,
    ) -> dict[str, Any]:
        workspace_context = build_workspace_context(workspace)
        tools = self.list_tools(
            db,
            workspace=workspace,
            principal=principal,
            app_id=app_id,
            include_meta=False,
            include_approval_required=include_approval_required,
        )
        paths: dict[str, Any] = {}
        for item in tools:
            operation = _tool_to_openapi_operation(item, workspace_context=workspace_context)
            paths[f"/mcp/tools/{item.descriptor.name}"] = {"post": operation}
        return {
            "openapi": "3.1.1",
            "info": {
                "title": (
                    f"Doowon AI Capability Export ({app_id})"
                    if app_id is not None
                    else "Doowon AI Capability Export"
                ),
                "version": "0.1.0",
            },
            "servers": [
                {
                    "url": f"/api/v1/workspaces/{workspace_context.workspace_slug}/ai",
                }
            ],
            "paths": paths,
        }

    def call_tool(
        self,
        db: Session,
        *,
        workspace: Workspace,
        principal: CallerPrincipal,
        user: User,
        tool_name: str,
        arguments: Mapping[str, Any],
        source: str,
        call_id: str | None = None,
        agent_run_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        return self._transport.call_tool(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            tool_name=tool_name,
            arguments=arguments,
            source=source,
            call_id=call_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )


def _descriptor_matches_app(descriptor: AiCapabilityDescriptor, *, app_id: str) -> bool:
    return descriptor.workspace_app_id == app_id


def _tool_to_openapi_operation(
    item: FilteredCapabilityTool,
    *,
    workspace_context: WorkspaceContext,
) -> dict[str, Any]:
    return {
        "operationId": item.descriptor.name,
        "summary": item.descriptor.name,
        "description": item.descriptor.description,
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": dict(item.mcp_tool["inputSchema"]),
                }
            },
        },
        "responses": {
            "200": {
                "description": "Successful tool call.",
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "tool": {"type": "string"},
                                "owner_domain": {"type": "string"},
                                "approval_required": {"type": "boolean"},
                                "result": {},
                            },
                            "required": [
                                "tool",
                                "owner_domain",
                                "approval_required",
                                "result",
                            ],
                        }
                    }
                },
            }
        },
        "x-doowon-workspace": workspace_context.workspace_slug,
        "x-doowon-capability-kind": item.descriptor.kind,
        "x-doowon-capability-mode": item.descriptor.mode,
    }
