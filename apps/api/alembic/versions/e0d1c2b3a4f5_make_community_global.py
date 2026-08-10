"""make_community_global

Revision ID: e0d1c2b3a4f5
Revises: c8d9e0f1a2b4
Create Date: 2026-06-10 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e0d1c2b3a4f5"
down_revision: Union[str, Sequence[str], None] = "c8d9e0f1a2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    op.add_column(
        "community_channels",
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.alter_column("community_channels", "active", server_default=None)

    op.drop_index(
        "ix_community_posts_workspace_channel_created",
        table_name="community_posts",
    )
    op.drop_index(op.f("ix_community_posts_workspace_id"), table_name="community_posts")

    if _is_sqlite():
        with op.batch_alter_table("community_posts") as batch_op:
            batch_op.drop_column("workspace_id")
    else:
        op.drop_constraint(
            "community_posts_workspace_id_fkey",
            "community_posts",
            type_="foreignkey",
        )
        op.drop_column("community_posts", "workspace_id")

    op.create_index(
        "ix_community_posts_channel_created",
        "community_posts",
        ["channel_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_community_posts_channel_created", table_name="community_posts")

    op.add_column(
        "community_posts",
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
    )
    if not _is_sqlite():
        op.create_foreign_key(
            "community_posts_workspace_id_fkey",
            "community_posts",
            "workspaces",
            ["workspace_id"],
            ["id"],
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
    op.drop_column("community_channels", "active")
