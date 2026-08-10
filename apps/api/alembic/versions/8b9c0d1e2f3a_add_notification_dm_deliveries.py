"""add_notification_dm_deliveries

Revision ID: 8b9c0d1e2f3a
Revises: 7a8b9c0d1e2f
Create Date: 2026-06-15 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b9c0d1e2f3a"
down_revision: Union[str, Sequence[str], None] = "7a8b9c0d1e2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_dm_deliveries",
        sa.Column("notification_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["dm_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["dm_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["pms_notifications.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("notification_id"),
        sa.UniqueConstraint("message_id", name="uq_notification_dm_deliveries_message"),
    )
    op.create_index(
        "ix_notification_dm_deliveries_conversation",
        "notification_dm_deliveries",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_notification_dm_deliveries_user",
        "notification_dm_deliveries",
        ["user_id", "created_at"],
    )
    op.create_index(
        op.f("ix_notification_dm_deliveries_conversation_id"),
        "notification_dm_deliveries",
        ["conversation_id"],
    )
    op.create_index(
        op.f("ix_notification_dm_deliveries_user_id"),
        "notification_dm_deliveries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_dm_deliveries_user_id"), table_name="notification_dm_deliveries")
    op.drop_index(
        op.f("ix_notification_dm_deliveries_conversation_id"),
        table_name="notification_dm_deliveries",
    )
    op.drop_index("ix_notification_dm_deliveries_user", table_name="notification_dm_deliveries")
    op.drop_index(
        "ix_notification_dm_deliveries_conversation",
        table_name="notification_dm_deliveries",
    )
    op.drop_table("notification_dm_deliveries")
