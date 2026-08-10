"""add_qna_documents

Revision ID: a9b8c7d6e5f4
Revises: a7b8c9d0e1f2
Create Date: 2026-06-09 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a9b8c7d6e5f4"
down_revision: str | Sequence[str] | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _create_index_once(index_name: str, columns: list[str]) -> None:
    if not _index_exists("qna_documents", index_name):
        op.create_index(index_name, "qna_documents", columns)


def upgrade() -> None:
    if not _table_exists("qna_documents"):
        op.create_table(
            "qna_documents",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column("external_id", sa.String(length=256), nullable=False),
            sa.Column("title", sa.String(length=512), nullable=False),
            sa.Column(
                "category",
                sa.String(length=120),
                server_default=sa.text("'일반'"),
                nullable=False,
            ),
            sa.Column("author", sa.String(length=160), nullable=True),
            sa.Column("posted_at", sa.String(length=40), nullable=True),
            sa.Column("body_text", sa.Text(), server_default=sa.text("''"), nullable=False),
            sa.Column("attachments", JSONB, nullable=True),
            sa.Column("char_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("content_checksum", sa.String(length=128), nullable=True),
            sa.Column("uploaded_by", sa.String(length=36), nullable=True),
            sa.Column("mime_type", sa.String(length=160), nullable=True),
            sa.Column(
                "rag_status",
                sa.String(length=24),
                server_default=sa.text("'pending'"),
                nullable=False,
            ),
            sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("indexed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "workspace_id", "kind", "external_id", name="uq_qna_doc_workspace_kind_external"
            ),
        )
    _create_index_once("ix_qna_documents_workspace_id", ["workspace_id"])
    _create_index_once("ix_qna_documents_workspace_kind", ["workspace_id", "kind"])
    _create_index_once("ix_qna_documents_content_checksum", ["content_checksum"])
    _create_index_once("ix_qna_documents_uploaded_by", ["uploaded_by"])


def downgrade() -> None:
    if not _table_exists("qna_documents"):
        return
    for index_name in (
        "ix_qna_documents_uploaded_by",
        "ix_qna_documents_content_checksum",
        "ix_qna_documents_workspace_kind",
        "ix_qna_documents_workspace_id",
    ):
        if _index_exists("qna_documents", index_name):
            op.drop_index(index_name, table_name="qna_documents")
    op.drop_table("qna_documents")
