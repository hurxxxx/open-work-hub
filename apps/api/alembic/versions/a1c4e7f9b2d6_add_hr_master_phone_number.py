"""Add ERP phone number to the HR master projection.

Revision ID: a1c4e7f9b2d6
Revises: d6c8e0f2a4b7
Create Date: 2026-07-30 11:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "a1c4e7f9b2d6"
down_revision: str | None = "d6c8e0f2a4b7"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "hr_master_person_rows",
        sa.Column("phone_number", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hr_master_person_rows", "phone_number")
