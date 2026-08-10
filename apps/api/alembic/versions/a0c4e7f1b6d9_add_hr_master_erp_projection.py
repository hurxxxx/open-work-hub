"""add HR master ERP consumer projection

Revision ID: a0c4e7f1b6d9
Revises: f9d2b5e8c3a7
Create Date: 2026-07-29 14:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a0c4e7f1b6d9"
down_revision: str | Sequence[str] | None = "f9d2b5e8c3a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hr_master_runs",
        sa.Column("erp_projection_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column("birth_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "hr_master_person_rows",
        sa.Column("hire_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "management_health_prior_uploads",
        sa.Column("source_erp_run_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "management_health_decision_runs",
        sa.Column("source_erp_run_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("management_health_decision_runs", "source_erp_run_id")
    op.drop_column("management_health_prior_uploads", "source_erp_run_id")
    op.drop_column("hr_master_person_rows", "hire_date")
    op.drop_column("hr_master_person_rows", "birth_date")
    op.drop_column("hr_master_runs", "erp_projection_hash")
