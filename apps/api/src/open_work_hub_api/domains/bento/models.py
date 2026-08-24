from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class BentoDocument(Base):
    __tablename__ = "bento_documents"
    __table_args__ = (
        CheckConstraint(
            "visibility in ('personal', 'workspace')",
            name="ck_bento_documents_visibility",
        ),
        Index("ix_bento_documents_workspace_id", "workspace_id"),
        Index("ix_bento_documents_owner_id", "owner_id"),
        Index("ix_bento_documents_archived_at", "archived_at"),
        Index("ix_bento_documents_updated_at", "updated_at"),
        Index("ix_bento_documents_visibility", "visibility"),
        Index(
            "ix_bento_documents_workspace_archived_updated",
            "workspace_id",
            "archived_at",
            "updated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), nullable=False)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="personal", nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    workspace = relationship("Workspace")
    owner = relationship("User")


class BentoAiJob(Base):
    __tablename__ = "bento_ai_jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('create', 'edit')", name="ck_bento_ai_jobs_kind"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_bento_ai_jobs_status",
        ),
        CheckConstraint(
            "visibility IN ('personal', 'workspace')",
            name="ck_bento_ai_jobs_visibility",
        ),
        Index(
            "ix_bento_ai_jobs_workspace_user_created",
            "workspace_id",
            "requested_by_id",
            "created_at",
        ),
        Index(
            "ix_bento_ai_jobs_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_bento_ai_jobs_active_target",
            "target_document_id",
            unique=True,
            postgresql_where=text(
                "target_document_id IS NOT NULL AND status IN ('queued', 'running')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(
        ForeignKey("ai_graph_runs.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="queued", server_default=text("'queued'"), nullable=False
    )
    runtime_adapter_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("bento_documents.id", ondelete="SET NULL"), nullable=True
    )
    result_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("bento_documents.id", ondelete="SET NULL"), nullable=True
    )
    base_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(20), default="personal", server_default=text("'personal'"), nullable=False
    )
    slide_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(
        String(16), default="auto", server_default=text("'auto'"), nullable=False
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class BentoAiJobInput(Base):
    __tablename__ = "bento_ai_job_inputs"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("bento_ai_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    current_document_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
