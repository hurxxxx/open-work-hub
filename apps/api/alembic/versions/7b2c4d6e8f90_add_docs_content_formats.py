"""add_docs_content_formats

Revision ID: 7b2c4d6e8f90
Revises: 6e1f2a3b4c5d
Create Date: 2026-05-18 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "7b2c4d6e8f90"
down_revision: str | Sequence[str] | None = "6e1f2a3b4c5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "docs_native_docs",
        sa.Column(
            "content_format",
            sa.String(length=24),
            server_default="block",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_docs_native_docs_content_format"),
        "docs_native_docs",
        ["content_format"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_docs_native_docs_content_format",
        "docs_native_docs",
        "content_format IN ('block', 'html')",
    )
    op.alter_column("docs_native_docs", "content_format", server_default=None)
    op.add_column("docs_native_doc_pages", sa.Column("content_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("docs_native_doc_pages", "content_text")
    op.drop_constraint("ck_docs_native_docs_content_format", "docs_native_docs", type_="check")
    op.drop_index(op.f("ix_docs_native_docs_content_format"), table_name="docs_native_docs")
    op.drop_column("docs_native_docs", "content_format")
