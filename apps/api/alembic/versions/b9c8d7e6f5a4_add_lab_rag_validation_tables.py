"""add_lab_rag_validation_tables

Revision ID: b9c8d7e6f5a4
Revises: a8c5d3f1b2e4
Create Date: 2026-05-27 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b9c8d7e6f5a4"
down_revision: str | Sequence[str] | None = "a8c5d3f1b2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "lab_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("source_root", sa.String(length=2048), nullable=False),
        sa.Column("strategy", sa.String(length=40), server_default="raw_plus_structured", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="draft", nullable=False),
        sa.Column("stats", JSONB_COMPAT, nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_datasets_workspace_created", "lab_datasets", ["workspace_id", "created_at"])
    op.create_index(op.f("ix_lab_datasets_workspace_id"), "lab_datasets", ["workspace_id"])
    op.create_index(op.f("ix_lab_datasets_status"), "lab_datasets", ["status"])
    op.create_index(op.f("ix_lab_datasets_created_by_id"), "lab_datasets", ["created_by_id"])

    op.create_table(
        "lab_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=160), server_default="application/octet-stream", nullable=False),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("mtime_epoch", sa.Float(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=24), server_default="pending", nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedded_object_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("artifact_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "source_path", name="uq_lab_documents_dataset_source_path"),
    )
    op.create_index("ix_lab_documents_dataset_status", "lab_documents", ["dataset_id", "status", "updated_at"])
    op.create_index("ix_lab_documents_workspace_status", "lab_documents", ["workspace_id", "status", "updated_at"])
    op.create_index(op.f("ix_lab_documents_workspace_id"), "lab_documents", ["workspace_id"])
    op.create_index(op.f("ix_lab_documents_dataset_id"), "lab_documents", ["dataset_id"])
    op.create_index(op.f("ix_lab_documents_content_hash"), "lab_documents", ["content_hash"])
    op.create_index(op.f("ix_lab_documents_status"), "lab_documents", ["status"])

    op.create_table(
        "lab_workbook_sheets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sheet_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["lab_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "name", name="uq_lab_sheets_document_name"),
    )
    op.create_index("ix_lab_sheets_document_order", "lab_workbook_sheets", ["document_id", "sheet_index"])
    op.create_index(op.f("ix_lab_workbook_sheets_document_id"), "lab_workbook_sheets", ["document_id"])

    op.create_table(
        "lab_workbook_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("sheet_id", sa.String(length=36), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("cells", JSONB_COMPAT, nullable=True),
        sa.Column("row_text", sa.Text(), server_default="", nullable=False),
        sa.Column("has_issue_keywords", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("structured_data", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["lab_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sheet_id"], ["lab_workbook_sheets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "sheet_name", "row_index", name="uq_lab_rows_document_sheet_row"),
    )
    op.create_index("ix_lab_rows_document_sheet_row", "lab_workbook_rows", ["document_id", "sheet_name", "row_index"])
    op.create_index(op.f("ix_lab_workbook_rows_document_id"), "lab_workbook_rows", ["document_id"])
    op.create_index(op.f("ix_lab_workbook_rows_sheet_id"), "lab_workbook_rows", ["sheet_id"])

    op.create_table(
        "lab_embedded_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("workbook_row_id", sa.String(length=36), nullable=True),
        sa.Column("object_id", sa.String(length=160), nullable=False),
        sa.Column("object_number", sa.Integer(), nullable=True),
        sa.Column("object_type", sa.String(length=40), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("anchor", JSONB_COMPAT, nullable=True),
        sa.Column("row_match_method", sa.String(length=80), nullable=True),
        sa.Column("row_match_score", sa.Float(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["lab_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workbook_row_id"], ["lab_workbook_rows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "object_id", name="uq_lab_objects_document_object"),
    )
    op.create_index("ix_lab_objects_document_row", "lab_embedded_objects", ["document_id", "workbook_row_id"])
    op.create_index(op.f("ix_lab_embedded_objects_document_id"), "lab_embedded_objects", ["document_id"])
    op.create_index(op.f("ix_lab_embedded_objects_workbook_row_id"), "lab_embedded_objects", ["workbook_row_id"])
    op.create_index(op.f("ix_lab_embedded_objects_content_hash"), "lab_embedded_objects", ["content_hash"])

    op.create_table(
        "lab_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("workbook_row_id", sa.String(length=36), nullable=True),
        sa.Column("embedded_object_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("storage_provider", sa.String(length=40), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["lab_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["embedded_object_id"], ["lab_embedded_objects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workbook_row_id"], ["lab_workbook_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_artifacts_document_type", "lab_artifacts", ["document_id", "artifact_type"])
    op.create_index("ix_lab_artifacts_object_type", "lab_artifacts", ["embedded_object_id", "artifact_type"])
    op.create_index(op.f("ix_lab_artifacts_workspace_id"), "lab_artifacts", ["workspace_id"])
    op.create_index(op.f("ix_lab_artifacts_dataset_id"), "lab_artifacts", ["dataset_id"])
    op.create_index(op.f("ix_lab_artifacts_document_id"), "lab_artifacts", ["document_id"])
    op.create_index(op.f("ix_lab_artifacts_workbook_row_id"), "lab_artifacts", ["workbook_row_id"])
    op.create_index(op.f("ix_lab_artifacts_embedded_object_id"), "lab_artifacts", ["embedded_object_id"])
    op.create_index(op.f("ix_lab_artifacts_artifact_type"), "lab_artifacts", ["artifact_type"])
    op.create_index(op.f("ix_lab_artifacts_content_hash"), "lab_artifacts", ["content_hash"])

    op.create_table(
        "lab_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("workbook_row_id", sa.String(length=36), nullable=True),
        sa.Column("embedded_object_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("chunk_id", sa.String(length=255), nullable=False),
        sa.Column("chunk_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("strategy", sa.String(length=60), server_default="direct_local_v1", nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("index_text", sa.Text(), nullable=False),
        sa.Column("vector_status", sa.String(length=24), server_default="not_embedded", nullable=False),
        sa.Column("embedding_provider", sa.String(length=80), nullable=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("metadata", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["lab_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dataset_id"], ["lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["lab_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["embedded_object_id"], ["lab_embedded_objects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workbook_row_id"], ["lab_workbook_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_id", name="uq_lab_chunks_document_chunk"),
    )
    op.create_index("ix_lab_chunks_dataset_document", "lab_chunks", ["dataset_id", "document_id"])
    op.create_index("ix_lab_chunks_object", "lab_chunks", ["embedded_object_id", "chunk_index"])
    op.create_index("ix_lab_chunks_row", "lab_chunks", ["workbook_row_id", "chunk_index"])
    op.create_index(op.f("ix_lab_chunks_workspace_id"), "lab_chunks", ["workspace_id"])
    op.create_index(op.f("ix_lab_chunks_dataset_id"), "lab_chunks", ["dataset_id"])
    op.create_index(op.f("ix_lab_chunks_document_id"), "lab_chunks", ["document_id"])
    op.create_index(op.f("ix_lab_chunks_workbook_row_id"), "lab_chunks", ["workbook_row_id"])
    op.create_index(op.f("ix_lab_chunks_embedded_object_id"), "lab_chunks", ["embedded_object_id"])
    op.create_index(op.f("ix_lab_chunks_artifact_id"), "lab_chunks", ["artifact_id"])
    op.create_index(op.f("ix_lab_chunks_vector_status"), "lab_chunks", ["vector_status"])

    op.create_table(
        "lab_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=40), server_default="ingest", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("total_documents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_documents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_documents", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("stats", JSONB_COMPAT, nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_jobs_workspace_status", "lab_jobs", ["workspace_id", "status", "created_at"])
    op.create_index("ix_lab_jobs_dataset_status", "lab_jobs", ["dataset_id", "status", "created_at"])
    op.create_index(op.f("ix_lab_jobs_workspace_id"), "lab_jobs", ["workspace_id"])
    op.create_index(op.f("ix_lab_jobs_dataset_id"), "lab_jobs", ["dataset_id"])
    op.create_index(op.f("ix_lab_jobs_status"), "lab_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("lab_jobs")
    op.drop_table("lab_chunks")
    op.drop_table("lab_artifacts")
    op.drop_table("lab_embedded_objects")
    op.drop_table("lab_workbook_rows")
    op.drop_table("lab_workbook_sheets")
    op.drop_table("lab_documents")
    op.drop_table("lab_datasets")
