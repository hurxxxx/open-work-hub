from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

HermesRunStatus = Literal[
    "pending",
    "dispatching",
    "queued",
    "running",
    "awaiting_approval",
    "stopping",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "invalid_output",
]


class HermesAgentStatusResponse(BaseModel):
    enabled: bool
    release: str
    provider: str
    model: str
    profile_status: str
    runtime: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class HermesSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    system_prompt: str | None = Field(default=None, max_length=50_000)
    scope_ref: str | None = Field(default=None, max_length=160)
    scope_resource_id: str | None = Field(default=None, max_length=256)

    @field_validator("title", "system_prompt", "scope_ref", "scope_resource_id")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class HermesSessionUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    pinned: bool | None = None
    archived: bool | None = None


class HermesSessionResponse(BaseModel):
    id: str
    title: str | None = None
    source: str | None = None
    model: str | None = None
    message_count: int = 0
    started_at: float | None = None
    last_active: float | None = None
    preview: str | None = None
    parent_session_id: str | None = None
    pinned: bool = False
    archived: bool = False
    scope_ref: str | None = None
    scope_resource_id: str | None = None
    created_at: datetime
    updated_at: datetime


class HermesSessionListResponse(BaseModel):
    data: list[HermesSessionResponse]
    limit: int
    offset: int
    has_more: bool


class HermesSessionMessagesResponse(BaseModel):
    session_id: str
    data: list[dict[str, Any]]
    pagination: dict[str, Any] = Field(default_factory=dict)


class HermesRunCreate(BaseModel):
    input: str = Field(min_length=1, max_length=200_000)
    instructions: str | None = Field(default=None, max_length=50_000)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list, max_length=500)
    allowed_app_ids: list[str] | None = Field(default=None, max_length=100)

    @field_validator("input")
    @classmethod
    def _non_blank_input(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("input must not be blank")
        return normalized

    @field_validator("allowed_app_ids")
    @classmethod
    def _normalize_allowed_app_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(
            dict.fromkeys(app_id.strip().lower() for app_id in value if app_id and app_id.strip())
        )


class HermesRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_binding_id: str | None = None
    kind: str
    workload_id: str | None = None
    status: HermesRunStatus
    stage: str | None = None
    progress_percent: int
    current_activity: str | None = None
    output_text: str | None = None
    output_payload: dict[str, Any] | None = None
    model_policy: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    allowed_app_ids: list[str] | None = None
    pending_approval: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HermesRunListResponse(BaseModel):
    data: list[HermesRunResponse]
    total: int


class HermesFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    relative_path: str
    size_bytes: int
    media_type: str
    sha256: str
    updated_at: datetime


class HermesFileListResponse(BaseModel):
    data: list[HermesFileResponse]


class HermesSteerRequest(BaseModel):
    input: str = Field(min_length=1, max_length=50_000)


class HermesApprovalDecision(BaseModel):
    request_id: str = Field(min_length=1, max_length=256)
    choice: Literal["once", "deny"]


class HermesJobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    schedule: str = Field(min_length=1, max_length=240)
    prompt: str = Field(min_length=1, max_length=200_000)
    skills: list[str] = Field(default_factory=list, max_length=100)
    repeat: int | None = Field(default=None, ge=1, le=100_000)


class HermesJobResponse(BaseModel):
    id: str
    name: str
    status: str
    schedule: str | None = None
    prompt: str | None = None
    next_run: Any | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class HermesJobListResponse(BaseModel):
    data: list[HermesJobResponse]
