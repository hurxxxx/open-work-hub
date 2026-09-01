from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive


HERMES_TERMINAL_MODES = ("standard", "yolo")
HERMES_TERMINAL_SESSION_STATUSES = (
    "starting",
    "running",
    "awaiting_approval",
    "stopping",
    "archiving",
    "exited",
    "terminated",
    "failed",
)
HERMES_TERMINAL_ACTIVE_STATUSES = frozenset(
    {"starting", "running", "awaiting_approval", "stopping", "archiving"}
)
HERMES_TERMINAL_APPROVAL_STATUSES = ("pending", "approved", "denied", "expired")
JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


def _sql_in_clause(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ",".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


class HermesTerminalSession(Base):
    __tablename__ = "hermes_terminal_sessions"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("mode", HERMES_TERMINAL_MODES),
            name="ck_hermes_terminal_sessions_mode",
        ),
        CheckConstraint(
            _sql_in_clause("status", HERMES_TERMINAL_SESSION_STATUSES),
            name="ck_hermes_terminal_sessions_status",
        ),
        CheckConstraint(
            "cols >= 20 AND cols <= 500 AND rows >= 5 AND rows <= 300",
            name="ck_hermes_terminal_sessions_size",
        ),
        CheckConstraint(
            "archive_attempts >= 0",
            name="ck_hermes_terminal_sessions_archive_attempts",
        ),
        CheckConstraint(
            "archive_target_status IS NULL OR "
            "archive_target_status IN ('exited','terminated','failed')",
            name="ck_hermes_terminal_sessions_archive_target",
        ),
        Index(
            "ix_hermes_terminal_sessions_owner_created",
            "workspace_id",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_hermes_terminal_sessions_status_activity",
            "status",
            "last_activity_at",
        ),
        Index(
            "ix_hermes_terminal_sessions_archive_recovery",
            "status",
            "archive_started_at",
            "archive_attempts",
        ),
        Index(
            "uq_hermes_terminal_sessions_active_owner",
            "workspace_id",
            "user_id",
            unique=True,
            postgresql_where=text(
                "status IN ('starting','running','awaiting_approval','stopping','archiving')"
            ),
            sqlite_where=text(
                "status IN ('starting','running','awaiting_approval','stopping','archiving')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_binding_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_profile_bindings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(
        String(16),
        default="standard",
        server_default=text("'standard'"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="starting",
        server_default=text("'starting'"),
        nullable=False,
    )
    allowed_app_ids: Mapped[list[str]] = mapped_column(
        JSONB_COMPAT,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    runtime_handle: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    broker_instance_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    mcp_token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    cols: Mapped[int] = mapped_column(Integer, default=120, server_default=text("120"))
    rows: Mapped[int] = mapped_column(Integer, default=32, server_default=text("32"))
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    archive_target_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    archive_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    archive_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archive_failure_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class HermesTerminalProfileState(Base):
    __tablename__ = "hermes_terminal_profile_states"
    __table_args__ = (
        CheckConstraint(
            "revision >= 0 AND archive_size_bytes >= 0",
            name="ck_hermes_terminal_profile_states_size_revision",
        ),
    )

    profile_binding_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_profile_bindings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    profile_name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    archive_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    archive_size_bytes: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class HermesTerminalArtifact(Base):
    __tablename__ = "hermes_terminal_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "relative_path",
            name="uq_hermes_terminal_artifacts_session_path",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_hermes_terminal_artifacts_size",
        ),
        Index(
            "ix_hermes_terminal_artifacts_owner_expiry",
            "workspace_id",
            "user_id",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_terminal_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class HermesTerminalToolApproval(Base):
    __tablename__ = "hermes_terminal_tool_approvals"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "request_id",
            name="uq_hermes_terminal_tool_approvals_session_request",
        ),
        CheckConstraint(
            _sql_in_clause("status", HERMES_TERMINAL_APPROVAL_STATUSES),
            name="ck_hermes_terminal_tool_approvals_status",
        ),
        CheckConstraint(
            "(consumed_at IS NULL AND external_call_id IS NULL) OR "
            "(consumed_at IS NOT NULL AND external_call_id IS NOT NULL)",
            name="ck_hermes_terminal_tool_approvals_consumption",
        ),
        Index(
            "ix_hermes_terminal_tool_approvals_session_status",
            "session_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_hermes_terminal_tool_approvals_external_call_id",
            "external_call_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_terminal_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(256), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(160), nullable=False)
    arguments_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB_COMPAT, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    choice: Mapped[str | None] = mapped_column(String(24), nullable=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_call_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
