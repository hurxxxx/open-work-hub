"""Pydantic request/response schemas for the conversations API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    scope_ref: Literal["meeting"] | None = None
    scope_resource_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationLivePendingApproval(_CamelModel):
    approval_id: str
    agent_run_id: str
    call_id: str
    tool: str
    resource_preview: str | None = None
    expires_at_ms: int
    status: Literal["pending", "approved", "rejected"]
    reason: str | None = None


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
    scope_ref: Literal["meeting"] | None = None
    scope_resource_id: str | None = None
    created_at: datetime
    updated_at: datetime
    live_pending_approval: ConversationLivePendingApproval | None = None
    turns: list[ConversationTurnOut] = Field(default_factory=list)


class ConversationListResponse(_CamelModel):
    items: list[ConversationSummary]
    next_cursor: str | None = None


class ConversationCreateRequest(_CamelModel):
    title: str = ""
    scope_ref: Literal["meeting"] | None = None
    scope_resource_id: str | None = None

    @model_validator(mode="after")
    def validate_scope_pair(self) -> "ConversationCreateRequest":
        if (self.scope_ref is None) != (self.scope_resource_id is None):
            raise ValueError("scope_ref and scope_resource_id must be provided together.")
        return self


class ConversationUpdateRequest(_CamelModel):
    title: str


def conversation_summary_from_row(row: Any) -> ConversationSummary:
    scope_ref = row.scope_ref if row.scope_ref == "meeting" else None
    scope_resource_id = row.scope_resource_id if scope_ref is not None else None
    return ConversationSummary(
        id=row.id,
        title=row.title,
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def conversation_turn_out_from_row(turn: Any) -> ConversationTurnOut:
    meta = turn.meta or {}
    raw_artifacts = meta.get("artifacts") or []
    artifacts: list[ArtifactOut] = []
    for record in raw_artifacts:
        if not isinstance(record, dict):
            continue
        artifact_id = record.get("id")
        if not artifact_id:
            continue
        artifacts.append(
            ArtifactOut(
                id=artifact_id,
                type=record.get("type") or "document",
                title=record.get("title"),
                language=record.get("language"),
                content=record.get("content") or "",
                status=record.get("status"),
            )
        )
    return ConversationTurnOut(
        id=turn.id,
        seq=turn.seq,
        role=turn.role,
        content=turn.content,
        reasoning=meta.get("reasoning"),
        reasoning_status=meta.get("reasoning_status"),
        finish_reason=meta.get("finish_reason"),
        response_status=meta.get("response_status"),
        provider=meta.get("provider"),
        policy=meta.get("policy"),
        chosen_pool=meta.get("chosen_pool"),
        decision_reason=meta.get("decision_reason"),
        forced_local=meta.get("forced_local"),
        pii_hits=list(meta.get("pii_hits") or []),
        tool_calls=list(meta.get("tool_calls") or []),
        pending_approvals=list(meta.get("pending_approvals") or []),
        artifacts=artifacts,
        created_at=turn.created_at,
    )


def conversation_detail_from_row(
    row: Any,
    *,
    live_pending_approval: dict[str, Any] | None = None,
) -> ConversationDetail:
    scope_ref = row.scope_ref if row.scope_ref == "meeting" else None
    scope_resource_id = row.scope_resource_id if scope_ref is not None else None
    return ConversationDetail(
        id=row.id,
        title=row.title,
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        live_pending_approval=(
            ConversationLivePendingApproval.model_validate(live_pending_approval)
            if live_pending_approval is not None
            else None
        ),
        turns=[conversation_turn_out_from_row(turn) for turn in row.turns],
    )
