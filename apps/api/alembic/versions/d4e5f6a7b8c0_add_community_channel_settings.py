"""add_community_channel_settings

Revision ID: d4e5f6a7b8c0
Revises: d3e4f5a6b7c8
Create Date: 2026-07-01 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c0"
down_revision: Union[str, Sequence[str], None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "community_channels",
        sa.Column("force_anonymous", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "community_channels",
        sa.Column("admin_only_content", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "community_channels",
        sa.Column("template_title", sa.String(length=240), server_default="", nullable=False),
    )
    op.add_column(
        "community_channels",
        sa.Column("template_body", sa.Text(), server_default="", nullable=False),
    )
    op.alter_column("community_channels", "force_anonymous", server_default=None)
    op.alter_column("community_channels", "admin_only_content", server_default=None)
    op.alter_column("community_channels", "template_title", server_default=None)
    op.alter_column("community_channels", "template_body", server_default=None)


def downgrade() -> None:
    op.drop_column("community_channels", "template_body")
    op.drop_column("community_channels", "template_title")
    op.drop_column("community_channels", "admin_only_content")
    op.drop_column("community_channels", "force_anonymous")
