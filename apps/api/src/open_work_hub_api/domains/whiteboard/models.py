from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def empty_scene() -> dict[str, Any]:
    return {"elements": [], "appState": {}, "files": {}}


class Whiteboard(Base):
    __tablename__ = "whiteboards"
    __table_args__ = (
        CheckConstraint(
            "ownership_kind IN ('personal', 'company')", name="ck_whiteboard_ownership"
        ),
        Index("ix_whiteboards_owner_created", "owner_id", "created_at"),
        Index("ix_whiteboards_updated", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_visible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ownership_kind: Mapped[str] = mapped_column(
        String(16), default="personal", nullable=False, index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source_app: Mapped[str] = mapped_column(
        String(64), default="whiteboard", nullable=False, index=True
    )
    source_kind: Mapped[str] = mapped_column(
        String(64), default="manual", nullable=False, index=True
    )
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    generation_kind: Mapped[str] = mapped_column(
        String(32), default="human", nullable=False, index=True
    )
    scene: Mapped[dict[str, Any]] = mapped_column(JSON, default=empty_scene, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    owner = relationship("User")
    targets: Mapped[list["WhiteboardTarget"]] = relationship(
        back_populates="whiteboard",
        cascade="all, delete-orphan",
    )
    user_shares: Mapped[list["WhiteboardUserShare"]] = relationship(
        back_populates="whiteboard",
        cascade="all, delete-orphan",
    )
    link_shares: Mapped[list["WhiteboardLinkShare"]] = relationship(
        back_populates="whiteboard",
        cascade="all, delete-orphan",
    )


class WhiteboardTarget(Base):
    __tablename__ = "whiteboard_targets"
    __table_args__ = (
        Index(
            "ix_whiteboard_targets_target_lookup",
            "target_app",
            "target_type",
            "target_id",
        ),
        Index(
            "uq_whiteboard_targets_primary",
            "whiteboard_id",
            unique=True,
            postgresql_where=text("is_primary IS TRUE"),
            sqlite_where=text("is_primary IS TRUE"),
        ),
        UniqueConstraint(
            "whiteboard_id",
            "target_app",
            "target_type",
            "target_id",
            name="uq_whiteboard_targets_board_target",
        ),
        Index(
            "uq_whiteboard_targets_meeting_target_slot",
            "target_app",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("target_app = 'meeting' AND target_type = 'meeting'"),
            sqlite_where=text("target_app = 'meeting' AND target_type = 'meeting'"),
        ),
        Index(
            "uq_whiteboard_targets_pms_task_list_target_slot",
            "target_app",
            "target_type",
            "target_id",
            unique=True,
            postgresql_where=text("target_app = 'pms' AND target_type = 'task_list'"),
            sqlite_where=text("target_app = 'pms' AND target_type = 'task_list'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    whiteboard_id: Mapped[str] = mapped_column(ForeignKey("whiteboards.id"), index=True)
    target_app: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    whiteboard: Mapped[Whiteboard] = relationship(back_populates="targets")
    created_by = relationship("User")


class WhiteboardUserShare(Base):
    __tablename__ = "whiteboard_user_shares"
    __table_args__ = (
        UniqueConstraint("whiteboard_id", "user_id", name="uq_whiteboard_user_share"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    whiteboard_id: Mapped[str] = mapped_column(ForeignKey("whiteboards.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    access_level: Mapped[str] = mapped_column(String(16), default="read", nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    whiteboard: Mapped[Whiteboard] = relationship(back_populates="user_shares")
    user = relationship("User", foreign_keys=[user_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


class WhiteboardLinkShare(Base):
    __tablename__ = "whiteboard_link_shares"
    __table_args__ = (UniqueConstraint("whiteboard_id", name="uq_whiteboard_link_share_board"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    whiteboard_id: Mapped[str] = mapped_column(ForeignKey("whiteboards.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    access_level: Mapped[str] = mapped_column(String(16), default="read", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    whiteboard: Mapped[Whiteboard] = relationship(back_populates="link_shares")
    created_by = relationship("User")


class WhiteboardCollabDocument(Base):
    __tablename__ = "whiteboard_collab_documents"
    __table_args__ = (
        UniqueConstraint("room_key", name="uq_whiteboard_collab_documents_room_key"),
        UniqueConstraint("whiteboard_id", name="uq_whiteboard_collab_documents_board"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_key: Mapped[str] = mapped_column(String(128), nullable=False)
    whiteboard_id: Mapped[str] = mapped_column(ForeignKey("whiteboards.id"), index=True)
    yjs_state: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    snapshot_scene: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    whiteboard = relationship("Whiteboard")


class WhiteboardUserItemPref(Base):
    __tablename__ = "whiteboard_user_item_prefs"
    __table_args__ = (
        UniqueConstraint("user_id", "whiteboard_id", name="uq_whiteboard_user_item_pref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    whiteboard_id: Mapped[str] = mapped_column(ForeignKey("whiteboards.id"), index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user = relationship("User")
    whiteboard = relationship("Whiteboard")


class WhiteboardGroupShare(Base):
    __tablename__ = "whiteboard_group_shares"
    __table_args__ = (
        CheckConstraint(
            "access_level IN ('read', 'edit')", name="ck_whiteboard_group_share_access"
        ),
    )
    whiteboard_id: Mapped[str] = mapped_column(
        ForeignKey("whiteboards.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    access_level: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
