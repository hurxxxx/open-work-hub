from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive

if TYPE_CHECKING:
    from open_work_hub_api.domains.auth.models import User


class OrganizationUnit(Base):
    __tablename__ = "organization_units"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_organization_units_name",
        ),
        CheckConstraint(
            "length(trim(unit_type)) > 0",
            name="ck_organization_units_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    unit_type: Mapped[str] = mapped_column(
        String(40),
        default="department",
        nullable=False,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("organization_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    head_user_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "users.id", ondelete="SET NULL", use_alter=True, name="fk_organization_unit_head_user"
        ),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    parent: Mapped["OrganizationUnit | None"] = relationship(
        remote_side="OrganizationUnit.id",
        back_populates="children",
    )
    children: Mapped[list["OrganizationUnit"]] = relationship(back_populates="parent")
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="primary_organization_unit",
        foreign_keys="User.primary_organization_unit_id",
    )
