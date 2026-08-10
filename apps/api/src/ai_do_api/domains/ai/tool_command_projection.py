from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from ai_do_api.domains.ai.events import (
    AgentEventEnvelope,
    EnvelopeEncoder,
    make_envelope,
    serialize_sse,
)
from ai_do_api.domains.ai.tool_call_event_projection import iter_tool_call_events
from ai_do_api.domains.ai.tool_result_projection import render_tool_result_message
from ai_do_api.domains.ai.tool_runtime import ToolCallExecution


@dataclass(frozen=True)
class ToolChatCommandResult:
    tool_name: str
    content: str
    finish_reason: Literal["stop", "error"]
    execution: ToolCallExecution


def build_tool_chat_command_result(
    execution: ToolCallExecution,
) -> ToolChatCommandResult:
    if execution.status == "ok":
        assert execution.response is not None
        tool_name = execution.response["tool"]
        content = render_tool_result_message(tool_name, execution.response["result"])
        finish_reason: Literal["stop", "error"] = "stop"
    elif execution.status == "blocked":
        tool_name = execution.tool_name
        content = execution.error_message or f"도구 {tool_name} 실행에는 승인 절차가 필요합니다."
        finish_reason = "stop"
    else:
        tool_name = execution.tool_name
        content = execution.error_message or "AI tool execution failed."
        finish_reason = "error"

    return ToolChatCommandResult(
        tool_name=tool_name,
        content=content,
        finish_reason=finish_reason,
        execution=execution,
    )


def build_tool_chat_response_payload(
    result: ToolChatCommandResult,
    *,
    requested_backend_mode: str | None,
) -> dict[str, Any]:
    tool_model = f"tool://{result.tool_name}"
    return {
        "model": tool_model,
        "content": result.content,
        "usage": None,
        "finish_reason": result.finish_reason,
        "provider": "tool",
        "backend": "primary",
        "fallback_used": False,
        "canonical_model": tool_model,
        "requested_backend_mode": requested_backend_mode,
        "policy": None,
        "chosen_pool": None,
        "decision_reason": "direct_tool_command",
        "forced_local": False,
        "pii_hits": [],
    }


def iter_tool_chat_command_events(
    *,
    encoder: EnvelopeEncoder,
    execution: ToolCallExecution,
) -> Iterator[AgentEventEnvelope]:
    if execution.status == "blocked":
        yield make_envelope(
            "tool_call_started",
            encoder.next_seq(),
            {
                "call_id": execution.call_id,
                "name": execution.tool_name,
                "args_preview": execution.arguments_json,
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
        yield make_envelope(
            "content_delta",
            encoder.next_seq(),
            {
                "text": execution.error_message
                or f"도구 {execution.tool_name} 실행에는 승인 절차가 필요합니다."
            },
        )
        yield make_envelope(
            "done",
            encoder.next_seq(),
            {
                "finish_reason": "stop",
                "audit_id": None,
                "meta": tool_done_meta(execution.tool_name),
            },
        )
        return

    yield from iter_tool_call_events(encoder=encoder, execution=execution)

    if execution.status == "error":
        message = execution.error_message or "AI tool execution failed."
        yield make_envelope(
            "error",
            encoder.next_seq(),
            {
                "code": "request_error",
                "message": message,
                "retryable": False,
            },
        )
        yield make_envelope(
            "done",
            encoder.next_seq(),
            {
                "finish_reason": "error",
                "audit_id": None,
                "meta": tool_done_meta(execution.tool_name),
            },
        )
        return

    assert execution.response is not None
    yield make_envelope(
        "content_delta",
        encoder.next_seq(),
        {
            "text": render_tool_result_message(
                execution.response["tool"],
                execution.response["result"],
            ),
        },
    )
    yield make_envelope(
        "done",
        encoder.next_seq(),
        {
            "finish_reason": "stop",
            "audit_id": None,
            "meta": tool_done_meta(execution.response["tool"]),
        },
    )


def iter_tool_chat_command_sse_events(
    *,
    encoder: EnvelopeEncoder,
    execution: ToolCallExecution,
) -> Iterator[dict[str, str]]:
    for event in iter_tool_chat_command_events(encoder=encoder, execution=execution):
        yield serialize_sse(event)


def tool_done_meta(tool_name: str) -> dict[str, Any]:
    tool_model = f"tool://{tool_name}"
    return {
        "policy": None,
        "chosen_pool": None,
        "decision_reason": "direct_tool_command",
        "forced_local": False,
        "pii_hits": [],
        "model": tool_model,
        "chosen_model": tool_model,
        "canonical_model": tool_model,
        "provider": "tool",
    }


__all__ = [
    "ToolChatCommandResult",
    "build_tool_chat_command_result",
    "build_tool_chat_response_payload",
    "iter_tool_chat_command_events",
    "iter_tool_chat_command_sse_events",
    "tool_done_meta",
]
