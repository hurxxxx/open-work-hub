"""add legacy issue assistant analysis result

Revision ID: f3c9e1a5b7d2
Revises: e2b8d0f4a6c9
Create Date: 2026-07-24 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f3c9e1a5b7d2"
down_revision: str | Sequence[str] | None = "e2b8d0f4a6c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "legacy_issue_assistant_runs",
        sa.Column(
            "analysis_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("legacy_issue_assistant_runs", "analysis_result")
