"""add legacy issue attachment descriptions

Revision ID: d9d1e2f3a4b5
Revises: d9d0e1f2a3b4
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d9d1e2f3a4b5"
down_revision: str | Sequence[str] | None = "d9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("legacy_issue_attachments", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("legacy_issue_attachments", "description")
