from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Diagram(Base):
    __tablename__ = "diagrams"
    __table_args__ = (
        CheckConstraint(
            "visibility in ('personal', 'workspace')",
            name="ck_diagrams_visibility",
        ),
        UniqueConstraint("source_storage_key", name="uq_diagrams_source_storage_key"),
        UniqueConstraint("preview_storage_key", name="uq_diagrams_preview_storage_key"),
        Index("ix_diagrams_workspace_id", "workspace_id"),
        Index("ix_diagrams_owner_id", "owner_id"),
        Index("ix_diagrams_archived_at", "archived_at"),
        Index("ix_diagrams_updated_at", "updated_at"),
        Index("ix_diagrams_visibility", "visibility"),
        Index(
            "ix_diagrams_workspace_archived_updated",
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
    source_storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    preview_storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
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
