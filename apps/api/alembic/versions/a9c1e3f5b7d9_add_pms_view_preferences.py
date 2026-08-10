"""add PMS view preferences

Revision ID: a9c1e3f5b7d9
Revises: d8e0f2a4b6c9
Create Date: 2026-07-16 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a9c1e3f5b7d9"
down_revision: str | Sequence[str] | None = "d8e0f2a4b6c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pms_view_preferences",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "task_list_group_by",
            sa.String(length=16),
            server_default=sa.text("'status'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "task_list_group_by IN ('none', 'status', 'assignee')",
            name="ck_pms_view_preferences_task_list_group_by",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("pms_view_preferences")
