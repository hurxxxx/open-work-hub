from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ImageGeneration(Base):
    __tablename__ = "image_generations"
    __table_args__ = (
        Index("ix_image_generations_owner_created", "owner_id", "created_at"),
        Index(
            "ix_image_generations_workspace_owner_created",
            "workspace_id",
            "owner_id",
            "created_at",
        ),
        Index(
            "ix_image_generations_workspace_image_status",
            "workspace_id",
            "image_status",
        ),
        Index(
            "ix_image_generations_workspace_owner_template_created",
            "workspace_id",
            "owner_id",
            "is_template",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)

    template_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_case: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    use_case_other: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    style: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    layout: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    context_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reference_image_keys: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    brief_versions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    brief_status: Mapped[str] = mapped_column(
        String(24), default="drafting", index=True, nullable=False
    )
    image_status: Mapped[str] = mapped_column(
        String(24), default="idle", index=True, nullable=False
    )

    image_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    image_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    image_execution_profile: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    agent_trace_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    celery_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    workspace = relationship("Workspace")
    owner = relationship("User", foreign_keys=[owner_id])
