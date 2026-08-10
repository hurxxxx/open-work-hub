"""add_personal_todo_items

Revision ID: c3d4e5f6a7b8
Revises: f4e6a8b9c2d3
Create Date: 2026-06-02 13:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "f4e6a8b9c2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_todo_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_todo_items_user_id", "personal_todo_items", ["user_id"])
    op.create_index(
        "ix_personal_todo_items_completed",
        "personal_todo_items",
        ["completed"],
    )
    op.create_index(
        "ix_personal_todo_items_user_completed_sort",
        "personal_todo_items",
        ["user_id", "completed", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_personal_todo_items_user_completed_sort",
        table_name="personal_todo_items",
    )
    op.drop_index("ix_personal_todo_items_completed", table_name="personal_todo_items")
    op.drop_index("ix_personal_todo_items_user_id", table_name="personal_todo_items")
    op.drop_table("personal_todo_items")
