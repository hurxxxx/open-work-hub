"""add usage targets

Revision ID: d9f0a1b2c3d4
Revises: d7e8f9a0b1c2
Create Date: 2026-06-19 10:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d9f0a1b2c3d4"
down_revision: str | Sequence[str] | None = "d7e8f9a0b1c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usage_target_users",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_usage_target_users_created_at",
        "usage_target_users",
        ["created_at"],
    )
    op.create_index(
        "ix_usage_target_users_created_by",
        "usage_target_users",
        ["created_by_user_id"],
    )

    op.create_table(
        "usage_target_org_units",
        sa.Column("org_unit_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_unit_id"], ["org_units.id"]),
        sa.PrimaryKeyConstraint("org_unit_id"),
    )
    op.create_index(
        "ix_usage_target_org_units_created_at",
        "usage_target_org_units",
        ["created_at"],
    )
    op.create_index(
        "ix_usage_target_org_units_created_by",
        "usage_target_org_units",
        ["created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_target_org_units_created_by", table_name="usage_target_org_units")
    op.drop_index("ix_usage_target_org_units_created_at", table_name="usage_target_org_units")
    op.drop_table("usage_target_org_units")
    op.drop_index("ix_usage_target_users_created_by", table_name="usage_target_users")
    op.drop_index("ix_usage_target_users_created_at", table_name="usage_target_users")
    op.drop_table("usage_target_users")
