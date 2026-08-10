"""add_image_execution_profile

Revision ID: fa0b1c2d3e5f
Revises: f9a0b1c2d3e4
Create Date: 2026-06-02 21:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "fa0b1c2d3e5f"
down_revision: str | Sequence[str] | None = "f9a0b1c2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "image_generations",
        sa.Column(
            "image_execution_profile",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.alter_column("image_generations", "image_execution_profile", server_default=None)


def downgrade() -> None:
    op.drop_column("image_generations", "image_execution_profile")
