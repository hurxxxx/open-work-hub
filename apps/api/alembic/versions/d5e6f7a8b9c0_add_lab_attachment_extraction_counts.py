"""add_lab_attachment_extraction_counts

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-05-27 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lab_documents",
        sa.Column("expected_embedded_object_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "lab_documents",
        sa.Column("embedded_object_gap_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("lab_documents", "embedded_object_gap_count")
    op.drop_column("lab_documents", "expected_embedded_object_count")
