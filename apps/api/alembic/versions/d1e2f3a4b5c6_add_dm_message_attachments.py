"""add_dm_message_attachments

Revision ID: d1e2f3a4b5c6
Revises: c7d8e9f0a123
Create Date: 2026-05-20 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: str | Sequence[str] | None = "c7d8e9f0a123"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dm_message_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("uploader_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=160),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["dm_conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["dm_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.alter_column("dm_message_attachments", "content_type", server_default=None)
    op.alter_column("dm_message_attachments", "size_bytes", server_default=None)
    op.create_index(
        "ix_dm_message_attachments_conversation",
        "dm_message_attachments",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_dm_message_attachments_message",
        "dm_message_attachments",
        ["message_id"],
    )
    op.create_index(
        "ix_dm_message_attachments_uploader",
        "dm_message_attachments",
        ["uploader_id", "created_at"],
    )
    op.create_index(
        op.f("ix_dm_message_attachments_conversation_id"),
        "dm_message_attachments",
        ["conversation_id"],
    )
    op.create_index(
        op.f("ix_dm_message_attachments_message_id"),
        "dm_message_attachments",
        ["message_id"],
    )
    op.create_index(
        op.f("ix_dm_message_attachments_uploader_id"),
        "dm_message_attachments",
        ["uploader_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dm_message_attachments_uploader_id"), table_name="dm_message_attachments")
    op.drop_index(op.f("ix_dm_message_attachments_message_id"), table_name="dm_message_attachments")
    op.drop_index(op.f("ix_dm_message_attachments_conversation_id"), table_name="dm_message_attachments")
    op.drop_index("ix_dm_message_attachments_uploader", table_name="dm_message_attachments")
    op.drop_index("ix_dm_message_attachments_message", table_name="dm_message_attachments")
    op.drop_index("ix_dm_message_attachments_conversation", table_name="dm_message_attachments")
    op.drop_table("dm_message_attachments")
