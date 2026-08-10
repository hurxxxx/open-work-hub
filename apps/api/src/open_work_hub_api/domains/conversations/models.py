"""Chat conversations + turns persistence.

Conversations are **per-user within a workspace** (ChatGPT/Claude-style
private history), **auto-titled** from the first user message, and
**soft-deleted** via ``deleted_at`` — list endpoints filter rows where
``deleted_at IS NULL``. Turns are stored verbatim alongside the rendering
metadata the frontend ``ChatTurn`` relies on (reasoning, tool calls,
policy/pool decision, PII hits) so a reloaded conversation looks identical
to the live thread.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import utcnow_naive


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        # The "my recent chats" sidebar query is the hot path.
        Index(
            "ix_conversations_workspace_user_updated",
            "workspace_id",
            "user_id",
            "updated_at",
        ),
        Index(
            "ix_conversations_workspace_scope_resource",
            "workspace_id",
            "scope_ref",
            "scope_resource_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    scope_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    turns: Mapped[list["ConversationTurn"]] = relationship(
        "ConversationTurn",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationTurn.seq",
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    __table_args__ = (
        # Unique on (conversation_id, seq) so a concurrent append race can
        # never silently insert two turns with the same sequence number —
        # the second transaction takes an integrity error and retries.
        UniqueConstraint("conversation_id", "seq", name="uq_conversation_turns_conversation_seq"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user|assistant
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Optional rendering metadata (reasoning text, tool calls, policy/pool
    # decision, PII hits). Schema mirrors the frontend ChatTurn shape so a
    # reloaded turn renders the same as a live-streamed one.
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    conversation = relationship("Conversation", back_populates="turns")
