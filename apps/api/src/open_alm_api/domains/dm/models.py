from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive


class DmConversation(Base):
    __tablename__ = "dm_conversations"
    __table_args__ = (
        UniqueConstraint("direct_key", name="uq_dm_conversations_direct_key"),
        Index("ix_dm_conversations_type", "conversation_type"),
        Index("ix_dm_conversations_updated_at", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    direct_key: Mapped[str | None] = mapped_column(String(96), nullable=True)
    title: Mapped[str | None] = mapped_column(String(140), nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    message_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    participants: Mapped[list["DmConversationParticipant"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="DmConversationParticipant.conversation_id",
    )
    messages: Mapped[list["DmMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="DmMessage.sequence",
    )


class DmConversationParticipant(Base):
    __tablename__ = "dm_conversation_participants"
    __table_args__ = (
        Index(
            "uq_dm_conversation_participants_active_user",
            "conversation_id",
            "user_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
        ),
        Index(
            "ix_dm_conversation_participants_user_active",
            "user_id",
            "left_at",
            "conversation_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("dm_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), default="member", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    muted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_read_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("dm_messages.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    conversation: Mapped[DmConversation] = relationship(
        back_populates="participants",
        foreign_keys=[conversation_id],
    )
    user = relationship("User")
    last_read_message = relationship("DmMessage", foreign_keys=[last_read_message_id])


class DmMessage(Base):
    __tablename__ = "dm_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "sequence", name="uq_dm_messages_conversation_sequence"
        ),
        Index("ix_dm_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_dm_messages_conversation_sequence", "conversation_id", "sequence"),
        Index(
            "ix_dm_messages_conversation_created_sequence",
            "conversation_id",
            "created_at",
            "sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("dm_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    reply_to_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("dm_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    conversation: Mapped[DmConversation] = relationship(back_populates="messages")
    sender = relationship("User")
    reply_to: Mapped["DmMessage | None"] = relationship(
        "DmMessage",
        remote_side=[id],
        foreign_keys=[reply_to_message_id],
    )
    attachments: Mapped[list["DmMessageAttachment"]] = relationship(
        back_populates="message",
        order_by="DmMessageAttachment.created_at",
    )


class DmMessageAttachment(Base):
    __tablename__ = "dm_message_attachments"
    __table_args__ = (
        Index("ix_dm_message_attachments_conversation", "conversation_id", "created_at"),
        Index("ix_dm_message_attachments_message", "message_id"),
        Index("ix_dm_message_attachments_uploader", "uploader_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("dm_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("dm_messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    uploader_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(160),
        default="application/octet-stream",
        nullable=False,
    )
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    conversation: Mapped[DmConversation] = relationship()
    message: Mapped[DmMessage | None] = relationship(back_populates="attachments")
    uploader = relationship("User")
