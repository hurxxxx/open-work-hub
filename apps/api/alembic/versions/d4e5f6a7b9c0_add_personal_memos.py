"""add_personal_memos

Revision ID: d4e5f6a7b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-06-02 15:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b9c0"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_memos",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_personal_memos_user"),
    )
    op.create_index("ix_personal_memos_user_id", "personal_memos", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_personal_memos_user_id", table_name="personal_memos")
    op.drop_table("personal_memos")
