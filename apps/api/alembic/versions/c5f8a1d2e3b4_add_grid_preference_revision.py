"""add grid preference revision

Revision ID: c5f8a1d2e3b4
Revises: b4d7e2f9a6c1
Create Date: 2026-07-31 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c5f8a1d2e3b4"
down_revision: str | Sequence[str] | None = "b4d7e2f9a6c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "legacy_issue_grid_preferences",
        sa.Column(
            "revision",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "legacy_issue_grid_preferences",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_legacy_issue_grid_preferences_revision",
        "legacy_issue_grid_preferences",
        "revision >= 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_legacy_issue_grid_preferences_revision",
        "legacy_issue_grid_preferences",
        type_="check",
    )
    op.drop_column("legacy_issue_grid_preferences", "is_deleted")
    op.drop_column("legacy_issue_grid_preferences", "revision")
