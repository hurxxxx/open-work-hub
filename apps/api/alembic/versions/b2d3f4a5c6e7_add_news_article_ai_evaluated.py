"""add news_articles.ai_evaluated

Tracks whether the AI curator already evaluated a collected article so the
14-day window is swept once and only newly-collected articles are re-evaluated.

Revision ID: b2d3f4a5c6e7
Revises: a1c2e3f4d5b6
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2d3f4a5c6e7"
down_revision = "a1c2e3f4d5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_articles",
        sa.Column(
            "ai_evaluated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("news_articles", "ai_evaluated")
