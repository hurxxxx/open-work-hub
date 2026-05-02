from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aidoo_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def empty_scene() -> dict[str, Any]:
    return {"elements": [], "appState": {}, "files": {}}


class Whiteboard(Base):
    __tablename__ = "whiteboards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    source_app: Mapped[str] = mapped_column(String(64), default="whiteboard", nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(64), default="manual", nullable=False, index=True)
    source_ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    generation_kind: Mapped[str] = mapped_column(String(32), default="human", nullable=False, index=True)
    scene: Mapped[dict[str, Any]] = mapped_column(JSON, default=empty_scene, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    workspace = relationship("Workspace")
    owner = relationship("User")
    containers: Mapped[list["WhiteboardContainer"]] = relationship(
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


class WhiteboardContainer(Base):
    __tablename__ = "whiteboard_containers"
    __table_args__ = (
        Index(
            "ix_whiteboard_containers_lookup",
            "container_app",
            "container_type",
            "container_id",
        ),
        Index(
            "uq_whiteboard_containers_primary",
            "whiteboard_id",
            unique=True,
            postgresql_where=text("is_primary IS TRUE"),
            sqlite_where=text("is_primary IS TRUE"),
        ),
        UniqueConstraint(
            "whiteboard_id",
            "container_app",
            "container_type",
            "container_id",
            name="uq_whiteboard_containers_board_container",
        ),
        Index(
            "uq_whiteboard_containers_meeting_slot",
            "container_app",
            "container_type",
            "container_id",
            unique=True,
            postgresql_where=text("container_app = 'meeting' AND container_type = 'meeting'"),
            sqlite_where=text("container_app = 'meeting' AND container_type = 'meeting'"),
        ),
        Index(
            "uq_whiteboard_containers_pms_task_list_slot",
            "container_app",
            "container_type",
            "container_id",
            unique=True,
            postgresql_where=text("container_app = 'pms' AND container_type = 'task_list'"),
            sqlite_where=text("container_app = 'pms' AND container_type = 'task_list'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    whiteboard_id: Mapped[str] = mapped_column(ForeignKey("whiteboards.id"), index=True)
    container_app: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    container_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    container_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    whiteboard: Mapped[Whiteboard] = relationship(back_populates="containers")
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
    __table_args__ = (
        UniqueConstraint("whiteboard_id", name="uq_whiteboard_link_share_board"),
    )

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
