"""Projection from filtered AI capability tools to MCP/OpenAPI exports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from open_work_hub_api.domains.ai.registry import (
    AiCapabilityDescriptor,
)
from open_work_hub_api.version import VERSION as APP_VERSION


class ToolSurfaceProjectionItem(Protocol):
    descriptor: AiCapabilityDescriptor
    mcp_tool: Mapping[str, Any]


def build_tool_manifest(
    tools: Iterable[ToolSurfaceProjectionItem],
    *,
    app_id: str | None = None,
) -> dict[str, Any]:
    return {
        "server": {
            "name": "corporate-ai-capabilities",
            "transport": "inproc",
            "capabilities": {"tools": {"listChanged": False}},
        },
        "app_id": app_id,
        "tools": [dict(item.mcp_tool) for item in tools],
    }


def build_tool_openapi_export(
    tools: Iterable[ToolSurfaceProjectionItem],
    *,
    app_id: str | None = None,
) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for item in tools:
        operation = _tool_to_openapi_operation(
            item,
        )
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
                "url": "/api/v1/chatbot",
            }
        ],
        "paths": paths,
    }


def _tool_to_openapi_operation(
    item: ToolSurfaceProjectionItem,
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
        "x-corporate-capability-kind": item.descriptor.kind,
        "x-corporate-capability-mode": item.descriptor.mode,
    }


__all__ = [
    "ToolSurfaceProjectionItem",
    "build_tool_manifest",
    "build_tool_openapi_export",
]
