"""add_diagram_visibility

Revision ID: d9c2d3e4f5a7
Revises: d9b1c2e3f4a6
Create Date: 2026-06-26 16:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9c2d3e4f5a7"
down_revision: Union[str, Sequence[str], None] = "d9b1c2e3f4a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "diagrams",
        sa.Column(
            "visibility",
            sa.String(length=20),
            server_default="personal",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_diagrams_visibility",
        "diagrams",
        "visibility in ('personal', 'workspace')",
    )
    op.create_index("ix_diagrams_visibility", "diagrams", ["visibility"])


def downgrade() -> None:
    op.drop_index("ix_diagrams_visibility", table_name="diagrams")
    op.drop_constraint("ck_diagrams_visibility", "diagrams", type_="check")
    op.drop_column("diagrams", "visibility")
