from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from open_work_hub_api.core.settings import HERMES_MODEL, HERMES_PROVIDER, HERMES_RELEASE


HermesTerminalMode = Literal["standard", "yolo"]
HermesTerminalStatus = Literal[
    "starting",
    "running",
    "awaiting_approval",
    "stopping",
    "archiving",
    "exited",
    "terminated",
    "failed",
]


class HermesTerminalConfigResponse(BaseModel):
    enabled: bool
    release: str = HERMES_RELEASE
    provider: str = HERMES_PROVIDER
    model: str = HERMES_MODEL
    standard_mode_available: bool = True
    yolo_mode_available: bool = True
    yolo_requires_acknowledgement: bool = True
    idle_timeout_seconds: int
    artifact_retention_days: int
    max_sessions_per_user: int
    max_sessions_per_workspace_user: int


class HermesTerminalSessionCreateRequest(BaseModel):
    mode: HermesTerminalMode = "standard"
    risk_acknowledged: bool = False
    cols: int = Field(default=120, ge=20, le=500)
    rows: int = Field(default=32, ge=5, le=300)

    @model_validator(mode="after")
    def validate_yolo_acknowledgement(self) -> "HermesTerminalSessionCreateRequest":
        if self.mode == "yolo" and not self.risk_acknowledged:
            raise ValueError("YOLO mode requires an explicit risk acknowledgement.")
        return self


class HermesTerminalSessionResponse(BaseModel):
    id: str
    title: str
    mode: HermesTerminalMode
    status: HermesTerminalStatus
    cols: int
    rows: int
    exit_code: int | None = None
    failure_code: str | None = None
    last_activity_at: datetime
    idle_expires_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class HermesTerminalSessionListResponse(BaseModel):
    items: list[HermesTerminalSessionResponse]


class HermesTerminalArtifactResponse(BaseModel):
    id: str
    relative_path: str
    display_name: str
    size_bytes: int
    media_type: str
    sha256: str
    expires_at: datetime
    created_at: datetime


class HermesTerminalFileEntryResponse(BaseModel):
    relative_path: str
    name: str
    kind: Literal["file", "directory"]
    size_bytes: int | None = None
    modified_at: datetime | None = None
    artifact_id: str | None = None


class HermesTerminalFileListResponse(BaseModel):
    path: str
    active: bool
    items: list[HermesTerminalFileEntryResponse]


class HermesTerminalApprovalResponse(BaseModel):
    id: str
    request_id: str
    tool_name: str
    arguments: dict
    status: Literal["pending", "approved", "denied", "expired"]
    choice: str | None = None
    expires_at: datetime
    decided_at: datetime | None = None
    created_at: datetime


class HermesTerminalApprovalListResponse(BaseModel):
    items: list[HermesTerminalApprovalResponse]


class HermesTerminalApprovalDecisionRequest(BaseModel):
    decision: Literal["approve", "deny"]


class BrokerSessionCreateRequest(BaseModel):
    session_id: str
    profile_key: str
    mode: HermesTerminalMode
    cols: int
    rows: int
    mcp_url: str
    mcp_token: str
    research_sources: dict[str, bool]
    profile_archive_base64: str | None = None


class BrokerSessionResponse(BaseModel):
    session_id: str
    runtime_handle: str
    broker_instance_id: str
    status: Literal["starting", "running", "exited", "failed"]
    exit_code: int | None = None
    failure_code: str | None = None


class BrokerFileEntry(BaseModel):
    relative_path: str
    name: str
    kind: Literal["file", "directory"]
    size_bytes: int | None = None
    modified_at: datetime | None = None


class BrokerFileListResponse(BaseModel):
    path: str
    items: list[BrokerFileEntry]
