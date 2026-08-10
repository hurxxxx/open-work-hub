"""add_announcements

Revision ID: b2c4d6e8f0a1
Revises: c9d0e1f2a3b4
Create Date: 2026-06-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_announcements_workspace_id"),
        "announcements",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_author_id"),
        "announcements",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_is_pinned"),
        "announcements",
        ["is_pinned"],
        unique=False,
    )
    op.create_index(
        op.f("ix_announcements_scope"),
        "announcements",
        ["scope"],
        unique=False,
    )
    op.create_index(
        "ix_announcements_workspace_pinned_created",
        "announcements",
        ["workspace_id", "is_pinned", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_announcements_scope_pinned_created",
        "announcements",
        ["scope", "is_pinned", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_announcements_scope_pinned_created",
        table_name="announcements",
    )
    op.drop_index(
        "ix_announcements_workspace_pinned_created",
        table_name="announcements",
    )
    op.drop_index(op.f("ix_announcements_scope"), table_name="announcements")
    op.drop_index(op.f("ix_announcements_is_pinned"), table_name="announcements")
    op.drop_index(op.f("ix_announcements_author_id"), table_name="announcements")
    op.drop_index(op.f("ix_announcements_workspace_id"), table_name="announcements")
    op.drop_table("announcements")
