"""expand PMS task activity values

Revision ID: a8c0d2e4f6b9
Revises: f7a9b1c3d5e8
Create Date: 2026-07-19 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a8c0d2e4f6b9"
down_revision: str | Sequence[str] | None = "f7a9b1c3d5e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column_name in ("from_value", "to_value"):
        op.alter_column(
            "pms_task_activity_logs",
            column_name,
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    for column_name in ("from_value", "to_value"):
        op.alter_column(
            "pms_task_activity_logs",
            column_name,
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=True,
            postgresql_using=f"left({column_name}, 255)",
        )
