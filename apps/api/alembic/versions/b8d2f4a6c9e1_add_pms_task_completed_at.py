"""add pms task completed_at

Revision ID: b8d2f4a6c9e1
Revises: a7c9e1f2b3d4
Create Date: 2026-07-07 09:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b8d2f4a6c9e1"
down_revision: str | Sequence[str] | None = "a7c9e1f2b3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pms_tasks",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pms_tasks", "completed_at")
