"""add community channel read only

Revision ID: c4e5f6a7b8d0
Revises: f0a1b2c3d4e6
Create Date: 2026-07-07 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e5f6a7b8d0"
down_revision: Union[str, Sequence[str], None] = "f0a1b2c3d4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "community_channels",
        sa.Column("read_only", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("community_channels", "read_only", server_default=None)


def downgrade() -> None:
    op.drop_column("community_channels", "read_only")
