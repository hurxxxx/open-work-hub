from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aidoo_api.core.db import Base
from aidoo_api.domains.meeting.models import utcnow_naive


RUN_STATUSES = (
    "pending",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "abandoned",
)
LIVE_RUN_STATUSES = ("pending", "running", "awaiting_approval")
INVOCATION_STATUSES = (
    "pending",
    "running",
    "awaiting_approval",
    "resumed",
    "completed",
    "failed",
    "cancelled",
    "abandoned",
)
RUNTIME_PROFILES = (
    "interactive_read",
    "grounded_report",
    "long_doc",
    "high_risk_action",
)


class AgentRun(Base):
    __tablename__ = "ai_agent_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','awaiting_approval','completed','failed','cancelled','abandoned')",
            name="ck_ai_agent_runs_status",
        ),
        CheckConstraint(
            "runtime_profile IN ('interactive_read','grounded_report','long_doc','high_risk_action')",
            name="ck_ai_agent_runs_runtime_profile",
        ),
        Index(
            "ix_ai_agent_runs_conversation_status_created",
            "conversation_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_ai_agent_runs_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_ai_agent_runs_live_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('pending','running','awaiting_approval')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    legacy_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_agent_run_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    runtime_profile: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="interactive_read",
        server_default=text("'interactive_read'"),
    )
    graph_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    model_profile_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class AgentInvocation(Base):
    __tablename__ = "ai_agent_invocations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','awaiting_approval','resumed','completed','failed','cancelled','abandoned')",
            name="ck_ai_agent_invocations_status",
        ),
        Index(
            "uq_ai_agent_invocations_run_seq",
            "agent_run_id",
            "invocation_seq",
            unique=True,
        ),
        Index(
            "uq_ai_agent_invocations_pending_approval_run",
            "agent_run_id",
            unique=True,
            postgresql_where=text("status = 'awaiting_approval'"),
        ),
        Index(
            "ix_ai_agent_invocations_run_status_seq",
            "agent_run_id",
            "status",
            "invocation_seq",
        ),
        Index(
            "ix_ai_agent_invocations_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invocation_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    input_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    usage_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class AgentTraceEvent(Base):
    __tablename__ = "ai_agent_trace_events"
    __table_args__ = (
        CheckConstraint("run_seq >= 0", name="ck_ai_agent_trace_events_run_seq_nonnegative"),
        CheckConstraint(
            "invocation_seq >= 0",
            name="ck_ai_agent_trace_events_invocation_seq_nonnegative",
        ),
        CheckConstraint("event_seq >= 0", name="ck_ai_agent_trace_events_event_seq_nonnegative"),
        Index(
            "uq_ai_agent_trace_events_run_event_seq",
            "agent_run_id",
            "event_seq",
            unique=True,
        ),
        Index(
            "ix_ai_agent_trace_events_run_order",
            "agent_run_id",
            "run_seq",
            "invocation_seq",
            "event_seq",
        ),
        Index(
            "ix_ai_agent_trace_events_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_invocation_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_agent_invocations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    invocation_seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    event_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


__all__ = ["AgentInvocation", "AgentRun", "AgentTraceEvent"]
