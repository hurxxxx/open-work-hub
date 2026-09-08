from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PlannerEvent(Base):
    __tablename__ = "planner_events"
    __table_args__ = (
        Index(
            "ix_planner_events_owner_start",
            "owner_id",
            "start_at",
        ),
        Index(
            "ix_planner_events_owner_end",
            "owner_id",
            "end_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    retrieval_partition_id: Mapped[str | None] = mapped_column(
        ForeignKey("retrieval_partitions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    legacy_visibility: Mapped[str] = mapped_column(
        "visibility",
        String(24),
        default="private",
        server_default=text("'private'"),
        index=True,
        nullable=False,
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    time_zone: Mapped[str] = mapped_column(
        String(64),
        default="Asia/Seoul",
        server_default=text("'Asia/Seoul'"),
        nullable=False,
    )
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    start_has_time: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    end_has_time: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    owner = relationship("User")
