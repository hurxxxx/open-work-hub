"""remove GeekNews from the news domain

Revision ID: b9d1f3a5c7e9
Revises: b9d1e3f5a7c0
Create Date: 2026-07-21 00:00:00.000000

The deleted article, recommendation, scrap, and usage-event rows are not
recoverable on downgrade. Downgrade only restores the former channel check.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "b9d1f3a5c7e9"
down_revision: str | Sequence[str] | None = "b9d1e3f5a7c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REMOVED_NEWS_PREDICATE = """
    channel = 'geeknews'
    OR lower(source) = 'geeknews'
    OR original_url ILIKE '%news.hada.io/%'
"""


def upgrade() -> None:
    for table_name in (
        "news_article_scraps",
        "news_recommended_articles",
        "news_articles",
    ):
        op.execute(f"DELETE FROM {table_name} WHERE {_REMOVED_NEWS_PREDICATE}")

    op.execute(
        """
        DELETE FROM usage_events
        WHERE app_id = 'news'
          AND (
            content_id ILIKE '%geeknews%'
            OR content_id ILIKE '%news.hada.io/%'
            OR route_path ILIKE '%geeknews%'
            OR source ILIKE '%geeknews%'
            OR CAST(event_metadata AS TEXT) ILIKE '%geeknews%'
            OR CAST(event_metadata AS TEXT) ILIKE '%news.hada.io/%'
          )
        """
    )

    op.drop_constraint("ck_news_articles_channel", "news_articles", type_="check")
    op.create_check_constraint(
        "ck_news_articles_channel",
        "news_articles",
        "channel IN ('keyword','front','car')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_news_articles_channel", "news_articles", type_="check")
    op.create_check_constraint(
        "ck_news_articles_channel",
        "news_articles",
        "channel IN ('keyword','front','car','geeknews')",
    )
