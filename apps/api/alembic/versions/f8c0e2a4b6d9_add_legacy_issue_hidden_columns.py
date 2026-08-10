"""Add legacy issue administrator-hidden columns.

Revision ID: f8c0e2a4b6d9
Revises: e7b9d1f3a5c8
Create Date: 2026-07-30 10:25:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f8c0e2a4b6d9"
down_revision: str | None = "e7b9d1f3a5c8"
branch_labels: str | None = None
depends_on: str | None = None

JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(),
    "sqlite",
)


def upgrade() -> None:
    op.add_column(
        "legacy_issue_column_orders",
        sa.Column("hidden_column_keys", JSONB_COMPAT, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("legacy_issue_column_orders", "hidden_column_keys")
