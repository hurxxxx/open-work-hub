"""Pydantic request/response schemas for the conversations API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from open_work_hub_api.domains.conversations.default_scope_adapters import (
    is_supported_conversation_scope_ref,
)
from open_work_hub_api.domains.conversations.scope_contract import (
    SCOPE_REF_MAX_LEN,
    SCOPE_RESOURCE_ID_MAX_LEN,
)


def _camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _lookup_alias_value(data: dict[str, Any], field_name: str) -> Any:
    return data.get(field_name, data.get(_camel(field_name)))


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
    scope_ref: ConversationScopeRef | None = None
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
    scope_ref: ConversationScopeRef | None = None
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
    scope_ref: ConversationScopeRef | None = Field(
        default=None,
        max_length=SCOPE_REF_MAX_LEN,
    )
    scope_resource_id: str | None = Field(
        default=None,
        max_length=SCOPE_RESOURCE_ID_MAX_LEN,
    )

    @model_validator(mode="before")
    @classmethod
    def validate_scope_before_field_types(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        scope_ref = _lookup_alias_value(data, "scope_ref")
        scope_resource_id = _lookup_alias_value(data, "scope_resource_id")
        if scope_ref is not None and not is_supported_conversation_scope_ref(str(scope_ref)):
            raise PydanticCustomError(
                "conversations.unsupported_scope",
                "Unsupported conversation scope: {scope_ref}",
                {"scope_ref": scope_ref},
            )
        if (scope_ref is None) != (scope_resource_id is None):
            raise PydanticCustomError(
                "conversations.scope_pair_required",
                "scope_ref and scope_resource_id must be provided together.",
                {},
            )
        return data

    @model_validator(mode="after")
    def validate_scope_pair(self) -> "ConversationCreateRequest":
        if (self.scope_ref is None) != (self.scope_resource_id is None):
            raise PydanticCustomError(
                "conversations.scope_pair_required",
                "scope_ref and scope_resource_id must be provided together.",
                {},
            )
        return self


class ConversationUpdateRequest(_CamelModel):
    title: str


ConversationScopeRef = str
