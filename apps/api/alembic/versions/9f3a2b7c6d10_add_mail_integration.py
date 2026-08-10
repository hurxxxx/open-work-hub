"""add_mail_integration

Revision ID: 9f3a2b7c6d10
Revises: 8a7c6e5d4b3f
Create Date: 2026-05-12 18:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9f3a2b7c6d10"
down_revision: str | Sequence[str] | None = "8a7c6e5d4b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mail_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("protocol", sa.String(length=16), nullable=False),
        sa.Column("incoming_host", sa.String(length=255), nullable=False),
        sa.Column("incoming_port", sa.Integer(), nullable=False),
        sa.Column("incoming_security", sa.String(length=16), nullable=False),
        sa.Column("incoming_username", sa.String(length=320), nullable=False),
        sa.Column("incoming_password_encrypted", sa.Text(), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("smtp_security", sa.String(length=16), nullable=False),
        sa.Column("smtp_username", sa.String(length=320), nullable=False),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=False),
        sa.Column("sync_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'not_tested'"), nullable=False
        ),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "email_address",
            name="uq_mail_accounts_workspace_user_email",
        ),
    )
    op.create_index("ix_mail_accounts_deleted_at", "mail_accounts", ["deleted_at"])
    op.create_index("ix_mail_accounts_email_address", "mail_accounts", ["email_address"])
    op.create_index("ix_mail_accounts_user_id", "mail_accounts", ["user_id"])
    op.create_index("ix_mail_accounts_workspace_id", "mail_accounts", ["workspace_id"])
    op.create_index(
        "ix_mail_accounts_workspace_user",
        "mail_accounts",
        ["workspace_id", "user_id"],
    )

    op.create_table(
        "mail_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("folder", sa.String(length=160), nullable=False),
        sa.Column("provider_uid", sa.String(length=256), nullable=False),
        sa.Column("provider_message_id", sa.String(length=512), nullable=True),
        sa.Column("thread_key", sa.String(length=512), nullable=True),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("from_text", sa.Text(), nullable=False),
        sa.Column("to_text", sa.Text(), nullable=False),
        sa.Column("cc_text", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("is_starred", sa.Boolean(), nullable=False),
        sa.Column("has_attachments", sa.Boolean(), nullable=False),
        sa.Column("body_status", sa.String(length=24), nullable=False),
        sa.Column("sync_seen_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "folder",
            "provider_uid",
            name="uq_mail_messages_account_folder_uid",
        ),
    )
    op.create_index("ix_mail_messages_account_id", "mail_messages", ["account_id"])
    op.create_index(
        "ix_mail_messages_provider_message_id", "mail_messages", ["provider_message_id"]
    )
    op.create_index("ix_mail_messages_thread_key", "mail_messages", ["thread_key"])
    op.create_index("ix_mail_messages_user_id", "mail_messages", ["user_id"])
    op.create_index("ix_mail_messages_workspace_id", "mail_messages", ["workspace_id"])
    op.create_index(
        "ix_mail_messages_workspace_user_flags",
        "mail_messages",
        ["workspace_id", "user_id", "is_read", "is_starred"],
    )
    op.create_index(
        "ix_mail_messages_workspace_user_received",
        "mail_messages",
        ["workspace_id", "user_id", "received_at"],
    )

    op.create_table(
        "mail_message_bodies",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["mail_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index("ix_mail_message_bodies_content_hash", "mail_message_bodies", ["content_hash"])

    op.create_table(
        "mail_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.String(length=256), nullable=True),
        sa.Column("disposition", sa.String(length=40), nullable=False),
        sa.Column("provider_part_id", sa.String(length=256), nullable=True),
        sa.Column("storage_provider", sa.String(length=40), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["mail_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mail_attachments_message_id", "mail_attachments", ["message_id"])

    op.create_table(
        "mail_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("source_message_id", sa.String(length=36), nullable=True),
        sa.Column("to_text", sa.Text(), nullable=False),
        sa.Column("cc_text", sa.Text(), nullable=False),
        sa.Column("bcc_text", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("ai_generated", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("send_error", sa.Text(), nullable=True),
        sa.Column("sent_message_id", sa.String(length=512), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"]),
        sa.ForeignKeyConstraint(["source_message_id"], ["mail_messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mail_drafts_account_id", "mail_drafts", ["account_id"])
    op.create_index("ix_mail_drafts_source_message_id", "mail_drafts", ["source_message_id"])
    op.create_index("ix_mail_drafts_user_id", "mail_drafts", ["user_id"])
    op.create_index("ix_mail_drafts_workspace_id", "mail_drafts", ["workspace_id"])
    op.create_index(
        "ix_mail_drafts_workspace_user_status",
        "mail_drafts",
        ["workspace_id", "user_id", "status"],
    )

    op.create_table(
        "mail_send_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"]),
        sa.ForeignKeyConstraint(["draft_id"], ["mail_drafts.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mail_send_attempts_account_id", "mail_send_attempts", ["account_id"])
    op.create_index("ix_mail_send_attempts_draft_id", "mail_send_attempts", ["draft_id"])
    op.create_index(
        "ix_mail_send_attempts_draft_created",
        "mail_send_attempts",
        ["draft_id", "created_at"],
    )
    op.create_index("ix_mail_send_attempts_user_id", "mail_send_attempts", ["user_id"])
    op.execute(
        sa.text(
            """
            INSERT INTO llm_policies (
                id, task_kind, policy_mode, description, updated_by, created_at, updated_at
            )
            VALUES
                (
                    '9f3a2b7c-6d10-4f01-9a01-000000000001',
                    'mail_summarize',
                    'local_only',
                    'Local-only summarization of synced mail messages.',
                    NULL,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                ),
                (
                    '9f3a2b7c-6d10-4f01-9a01-000000000002',
                    'mail_reply_draft',
                    'local_only',
                    'Local-only business email reply drafting.',
                    NULL,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                ),
                (
                    '9f3a2b7c-6d10-4f01-9a01-000000000003',
                    'mail_thread_brief',
                    'local_only',
                    'Local-only brief for related mail messages.',
                    NULL,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
            ON CONFLICT (task_kind) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM llm_policies
            WHERE task_kind IN ('mail_summarize', 'mail_reply_draft', 'mail_thread_brief')
            """
        )
    )
    op.drop_index("ix_mail_send_attempts_user_id", table_name="mail_send_attempts")
    op.drop_index("ix_mail_send_attempts_draft_created", table_name="mail_send_attempts")
    op.drop_index("ix_mail_send_attempts_draft_id", table_name="mail_send_attempts")
    op.drop_index("ix_mail_send_attempts_account_id", table_name="mail_send_attempts")
    op.drop_table("mail_send_attempts")
    op.drop_index("ix_mail_drafts_workspace_user_status", table_name="mail_drafts")
    op.drop_index("ix_mail_drafts_workspace_id", table_name="mail_drafts")
    op.drop_index("ix_mail_drafts_user_id", table_name="mail_drafts")
    op.drop_index("ix_mail_drafts_source_message_id", table_name="mail_drafts")
    op.drop_index("ix_mail_drafts_account_id", table_name="mail_drafts")
    op.drop_table("mail_drafts")
    op.drop_index("ix_mail_attachments_message_id", table_name="mail_attachments")
    op.drop_table("mail_attachments")
    op.drop_index("ix_mail_message_bodies_content_hash", table_name="mail_message_bodies")
    op.drop_table("mail_message_bodies")
    op.drop_index("ix_mail_messages_workspace_user_received", table_name="mail_messages")
    op.drop_index("ix_mail_messages_workspace_user_flags", table_name="mail_messages")
    op.drop_index("ix_mail_messages_workspace_id", table_name="mail_messages")
    op.drop_index("ix_mail_messages_user_id", table_name="mail_messages")
    op.drop_index("ix_mail_messages_thread_key", table_name="mail_messages")
    op.drop_index("ix_mail_messages_provider_message_id", table_name="mail_messages")
    op.drop_index("ix_mail_messages_account_id", table_name="mail_messages")
    op.drop_table("mail_messages")
    op.drop_index("ix_mail_accounts_workspace_user", table_name="mail_accounts")
    op.drop_index("ix_mail_accounts_workspace_id", table_name="mail_accounts")
    op.drop_index("ix_mail_accounts_user_id", table_name="mail_accounts")
    op.drop_index("ix_mail_accounts_email_address", table_name="mail_accounts")
    op.drop_index("ix_mail_accounts_deleted_at", table_name="mail_accounts")
    op.drop_table("mail_accounts")
