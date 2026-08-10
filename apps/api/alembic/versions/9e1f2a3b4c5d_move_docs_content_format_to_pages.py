"""move_docs_content_format_to_pages

Revision ID: 9e1f2a3b4c5d
Revises: 8c3d5e7f9012
Create Date: 2026-05-18 22:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9e1f2a3b4c5d"
down_revision: str | Sequence[str] | None = "8c3d5e7f9012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "docs_native_doc_pages",
        sa.Column(
            "content_format",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'block'"),
        ),
    )
    op.execute(
        """
        UPDATE docs_native_doc_pages AS page
        SET content_format = doc.content_format
        FROM docs_native_docs AS doc
        WHERE page.doc_id = doc.id
        """
    )
    op.create_index(
        op.f("ix_docs_native_doc_pages_content_format"),
        "docs_native_doc_pages",
        ["content_format"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_docs_native_doc_pages_content_format",
        "docs_native_doc_pages",
        "content_format IN ('block', 'html')",
    )
    op.alter_column("docs_native_doc_pages", "content_format", server_default=None)

    op.drop_constraint("ck_docs_native_docs_content_format", "docs_native_docs", type_="check")
    op.drop_index(op.f("ix_docs_native_docs_content_format"), table_name="docs_native_docs")
    op.drop_column("docs_native_docs", "content_format")


def downgrade() -> None:
    op.add_column(
        "docs_native_docs",
        sa.Column(
            "content_format",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'block'"),
        ),
    )
    op.execute(
        """
        UPDATE docs_native_docs AS doc
        SET content_format = COALESCE(first_page.content_format, 'block')
        FROM (
            SELECT DISTINCT ON (doc_id) doc_id, content_format
            FROM docs_native_doc_pages
            WHERE trashed_at IS NULL
            ORDER BY doc_id, sort_order ASC, created_at ASC, id ASC
        ) AS first_page
        WHERE first_page.doc_id = doc.id
        """
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

    op.drop_constraint("ck_docs_native_doc_pages_content_format", "docs_native_doc_pages", type_="check")
    op.drop_index(op.f("ix_docs_native_doc_pages_content_format"), table_name="docs_native_doc_pages")
    op.drop_column("docs_native_doc_pages", "content_format")
