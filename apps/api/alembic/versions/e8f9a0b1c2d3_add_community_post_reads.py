"""add community post reads

Revision ID: e8f9a0b1c2d3
Revises: c7f8e9d0a1b2
Create Date: 2026-07-13 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d3"
down_revision: str | Sequence[str] | None = "c7f8e9d0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "community_post_reads",
        sa.Column("post_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["community_posts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("post_id", "user_id"),
    )
    op.create_index(
        "ix_community_post_reads_user_id",
        "community_post_reads",
        ["user_id"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO community_post_reads (post_id, user_id, read_at)
            SELECT id, author_id, updated_at
            FROM community_posts
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_post_reads_user_id",
        table_name="community_post_reads",
    )
    op.drop_table("community_post_reads")
