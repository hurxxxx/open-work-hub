from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
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
