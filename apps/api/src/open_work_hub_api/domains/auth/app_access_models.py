from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from open_work_hub_api.core.db import Base


class AppAccessPolicy(Base):
    __tablename__ = "app_access_policies"
    __table_args__ = (
        CheckConstraint("audience IN ('all', 'selected')", name="ck_app_access_audience"),
    )

    app_id: Mapped[str] = mapped_column(
        ForeignKey("company_app_controls.app_id", ondelete="CASCADE"), primary_key=True
    )
    audience: Mapped[str] = mapped_column(String(16), default="selected", nullable=False)


class AppUserGrant(Base):
    __tablename__ = "app_user_grants"

    app_id: Mapped[str] = mapped_column(
        ForeignKey("app_access_policies.app_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class AppGroupGrant(Base):
    __tablename__ = "app_group_grants"

    app_id: Mapped[str] = mapped_column(
        ForeignKey("app_access_policies.app_id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True
    )
