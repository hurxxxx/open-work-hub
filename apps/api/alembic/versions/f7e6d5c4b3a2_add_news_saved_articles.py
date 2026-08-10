"""add news_saved_articles table

Revision ID: f7e6d5c4b3a2
Revises: a3b5c7d9e1f2
Create Date: 2026-06-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7e6d5c4b3a2"
down_revision: Union[str, Sequence[str], None] = "a3b5c7d9e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_saved_articles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("keyword", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("original_url", sa.String(length=2048), nullable=False),
        sa.Column("published_date", sa.String(length=10), nullable=False),
        sa.Column("saved_by_id", sa.String(length=36), nullable=True),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("original_url", name="uq_news_saved_articles_url"),
    )


def downgrade() -> None:
    op.drop_table("news_saved_articles")
