from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.ai import approvals as ai_approvals
from open_work_hub_api.domains.ai.registry import AiCapabilityDescriptor
from open_work_hub_api.domains.ai.tool_approval_projection import (
    build_rejected_approval_payload,
    build_resource_preview,
    render_approval_preview,
)

if TYPE_CHECKING:
    from open_work_hub_api.domains.auth.models import Workspace


class ToolRequiresApproval(Exception):
    def __init__(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments_json: str,
        resource_preview: str | None,
    ) -> None:
        super().__init__(f"AI tool requires approval before execution: {tool_name}")
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.arguments_json = arguments_json
        self.resource_preview = resource_preview


def approval_required_http_exception(error: ToolRequiresApproval) -> HTTPException:
    return localized_http_exception(
        status_code=status.HTTP_409_CONFLICT,
        code="ai.tool_requires_approval",
        tool_name=error.tool_name,
    )


def build_tool_requires_approval(
    *,
    tool_call_id: str,
    tool_name: str,
    validated_arguments: Mapping[str, Any],
    descriptor: AiCapabilityDescriptor | None,
    workspace: Workspace,
    principal: CallerPrincipal,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ToolRequiresApproval:
    return ToolRequiresApproval(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments_json=json.dumps(
            jsonable_encoder(validated_arguments),
            ensure_ascii=False,
            sort_keys=True,
        ),
        resource_preview=build_resource_preview(
            descriptor=descriptor,
            workspace=workspace,
            principal=principal,
            parsed_args=parsed_args,
        ),
    )


def validate_replayed_approval(
    *,
    approval: ai_approvals.AiToolApproval,
    tool_name: str,
    call_id: str | None,
) -> None:
    if approval.tool_name != tool_name:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.approval_tool_mismatch",
        )
    if call_id is not None and approval.tool_call_id != call_id:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.approval_tool_call_mismatch",
        )


__all__ = [
    "ToolRequiresApproval",
    "approval_required_http_exception",
    "build_rejected_approval_payload",
    "build_resource_preview",
    "build_tool_requires_approval",
    "render_approval_preview",
    "validate_replayed_approval",
]
