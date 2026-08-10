"""repair global personal app legacy scope columns

Revision ID: e5f7a9b1c3d6
Revises: d4f6a8b0c2e5
Create Date: 2026-07-17 15:10:00.000000

The first deployed form of c2e4f6a8b0d3 removed the legacy workspace and
visibility columns. That revision was hardened before release to preserve the
columns, but databases that had already applied the original form cannot rerun
the same revision. Normalize both historical shapes with a forward repair.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e5f7a9b1c3d6"
down_revision: str | Sequence[str] | None = "d4f6a8b0c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column(table_name: str, column_name: str) -> dict[str, object] | None:
    for column in sa.inspect(op.get_bind()).get_columns(table_name):
        if column["name"] == column_name:
            return column
    return None


def _ensure_nullable_scope_column(
    table_name: str,
    column_name: str,
    referred_table: str,
) -> bool:
    column = _column(table_name, column_name)
    added = column is None
    if added:
        op.add_column(
            table_name,
            sa.Column(column_name, sa.String(length=36), nullable=True),
        )
    elif column and not bool(column["nullable"]):
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.String(length=36),
            existing_nullable=False,
            nullable=True,
        )

    foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    if not any(
        foreign_key.get("constrained_columns") == [column_name]
        and foreign_key.get("referred_table") == referred_table
        for foreign_key in foreign_keys
    ):
        op.create_foreign_key(
            f"{table_name}_{column_name}_fkey",
            table_name,
            referred_table,
            [column_name],
            ["id"],
        )

    _ensure_index(
        table_name,
        f"ix_{table_name}_{column_name}",
        [column_name],
    )
    return added


def _ensure_index(
    table_name: str,
    index_name: str,
    column_names: list[str],
) -> None:
    indexes = sa.inspect(op.get_bind()).get_indexes(table_name)
    if any(index.get("name") == index_name for index in indexes):
        return
    op.create_index(index_name, table_name, column_names, unique=False)


def _ensure_unique_constraint(
    table_name: str,
    constraint_name: str,
    column_names: list[str],
) -> None:
    constraints = sa.inspect(op.get_bind()).get_unique_constraints(table_name)
    if any(constraint.get("name") == constraint_name for constraint in constraints):
        return
    op.create_unique_constraint(constraint_name, table_name, column_names)


def _repair_mail_scope() -> None:
    added: dict[tuple[str, str], bool] = {}
    for table_name, column_name, referred_table in (
        ("mail_accounts", "workspace_id", "workspaces"),
        ("mail_messages", "workspace_id", "workspaces"),
        ("mail_messages", "user_id", "users"),
        ("mail_drafts", "workspace_id", "workspaces"),
        ("mail_drafts", "user_id", "users"),
        ("mail_send_attempts", "user_id", "users"),
        ("mail_mailboxes", "workspace_id", "workspaces"),
        ("mail_mailboxes", "user_id", "users"),
        ("mail_sync_states", "workspace_id", "workspaces"),
        ("mail_sync_states", "user_id", "users"),
        ("mail_sync_jobs", "workspace_id", "workspaces"),
        ("mail_sync_jobs", "user_id", "users"),
    ):
        added[(table_name, column_name)] = _ensure_nullable_scope_column(
            table_name,
            column_name,
            referred_table,
        )

    op.alter_column(
        "mail_accounts",
        "account_label",
        existing_type=sa.String(length=160),
        existing_nullable=False,
        server_default=sa.text("''"),
    )

    for table_name in (
        "mail_messages",
        "mail_drafts",
        "mail_mailboxes",
        "mail_sync_states",
        "mail_sync_jobs",
    ):
        if not (added[(table_name, "workspace_id")] or added[(table_name, "user_id")]):
            continue
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name} AS child
                SET workspace_id = COALESCE(
                        child.workspace_id,
                        account.workspace_id
                    ),
                    user_id = COALESCE(child.user_id, account.user_id)
                FROM mail_accounts AS account
                WHERE account.id = child.account_id
                  AND (child.workspace_id IS NULL OR child.user_id IS NULL)
                """
            )
        )

    if added[("mail_send_attempts", "user_id")]:
        op.execute(
            sa.text(
                """
                UPDATE mail_send_attempts AS attempt
                SET user_id = account.user_id
                FROM mail_accounts AS account
                WHERE account.id = attempt.account_id
                  AND attempt.user_id IS NULL
                """
            )
        )

    _ensure_index(
        "mail_accounts",
        "ix_mail_accounts_workspace_user",
        ["workspace_id", "user_id"],
    )
    _ensure_unique_constraint(
        "mail_accounts",
        "uq_mail_accounts_workspace_user_email",
        ["workspace_id", "user_id", "email_address"],
    )
    _ensure_index(
        "mail_messages",
        "ix_mail_messages_workspace_user_received",
        ["workspace_id", "user_id", "received_at"],
    )
    _ensure_index(
        "mail_messages",
        "ix_mail_messages_workspace_user_flags",
        ["workspace_id", "user_id", "is_read", "is_starred"],
    )
    _ensure_index(
        "mail_drafts",
        "ix_mail_drafts_workspace_user_status",
        ["workspace_id", "user_id", "status"],
    )


def _repair_planner_scope() -> None:
    workspace_added = _ensure_nullable_scope_column(
        "planner_events",
        "workspace_id",
        "workspaces",
    )
    if _column("planner_events", "visibility") is None:
        op.add_column(
            "planner_events",
            sa.Column(
                "visibility",
                sa.String(length=24),
                server_default=sa.text("'private'"),
                nullable=False,
            ),
        )
    else:
        op.alter_column(
            "planner_events",
            "visibility",
            existing_type=sa.String(length=24),
            existing_nullable=False,
            server_default=sa.text("'private'"),
            nullable=False,
        )

    op.alter_column(
        "planner_events",
        "time_zone",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=sa.text("'Asia/Seoul'"),
    )

    if workspace_added:
        op.execute(
            sa.text(
                """
                WITH candidates AS (
                    SELECT entity_id AS event_id, workspace_id
                    FROM search_index_jobs
                    WHERE entity_type = 'planner_event'
                      AND workspace_id IS NOT NULL
                    UNION ALL
                    SELECT resource_id AS event_id, workspace_id
                    FROM rag_sync_jobs
                    WHERE resource_type = 'planner_event'
                      AND workspace_id IS NOT NULL
                ),
                unique_candidates AS (
                    SELECT event_id, min(workspace_id) AS workspace_id
                    FROM candidates
                    GROUP BY event_id
                    HAVING count(DISTINCT workspace_id) = 1
                )
                UPDATE planner_events AS event
                SET workspace_id = candidate.workspace_id
                FROM unique_candidates AS candidate
                WHERE event.id = candidate.event_id
                  AND event.workspace_id IS NULL
                """
            )
        )

    _ensure_index(
        "planner_events",
        "ix_planner_events_visibility",
        ["visibility"],
    )
    _ensure_index(
        "planner_events",
        "ix_planner_events_workspace_owner_start",
        ["workspace_id", "owner_id", "start_at"],
    )
    _ensure_index(
        "planner_events",
        "ix_planner_events_workspace_owner_end",
        ["workspace_id", "owner_id", "end_at"],
    )


def upgrade() -> None:
    _repair_mail_scope()
    _repair_planner_scope()


def downgrade() -> None:
    # The preceding revision's current contract already contains these
    # columns. Removing them would recreate the historical destructive drift.
    pass
