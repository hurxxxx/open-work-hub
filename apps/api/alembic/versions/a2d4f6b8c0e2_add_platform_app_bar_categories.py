"""add_platform_app_bar_categories

Revision ID: a2d4f6b8c0e2
Revises: f6e7d8c9b0a1
Create Date: 2026-07-08 10:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2d4f6b8c0e2"
down_revision: Union[str, Sequence[str], None] = "f6e7d8c9b0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_app_bar_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("icon_key", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_platform_app_bar_categories_key"),
    )
    op.create_index(
        op.f("ix_platform_app_bar_categories_key"),
        "platform_app_bar_categories",
        ["key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_platform_app_bar_categories_position"),
        "platform_app_bar_categories",
        ["position"],
        unique=False,
    )
    op.create_table(
        "platform_app_bar_category_apps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["platform_app_bar_categories.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", "app_id", name="uq_platform_app_bar_category_app"),
        sa.UniqueConstraint("app_id", name="uq_platform_app_bar_category_apps_app_id"),
    )
    op.create_index(
        op.f("ix_platform_app_bar_category_apps_app_id"),
        "platform_app_bar_category_apps",
        ["app_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_platform_app_bar_category_apps_category_id"),
        "platform_app_bar_category_apps",
        ["category_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_platform_app_bar_category_apps_position"),
        "platform_app_bar_category_apps",
        ["position"],
        unique=False,
    )

    op.execute(sa.text("delete from platform_app_visibility where app_id = 'extensions'"))
    op.execute(sa.text("delete from workspace_app_entitlements where app_id = 'extensions'"))


def downgrade() -> None:
    op.drop_index(
        op.f("ix_platform_app_bar_category_apps_position"),
        table_name="platform_app_bar_category_apps",
    )
    op.drop_index(
        op.f("ix_platform_app_bar_category_apps_category_id"),
        table_name="platform_app_bar_category_apps",
    )
    op.drop_index(
        op.f("ix_platform_app_bar_category_apps_app_id"),
        table_name="platform_app_bar_category_apps",
    )
    op.drop_table("platform_app_bar_category_apps")
    op.drop_index(
        op.f("ix_platform_app_bar_categories_position"),
        table_name="platform_app_bar_categories",
    )
    op.drop_index(
        op.f("ix_platform_app_bar_categories_key"),
        table_name="platform_app_bar_categories",
    )
    op.drop_table("platform_app_bar_categories")
