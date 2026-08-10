"""add_lab_document_duplicate_references

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-28 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lab_documents",
        sa.Column("duplicate_of_document_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_lab_documents_duplicate_of_document_id"),
        "lab_documents",
        ["duplicate_of_document_id"],
    )
    op.create_foreign_key(
        "fk_lab_documents_duplicate_of_document_id_lab_documents",
        "lab_documents",
        "lab_documents",
        ["duplicate_of_document_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_lab_documents_duplicate_of_document_id_lab_documents",
        "lab_documents",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_lab_documents_duplicate_of_document_id"), table_name="lab_documents")
    op.drop_column("lab_documents", "duplicate_of_document_id")
