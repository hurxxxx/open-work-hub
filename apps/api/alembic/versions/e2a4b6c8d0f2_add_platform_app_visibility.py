"""add_platform_app_visibility

Revision ID: e2a4b6c8d0f2
Revises: e0d1c2b3a4f5
Create Date: 2026-06-11 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2a4b6c8d0f2"
down_revision: Union[str, Sequence[str], None] = "e0d1c2b3a4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_app_visibility",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_id", name="uq_platform_app_visibility_app_id"),
    )
    op.create_index(
        op.f("ix_platform_app_visibility_app_id"),
        "platform_app_visibility",
        ["app_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_platform_app_visibility_visible"),
        "platform_app_visibility",
        ["visible"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_platform_app_visibility_visible"),
        table_name="platform_app_visibility",
    )
    op.drop_index(
        op.f("ix_platform_app_visibility_app_id"),
        table_name="platform_app_visibility",
    )
    op.drop_table("platform_app_visibility")
