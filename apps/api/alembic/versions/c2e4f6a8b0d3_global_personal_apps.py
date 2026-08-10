"""make community, mail, and planner global personal app aware

Revision ID: c2e4f6a8b0d3
Revises: b1d3f5a7c9e2
Create Date: 2026-07-16 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa


revision: str = "c2e4f6a8b0d3"
down_revision: str | Sequence[str] | None = "b1d3f5a7c9e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


GLOBAL_APP_IDS = ("community", "mail", "planner")
PERSONAL_TOOL_APP_IDS = ("mail", "planner")


def _remove_personal_tools_from_user_layouts() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.String()),
        sa.column("app_bar_layout", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(users.c.id, users.c.app_bar_layout).where(users.c.app_bar_layout.is_not(None))
    )
    for user_id, layout in rows:
        if not isinstance(layout, dict):
            continue
        pinned_app_ids = layout.get("pinned_app_ids")
        if not isinstance(pinned_app_ids, list):
            continue
        normalized = [app_id for app_id in pinned_app_ids if app_id not in PERSONAL_TOOL_APP_IDS]
        if normalized == pinned_app_ids:
            continue
        next_layout: dict[str, Any] = dict(layout)
        next_layout["pinned_app_ids"] = normalized
        bind.execute(users.update().where(users.c.id == user_id).values(app_bar_layout=next_layout))


def _enqueue_planner_index_deletes() -> None:
    op.execute("DELETE FROM search_index_jobs WHERE entity_type = 'planner_event'")
    op.execute(
        sa.text(
            """
            INSERT INTO search_index_jobs (
                id, workspace_id, entity_type, entity_id, operation,
                status, attempts, created_at, updated_at
            )
            SELECT
                substr(md5('planner-search-delete:' || event.id), 1, 32),
                event.workspace_id,
                'planner_event',
                event.id,
                'delete',
                'pending',
                0,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM planner_events AS event
            """
        )
    )
    op.execute("DELETE FROM rag_sync_jobs WHERE resource_type = 'planner_event'")
    op.execute(
        sa.text(
            """
            INSERT INTO rag_sync_jobs (
                id, scope_kind, workspace_id, lane, resource_type, resource_id,
                operation, status, attempts, created_at, updated_at
            )
            SELECT
                substr(md5('planner-rag-delete:' || event.id), 1, 32),
                'workspace',
                event.workspace_id,
                'realtime',
                'planner_event',
                event.id,
                'delete',
                'pending',
                0,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM planner_events AS event
            """
        )
    )


def _upgrade_mail() -> None:
    op.add_column(
        "mail_accounts",
        sa.Column(
            "account_label",
            sa.String(length=160),
            server_default=sa.text("''"),
            nullable=False,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE mail_accounts AS account
            SET account_label = COALESCE(
                NULLIF(workspace.name, ''),
                NULLIF(account.display_name, ''),
                account.email_address
            )
            FROM workspaces AS workspace
            WHERE workspace.id = account.workspace_id
            """
        )
    )
    op.alter_column(
        "mail_accounts",
        "workspace_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
        nullable=True,
    )
    op.create_index(
        "ix_mail_accounts_user_created",
        "mail_accounts",
        ["user_id", "created_at"],
    )

    op.create_index(
        "ix_mail_messages_account_received",
        "mail_messages",
        ["account_id", "received_at"],
    )
    op.create_index(
        "ix_mail_messages_account_flags",
        "mail_messages",
        ["account_id", "is_read", "is_starred"],
    )
    op.alter_column(
        "mail_messages",
        "workspace_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "mail_messages",
        "user_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
        nullable=True,
    )

    op.create_index(
        "ix_mail_drafts_account_status",
        "mail_drafts",
        ["account_id", "status"],
    )
    op.alter_column(
        "mail_drafts",
        "workspace_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "mail_drafts",
        "user_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
        nullable=True,
    )

    op.alter_column(
        "mail_send_attempts",
        "user_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
        nullable=True,
    )
    for table_name in (
        "mail_mailboxes",
        "mail_sync_states",
        "mail_sync_jobs",
    ):
        op.alter_column(
            table_name,
            "workspace_id",
            existing_type=sa.String(length=36),
            existing_nullable=False,
            nullable=True,
        )
        op.alter_column(
            table_name,
            "user_id",
            existing_type=sa.String(length=36),
            existing_nullable=False,
            nullable=True,
        )


