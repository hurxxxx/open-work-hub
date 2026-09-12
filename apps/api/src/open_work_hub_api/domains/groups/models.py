from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive

if TYPE_CHECKING:
    from open_work_hub_api.domains.auth.models import User


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("source", "source_reference", name="uq_groups_source_reference"),
        CheckConstraint("source IN ('hr', 'local')", name="ck_groups_source"),
        CheckConstraint("length(trim(name)) > 0", name="ck_groups_name"),
        CheckConstraint(
            "source != 'hr' OR (slug IS NOT NULL AND unit_type IS NOT NULL)",
            name="ck_groups_hr_metadata",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(24), default="local", nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    source_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    slug: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    unit_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    head_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_group_head_user"),
        nullable=True,
        index=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="primary_organization_unit",
        foreign_keys="User.primary_organization_unit_id",
    )

    @property
    def membership_mode(self) -> str:
        return "hr_assignment" if self.source == "hr" else "manual"


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
