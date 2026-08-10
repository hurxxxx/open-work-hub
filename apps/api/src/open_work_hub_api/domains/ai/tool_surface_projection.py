"""Projection from filtered AI capability tools to MCP/OpenAPI exports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from open_work_hub_api.domains.ai.registry import (
    AiCapabilityDescriptor,
    WorkspaceContext,
    build_workspace_context,
)
from open_work_hub_api.domains.auth.models import Workspace
from open_work_hub_api.version import VERSION as APP_VERSION


class ToolSurfaceProjectionItem(Protocol):
    descriptor: AiCapabilityDescriptor
    mcp_tool: Mapping[str, Any]


def build_tool_manifest(
    tools: Iterable[ToolSurfaceProjectionItem],
    *,
    workspace: Workspace,
    app_id: str | None = None,
) -> dict[str, Any]:
    workspace_context = build_workspace_context(workspace)
    return {
        "server": {
            "name": "corporate-ai-capabilities",
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


def build_tool_openapi_export(
    tools: Iterable[ToolSurfaceProjectionItem],
    *,
    workspace: Workspace,
    app_id: str | None = None,
) -> dict[str, Any]:
    workspace_context = build_workspace_context(workspace)
    paths: dict[str, Any] = {}
    for item in tools:
        operation = _tool_to_openapi_operation(item, workspace_context=workspace_context)
        paths[f"/mcp/tools/{item.descriptor.name}"] = {"post": operation}
    return {
        "openapi": "3.1.1",
        "info": {
            "title": (
                f"Open Work Hub AI Capability Export ({app_id})"
                if app_id is not None
                else "Open Work Hub AI Capability Export"
            ),
            "version": APP_VERSION,
        },
        "servers": [
            {
                "url": f"/api/v1/workspaces/{workspace_context.workspace_slug}/chatbot",
            }
        ],
        "paths": paths,
    }


def _tool_to_openapi_operation(
    item: ToolSurfaceProjectionItem,
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
        "x-corporate-workspace": workspace_context.workspace_slug,
        "x-corporate-capability-kind": item.descriptor.kind,
        "x-corporate-capability-mode": item.descriptor.mode,
    }


__all__ = [
    "ToolSurfaceProjectionItem",
    "build_tool_manifest",
    "build_tool_openapi_export",
]
