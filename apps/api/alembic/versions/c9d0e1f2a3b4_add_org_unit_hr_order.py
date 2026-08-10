"""add_org_unit_hr_order

Revision ID: c9d0e1f2a3b4
Revises: b0c2d4e6f8a1
Create Date: 2026-06-10 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "b0c2d4e6f8a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("org_units", sa.Column("hr_org_order", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("org_units", "hr_org_order")
