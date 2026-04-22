from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.events import AgentEventEnvelope, EnvelopeEncoder, make_envelope
from aidoo_api.domains.ai.tool_service import (
    ToolRequiresApproval,
    execute_tool,
    preview_text,
    serialize_rejected_tool_result_for_llm,
    serialize_tool_result_for_llm,
    tool_result_preview,
)
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id


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
            reason = None
            if self.response is not None:
                result = self.response.get("result")
                if isinstance(result, Mapping):
                    raw_reason = result.get("reason")
                    if isinstance(raw_reason, str):
                        reason = raw_reason
            return serialize_rejected_tool_result_for_llm(
                tool_name=self.tool_name,
                reason=reason,
            )
        return serialize_tool_result_for_llm(
            tool_name=self.tool_name,
            error=self.error_message or "Tool execution failed.",
        )


def execute_tool_call(
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
    approved_call_id: str | None = None,
) -> ToolCallExecution:
    resolved_call_id = call_id or new_id()
    arguments_json = json.dumps(dict(arguments), ensure_ascii=False, sort_keys=True)
    try:
        response = execute_tool(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
            tool_name=tool_name,
            arguments=arguments,
            source=source,
            call_id=resolved_call_id,
            agent_run_id=agent_run_id,
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
        message = _error_message(error)
        if (
            error.status_code == status.HTTP_409_CONFLICT
            and approved_call_id is None
            and _is_approval_required_conflict(error)
        ):
            return ToolCallExecution(
                call_id=resolved_call_id,
                tool_name=tool_name,
                arguments_json=arguments_json,
                status="blocked",
                error_message=message,
                approval_id=new_id(),
                approval_expires_at_ms=int(time.time() * 1000) + 86_400_000,
            )
        return ToolCallExecution(
            call_id=resolved_call_id,
            tool_name=tool_name,
            arguments_json=arguments_json,
            status="error",
            error_message=message,
        )

    return ToolCallExecution(
        call_id=resolved_call_id,
        tool_name=tool_name,
        arguments_json=arguments_json,
        status=(
            "rejected"
            if isinstance(response.get("result"), Mapping)
            and response["result"].get("status") == "rejected"
            else "ok"
        ),
        response=response,
    )


def _is_approval_required_conflict(error: HTTPException) -> bool:
    detail = error.detail
    if not isinstance(detail, str):
        return False
    return detail.startswith("AI tool requires approval before execution:")


def iter_tool_call_events(
    *,
    encoder: EnvelopeEncoder,
    execution: ToolCallExecution,
    include_call_frames: bool = True,
) -> Iterator[AgentEventEnvelope]:
    if include_call_frames:
        yield make_envelope(
            "tool_call_started",
            encoder.next_seq(),
            {
                "call_id": execution.call_id,
                "name": execution.tool_name,
                "args_preview": preview_text(execution.arguments_json, limit=240),
            },
        )
        yield make_envelope(
            "tool_call_args_delta",
            encoder.next_seq(),
            {
                "call_id": execution.call_id,
                "delta": execution.arguments_json,
            },
        )
    if execution.status == "blocked":
        yield make_envelope(
            "approval_required",
            encoder.next_seq(),
            {
                "approval_id": execution.approval_id or new_id(),
                "call_id": execution.call_id,
                "tool": execution.tool_name,
                "resource_preview": execution.resource_preview
                or preview_text(execution.arguments_json, limit=240),
                # Non-agent callers may surface a blocked tool call without a
                # persisted approval row. In that case we only have a
                # placeholder TTL; the agent halt path overrides this with the
                # real approval.expires_at from the database.
                "expires_at_ms": execution.approval_expires_at_ms or int(time.time() * 1000) + 86_400_000,
            },
        )
        return

    if execution.status == "error":
        yield make_envelope(
            "tool_result",
            encoder.next_seq(),
            {
                "call_id": execution.call_id,
                "status": "error",
                "error": execution.error_message or "AI tool execution failed.",
            },
        )
        return

    if execution.status == "rejected":
        rejection_reason = None
        if execution.response is not None:
            result = execution.response.get("result")
            if isinstance(result, Mapping):
                raw_reason = result.get("reason")
                if isinstance(raw_reason, str):
                    rejection_reason = raw_reason
        yield make_envelope(
            "tool_result",
            encoder.next_seq(),
            {
                "call_id": execution.call_id,
                "status": "rejected",
                "error": rejection_reason or "Approval request was rejected.",
                "result_preview": (
                    tool_result_preview(execution.response["result"])
                    if execution.response is not None
                    else None
                ),
            },
        )
        return

    assert execution.response is not None
    yield make_envelope(
        "tool_result",
        encoder.next_seq(),
        {
            "call_id": execution.call_id,
            "status": "ok",
            "result_preview": tool_result_preview(execution.response["result"]),
        },
    )


def _error_message(error: HTTPException) -> str:
    detail = error.detail
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return "AI tool execution failed."
