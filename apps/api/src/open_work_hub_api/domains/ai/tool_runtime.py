from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.ai.tool_call_event_projection import iter_tool_call_events
from open_work_hub_api.domains.ai.tool_error_projection import tool_http_exception_message
from open_work_hub_api.domains.ai.tool_result_projection import (
    is_rejected_tool_response,
    rejected_tool_reason_from_response,
    serialize_rejected_tool_result_for_llm,
    serialize_tool_result_for_llm,
)
from open_work_hub_api.domains.ai.tool_service import ToolRequiresApproval, execute_tool
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id

ToolCallStatus = Literal["ok", "error", "blocked", "rejected"]


@dataclass(frozen=True)
class ToolCallExecution:
    call_id: str
    tool_name: str
    arguments_json: str
    status: ToolCallStatus
    response: dict[str, Any] | None = None
    error_message: str | None = None
    approval_id: str | None = None
    approval_expires_at_ms: int | None = None
    resource_preview: str | None = None

    @property
    def llm_result_content(self) -> str:
        if self.status == "ok" and self.response is not None:
            return serialize_tool_result_for_llm(
                tool_name=self.tool_name,
                result=self.response["result"],
            )
        if self.status == "rejected":
            return serialize_rejected_tool_result_for_llm(
                tool_name=self.tool_name,
                reason=rejected_tool_reason_from_response(self.response),
            )
        return serialize_tool_result_for_llm(
            tool_name=self.tool_name,
            error=self.error_message or "Tool execution failed.",
        )


def execute_tool_call(
    db: Session,
    *,
    principal: CallerPrincipal,
    user: User,
    tool_name: str,
    arguments: Mapping[str, Any],
    source: str,
    call_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    approved_call_id: str | None = None,
) -> ToolCallExecution:
    resolved_call_id = call_id or new_id()
    arguments_json = json.dumps(dict(arguments), ensure_ascii=False, sort_keys=True)
    try:
        response = execute_tool(
            db,
            principal=principal,
            user=user,
            tool_name=tool_name,
            arguments=arguments,
            source=source,
            call_id=resolved_call_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            approved_call_id=approved_call_id,
        )
    except ToolRequiresApproval as approval_required:
        return ToolCallExecution(
            call_id=resolved_call_id,
            tool_name=tool_name,
            arguments_json=approval_required.arguments_json,
            status="blocked",
            error_message=str(approval_required),
            approval_expires_at_ms=int(time.time() * 1000) + 86_400_000,
            resource_preview=approval_required.resource_preview,
        )
    except HTTPException as error:
        # Approval-required is raised as ToolRequiresApproval and caught
        # above. Any other HTTPException — including 409s like "approval
        # already resolved" or "summary not ready" — is a tool-level error
        # and must not be coerced into the approval-blocked path.
        return ToolCallExecution(
            call_id=resolved_call_id,
            tool_name=tool_name,
            arguments_json=arguments_json,
            status="error",
            error_message=tool_http_exception_message(error),
        )

    return ToolCallExecution(
        call_id=resolved_call_id,
        tool_name=tool_name,
        arguments_json=arguments_json,
        status="rejected" if is_rejected_tool_response(response) else "ok",
        response=response,
    )


__all__ = [
    "ToolCallExecution",
    "ToolCallStatus",
    "execute_tool_call",
    "iter_tool_call_events",
]
