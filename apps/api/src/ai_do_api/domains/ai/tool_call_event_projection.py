"""Projection from AI tool call executions to agent event envelopes."""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from typing import Any, Protocol

from ai_do_api.domains.ai.events import AgentEventEnvelope, EnvelopeEncoder, make_envelope
from ai_do_api.domains.ai.tool_stream_projection import (
    make_tool_call_frame_events,
    make_tool_result_frame_event,
    preview_tool_event_text,
)
from ai_do_api.domains.ai.tool_result_projection import (
    project_rejected_tool_response,
    tool_result_preview,
)
from ai_do_api.domains.auth.security import new_id


class ToolCallEventExecution(Protocol):
    call_id: str
    tool_name: str
    arguments_json: str
    status: str
    response: Mapping[str, Any] | None
    error_message: str | None
    approval_id: str | None
    approval_expires_at_ms: int | None
    resource_preview: str | None


def iter_tool_call_events(
    *,
    encoder: EnvelopeEncoder,
    execution: ToolCallEventExecution,
    include_call_frames: bool = True,
) -> Iterator[AgentEventEnvelope]:
    if include_call_frames:
        yield from make_tool_call_frame_events(
            encoder=encoder,
            call_id=execution.call_id,
            tool_name=execution.tool_name,
            arguments=execution.arguments_json,
            emit_arguments_delta=True,
            preview_suffix="…",
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
                or preview_tool_event_text(
                    execution.arguments_json,
                    limit=240,
                    suffix="…",
                ),
                # Non-agent callers may surface a blocked tool call without a
                # persisted approval row. In that case only a placeholder TTL
                # exists; the agent halt path overrides it with the database
                # approval.expires_at value.
                "expires_at_ms": execution.approval_expires_at_ms
                or int(time.time() * 1000) + 86_400_000,
            },
        )
        return

    if execution.status == "error":
        yield make_tool_result_frame_event(
            encoder=encoder,
            call_id=execution.call_id,
            status="error",
            error=execution.error_message or "AI tool execution failed.",
        )
        return

    if execution.status == "rejected":
        rejected_projection = project_rejected_tool_response(execution.response)
        yield make_tool_result_frame_event(
            encoder=encoder,
            call_id=execution.call_id,
            status="rejected",
            error=rejected_projection.error_message,
            result_preview=rejected_projection.result_preview,
        )
        return

    assert execution.response is not None
    yield make_tool_result_frame_event(
        encoder=encoder,
        call_id=execution.call_id,
        status="ok",
        result_preview=tool_result_preview(execution.response["result"]),
    )


__all__ = [
    "ToolCallEventExecution",
    "iter_tool_call_events",
]
