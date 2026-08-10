"""rename pms task completed_at to completed_date

Revision ID: c9e1f2a3b4d5
Revises: b8d2f4a6c9e1
Create Date: 2026-07-07 10:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c9e1f2a3b4d5"
down_revision: str | Sequence[str] | None = "b8d2f4a6c9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pms_tasks",
        sa.Column("completed_date", sa.Date(), nullable=True),
    )
    op.execute(
        "UPDATE pms_tasks SET completed_date = completed_at::date "
        "WHERE completed_at IS NOT NULL"
    )
    op.drop_column("pms_tasks", "completed_at")


def downgrade() -> None:
    op.add_column(
        "pms_tasks",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        "UPDATE pms_tasks SET completed_at = completed_date::timestamp "
        "WHERE completed_date IS NOT NULL"
    )
    op.drop_column("pms_tasks", "completed_date")
