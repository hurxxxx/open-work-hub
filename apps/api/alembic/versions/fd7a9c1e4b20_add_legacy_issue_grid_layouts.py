"""add legacy issue grid layout snapshots

Revision ID: fd7a9c1e4b20
Revises: fc6d8b2e0a31
Create Date: 2026-07-23 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "fd7a9c1e4b20"
down_revision: str | Sequence[str] | None = "fc6d8b2e0a31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(),
    "sqlite",
)


def upgrade() -> None:
    op.add_column(
        "legacy_issue_data_revisions",
        sa.Column("grid_layout", _JSONB_COMPAT, nullable=True),
    )
    op.add_column(
        "legacy_issue_vehicle_module_checklists",
        sa.Column("grid_layout", _JSONB_COMPAT, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("legacy_issue_vehicle_module_checklists", "grid_layout")
    op.drop_column("legacy_issue_data_revisions", "grid_layout")
