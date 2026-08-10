"""add_legacy_issue_record_history

Revision ID: f1e2d3c4b5a6
Revises: e0f1a2b3c4d5
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f1e2d3c4b5a6"
down_revision: str | Sequence[str] | None = "e0f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "legacy_issue_record_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("record_kind", sa.String(length=32), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=True),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("field_key", sa.String(length=160), nullable=True),
        sa.Column("field_label", sa.String(length=255), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("details", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_history_record",
        "legacy_issue_record_history",
        ["workspace_id", "record_kind", "record_id", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_history_module_record",
        "legacy_issue_record_history",
        ["workspace_id", "module_key", "record_id", "created_at"],
    )
    op.create_index(
        op.f("ix_legacy_issue_record_history_action"),
        "legacy_issue_record_history",
        ["action"],
    )
    op.create_index(
        op.f("ix_legacy_issue_record_history_actor_user_id"),
        "legacy_issue_record_history",
        ["actor_user_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_record_history_module_key"),
        "legacy_issue_record_history",
        ["module_key"],
    )
    op.create_index(
        op.f("ix_legacy_issue_record_history_record_id"),
        "legacy_issue_record_history",
        ["record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_record_history_record_kind"),
        "legacy_issue_record_history",
        ["record_kind"],
    )
    op.create_index(
        op.f("ix_legacy_issue_record_history_workspace_id"),
        "legacy_issue_record_history",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_legacy_issue_record_history_workspace_id"),
        table_name="legacy_issue_record_history",
    )
    op.drop_index(
        op.f("ix_legacy_issue_record_history_record_kind"),
        table_name="legacy_issue_record_history",
    )
    op.drop_index(
        op.f("ix_legacy_issue_record_history_record_id"),
        table_name="legacy_issue_record_history",
    )
    op.drop_index(
        op.f("ix_legacy_issue_record_history_module_key"),
        table_name="legacy_issue_record_history",
    )
    op.drop_index(
        op.f("ix_legacy_issue_record_history_actor_user_id"),
        table_name="legacy_issue_record_history",
    )
    op.drop_index(
        op.f("ix_legacy_issue_record_history_action"),
        table_name="legacy_issue_record_history",
    )
    op.drop_index(
        "ix_legacy_issue_history_module_record",
        table_name="legacy_issue_record_history",
    )
    op.drop_index(
        "ix_legacy_issue_history_record",
        table_name="legacy_issue_record_history",
    )
    op.drop_table("legacy_issue_record_history")
