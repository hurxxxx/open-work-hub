"""add_mail_sync_state_jobs

Revision ID: 6e1f2a3b4c5d
Revises: 5d7a9c2e4f10
Create Date: 2026-05-18 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6e1f2a3b4c5d"
down_revision: str | Sequence[str] | None = "5d7a9c2e4f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mail_accounts",
        sa.Column(
            "provider_kind",
            sa.String(length=32),
            server_default=sa.text("'imap'"),
            nullable=False,
        ),
    )
    op.add_column(
        "mail_accounts",
        sa.Column("last_sync_new_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "mail_accounts",
        sa.Column(
            "last_sync_updated_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.add_column(
        "mail_accounts",
        sa.Column(
            "last_sync_deleted_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE mail_accounts
            SET provider_kind = protocol
            WHERE provider_kind = 'imap' AND protocol IS NOT NULL
            """
        )
    )

    op.create_table(
        "mail_mailboxes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("provider_mailbox_id", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("sync_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "provider_mailbox_id",
            name="uq_mail_mailboxes_account_provider_id",
        ),
    )
    op.create_index("ix_mail_mailboxes_account_id", "mail_mailboxes", ["account_id"])
    op.create_index("ix_mail_mailboxes_user_id", "mail_mailboxes", ["user_id"])
    op.create_index("ix_mail_mailboxes_workspace_id", "mail_mailboxes", ["workspace_id"])
    op.create_index(
        "ix_mail_mailboxes_account_role",
        "mail_mailboxes",
        ["account_id", "role"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO mail_mailboxes (
                id, workspace_id, user_id, account_id, provider_mailbox_id, role,
                display_name, sync_enabled, created_at, updated_at
            )
            SELECT
                substr(md5(id || chr(58) || 'inbox'), 1, 32),
                workspace_id,
                user_id,
                id,
                'INBOX',
                'inbox',
                'INBOX',
                true,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM mail_accounts
            ON CONFLICT (account_id, provider_mailbox_id) DO NOTHING
            """
        )
    )

    op.add_column("mail_messages", sa.Column("mailbox_id", sa.String(length=36), nullable=True))
    op.add_column(
        "mail_messages", sa.Column("remote_identity", sa.String(length=768), nullable=True)
    )
    op.add_column(
        "mail_messages",
        sa.Column("remote_flags_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "mail_messages",
        sa.Column("local_state_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("mail_messages", sa.Column("remote_deleted_at", sa.DateTime(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE mail_messages AS message
            SET
                mailbox_id = mailbox.id,
                remote_identity = 'legacy:' || message.id,
                remote_flags_json = '{}'::jsonb,
                local_state_json = '{}'::jsonb,
                remote_deleted_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            FROM mail_mailboxes AS mailbox
            WHERE mailbox.account_id = message.account_id
              AND mailbox.role = 'inbox'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE mail_messages
            SET
                remote_identity = COALESCE(remote_identity, 'legacy:' || id),
                remote_flags_json = COALESCE(remote_flags_json, '{}'::jsonb),
                local_state_json = COALESCE(local_state_json, '{}'::jsonb)
            """
        )
    )
    op.alter_column(
        "mail_messages", "remote_identity", existing_type=sa.String(length=768), nullable=False
    )
    op.alter_column(
        "mail_messages",
        "remote_flags_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.alter_column(
        "mail_messages",
        "local_state_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )
    op.drop_constraint(
        "uq_mail_messages_account_folder_uid",
        "mail_messages",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_mail_messages_account_remote_identity",
        "mail_messages",
        ["account_id", "remote_identity"],
    )
    op.create_foreign_key(
        "fk_mail_messages_mailbox_id_mail_mailboxes",
        "mail_messages",
        "mail_mailboxes",
        ["mailbox_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_mail_messages_mailbox_id", "mail_messages", ["mailbox_id"])
    op.create_index("ix_mail_messages_remote_deleted_at", "mail_messages", ["remote_deleted_at"])
    op.create_index(
        "ix_mail_messages_account_mailbox",
        "mail_messages",
        ["account_id", "mailbox_id"],
    )

    op.create_table(
        "mail_sync_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("mailbox_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), server_default=sa.text("'idle'"), nullable=False),
        sa.Column("cursor_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_full_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_incremental_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mailbox_id"], ["mail_mailboxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mailbox_id", name="uq_mail_sync_states_mailbox"),
    )
    op.create_index("ix_mail_sync_states_account_id", "mail_sync_states", ["account_id"])
    op.create_index("ix_mail_sync_states_mailbox_id", "mail_sync_states", ["mailbox_id"])
    op.create_index("ix_mail_sync_states_user_id", "mail_sync_states", ["user_id"])
    op.create_index("ix_mail_sync_states_workspace_id", "mail_sync_states", ["workspace_id"])
    op.create_index(
        "ix_mail_sync_states_account_status",
        "mail_sync_states",
        ["account_id", "status"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO mail_sync_states (
                id, workspace_id, user_id, account_id, mailbox_id, status,
                cursor_json, created_at, updated_at
            )
            SELECT
                substr(md5(mailbox.id || chr(58) || 'state'), 1, 32),
                mailbox.workspace_id,
                mailbox.user_id,
                mailbox.account_id,
                mailbox.id,
                'idle',
                '{}'::jsonb,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM mail_mailboxes AS mailbox
            ON CONFLICT (mailbox_id) DO NOTHING
            """
        )
    )

    op.create_table(
        "mail_sync_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("mailbox_id", sa.String(length=36), nullable=False),
        sa.Column(
            "operation",
            sa.String(length=24),
            server_default=sa.text("'incremental'"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("last_published_at", sa.DateTime(), nullable=True),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('initial','incremental','reconcile','fetch_body')",
            name="ck_mail_sync_jobs_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_mail_sync_jobs_status",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["mail_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mailbox_id"], ["mail_mailboxes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mail_sync_jobs_account_id", "mail_sync_jobs", ["account_id"])
    op.create_index("ix_mail_sync_jobs_mailbox_id", "mail_sync_jobs", ["mailbox_id"])
    op.create_index("ix_mail_sync_jobs_user_id", "mail_sync_jobs", ["user_id"])
    op.create_index("ix_mail_sync_jobs_workspace_id", "mail_sync_jobs", ["workspace_id"])
    op.create_index("ix_mail_sync_jobs_next_retry_at", "mail_sync_jobs", ["next_retry_at"])
    op.create_index("ix_mail_sync_jobs_last_published_at", "mail_sync_jobs", ["last_published_at"])
    op.create_index(
        "ix_mail_sync_jobs_account_status_retry",
        "mail_sync_jobs",
        ["account_id", "status", "next_retry_at"],
    )
    op.create_index(
        "uq_mail_sync_jobs_active_scope",
        "mail_sync_jobs",
        ["account_id", "mailbox_id", "operation"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
        sqlite_where=sa.text("status IN ('pending', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index("uq_mail_sync_jobs_active_scope", table_name="mail_sync_jobs")
    op.drop_index("ix_mail_sync_jobs_account_status_retry", table_name="mail_sync_jobs")
    op.drop_index("ix_mail_sync_jobs_last_published_at", table_name="mail_sync_jobs")
    op.drop_index("ix_mail_sync_jobs_next_retry_at", table_name="mail_sync_jobs")
    op.drop_index("ix_mail_sync_jobs_workspace_id", table_name="mail_sync_jobs")
    op.drop_index("ix_mail_sync_jobs_user_id", table_name="mail_sync_jobs")
    op.drop_index("ix_mail_sync_jobs_mailbox_id", table_name="mail_sync_jobs")
    op.drop_index("ix_mail_sync_jobs_account_id", table_name="mail_sync_jobs")
    op.drop_table("mail_sync_jobs")

    op.drop_index("ix_mail_sync_states_account_status", table_name="mail_sync_states")
    op.drop_index("ix_mail_sync_states_workspace_id", table_name="mail_sync_states")
    op.drop_index("ix_mail_sync_states_user_id", table_name="mail_sync_states")
    op.drop_index("ix_mail_sync_states_mailbox_id", table_name="mail_sync_states")
    op.drop_index("ix_mail_sync_states_account_id", table_name="mail_sync_states")
    op.drop_table("mail_sync_states")

    op.drop_index("ix_mail_messages_account_mailbox", table_name="mail_messages")
    op.drop_index("ix_mail_messages_remote_deleted_at", table_name="mail_messages")
    op.drop_index("ix_mail_messages_mailbox_id", table_name="mail_messages")
    op.drop_constraint(
        "fk_mail_messages_mailbox_id_mail_mailboxes",
        "mail_messages",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_mail_messages_account_remote_identity",
        "mail_messages",
        type_="unique",
    )
    op.execute(
        sa.text(
            """
            DELETE FROM mail_messages AS older
            USING mail_messages AS newer
            WHERE older.account_id = newer.account_id
              AND older.folder = newer.folder
              AND older.provider_uid = newer.provider_uid
              AND older.id < newer.id
            """
        )
    )
    op.create_unique_constraint(
        "uq_mail_messages_account_folder_uid",
        "mail_messages",
        ["account_id", "folder", "provider_uid"],
    )
    op.drop_column("mail_messages", "remote_deleted_at")
    op.drop_column("mail_messages", "local_state_json")
    op.drop_column("mail_messages", "remote_flags_json")
    op.drop_column("mail_messages", "remote_identity")
    op.drop_column("mail_messages", "mailbox_id")

    op.drop_index("ix_mail_mailboxes_account_role", table_name="mail_mailboxes")
    op.drop_index("ix_mail_mailboxes_workspace_id", table_name="mail_mailboxes")
    op.drop_index("ix_mail_mailboxes_user_id", table_name="mail_mailboxes")
    op.drop_index("ix_mail_mailboxes_account_id", table_name="mail_mailboxes")
    op.drop_table("mail_mailboxes")

    op.drop_column("mail_accounts", "last_sync_deleted_count")
    op.drop_column("mail_accounts", "last_sync_updated_count")
    op.drop_column("mail_accounts", "last_sync_new_count")
    op.drop_column("mail_accounts", "provider_kind")
