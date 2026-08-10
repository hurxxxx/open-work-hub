"""add_news_tables

Revision ID: b7c1d9e2f4a8
Revises: c8a9d0e1f2b3
Create Date: 2026-06-08 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c1d9e2f4a8"
down_revision: str | Sequence[str] | None = "c8a9d0e1f2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "news_articles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("keyword", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column("published_date", sa.String(length=10), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column("images", JSONB, nullable=True),
        sa.Column("tables", JSONB, nullable=True),
        sa.Column("article_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("collected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "channel IN ('keyword','front','car')",
            name="ck_news_articles_channel",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel", "original_url", name="uq_news_articles_channel_url"),
    )
    op.create_index("ix_news_articles_channel", "news_articles", ["channel"])
    op.create_index(
        "ix_news_articles_channel_date",
        "news_articles",
        ["channel", "published_date"],
    )

    op.create_table(
        "news_filter_settings",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("keyword_filter", JSONB, nullable=False),
        sa.Column("car_filter", JSONB, nullable=False),
        sa.Column("keyword_ui_filters", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("news_filter_settings")
    op.drop_index("ix_news_articles_channel_date", table_name="news_articles")
    op.drop_index("ix_news_articles_channel", table_name="news_articles")
    op.drop_table("news_articles")
