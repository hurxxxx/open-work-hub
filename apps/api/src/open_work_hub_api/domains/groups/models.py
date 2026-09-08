from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'organization' AND organization_unit_id IS NOT NULL) OR "
            "(kind = 'manual' AND organization_unit_id IS NULL AND length(trim(name)) > 0)",
            name="ck_groups_origin",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    organization_unit_id: Mapped[str | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="CASCADE"), unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
