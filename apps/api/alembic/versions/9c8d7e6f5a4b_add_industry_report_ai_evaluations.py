"""add industry report AI evaluation markers

Records both relevant and non-relevant AI curation verdicts so periodic
industry-report curation does not repeatedly send the same reports to the LLM.

Revision ID: 9c8d7e6f5a4b
Revises: b8c9d0e1f2a3
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9c8d7e6f5a4b"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "industry_report_ai_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ref", sa.String(length=2048), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("relevant", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("reason_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("evaluated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ref", name="uq_industry_report_ai_evaluations_ref"),
    )


def downgrade() -> None:
    op.drop_table("industry_report_ai_evaluations")
