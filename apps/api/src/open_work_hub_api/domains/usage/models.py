from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_dedupe_key", "dedupe_key"),
        Index("ix_usage_events_user_occurred", "actor_user_id", "occurred_at"),
        Index("ix_usage_events_app_occurred", "app_id", "occurred_at"),
        Index("ix_usage_events_type_occurred", "event_type", "occurred_at"),
        Index("ix_usage_events_content_kind_occurred", "content_kind", "occurred_at"),
        Index("ix_usage_events_route_occurred", "route_path", "occurred_at"),
        Index("ix_usage_events_occurred", "occurred_at"),
        Index(
            "ix_usage_events_type_kind_occurred_user",
            "event_type",
            "content_kind",
            "occurred_at",
            "actor_user_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_kind: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    content_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    route_path: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False, index=True
    )
    last_occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class UsageExcludedUser(Base):
    __tablename__ = "usage_excluded_users"
    __table_args__ = (
        Index("ix_usage_excluded_users_created_at", "created_at"),
        Index("ix_usage_excluded_users_created_by", "created_by_user_id"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class UsageTargetUser(Base):
    __tablename__ = "usage_target_users"
    __table_args__ = (
        Index("ix_usage_target_users_created_at", "created_at"),
        Index("ix_usage_target_users_created_by", "created_by_user_id"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
