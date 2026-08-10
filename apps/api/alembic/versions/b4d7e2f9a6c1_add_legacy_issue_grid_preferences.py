"""add legacy issue grid preferences

Revision ID: b4d7e2f9a6c1
Revises: a3f6c9e1b4d8
Create Date: 2026-07-31 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b4d7e2f9a6c1"
down_revision: str | Sequence[str] | None = "a3f6c9e1b4d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(
    sa.JSON(),
    "sqlite",
)


def upgrade() -> None:
    op.create_table(
        "legacy_issue_grid_preferences",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("grid_kind", sa.String(length=32), nullable=False),
        sa.Column("grid_key", sa.String(length=160), nullable=False),
        sa.Column("column_order", _JSONB_COMPAT, nullable=False),
        sa.Column("hidden_column_keys", _JSONB_COMPAT, nullable=False),
        sa.Column("frozen_column_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "grid_kind IN ('dataset', 'vehicle-module-checklist')",
            name="ck_legacy_issue_grid_preferences_grid_kind",
        ),
        sa.CheckConstraint(
            "frozen_column_count >= 0 AND frozen_column_count <= 200",
            name="ck_legacy_issue_grid_preferences_frozen_column_count",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id",
            "user_id",
            "grid_kind",
            "grid_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("legacy_issue_grid_preferences")
