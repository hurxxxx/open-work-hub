from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aidoo_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class NativeDoc(Base):
    __tablename__ = "docs_native_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
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
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    workspace = relationship("Workspace")
    owner = relationship("User")
    pages: Mapped[list["NativeDocPage"]] = relationship(
        back_populates="doc",
        cascade="all, delete-orphan",
    )
    user_shares: Mapped[list["NativeDocUserShare"]] = relationship(
        back_populates="doc",
        cascade="all, delete-orphan",
    )
    link_shares: Mapped[list["NativeDocLinkShare"]] = relationship(
        back_populates="doc",
        cascade="all, delete-orphan",
    )
    meeting_access_grants: Mapped[list["DocMeetingAccess"]] = relationship(
        back_populates="doc",
        cascade="all, delete-orphan",
    )


class NativeDocPage(Base):
    __tablename__ = "docs_native_doc_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("docs_native_docs.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs_native_doc_pages.id"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    content_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
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
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by = relationship("User")
    doc: Mapped["NativeDoc"] = relationship(back_populates="pages")
    parent: Mapped["NativeDocPage | None"] = relationship(
        remote_side="NativeDocPage.id",
        back_populates="children",
    )
    children: Mapped[list["NativeDocPage"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )


class NativeDocUserShare(Base):
    __tablename__ = "docs_native_doc_user_shares"
    __table_args__ = (
        UniqueConstraint("doc_id", "user_id", name="uq_docs_native_doc_user_share"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("docs_native_docs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    access_level: Mapped[str] = mapped_column(String(16), default="read")
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    doc: Mapped[NativeDoc] = relationship(back_populates="user_shares")
    user = relationship("User", foreign_keys=[user_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


class NativeDocLinkShare(Base):
    __tablename__ = "docs_native_doc_link_shares"
    __table_args__ = (
        UniqueConstraint("doc_id", name="uq_docs_native_doc_link_share_doc"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("docs_native_docs.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    access_level: Mapped[str] = mapped_column(String(16), default="read")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
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
    doc: Mapped[NativeDoc] = relationship(back_populates="link_shares")
    created_by = relationship("User")


class DocMeetingAccess(Base):
    __tablename__ = "docs_meeting_access"
    __table_args__ = (
        Index("ix_docs_meeting_access_user_revoked", "user_id", "revoked_at"),
        Index(
            "ix_docs_meeting_access_meeting_revoked",
            "granted_by_meeting_id",
            "revoked_at",
        ),
        Index(
            "ix_docs_meeting_access_expires_active",
            "expires_at",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_docs_meeting_access_active",
            "doc_id",
            "user_id",
            "granted_by_meeting_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("docs_native_docs.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    access_level: Mapped[str] = mapped_column(String(16), default="read")
    granted_by_meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id"),
        nullable=True,
        index=True,
    )
    granted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reason: Mapped[str] = mapped_column(String(24), default="meeting_attendee")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    revoke_reason: Mapped[str | None] = mapped_column(String(24), nullable=True)
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

    doc: Mapped[NativeDoc] = relationship(back_populates="meeting_access_grants")
    user = relationship("User", foreign_keys=[user_id])
    granted_by_user = relationship("User", foreign_keys=[granted_by_user_id])
    revoked_by_user = relationship("User", foreign_keys=[revoked_by_user_id])


class DocsUserItemPref(Base):
    __tablename__ = "docs_user_item_prefs"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_doc_id", name="uq_docs_user_item_pref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_doc_id: Mapped[str] = mapped_column(String(36), index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_viewed_page_source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    last_viewed_page_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    user = relationship("User")


class DocsCollabDocument(Base):
    __tablename__ = "docs_collab_documents"
    __table_args__ = (
        UniqueConstraint("room_key", name="uq_docs_collab_documents_room_key"),
        UniqueConstraint(
            "source_type",
            "source_page_id",
            name="uq_docs_collab_documents_source_page",
        ),
        Index(
            "ix_docs_collab_documents_source_page",
            "source_type",
            "source_page_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_page_id: Mapped[str] = mapped_column(String(36), nullable=False)
    yjs_state: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    snapshot_content_blocks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    last_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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
