from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_do_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        Index(
            "ix_announcements_workspace_pinned_created",
            "workspace_id",
            "is_pinned",
            "created_at",
        ),
        Index(
            "ix_announcements_scope_pinned_created",
            "scope",
            "is_pinned",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    # "workspace": visible only within the owning workspace.
    # "company": company-wide notice, visible across all workspaces.
    scope: Mapped[str] = mapped_column(
        String(24), default="workspace", index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    author = relationship("User")
