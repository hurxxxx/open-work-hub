from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
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
        ),
        UniqueConstraint(
            "whiteboard_id",
            "container_app",
            "container_type",
            "container_id",
            name="uq_whiteboard_containers_board_container",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    whiteboard_id: Mapped[str] = mapped_column(ForeignKey("whiteboards.id"), index=True)
    container_app: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    container_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    container_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    whiteboard: Mapped[Whiteboard] = relationship(back_populates="containers")


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

