"""add origin/reason to industry_report_saved

Distinguishes admin manual saves (저장된 산업 리포트) from AI-curated picks
(AI 추천 리포트) and carries the AI relevance reason.

Revision ID: 781ea30b825d
Revises: c3e4f5a6b7d8
Create Date: 2026-06-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "781ea30b825d"
down_revision = "c3e4f5a6b7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "industry_report_saved",
        sa.Column("origin", sa.String(length=8), nullable=False, server_default="manual"),
    )
    op.add_column(
        "industry_report_saved",
        sa.Column("reason", sa.String(length=16), nullable=False, server_default=""),
    )
    op.add_column(
        "industry_report_saved",
        sa.Column("reason_detail", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("industry_report_saved", "reason_detail")
    op.drop_column("industry_report_saved", "reason")
    op.drop_column("industry_report_saved", "origin")
