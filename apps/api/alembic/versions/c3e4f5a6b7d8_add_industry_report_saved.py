"""add industry_report_saved table

Admin-saved industry reports (trend / autojournal / KDI), independent of the
crawl cache so they persist and are viewable with attachment preview.

Revision ID: c3e4f5a6b7d8
Revises: b2d3f4a5c6e7
Create Date: 2026-06-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3e4f5a6b7d8"
down_revision = "b2d3f4a5c6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "industry_report_saved",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("ref", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("org", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("published_date", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("url", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("company", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("saved_by_id", sa.String(length=36), nullable=True),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ref", name="uq_industry_report_saved_ref"),
    )


def downgrade() -> None:
    op.drop_table("industry_report_saved")
