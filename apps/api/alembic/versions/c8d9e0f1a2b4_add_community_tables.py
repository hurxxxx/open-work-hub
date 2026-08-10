"""add_community_tables

Revision ID: c8d9e0f1a2b4
Revises: b2c4d6e8f0a1
Create Date: 2026-06-10 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b4"
down_revision: Union[str, Sequence[str], None] = "b2c4d6e8f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_SUGGESTIONS_CHANNEL_ID = "8f2f3d64-2261-4ec7-b1e8-7f4ce8c273f1"


def upgrade() -> None:
    op.create_table(
        "community_channels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_community_channels_key"),
        "community_channels",
        ["key"],
        unique=True,
    )
    op.create_index(
        "ix_community_channels_position",
        "community_channels",
        ["position"],
        unique=False,
    )

    op.create_table(
        "community_posts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["channel_id"], ["community_channels.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_community_posts_author_id"),
        "community_posts",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_community_posts_channel_id"),
        "community_posts",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_community_posts_workspace_id"),
        "community_posts",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_community_posts_workspace_channel_created",
        "community_posts",
        ["workspace_id", "channel_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "community_comments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("post_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("parent_comment_id", sa.String(length=36), nullable=True),
        sa.Column("is_anonymous", sa.Boolean(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["parent_comment_id"],
            ["community_comments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["community_posts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_community_comments_author_id"),
        "community_comments",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_community_comments_parent_comment_id"),
        "community_comments",
        ["parent_comment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_community_comments_post_id"),
        "community_comments",
        ["post_id"],
        unique=False,
    )
    op.create_index(
        "ix_community_comments_post_created",
        "community_comments",
        ["post_id", "created_at"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO community_channels
                (id, key, name, description, position, created_at, updated_at)
            VALUES
                (:id, 'suggestions', 'Suggestions',
                 'Ideas, requests, and improvement threads.', 0, now(), now())
            ON CONFLICT (key) DO NOTHING
            """
        ).bindparams(id=DEFAULT_SUGGESTIONS_CHANNEL_ID)
    )


def downgrade() -> None:
    op.drop_index(
        "ix_community_comments_post_created",
        table_name="community_comments",
    )
    op.drop_index(
        op.f("ix_community_comments_post_id"),
        table_name="community_comments",
    )
    op.drop_index(
        op.f("ix_community_comments_parent_comment_id"),
        table_name="community_comments",
    )
    op.drop_index(
        op.f("ix_community_comments_author_id"),
        table_name="community_comments",
    )
    op.drop_table("community_comments")
    op.drop_index(
        "ix_community_posts_workspace_channel_created",
        table_name="community_posts",
    )
    op.drop_index(
        op.f("ix_community_posts_workspace_id"),
        table_name="community_posts",
    )
    op.drop_index(
        op.f("ix_community_posts_channel_id"),
        table_name="community_posts",
    )
    op.drop_index(
        op.f("ix_community_posts_author_id"),
        table_name="community_posts",
    )
    op.drop_table("community_posts")
    op.drop_index(
        "ix_community_channels_position",
        table_name="community_channels",
    )
    op.drop_index(op.f("ix_community_channels_key"), table_name="community_channels")
    op.drop_table("community_channels")
