"""add industry_report_files source/source_key for crawled reports

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-06-09 00:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "industry_report_files",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="upload"),
    )
    op.add_column(
        "industry_report_files",
        sa.Column("source_key", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_industry_report_files_company_source_key",
        "industry_report_files",
        ["company", "source_key"],
    )
    # Drop the server default now that existing rows are backfilled; the ORM
    # supplies the value on insert.
    op.alter_column("industry_report_files", "source", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "uq_industry_report_files_company_source_key",
        "industry_report_files",
        type_="unique",
    )
    op.drop_column("industry_report_files", "source_key")
    op.drop_column("industry_report_files", "source")
