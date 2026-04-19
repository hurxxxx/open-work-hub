"""Agent event envelope contract for streaming chat responses.

Phase 2 publishes only ``content_delta``, ``reasoning_delta``, ``usage``,
``done``, and ``error``. The tool-calling and approval event types are
defined here so consumers pin one discriminated union now; Phase 3/4 turn
on publishers without touching the wire format.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Discriminator, Field, TypeAdapter


# ---------------------------------------------------------------------------
# Data payloads
# ---------------------------------------------------------------------------


class ContentDeltaData(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str


class ReasoningDeltaData(BaseModel):
    model_config = ConfigDict(frozen=True)
    text: str


class UsageData(BaseModel):
    model_config = ConfigDict(frozen=True)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class DoneMeta(BaseModel):
    model_config = ConfigDict(frozen=True)
    policy: str | None = None
    chosen_pool: Literal["local", "external"] | None = None
    decision_reason: str | None = None
    forced_local: bool = False
    pii_hits: list[str] = Field(default_factory=list)
    model: str | None = None
    chosen_model: str | None = None
    canonical_model: str | None = None
    provider: str | None = None


DoneFinishReason = Literal["stop", "length", "cancelled", "error"]


class DoneData(BaseModel):
    model_config = ConfigDict(frozen=True)
    finish_reason: DoneFinishReason
    audit_id: str | None = None
    meta: DoneMeta | None = None


class ErrorData(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    message: str
    retryable: bool = False


class ConversationAttachedData(BaseModel):
    """Emitted once at stream start so the client learns which persisted
    conversation row its turns are being appended to.

    Always precedes the first ``content_delta``/``reasoning_delta`` so a UI
    that tracks conversation ids can bind the id before any rendering begins.
    """

    model_config = ConfigDict(frozen=True)
    conversation_id: str


# Reserved P3 payloads (not emitted in P2).
class ToolCallStartedData(BaseModel):
    model_config = ConfigDict(frozen=True)
    call_id: str
    name: str
    args_preview: str | None = None


class ToolCallArgsDeltaData(BaseModel):
    model_config = ConfigDict(frozen=True)
    call_id: str
    delta: str


class ToolResultData(BaseModel):
    model_config = ConfigDict(frozen=True)
    call_id: str
    status: Literal["ok", "error"]
    result_preview: str | None = None
    error: str | None = None


# Reserved P4 payloads (not emitted in P2).
class ApprovalRequiredData(BaseModel):
    model_config = ConfigDict(frozen=True)
    approval_id: str
    tool: str
    resource_preview: str | None = None


class ApprovalResolvedData(BaseModel):
    model_config = ConfigDict(frozen=True)
    approval_id: str
    decision: Literal["approved", "rejected"]


# ---------------------------------------------------------------------------
# Envelopes
# ---------------------------------------------------------------------------


class _EnvelopeBase(BaseModel):
    model_config = ConfigDict(frozen=True)
    seq: int = Field(..., ge=0)
    timestamp_ms: int = Field(..., ge=0)


class ContentDeltaEvent(_EnvelopeBase):
    type: Literal["content_delta"] = "content_delta"
    data: ContentDeltaData


class ReasoningDeltaEvent(_EnvelopeBase):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    data: ReasoningDeltaData


class UsageEvent(_EnvelopeBase):
    type: Literal["usage"] = "usage"
    data: UsageData


class DoneEvent(_EnvelopeBase):
    type: Literal["done"] = "done"
    data: DoneData


class ErrorEvent(_EnvelopeBase):
    type: Literal["error"] = "error"
    data: ErrorData


class ConversationAttachedEvent(_EnvelopeBase):
    type: Literal["conversation_attached"] = "conversation_attached"
    data: ConversationAttachedData


class ToolCallStartedEvent(_EnvelopeBase):
    type: Literal["tool_call_started"] = "tool_call_started"
    data: ToolCallStartedData


class ToolCallArgsDeltaEvent(_EnvelopeBase):
    type: Literal["tool_call_args_delta"] = "tool_call_args_delta"
    data: ToolCallArgsDeltaData


class ToolResultEvent(_EnvelopeBase):
    type: Literal["tool_result"] = "tool_result"
    data: ToolResultData


class ApprovalRequiredEvent(_EnvelopeBase):
    type: Literal["approval_required"] = "approval_required"
    data: ApprovalRequiredData


class ApprovalResolvedEvent(_EnvelopeBase):
    type: Literal["approval_resolved"] = "approval_resolved"
    data: ApprovalResolvedData


AgentEventEnvelope = Annotated[
    Union[
        ContentDeltaEvent,
        ReasoningDeltaEvent,
        UsageEvent,
        DoneEvent,
        ErrorEvent,
        ConversationAttachedEvent,
        ToolCallStartedEvent,
        ToolCallArgsDeltaEvent,
        ToolResultEvent,
        ApprovalRequiredEvent,
        ApprovalResolvedEvent,
    ],
    Discriminator("type"),
]


_ENVELOPE_ADAPTER: TypeAdapter[Any] = TypeAdapter(AgentEventEnvelope)


_PUBLISHED_TYPES: dict[str, type[_EnvelopeBase]] = {
    "content_delta": ContentDeltaEvent,
    "reasoning_delta": ReasoningDeltaEvent,
    "usage": UsageEvent,
    "done": DoneEvent,
    "error": ErrorEvent,
    "conversation_attached": ConversationAttachedEvent,
    "tool_call_started": ToolCallStartedEvent,
    "tool_call_args_delta": ToolCallArgsDeltaEvent,
    "tool_result": ToolResultEvent,
    "approval_required": ApprovalRequiredEvent,
    "approval_resolved": ApprovalResolvedEvent,
}


def make_envelope(
    event_type: str,
    seq: int,
    data: Mapping[str, Any],
    *,
    timestamp_ms: int | None = None,
) -> Any:
    """Validate and build one envelope. Single construction path."""

    cls = _PUBLISHED_TYPES.get(event_type)
    if cls is None:
        raise ValueError(f"unknown envelope type: {event_type!r}")
    return cls(
        seq=seq,
        timestamp_ms=timestamp_ms if timestamp_ms is not None else _now_ms(),
        data=data,  # type: ignore[arg-type]
    )


def serialize_sse(event: Any) -> dict[str, str]:
    """Shape expected by ``sse_starlette.EventSourceResponse``.

    Returns a mapping with ``event`` (type) and ``data`` (JSON payload).
    ``exclude_none=True`` keeps reserved fields out of the wire when unset.
    """

    return {
        "event": event.type,
        "data": event.model_dump_json(exclude_none=True),
    }


class EnvelopeEncoder:
    """Monotone ``seq`` counter scoped to one stream."""

    __slots__ = ("_seq",)

    def __init__(self) -> None:
        self._seq = 0

    def next_seq(self) -> int:
        value = self._seq
        self._seq += 1
        return value


def envelope_schema() -> dict[str, Any]:
    """JSON schema snapshot for the discriminated union (test anchor)."""

    return _ENVELOPE_ADAPTER.json_schema()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


__all__ = [
    "AgentEventEnvelope",
    "ContentDeltaEvent",
    "ReasoningDeltaEvent",
    "UsageEvent",
    "DoneEvent",
    "ErrorEvent",
    "ToolCallStartedEvent",
    "ToolCallArgsDeltaEvent",
    "ToolResultEvent",
    "ApprovalRequiredEvent",
    "ApprovalResolvedEvent",
    "DoneMeta",
    "EnvelopeEncoder",
    "envelope_schema",
    "make_envelope",
    "serialize_sse",
]
