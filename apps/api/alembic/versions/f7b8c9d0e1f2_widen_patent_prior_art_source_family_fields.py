"""widen patent prior art source family fields

Revision ID: f7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f7b8c9d0e1f2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "patent_prior_art_source_documents",
        "family_id",
        existing_type=sa.String(length=160),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "patent_prior_art_source_documents",
        "priority_number",
        existing_type=sa.String(length=160),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "patent_prior_art_source_documents",
        "priority_number",
        existing_type=sa.Text(),
        type_=sa.String(length=160),
        existing_nullable=True,
    )
    op.alter_column(
        "patent_prior_art_source_documents",
        "family_id",
        existing_type=sa.Text(),
        type_=sa.String(length=160),
        existing_nullable=True,
    )
