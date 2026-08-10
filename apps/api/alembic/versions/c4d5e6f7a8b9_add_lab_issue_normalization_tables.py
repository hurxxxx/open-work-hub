"""add_lab_issue_normalization_tables

Revision ID: c4d5e6f7a8b9
Revises: b9c8d7e6f5a4
Create Date: 2026-05-27 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = "b9c8d7e6f5a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "lab_issue_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("workbook_row_id", sa.String(length=36), nullable=True),
        sa.Column("record_key", sa.String(length=512), nullable=False),
        sa.Column("schema_version", sa.String(length=40), server_default="legacy_issue_v1", nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("source_path", sa.String(length=2048), nullable=False),
        sa.Column("sheet_name", sa.String(length=255), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("header_row_index", sa.Integer(), nullable=True),
        sa.Column("row_hash", sa.String(length=128), nullable=True),
        sa.Column("issue_no", sa.String(length=120), nullable=True),
        sa.Column("occurrence_date", sa.String(length=120), nullable=True),
        sa.Column("development_stage", sa.String(length=160), nullable=True),
        sa.Column("vehicle", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("classification", sa.String(length=255), nullable=True),
        sa.Column("subsystem", sa.String(length=255), nullable=True),
        sa.Column("symptom", sa.Text(), nullable=True),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("countermeasure", sa.Text(), nullable=True),
        sa.Column("action_owner", sa.String(length=255), nullable=True),
        sa.Column("action_status", sa.String(length=255), nullable=True),
        sa.Column("apply_status", sa.String(length=255), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("oem_open", sa.String(length=120), nullable=True),
        sa.Column("software_version", sa.String(length=255), nullable=True),
        sa.Column("issue_frequency", sa.String(length=255), nullable=True),
        sa.Column("issue_status", sa.String(length=255), nullable=True),
        sa.Column("attachment_note", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_fields", JSONB_COMPAT, nullable=True),
        sa.Column("normalized_fields", JSONB_COMPAT, nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["lab_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workbook_row_id"], ["lab_workbook_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "record_key", name="uq_lab_issue_records_dataset_record_key"),
    )
    op.create_index("ix_lab_issue_records_dataset_document", "lab_issue_records", ["dataset_id", "document_id"])
    op.create_index("ix_lab_issue_records_document_row", "lab_issue_records", ["document_id", "workbook_row_id"])
    op.create_index(
        "ix_lab_issue_records_lookup",
        "lab_issue_records",
        ["dataset_id", "vehicle", "category", "classification"],
    )
    op.create_index(op.f("ix_lab_issue_records_workspace_id"), "lab_issue_records", ["workspace_id"])
    op.create_index(op.f("ix_lab_issue_records_dataset_id"), "lab_issue_records", ["dataset_id"])
    op.create_index(op.f("ix_lab_issue_records_document_id"), "lab_issue_records", ["document_id"])
    op.create_index(op.f("ix_lab_issue_records_workbook_row_id"), "lab_issue_records", ["workbook_row_id"])
    op.create_index(op.f("ix_lab_issue_records_row_hash"), "lab_issue_records", ["row_hash"])

    op.create_table(
        "lab_issue_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("issue_record_id", sa.String(length=36), nullable=False),
        sa.Column("workbook_row_id", sa.String(length=36), nullable=True),
        sa.Column("embedded_object_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("attachment_kind", sa.String(length=60), server_default="embedded_object", nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=160), nullable=True),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("text_preview", sa.Text(), nullable=True),
        sa.Column("metadata", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["lab_artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dataset_id"], ["lab_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["lab_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["embedded_object_id"], ["lab_embedded_objects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_record_id"], ["lab_issue_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workbook_row_id"], ["lab_workbook_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issue_record_id",
            "embedded_object_id",
            name="uq_lab_issue_attachments_record_object",
        ),
    )
    op.create_index(
        "ix_lab_issue_attachments_dataset_document",
        "lab_issue_attachments",
        ["dataset_id", "document_id"],
    )
    op.create_index(
        "ix_lab_issue_attachments_record",
        "lab_issue_attachments",
        ["issue_record_id", "attachment_kind"],
    )
    op.create_index(op.f("ix_lab_issue_attachments_workspace_id"), "lab_issue_attachments", ["workspace_id"])
    op.create_index(op.f("ix_lab_issue_attachments_dataset_id"), "lab_issue_attachments", ["dataset_id"])
    op.create_index(op.f("ix_lab_issue_attachments_document_id"), "lab_issue_attachments", ["document_id"])
    op.create_index(op.f("ix_lab_issue_attachments_issue_record_id"), "lab_issue_attachments", ["issue_record_id"])
    op.create_index(op.f("ix_lab_issue_attachments_workbook_row_id"), "lab_issue_attachments", ["workbook_row_id"])
    op.create_index(
        op.f("ix_lab_issue_attachments_embedded_object_id"),
        "lab_issue_attachments",
        ["embedded_object_id"],
    )
    op.create_index(op.f("ix_lab_issue_attachments_artifact_id"), "lab_issue_attachments", ["artifact_id"])


def downgrade() -> None:
    op.drop_table("lab_issue_attachments")
    op.drop_table("lab_issue_records")
