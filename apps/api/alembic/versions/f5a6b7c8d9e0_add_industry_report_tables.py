"""add_industry_report_tables

Revision ID: f5a6b7c8d9e0
Revises: b7c1d9e2f4a8
Create Date: 2026-06-09 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f5a6b7c8d9e0"
down_revision: str | Sequence[str] | None = "b7c1d9e2f4a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "industry_report_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("published_date", sa.String(length=10), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_industry_report_files_company", "industry_report_files", ["company"]
    )

    op.create_table(
        "industry_report_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("keyword", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("org", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("published_date", sa.String(length=32), nullable=False),
        sa.Column("extra", JSONB, nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source IN ('autojournal','kdi_nara','kdi_material','kdi_domestic')",
            name="ck_industry_report_items_source",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "url", name="uq_industry_report_items_source_url"),
    )
    op.create_index("ix_industry_report_items_source", "industry_report_items", ["source"])
    op.create_index(
        "ix_industry_report_items_source_date",
        "industry_report_items",
        ["source", "published_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_industry_report_items_source_date", table_name="industry_report_items")
    op.drop_index("ix_industry_report_items_source", table_name="industry_report_items")
    op.drop_table("industry_report_items")
    op.drop_index("ix_industry_report_files_company", table_name="industry_report_files")
    op.drop_table("industry_report_files")
