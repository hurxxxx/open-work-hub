from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User, utcnow_naive


class Team(Base):
    __tablename__ = "pms_spaces"
    __table_args__ = (UniqueConstraint("key", name="uq_pms_space_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(48), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    members: Mapped[list["TeamMember"]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
    )


class TeamMember(Base):
    __tablename__ = "pms_space_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_pms_space_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("pms_spaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="member", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship("User")


class SpaceGroupBinding(Base):
    __tablename__ = "pms_space_group_bindings"
    __table_args__ = (
        CheckConstraint("role IN ('viewer', 'member', 'admin')", name="ck_pms_space_group_role"),
    )

    team_id: Mapped[str] = mapped_column(
        ForeignKey("pms_spaces.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
