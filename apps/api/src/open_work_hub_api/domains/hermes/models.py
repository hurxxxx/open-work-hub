from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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


HERMES_PROFILE_STATUSES = ("provisioning", "active", "error", "disabled")
HERMES_SESSION_STATUSES = ("active", "archived", "deleted")
HERMES_RUN_KINDS = ("interactive", "workload", "scheduled")
HERMES_RUN_STATUSES = (
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
)
HERMES_DISPATCH_STATUSES = (
    "pending",
    "claimed",
    "dispatched",
    "dead_letter",
    "cancelled",
)
HERMES_APPROVAL_STATUSES = ("pending", "approved", "denied", "expired")
HERMES_JOB_STATUSES = ("active", "paused", "deleted", "error")
JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


def _sql_in_clause(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ",".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


class HermesResearchSourceSettings(Base):
    __tablename__ = "hermes_research_source_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_hermes_research_source_settings_singleton"),
        CheckConstraint(
            "revision >= 1",
            name="ck_hermes_research_source_settings_revision",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        server_default=text("1"),
    )
    semantic_scholar_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    arxiv_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    openalex_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    crossref_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
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


class HermesProfileBinding(Base):
    __tablename__ = "hermes_profile_bindings"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_hermes_profile_bindings_workspace_user",
        ),
        CheckConstraint(
            _sql_in_clause("status", HERMES_PROFILE_STATUSES),
            name="ck_hermes_profile_bindings_status",
        ),
        CheckConstraint(
            "policy_revision >= 1",
            name="ck_hermes_profile_bindings_policy_revision",
        ),
        Index(
            "ix_hermes_profile_bindings_status_updated",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
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
    profile_name: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(24),
        default="provisioning",
        server_default=text("'provisioning'"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    policy_revision: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default=text("1"),
        nullable=False,
    )
    last_error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provisioned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class HermesSessionBinding(Base):
    __tablename__ = "hermes_session_bindings"
    __table_args__ = (
        UniqueConstraint(
            "profile_binding_id",
            "hermes_session_id",
            name="uq_hermes_session_bindings_profile_session",
        ),
        CheckConstraint(
            _sql_in_clause("status", HERMES_SESSION_STATUSES),
            name="ck_hermes_session_bindings_status",
        ),
        Index(
            "ix_hermes_session_bindings_owner_updated",
            "workspace_id",
            "user_id",
            "updated_at",
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
    hermes_session_id: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str | None] = mapped_column(String(240), nullable=True)
    scope_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    scope_resource_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24),
        default="active",
        server_default=text("'active'"),
        nullable=False,
    )
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


class HermesRunProjection(Base):
    __tablename__ = "hermes_run_projections"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("kind", HERMES_RUN_KINDS),
            name="ck_hermes_run_projections_kind",
        ),
        CheckConstraint(
            _sql_in_clause("status", HERMES_RUN_STATUSES),
            name="ck_hermes_run_projections_status",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_hermes_run_projections_progress",
        ),
        CheckConstraint(
            "execution_attempts >= 0",
            name="ck_hermes_run_projections_attempts",
        ),
        Index(
            "ix_hermes_run_projections_owner_created",
            "workspace_id",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_hermes_run_projections_status_updated",
            "status",
            "updated_at",
        ),
        Index(
            "ix_hermes_run_projections_session_created",
            "session_binding_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_binding_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_profile_bindings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_binding_id: Mapped[str | None] = mapped_column(
        ForeignKey("hermes_session_bindings.id", ondelete="SET NULL"),
        nullable=True,
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
    hermes_run_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        unique=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    workload_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    stage: Mapped[str | None] = mapped_column(String(160), nullable=True)
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    current_activity: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage: Mapped[dict[str, Any]] = mapped_column(
        JSONB_COMPAT,
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    allowed_app_ids: Mapped[list[str] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    pending_approval: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    execution_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class HermesRunInput(Base):
    __tablename__ = "hermes_run_inputs"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_run_projections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_history: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB_COMPAT,
        default=list,
        server_default=text("'[]'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class HermesDispatchOutbox(Base):
    __tablename__ = "hermes_dispatch_outbox"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", HERMES_DISPATCH_STATUSES),
            name="ck_hermes_dispatch_outbox_status",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_hermes_dispatch_outbox_attempts",
        ),
        Index(
            "ix_hermes_dispatch_outbox_due",
            "status",
            "available_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_run_projections.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class HermesRunEvent(Base):
    __tablename__ = "hermes_run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_hermes_run_events_sequence"),
        Index("ix_hermes_run_events_run_sequence", "run_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_run_projections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB_COMPAT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class HermesToolApproval(Base):
    __tablename__ = "hermes_tool_approvals"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", HERMES_APPROVAL_STATUSES),
            name="ck_hermes_tool_approvals_status",
        ),
        UniqueConstraint(
            "run_id",
            "request_id",
            name="uq_hermes_tool_approvals_run_request",
        ),
        CheckConstraint(
            "(consumed_at IS NULL AND consumed_tool_name IS NULL "
            "AND consumed_arguments_sha256 IS NULL AND external_call_id IS NULL) "
            "OR (consumed_at IS NOT NULL AND consumed_tool_name IS NOT NULL "
            "AND consumed_arguments_sha256 IS NOT NULL AND external_call_id IS NOT NULL)",
            name="ck_hermes_tool_approvals_consumption",
        ),
        Index("ix_hermes_tool_approvals_status_created", "status", "created_at"),
        Index(
            "ix_hermes_tool_approvals_external_call_id",
            "external_call_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("hermes_run_projections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_id: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB_COMPAT, nullable=False)
    choice: Mapped[str | None] = mapped_column(String(24), nullable=True)
    decided_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_tool_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    consumed_arguments_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    external_call_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class HermesJobBinding(Base):
    __tablename__ = "hermes_job_bindings"
    __table_args__ = (
        UniqueConstraint(
            "profile_binding_id",
            "hermes_job_id",
            name="uq_hermes_job_bindings_profile_job",
        ),
        CheckConstraint(
            _sql_in_clause("status", HERMES_JOB_STATUSES),
            name="ck_hermes_job_bindings_status",
        ),
        Index(
            "ix_hermes_job_bindings_owner_updated",
            "workspace_id",
            "user_id",
            "updated_at",
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
    hermes_job_id: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="active",
        server_default=text("'active'"),
        nullable=False,
    )
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
