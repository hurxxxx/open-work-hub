from __future__ import annotations

from typing import Literal

from open_alm_api.domains.ai.events import AgentEventEnvelope, EnvelopeEncoder, make_envelope


ToolStreamResultStatus = Literal["ok", "error", "rejected"]


def preview_tool_event_text(
    text: str,
    *,
    limit: int,
    suffix: str = "...",
) -> str:
    if len(text) <= limit:
        return text
    if limit <= len(suffix):
        return suffix[:limit]
    return f"{text[: limit - len(suffix)]}{suffix}"


def make_tool_call_frame_events(
    *,
    encoder: EnvelopeEncoder,
    call_id: str,
    tool_name: str,
    arguments: str,
    emit_arguments_delta: bool,
    preview_suffix: str = "...",
) -> list[AgentEventEnvelope]:
    events = [
        make_envelope(
            "tool_call_started",
            encoder.next_seq(),
            {
                "call_id": call_id,
                "name": tool_name,
                "args_preview": preview_tool_event_text(
                    arguments,
                    limit=240,
                    suffix=preview_suffix,
                ),
            },
        )
    ]
    if emit_arguments_delta:
        events.append(
            make_envelope(
                "tool_call_args_delta",
                encoder.next_seq(),
                {
                    "call_id": call_id,
                    "delta": arguments,
                },
            )
        )
    return events


def make_tool_result_frame_event(
    *,
    encoder: EnvelopeEncoder,
    call_id: str,
    status: ToolStreamResultStatus,
    result_preview: str | None = None,
    error: str | None = None,
) -> AgentEventEnvelope:
    return make_envelope(
        "tool_result",
        encoder.next_seq(),
        {
            "call_id": call_id,
            "status": status,
            "result_preview": result_preview,
            "error": error,
        },
    )


__all__ = [
    "ToolStreamResultStatus",
    "make_tool_call_frame_events",
    "make_tool_result_frame_event",
    "preview_tool_event_text",
]
