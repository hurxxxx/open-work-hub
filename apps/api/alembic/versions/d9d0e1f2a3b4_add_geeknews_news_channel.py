"""add geeknews news channel

Revision ID: d9d0e1f2a3b4
Revises: d9c2d3e4f5a7
Create Date: 2026-06-28
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d9d0e1f2a3b4"
down_revision: str | Sequence[str] | None = "d9c2d3e4f5a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_news_articles_channel", "news_articles", type_="check")
    op.create_check_constraint(
        "ck_news_articles_channel",
        "news_articles",
        "channel IN ('keyword','front','car','geeknews')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM news_articles WHERE channel = 'geeknews'")
    op.drop_constraint("ck_news_articles_channel", "news_articles", type_="check")
    op.create_check_constraint(
        "ck_news_articles_channel",
        "news_articles",
        "channel IN ('keyword','front','car')",
    )
