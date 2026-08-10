"""add_dm_message_replies

Revision ID: a3b5c7d9e1f2
Revises: f2e3d4c5b6a7
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a3b5c7d9e1f2"
down_revision: str | Sequence[str] | None = "f2e3d4c5b6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "dm_messages",
        sa.Column("reply_to_message_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_dm_messages_reply_to_message_id"),
        "dm_messages",
        ["reply_to_message_id"],
    )
    op.create_foreign_key(
        op.f("fk_dm_messages_reply_to_message_id_dm_messages"),
        "dm_messages",
        "dm_messages",
        ["reply_to_message_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_dm_messages_reply_to_message_id_dm_messages"),
        "dm_messages",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_dm_messages_reply_to_message_id"), table_name="dm_messages")
    op.drop_column("dm_messages", "reply_to_message_id")
