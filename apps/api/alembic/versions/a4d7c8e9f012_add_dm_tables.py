"""add_dm_tables

Revision ID: a4d7c8e9f012
Revises: 9e1f2a3b4c5d
Create Date: 2026-05-19 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a4d7c8e9f012"
down_revision: str | Sequence[str] | None = "9e1f2a3b4c5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dm_conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_type", sa.String(length=16), nullable=False),
        sa.Column("direct_key", sa.String(length=96), nullable=True),
        sa.Column("title", sa.String(length=140), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("message_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("direct_key", name="uq_dm_conversations_direct_key"),
    )
    op.create_index(op.f("ix_dm_conversations_created_by_id"), "dm_conversations", ["created_by_id"])
    op.create_index("ix_dm_conversations_type", "dm_conversations", ["conversation_type"])
    op.create_index("ix_dm_conversations_updated_at", "dm_conversations", ["updated_at"])

    op.create_table(
        "dm_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("sender_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["dm_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_dm_messages_conversation_sequence"),
    )
    op.create_index("ix_dm_messages_conversation_created", "dm_messages", ["conversation_id", "created_at"])
    op.create_index("ix_dm_messages_conversation_sequence", "dm_messages", ["conversation_id", "sequence"])
    op.create_index(op.f("ix_dm_messages_conversation_id"), "dm_messages", ["conversation_id"])
    op.create_index(op.f("ix_dm_messages_sender_id"), "dm_messages", ["sender_id"])

    op.create_table(
        "dm_conversation_participants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("left_at", sa.DateTime(), nullable=True),
        sa.Column("muted_at", sa.DateTime(), nullable=True),
        sa.Column("last_read_message_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["dm_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_read_message_id"], ["dm_messages.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dm_conversation_participants_user_active",
        "dm_conversation_participants",
        ["user_id", "left_at", "conversation_id"],
    )
    op.create_index(
        "uq_dm_conversation_participants_active_user",
        "dm_conversation_participants",
        ["conversation_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )
    op.create_index(
        op.f("ix_dm_conversation_participants_conversation_id"),
        "dm_conversation_participants",
        ["conversation_id"],
    )
    op.create_index(
        op.f("ix_dm_conversation_participants_left_at"),
        "dm_conversation_participants",
        ["left_at"],
    )
    op.create_index(
        op.f("ix_dm_conversation_participants_user_id"),
        "dm_conversation_participants",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dm_conversation_participants_user_id"), table_name="dm_conversation_participants")
    op.drop_index(op.f("ix_dm_conversation_participants_left_at"), table_name="dm_conversation_participants")
    op.drop_index(op.f("ix_dm_conversation_participants_conversation_id"), table_name="dm_conversation_participants")
    op.drop_index("uq_dm_conversation_participants_active_user", table_name="dm_conversation_participants")
    op.drop_index("ix_dm_conversation_participants_user_active", table_name="dm_conversation_participants")
    op.drop_table("dm_conversation_participants")

    op.drop_index(op.f("ix_dm_messages_sender_id"), table_name="dm_messages")
    op.drop_index(op.f("ix_dm_messages_conversation_id"), table_name="dm_messages")
    op.drop_index("ix_dm_messages_conversation_sequence", table_name="dm_messages")
    op.drop_index("ix_dm_messages_conversation_created", table_name="dm_messages")
    op.drop_table("dm_messages")

    op.drop_index("ix_dm_conversations_updated_at", table_name="dm_conversations")
    op.drop_index("ix_dm_conversations_type", table_name="dm_conversations")
    op.drop_index(op.f("ix_dm_conversations_created_by_id"), table_name="dm_conversations")
    op.drop_table("dm_conversations")
