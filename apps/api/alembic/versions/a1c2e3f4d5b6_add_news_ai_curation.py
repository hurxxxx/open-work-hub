"""add news AI curation columns

Adds AI-curation support to the news domain:
- news_saved_articles: origin / reason / reason_detail (distinguish AI picks from
  manual saves and carry the AI relevance reason).
- news_filter_settings: ai_profile / ai_curate_enabled / ai_curated_at (editable
  company profile + auto-curation toggle + last-run timestamp for staleness).

Revision ID: a1c2e3f4d5b6
Revises: f7e6d5c4b3a2
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1c2e3f4d5b6"
down_revision = "f7e6d5c4b3a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_saved_articles",
        sa.Column("origin", sa.String(length=8), nullable=False, server_default="manual"),
    )
    op.add_column(
        "news_saved_articles",
        sa.Column("reason", sa.String(length=16), nullable=False, server_default=""),
    )
    op.add_column(
        "news_saved_articles",
        sa.Column("reason_detail", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "news_filter_settings",
        sa.Column("ai_profile", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "news_filter_settings",
        sa.Column(
            "ai_curate_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "news_filter_settings",
        sa.Column("ai_curated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("news_filter_settings", "ai_curated_at")
    op.drop_column("news_filter_settings", "ai_curate_enabled")
    op.drop_column("news_filter_settings", "ai_profile")
    op.drop_column("news_saved_articles", "reason_detail")
    op.drop_column("news_saved_articles", "reason")
    op.drop_column("news_saved_articles", "origin")
