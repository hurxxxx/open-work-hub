"""Remove the legacy notification-to-DM delivery channel.

Revision ID: e3b1c7d9a4f2
Revises: d6a9f4c2b8e1
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e3b1c7d9a4f2"
down_revision: str | Sequence[str] | None = "d6a9f4c2b8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_pms_notifications_global_origin",
        "pms_notifications",
        type_="check",
    )
    op.drop_index(
        "ix_pms_notifications_dm_thread_unread",
        table_name="pms_notifications",
    )
    op.drop_table("notification_dm_deliveries")
    op.execute("DELETE FROM pms_notifications WHERE type = 'dm_message'")
    op.execute(
        "DELETE FROM dm_conversations WHERE created_by_id = "
        "'open-work-hub-notification-bot'"
    )
    op.execute(
        "DELETE FROM users WHERE id = 'open-work-hub-notification-bot' "
        "AND NOT EXISTS (SELECT 1 FROM dm_messages WHERE sender_id = users.id) "
        "AND NOT EXISTS ("
        "SELECT 1 FROM dm_conversation_participants WHERE user_id = users.id"
        ")"
    )
    op.create_index(
        "ix_pms_notifications_user_source_unread",
        "pms_notifications",
        ["user_id", "origin_app_id", "source_type", "source_id"],
        postgresql_where=sa.text("is_read = false"),
    )
    op.create_check_constraint(
        "ck_pms_notifications_global_origin",
        "pms_notifications",
        "origin_app_id IS NOT NULL AND source_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_pms_notifications_global_origin",
        "pms_notifications",
        type_="check",
    )
    op.drop_index(
        "ix_pms_notifications_user_source_unread",
        table_name="pms_notifications",
    )
    op.create_check_constraint(
        "ck_pms_notifications_global_origin",
        "pms_notifications",
        "type = 'dm_message' OR (origin_app_id IS NOT NULL AND source_id IS NOT NULL)",
    )
    op.create_index(
        "ix_pms_notifications_dm_thread_unread",
        "pms_notifications",
        ["user_id", "source_type", "source_id"],
        postgresql_where=sa.text("is_read = false"),
    )
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
        sa.UniqueConstraint(
            "message_id",
            name="uq_notification_dm_deliveries_message",
        ),
    )
    op.create_index(
        "ix_notification_dm_deliveries_conversation",
        "notification_dm_deliveries",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_notification_dm_deliveries_conversation_id",
        "notification_dm_deliveries",
        ["conversation_id"],
    )
    op.create_index(
        "ix_notification_dm_deliveries_user",
        "notification_dm_deliveries",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_notification_dm_deliveries_user_conversation",
        "notification_dm_deliveries",
        ["user_id", "conversation_id", "notification_id"],
    )
    op.create_index(
        "ix_notification_dm_deliveries_user_id",
        "notification_dm_deliveries",
        ["user_id"],
    )
