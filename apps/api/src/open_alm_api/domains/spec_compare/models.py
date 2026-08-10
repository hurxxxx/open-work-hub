from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class SpecCompareJob(Base):
    __tablename__ = "spec_compare_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_spec_compare_jobs_status",
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_spec_compare_jobs_progress",
        ),
        Index(
            "ix_spec_compare_jobs_workspace_owner_created",
            "workspace_id",
            "owner_id",
            "created_at",
        ),
        Index(
            "ix_spec_compare_jobs_workspace_status_created",
            "workspace_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default="queued", server_default=text("'queued'"), index=True, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    status_message: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    base_file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    base_mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    base_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    base_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)

    target_file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    target_mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    target_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)

    result_json_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    report_markdown_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONB_COMPAT, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    workspace = relationship("Workspace")
    owner = relationship("User", foreign_keys=[owner_id])
    spec_items = relationship(
        "SpecCompareSpecItem",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SpecCompareSpecItem(Base):
    __tablename__ = "spec_compare_spec_items"
    __table_args__ = (
        CheckConstraint(
            "document_role IN ('base','target')",
            name="ck_spec_compare_spec_items_document_role",
        ),
        UniqueConstraint(
            "job_id",
            "document_role",
            "item_id",
            name="uq_spec_compare_spec_items_job_role_item",
        ),
        Index(
            "ix_spec_compare_spec_items_job_role",
            "job_id",
            "document_role",
        ),
        Index(
            "ix_spec_compare_spec_items_normalized_key",
            "normalized_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(140), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("spec_compare_jobs.id", ondelete="CASCADE"), nullable=False
    )
    document_role: Mapped[str] = mapped_column(String(16), nullable=False)
    item_id: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    item_name: Mapped[str] = mapped_column(String(300), nullable=False)
    value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    unit: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    condition: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(160), nullable=False)
    locator_label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    section_path: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    source_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
