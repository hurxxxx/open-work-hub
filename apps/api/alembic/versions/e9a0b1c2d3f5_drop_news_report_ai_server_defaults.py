"""drop news/report AI server defaults

Revision ID: e9a0b1c2d3f5
Revises: e8f9a0b1c2d4
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e9a0b1c2d3f5"
down_revision = "e8f9a0b1c2d4"
branch_labels = None
depends_on = None


def _drop_default(table_name: str, column_name: str, column_type: sa.TypeEngine) -> None:
    op.alter_column(
        table_name,
        column_name,
        existing_type=column_type,
        existing_nullable=False,
        server_default=None,
    )


def upgrade() -> None:
    _drop_default("industry_report_ai_evaluations", "relevant", sa.Boolean())
    _drop_default("industry_report_ai_evaluations", "reason", sa.String(length=16))
    _drop_default("industry_report_ai_evaluations", "reason_detail", sa.Text())

    _drop_default("industry_report_recommended", "org", sa.String(length=255))
    _drop_default("industry_report_recommended", "published_date", sa.String(length=32))
    _drop_default("industry_report_recommended", "url", sa.String(length=2048))
    _drop_default("industry_report_recommended", "company", sa.String(length=32))
    _drop_default("industry_report_recommended", "origin", sa.String(length=8))
    _drop_default("industry_report_recommended", "reason", sa.String(length=16))
    _drop_default("industry_report_recommended", "reason_detail", sa.Text())

    _drop_default("news_articles", "ai_evaluated", sa.Boolean())
    _drop_default("news_filter_settings", "ai_profile", sa.Text())
    _drop_default("news_filter_settings", "ai_curate_enabled", sa.Boolean())
    _drop_default("news_recommended_articles", "origin", sa.String(length=8))
    _drop_default("news_recommended_articles", "reason", sa.String(length=16))
    _drop_default("news_recommended_articles", "reason_detail", sa.Text())


def downgrade() -> None:
    op.alter_column(
        "news_recommended_articles",
        "reason_detail",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "news_recommended_articles",
        "reason",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "news_recommended_articles",
        "origin",
        existing_type=sa.String(length=8),
        existing_nullable=False,
        server_default="manual",
    )
    op.alter_column(
        "news_filter_settings",
        "ai_curate_enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "news_filter_settings",
        "ai_profile",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "news_articles",
        "ai_evaluated",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.false(),
    )

    op.alter_column(
        "industry_report_recommended",
        "reason_detail",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "industry_report_recommended",
        "reason",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "industry_report_recommended",
        "origin",
        existing_type=sa.String(length=8),
        existing_nullable=False,
        server_default="manual",
    )
    op.alter_column(
        "industry_report_recommended",
        "company",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "industry_report_recommended",
        "url",
        existing_type=sa.String(length=2048),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "industry_report_recommended",
        "published_date",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "industry_report_recommended",
        "org",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        server_default="",
    )

    op.alter_column(
        "industry_report_ai_evaluations",
        "reason_detail",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "industry_report_ai_evaluations",
        "reason",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        server_default="",
    )
    op.alter_column(
        "industry_report_ai_evaluations",
        "relevant",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.false(),
    )
