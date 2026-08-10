"""modernize_dm_conversations

Revision ID: b6c8d9e0f123
Revises: a4d7c8e9f012
Create Date: 2026-05-19 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b6c8d9e0f123"
down_revision: str | Sequence[str] | None = "a4d7c8e9f012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("dm_conversations"):
        return
    if not inspector.has_table("dm_threads"):
        return

    op.rename_table("dm_threads", "dm_conversations")
    if inspector.has_table("dm_thread_participants"):
        op.rename_table("dm_thread_participants", "dm_conversation_participants")

    inspector = sa.inspect(bind)
    conversation_columns = {column["name"] for column in inspector.get_columns("dm_conversations")}
    participant_columns = {
        column["name"] for column in inspector.get_columns("dm_conversation_participants")
    }
    message_columns = {column["name"] for column in inspector.get_columns("dm_messages")}

    if "participant_key" in conversation_columns:
        op.alter_column(
            "dm_conversations",
            "participant_key",
            new_column_name="direct_key",
            existing_type=sa.String(length=96),
            existing_nullable=True,
        )
        op.alter_column(
            "dm_conversations",
            "direct_key",
            existing_type=sa.String(length=96),
            nullable=True,
        )
    if "thread_type" in conversation_columns:
        op.alter_column(
            "dm_conversations",
            "thread_type",
            new_column_name="conversation_type",
            existing_type=sa.String(length=16),
            existing_nullable=False,
        )
    elif "conversation_type" not in conversation_columns:
        op.add_column(
            "dm_conversations",
            sa.Column("conversation_type", sa.String(length=16), nullable=False, server_default="direct"),
        )
        op.alter_column("dm_conversations", "conversation_type", server_default=None)
    if "title" not in conversation_columns:
        op.add_column("dm_conversations", sa.Column("title", sa.String(length=140), nullable=True))
    if "message_seq" not in conversation_columns:
        op.add_column(
            "dm_conversations",
            sa.Column("message_seq", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("dm_conversations", "message_seq", server_default=None)
    if "created_by_id" not in conversation_columns:
        op.add_column("dm_conversations", sa.Column("created_by_id", sa.String(length=36), nullable=True))

    if "thread_id" in participant_columns:
        op.alter_column(
            "dm_conversation_participants",
            "thread_id",
            new_column_name="conversation_id",
            existing_type=sa.String(length=36),
            existing_nullable=False,
        )
    if "role" not in participant_columns:
        op.add_column(
            "dm_conversation_participants",
            sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
        )
        op.alter_column("dm_conversation_participants", "role", server_default=None)
    if "joined_at" not in participant_columns:
        op.add_column("dm_conversation_participants", sa.Column("joined_at", sa.DateTime(), nullable=True))
        bind.execute(sa.text("UPDATE dm_conversation_participants SET joined_at = created_at"))
        op.alter_column("dm_conversation_participants", "joined_at", nullable=False)
    if "left_at" not in participant_columns:
        op.add_column("dm_conversation_participants", sa.Column("left_at", sa.DateTime(), nullable=True))
    if "muted_at" not in participant_columns:
        op.add_column("dm_conversation_participants", sa.Column("muted_at", sa.DateTime(), nullable=True))
    if "last_read_message_id" not in participant_columns:
        op.add_column(
            "dm_conversation_participants",
            sa.Column("last_read_message_id", sa.String(length=36), nullable=True),
        )

    if "thread_id" in message_columns:
        op.alter_column(
            "dm_messages",
            "thread_id",
            new_column_name="conversation_id",
            existing_type=sa.String(length=36),
            existing_nullable=False,
        )
    if "sequence" not in message_columns:
        op.add_column("dm_messages", sa.Column("sequence", sa.Integer(), nullable=True))
        bind.execute(
            sa.text(
                """
                WITH ranked AS (
                    SELECT id,
                           row_number() OVER (
                               PARTITION BY conversation_id
                               ORDER BY created_at, id
                           ) AS seq
                    FROM dm_messages
                )
                UPDATE dm_messages
                SET sequence = ranked.seq
                FROM ranked
                WHERE dm_messages.id = ranked.id
                """
            )
        )
        op.alter_column("dm_messages", "sequence", nullable=False)

    bind.execute(
        sa.text(
            """
            UPDATE dm_conversations AS conversation
            SET message_seq = COALESCE(message_counts.max_sequence, 0)
            FROM (
                SELECT conversation_id, max(sequence) AS max_sequence
                FROM dm_messages
                GROUP BY conversation_id
            ) AS message_counts
            WHERE conversation.id = message_counts.conversation_id
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE dm_conversations AS conversation
            SET created_by_id = first_participant.user_id
            FROM (
                SELECT DISTINCT ON (conversation_id) conversation_id, user_id
                FROM dm_conversation_participants
                ORDER BY conversation_id, created_at, id
            ) AS first_participant
            WHERE conversation.id = first_participant.conversation_id
              AND conversation.created_by_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE dm_conversation_participants AS participant
            SET last_read_message_id = (
                SELECT id
                FROM dm_messages
                WHERE conversation_id = participant.conversation_id
                  AND created_at <= participant.last_read_at
                ORDER BY sequence DESC
                LIMIT 1
            )
            WHERE participant.last_read_at IS NOT NULL
              AND participant.last_read_message_id IS NULL
            """
        )
    )

    if "last_read_at" in participant_columns:
        op.drop_column("dm_conversation_participants", "last_read_at")
    op.alter_column("dm_conversations", "created_by_id", nullable=False)


def downgrade() -> None:
    # This migration is a compatibility bridge for pre-release DM tables. The
    # canonical schema is already created by the previous migration on fresh DBs.
    return
