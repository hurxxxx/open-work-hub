from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CommunityChannel(Base):
    __tablename__ = "community_channels"
    __table_args__ = (
        Index("ix_community_channels_position", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    read_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    force_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_only_content: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    template_title: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    template_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    posts: Mapped[list["CommunityPost"]] = relationship(back_populates="channel")


class CommunityPost(Base):
    __tablename__ = "community_posts"
    __table_args__ = (
        Index(
            "ix_community_posts_channel_created",
            "channel_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("community_channels.id"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    author = relationship("User")
    channel: Mapped[CommunityChannel] = relationship(back_populates="posts")
    comments: Mapped[list["CommunityComment"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )
    reads: Mapped[list["CommunityPostRead"]] = relationship(
        back_populates="post",
        cascade="all, delete-orphan",
    )


class CommunityPostRead(Base):
    __tablename__ = "community_post_reads"
    __table_args__ = (Index("ix_community_post_reads_user_id", "user_id"),)

    post_id: Mapped[str] = mapped_column(
        ForeignKey("community_posts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )

    post: Mapped[CommunityPost] = relationship(back_populates="reads")


class CommunityComment(Base):
    __tablename__ = "community_comments"
    __table_args__ = (
        Index("ix_community_comments_post_created", "post_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    post_id: Mapped[str] = mapped_column(
        ForeignKey("community_posts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    parent_comment_id: Mapped[str | None] = mapped_column(
        ForeignKey("community_comments.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )

    author = relationship("User")
    post: Mapped[CommunityPost] = relationship(back_populates="comments")
    parent = relationship("CommunityComment", remote_side="CommunityComment.id")
