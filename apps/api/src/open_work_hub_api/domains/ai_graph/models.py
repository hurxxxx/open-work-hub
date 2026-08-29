from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive


GRAPH_RUN_STATUSES = ("pending", "running", "completed", "failed", "cancelled")
GRAPH_RUN_VISIBILITIES = ("private", "workspace")
GRAPH_DISPATCH_STATUSES = (
    "pending",
    "claimed",
    "dispatched",
    "dead_letter",
    "cancelled",
)
JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


# LangGraph checkpoint-postgres 3.1.0 owns the read/write semantics. These
# metadata declarations let Alembic guard the package schema against drift.
CHECKPOINT_MIGRATIONS_TABLE = Table(
    "checkpoint_migrations",
    Base.metadata,
    Column("v", Integer, primary_key=True),
)
CHECKPOINTS_TABLE = Table(
    "checkpoints",
    Base.metadata,
    Column("thread_id", Text, primary_key=True),
    Column("checkpoint_ns", Text, primary_key=True, server_default=text("''")),
    Column("checkpoint_id", Text, primary_key=True),
    Column("parent_checkpoint_id", Text, nullable=True),
    Column("type", Text, nullable=True),
    Column("checkpoint", JSONB_COMPAT, nullable=False),
    Column("metadata", JSONB_COMPAT, server_default=text("'{}'"), nullable=False),
    Index("checkpoints_thread_id_idx", "thread_id"),
)
CHECKPOINT_BLOBS_TABLE = Table(
    "checkpoint_blobs",
    Base.metadata,
    Column("thread_id", Text, primary_key=True),
    Column("checkpoint_ns", Text, primary_key=True, server_default=text("''")),
    Column("channel", Text, primary_key=True),
    Column("version", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("blob", LargeBinary, nullable=True),
    Index("checkpoint_blobs_thread_id_idx", "thread_id"),
)
CHECKPOINT_WRITES_TABLE = Table(
    "checkpoint_writes",
    Base.metadata,
    Column("thread_id", Text, primary_key=True),
    Column("checkpoint_ns", Text, primary_key=True, server_default=text("''")),
    Column("checkpoint_id", Text, primary_key=True),
    Column("task_id", Text, primary_key=True),
    Column("idx", Integer, primary_key=True),
    Column("channel", Text, nullable=False),
    Column("type", Text, nullable=True),
    Column("blob", LargeBinary, nullable=False),
    Column("task_path", Text, server_default=text("''"), nullable=False),
    Index("checkpoint_writes_thread_id_idx", "thread_id"),
)


def _sql_in_clause(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ",".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


class AiGraphRun(Base):
    """UI/ACL projection only; durable graph state lives in LangGraph checkpoints."""

    __tablename__ = "ai_graph_runs"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", GRAPH_RUN_STATUSES),
            name="ck_ai_graph_runs_status",
        ),
        CheckConstraint(
            _sql_in_clause("visibility", GRAPH_RUN_VISIBILITIES),
            name="ck_ai_graph_runs_visibility",
        ),
        CheckConstraint(
            "current_step >= 0 AND total_steps >= 0 AND current_step <= total_steps",
            name="ck_ai_graph_runs_steps",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_ai_graph_runs_progress",
        ),
        CheckConstraint(
            "execution_attempts >= 0",
            name="ck_ai_graph_runs_execution_attempts",
        ),
        Index(
            "ix_ai_graph_runs_workspace_user_created",
            "workspace_id",
            "requested_by_user_id",
            "created_at",
        ),
        Index(
            "ix_ai_graph_runs_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_ai_graph_runs_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index(
            "ix_ai_graph_runs_status_lease",
            "status",
            "execution_lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    graph_id: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(64), nullable=False)
    checkpoint_thread_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
    )
    checkpoint_ns: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    stage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    total_steps: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status_message_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    execution_claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    execution_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    visibility: Mapped[str] = mapped_column(
        String(24),
        default="private",
        server_default=text("'private'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class AiGraphDispatchOutbox(Base):
    """Transactional dispatch intent. ``payload_ref`` points to app-owned input."""

    __tablename__ = "ai_graph_dispatch_outbox"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", GRAPH_DISPATCH_STATUSES),
            name="ck_ai_graph_dispatch_outbox_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_ai_graph_dispatch_outbox_attempts"),
        Index(
            "ix_ai_graph_dispatch_outbox_due",
            "status",
            "available_at",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    graph_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_graph_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    payload_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    queue_name: Mapped[str] = mapped_column(String(128), nullable=False)
    task_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class AiGraphRunInput(Base):
    """Immutable bootstrap input, removed after a terminal run/checkpoint."""

    __tablename__ = "ai_graph_run_inputs"
    __table_args__ = (
        CheckConstraint(
            "schema_version >= 1",
            name="ck_ai_graph_run_inputs_schema_version",
        ),
    )

    graph_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_graph_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB_COMPAT, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class AiGraphRunNodeProgress(Base):
    """Idempotent UI progress marker; not graph execution state."""

    __tablename__ = "ai_graph_run_node_progress"

    graph_run_id: Mapped[str] = mapped_column(
        ForeignKey("ai_graph_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    node_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