def _upgrade_planner() -> None:
    _enqueue_planner_index_deletes()
    op.add_column(
        "planner_events",
        sa.Column(
            "time_zone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Seoul'"),
            nullable=False,
        ),
    )
    op.alter_column(
        "planner_events",
        "workspace_id",
        existing_type=sa.String(length=36),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "planner_events",
        "visibility",
        existing_type=sa.String(length=24),
        existing_nullable=False,
        server_default=sa.text("'private'"),
    )
    op.create_index(
        "ix_planner_events_owner_start",
        "planner_events",
        ["owner_id", "start_at"],
    )
    op.create_index(
        "ix_planner_events_owner_end",
        "planner_events",
        ["owner_id", "end_at"],
    )


def upgrade() -> None:
    _remove_personal_tools_from_user_layouts()
    op.execute(
        sa.text("DELETE FROM workspace_app_entitlements WHERE app_id IN :app_ids").bindparams(
            sa.bindparam("app_ids", expanding=True, value=GLOBAL_APP_IDS)
        )
    )
    op.execute(
        sa.text("DELETE FROM platform_app_bar_category_apps WHERE app_id IN :app_ids").bindparams(
            sa.bindparam("app_ids", expanding=True, value=PERSONAL_TOOL_APP_IDS)
        )
    )
    _upgrade_mail()
    _upgrade_planner()


def _restore_account_workspace_ids() -> None:
    op.execute(
        sa.text(
            """
            UPDATE mail_accounts AS account
            SET workspace_id = (
                SELECT workspace.id
                FROM workspaces AS workspace
                LEFT JOIN workspace_user_bindings AS binding
                  ON binding.workspace_id = workspace.id
                 AND binding.user_id = account.user_id
                WHERE workspace.name = account.account_label
                   OR binding.user_id IS NOT NULL
                ORDER BY
                    CASE WHEN workspace.name = account.account_label THEN 0 ELSE 1 END,
                    workspace.name,
                    workspace.id
                LIMIT 1
            )
            WHERE account.workspace_id IS NULL
            """
        )
    )
    op.alter_column(
        "mail_accounts",
        "workspace_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
        nullable=False,
    )


def _restore_mail_child_scope(
    table_name: str,
    *,
    account_column: str = "account_id",
) -> None:
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name} AS child
            SET workspace_id = account.workspace_id,
                user_id = account.user_id
            FROM mail_accounts AS account
            WHERE account.id = child.{account_column}
              AND child.workspace_id IS NULL
            """
        )
    )
    op.alter_column(
        table_name,
        "workspace_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        table_name,
        "user_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
        nullable=False,
    )


def _downgrade_mail() -> None:
    _restore_account_workspace_ids()
    _restore_mail_child_scope("mail_messages")
    _restore_mail_child_scope("mail_drafts")
    op.execute(
        """
        UPDATE mail_send_attempts AS attempt
        SET user_id = account.user_id
        FROM mail_accounts AS account
        WHERE account.id = attempt.account_id
          AND attempt.user_id IS NULL
        """
    )
    op.alter_column(
        "mail_send_attempts",
        "user_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
        nullable=False,
    )
    _restore_mail_child_scope("mail_mailboxes")
    _restore_mail_child_scope("mail_sync_states")
    _restore_mail_child_scope("mail_sync_jobs")

    op.drop_index("ix_mail_messages_account_received", table_name="mail_messages")
    op.drop_index("ix_mail_messages_account_flags", table_name="mail_messages")
    op.drop_index("ix_mail_drafts_account_status", table_name="mail_drafts")
    op.drop_index("ix_mail_accounts_user_created", table_name="mail_accounts")
    op.drop_column("mail_accounts", "account_label")


def _downgrade_planner() -> None:
    op.drop_index("ix_planner_events_owner_end", table_name="planner_events")
    op.drop_index("ix_planner_events_owner_start", table_name="planner_events")
    op.execute(
        sa.text(
            """
            UPDATE planner_events AS event
            SET workspace_id = (
                SELECT binding.workspace_id
                FROM workspace_user_bindings AS binding
                WHERE binding.user_id = event.owner_id
                ORDER BY binding.workspace_id
                LIMIT 1
            )
            WHERE event.workspace_id IS NULL
            """
        )
    )
    op.alter_column(
        "planner_events",
        "workspace_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "planner_events",
        "visibility",
        existing_type=sa.String(length=24),
        existing_nullable=False,
        server_default=None,
    )
    op.drop_column("planner_events", "time_zone")


def downgrade() -> None:
    _downgrade_planner()
    _downgrade_mail()
