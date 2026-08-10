"""remove pms time tracking

Revision ID: d7e8f9a0b1c2
Revises: c4d5e6f7a8b0
Create Date: 2026-06-18 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d7e8f9a0b1c2"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("pms_time_entries")
    op.drop_column("pms_tasks", "estimate_hours")


def downgrade() -> None:
    op.add_column("pms_tasks", sa.Column("estimate_hours", sa.Float(), nullable=True))
    op.create_table(
        "pms_time_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["pms_tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pms_time_entries_task_id"),
        "pms_time_entries",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pms_time_entries_user_id"),
        "pms_time_entries",
        ["user_id"],
        unique=False,
    )
