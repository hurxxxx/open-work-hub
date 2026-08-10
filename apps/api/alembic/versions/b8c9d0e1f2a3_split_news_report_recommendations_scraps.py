"""split news/report recommendations from user scraps

Revision ID: b8c9d0e1f2a3
Revises: 781ea30b825d
Create Date: 2026-06-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "781ea30b825d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("news_saved_articles", "news_recommended_articles")
    op.alter_column(
        "news_recommended_articles",
        "saved_by_id",
        new_column_name="recommended_by_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
    )
    op.alter_column(
        "news_recommended_articles",
        "saved_at",
        new_column_name="recommended_at",
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.drop_constraint(
        "uq_news_saved_articles_url",
        "news_recommended_articles",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_news_recommended_articles_url",
        "news_recommended_articles",
        ["original_url"],
    )
    op.create_table(
        "news_article_scraps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("keyword", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column("published_date", sa.String(length=10), nullable=False),
        sa.Column("scrapped_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "original_url",
            name="uq_news_article_scraps_user_url",
        ),
    )
    op.create_index("ix_news_article_scraps_user_id", "news_article_scraps", ["user_id"])
    op.create_index(
        "ix_news_article_scraps_user_date",
        "news_article_scraps",
        ["user_id", "scrapped_at"],
    )

    op.rename_table("industry_report_saved", "industry_report_recommended")
    op.alter_column(
        "industry_report_recommended",
        "saved_by_id",
        new_column_name="recommended_by_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
    )
    op.alter_column(
        "industry_report_recommended",
        "saved_at",
        new_column_name="recommended_at",
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.drop_constraint(
        "uq_industry_report_saved_ref",
        "industry_report_recommended",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_industry_report_recommended_ref",
        "industry_report_recommended",
        ["ref"],
    )
    op.create_table(
        "industry_report_scraps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("ref", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("org", sa.String(length=255), nullable=False),
        sa.Column("published_date", sa.String(length=32), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("company", sa.String(length=32), nullable=False),
        sa.Column("scrapped_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "ref", name="uq_industry_report_scraps_user_ref"),
    )
    op.create_index("ix_industry_report_scraps_user_id", "industry_report_scraps", ["user_id"])
    op.create_index(
        "ix_industry_report_scraps_user_date",
        "industry_report_scraps",
        ["user_id", "scrapped_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_industry_report_scraps_user_date", table_name="industry_report_scraps")
    op.drop_index("ix_industry_report_scraps_user_id", table_name="industry_report_scraps")
    op.drop_table("industry_report_scraps")
    op.drop_constraint(
        "uq_industry_report_recommended_ref",
        "industry_report_recommended",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_industry_report_saved_ref",
        "industry_report_recommended",
        ["ref"],
    )
    op.alter_column(
        "industry_report_recommended",
        "recommended_at",
        new_column_name="saved_at",
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "industry_report_recommended",
        "recommended_by_id",
        new_column_name="saved_by_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
    )
    op.rename_table("industry_report_recommended", "industry_report_saved")

    op.drop_index("ix_news_article_scraps_user_date", table_name="news_article_scraps")
    op.drop_index("ix_news_article_scraps_user_id", table_name="news_article_scraps")
    op.drop_table("news_article_scraps")
    op.drop_constraint(
        "uq_news_recommended_articles_url",
        "news_recommended_articles",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_news_saved_articles_url",
        "news_recommended_articles",
        ["original_url"],
    )
    op.alter_column(
        "news_recommended_articles",
        "recommended_at",
        new_column_name="saved_at",
        existing_type=sa.DateTime(),
        existing_nullable=False,
    )
    op.alter_column(
        "news_recommended_articles",
        "recommended_by_id",
        new_column_name="saved_by_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
    )
    op.rename_table("news_recommended_articles", "news_saved_articles")
