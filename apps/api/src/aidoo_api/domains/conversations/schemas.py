"""Pydantic request/response schemas for the conversations API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ConversationSummary(_CamelModel):
    """Row shape for the conversation list sidebar — no turn bodies."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ArtifactOut(_CamelModel):
    """One saved artifact attached to an assistant turn.

    Mirrors the live ``ArtifactBuffer`` the UI builds during streaming so
    reopening a conversation re-opens the side panel with the same content.
    """

    id: str
    type: str
    title: str | None = None
    # Only populated for ``type="code"`` artifacts — the client uses it
    # to pick a syntax highlighter. Other types leave it null.
    language: str | None = None
    content: str
    status: str | None = None


class ConversationTurnOut(_CamelModel):
    """Flattened turn shape matching the frontend ChatTurn contract.

    Rendering metadata (reasoning, tool calls, policy decisions, PII hits,
    artifacts) is lifted from the stored ``meta`` dict into top-level fields
    so the existing MessageBubble / ThinkingPanel / ToolCallCard / Artifact
    renderers don't need a second translation step when a saved conversation
    is reloaded.
    """

    id: str
    seq: int
    role: str
    content: str
    reasoning: str | None = None
    reasoning_status: str | None = None
    finish_reason: str | None = None
    response_status: str | None = None
    provider: str | None = None
    policy: str | None = None
    chosen_pool: str | None = None
    decision_reason: str | None = None
    forced_local: bool | None = None
    pii_hits: list[str] = Field(default_factory=list)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)
    created_at: datetime


class ConversationDetail(_CamelModel):
    """Conversation + full turn list for the detail view."""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    turns: list[ConversationTurnOut] = Field(default_factory=list)


class ConversationListResponse(_CamelModel):
    items: list[ConversationSummary]
    next_cursor: str | None = None


class ConversationCreateRequest(_CamelModel):
    title: str = ""


class ConversationUpdateRequest(_CamelModel):
    title: str
