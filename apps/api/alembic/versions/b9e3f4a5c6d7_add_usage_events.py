"""add_usage_events

Revision ID: b9e3f4a5c6d7
Revises: a8d2f6c1e9b3
Create Date: 2026-06-18 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b9e3f4a5c6d7"
down_revision: Union[str, Sequence[str], None] = "a8d2f6c1e9b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("content_kind", sa.String(length=64), nullable=True),
        sa.Column("content_id", sa.String(length=512), nullable=True),
        sa.Column("content_title", sa.String(length=300), nullable=True),
        sa.Column("route_path", sa.String(length=240), nullable=True),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("bucket_started_at", sa.DateTime(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("last_occurred_at", sa.DateTime(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_actor_user_id", "usage_events", ["actor_user_id"])
    op.create_index("ix_usage_events_app_id", "usage_events", ["app_id"])
    op.create_index("ix_usage_events_app_occurred", "usage_events", ["app_id", "occurred_at"])
    op.create_index(
        "ix_usage_events_bucket_started_at",
        "usage_events",
        ["bucket_started_at"],
    )
    op.create_index("ix_usage_events_content_kind", "usage_events", ["content_kind"])
    op.create_index(
        "ix_usage_events_content_kind_occurred",
        "usage_events",
        ["content_kind", "occurred_at"],
    )
    op.create_index("ix_usage_events_dedupe_key", "usage_events", ["dedupe_key"])
    op.create_index("ix_usage_events_event_type", "usage_events", ["event_type"])
    op.create_index(
        "ix_usage_events_occurred_at",
        "usage_events",
        ["occurred_at"],
    )
    op.create_index("ix_usage_events_route_path", "usage_events", ["route_path"])
    op.create_index(
        "ix_usage_events_route_occurred",
        "usage_events",
        ["route_path", "occurred_at"],
    )
    op.create_index(
        "ix_usage_events_type_occurred",
        "usage_events",
        ["event_type", "occurred_at"],
    )
    op.create_index(
        "ix_usage_events_user_occurred",
        "usage_events",
        ["actor_user_id", "occurred_at"],
    )
    op.create_index("ix_usage_events_workspace_id", "usage_events", ["workspace_id"])
    op.create_table(
        "usage_excluded_users",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_usage_excluded_users_created_at",
        "usage_excluded_users",
        ["created_at"],
    )
    op.create_index(
        "ix_usage_excluded_users_created_by",
        "usage_excluded_users",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_excluded_users_created_by", table_name="usage_excluded_users")
    op.drop_index("ix_usage_excluded_users_created_at", table_name="usage_excluded_users")
    op.drop_table("usage_excluded_users")
    op.drop_index("ix_usage_events_workspace_id", table_name="usage_events")
    op.drop_index("ix_usage_events_user_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_type_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_route_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_route_path", table_name="usage_events")
    op.drop_index("ix_usage_events_occurred_at", table_name="usage_events")
    op.drop_index("ix_usage_events_event_type", table_name="usage_events")
    op.drop_index("ix_usage_events_dedupe_key", table_name="usage_events")
    op.drop_index("ix_usage_events_content_kind_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_content_kind", table_name="usage_events")
    op.drop_index("ix_usage_events_bucket_started_at", table_name="usage_events")
    op.drop_index("ix_usage_events_app_occurred", table_name="usage_events")
    op.drop_index("ix_usage_events_app_id", table_name="usage_events")
    op.drop_index("ix_usage_events_actor_user_id", table_name="usage_events")
    op.drop_table("usage_events")
