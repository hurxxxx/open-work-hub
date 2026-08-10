"""rename_lab_schema_to_legacy_issues

Revision ID: a2b4c6d8e0f1
Revises: f1a2b3c4d5e6
Create Date: 2026-06-01 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "a2b4c6d8e0f1"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_RENAMES: tuple[tuple[str, str], ...] = (
    ("lab_ingestion_batches", "legacy_issue_datasets"),
    ("lab_documents", "legacy_issue_documents"),
    ("lab_workbook_sheets", "legacy_issue_workbook_sheets"),
    ("lab_workbook_rows", "legacy_issue_workbook_rows"),
    ("lab_embedded_objects", "legacy_issue_embedded_objects"),
    ("lab_artifacts", "legacy_issue_artifacts"),
    ("lab_issue_records", "legacy_issue_records"),
    ("lab_issue_attachments", "legacy_issue_attachments"),
    ("lab_chunks", "legacy_issue_chunks"),
    ("lab_jobs", "legacy_issue_jobs"),
)


DATASET_COLUMN_TABLES: tuple[str, ...] = (
    "legacy_issue_documents",
    "legacy_issue_artifacts",
    "legacy_issue_records",
    "legacy_issue_attachments",
    "legacy_issue_chunks",
    "legacy_issue_jobs",
)


CONSTRAINT_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("legacy_issue_datasets", "lab_ingestion_batches_pkey", "legacy_issue_datasets_pkey"),
    (
        "legacy_issue_datasets",
        "lab_ingestion_batches_workspace_id_fkey",
        "legacy_issue_datasets_workspace_id_fkey",
    ),
    (
        "legacy_issue_datasets",
        "lab_ingestion_batches_created_by_id_fkey",
        "legacy_issue_datasets_created_by_id_fkey",
    ),
    ("legacy_issue_documents", "lab_documents_pkey", "legacy_issue_documents_pkey"),
    (
        "legacy_issue_documents",
        "lab_documents_workspace_id_fkey",
        "legacy_issue_documents_workspace_id_fkey",
    ),
    (
        "legacy_issue_documents",
        "lab_documents_ingestion_batch_id_fkey",
        "legacy_issue_documents_dataset_id_fkey",
    ),
    (
        "legacy_issue_documents",
        "fk_lab_documents_duplicate_of_document_id_lab_documents",
        "fk_legacy_issue_documents_duplicate_of_document_id_legacy_issue_documents",
    ),
    (
        "legacy_issue_documents",
        "uq_lab_documents_ingestion_batch_source_path",
        "uq_legacy_issue_documents_dataset_source_path",
    ),
    ("legacy_issue_workbook_sheets", "lab_workbook_sheets_pkey", "legacy_issue_workbook_sheets_pkey"),
    (
        "legacy_issue_workbook_sheets",
        "lab_workbook_sheets_document_id_fkey",
        "legacy_issue_workbook_sheets_document_id_fkey",
    ),
    (
        "legacy_issue_workbook_sheets",
        "uq_lab_sheets_document_name",
        "uq_legacy_issue_sheets_document_name",
    ),
    ("legacy_issue_workbook_rows", "lab_workbook_rows_pkey", "legacy_issue_workbook_rows_pkey"),
    (
        "legacy_issue_workbook_rows",
        "lab_workbook_rows_document_id_fkey",
        "legacy_issue_workbook_rows_document_id_fkey",
    ),
    (
        "legacy_issue_workbook_rows",
        "lab_workbook_rows_sheet_id_fkey",
        "legacy_issue_workbook_rows_sheet_id_fkey",
    ),
    (
        "legacy_issue_workbook_rows",
        "uq_lab_rows_document_sheet_row",
        "uq_legacy_issue_rows_document_sheet_row",
    ),
    ("legacy_issue_embedded_objects", "lab_embedded_objects_pkey", "legacy_issue_embedded_objects_pkey"),
    (
        "legacy_issue_embedded_objects",
        "lab_embedded_objects_document_id_fkey",
        "legacy_issue_embedded_objects_document_id_fkey",
    ),
    (
        "legacy_issue_embedded_objects",
        "lab_embedded_objects_workbook_row_id_fkey",
        "legacy_issue_embedded_objects_workbook_row_id_fkey",
    ),
    (
        "legacy_issue_embedded_objects",
        "uq_lab_objects_document_object",
        "uq_legacy_issue_objects_document_object",
    ),
    ("legacy_issue_artifacts", "lab_artifacts_pkey", "legacy_issue_artifacts_pkey"),
    (
        "legacy_issue_artifacts",
        "lab_artifacts_workspace_id_fkey",
        "legacy_issue_artifacts_workspace_id_fkey",
    ),
    (
        "legacy_issue_artifacts",
        "lab_artifacts_ingestion_batch_id_fkey",
        "legacy_issue_artifacts_dataset_id_fkey",
    ),
    (
        "legacy_issue_artifacts",
        "lab_artifacts_document_id_fkey",
        "legacy_issue_artifacts_document_id_fkey",
    ),
    (
        "legacy_issue_artifacts",
        "lab_artifacts_workbook_row_id_fkey",
        "legacy_issue_artifacts_workbook_row_id_fkey",
    ),
    (
        "legacy_issue_artifacts",
        "lab_artifacts_embedded_object_id_fkey",
        "legacy_issue_artifacts_embedded_object_id_fkey",
    ),
    ("legacy_issue_records", "lab_issue_records_pkey", "legacy_issue_records_pkey"),
    (
        "legacy_issue_records",
        "lab_issue_records_workspace_id_fkey",
        "legacy_issue_records_workspace_id_fkey",
    ),
    (
        "legacy_issue_records",
        "lab_issue_records_ingestion_batch_id_fkey",
        "legacy_issue_records_dataset_id_fkey",
    ),
    (
        "legacy_issue_records",
        "lab_issue_records_document_id_fkey",
        "legacy_issue_records_document_id_fkey",
    ),
    (
        "legacy_issue_records",
        "lab_issue_records_workbook_row_id_fkey",
        "legacy_issue_records_workbook_row_id_fkey",
    ),
    (
        "legacy_issue_records",
        "uq_lab_issue_records_ingestion_batch_record_key",
        "uq_legacy_issue_records_dataset_record_key",
    ),
    ("legacy_issue_attachments", "lab_issue_attachments_pkey", "legacy_issue_attachments_pkey"),
    (
        "legacy_issue_attachments",
        "lab_issue_attachments_workspace_id_fkey",
        "legacy_issue_attachments_workspace_id_fkey",
    ),
    (
        "legacy_issue_attachments",
        "lab_issue_attachments_ingestion_batch_id_fkey",
        "legacy_issue_attachments_dataset_id_fkey",
    ),
    (
        "legacy_issue_attachments",
        "lab_issue_attachments_document_id_fkey",
        "legacy_issue_attachments_document_id_fkey",
    ),
    (
        "legacy_issue_attachments",
        "lab_issue_attachments_issue_record_id_fkey",
        "legacy_issue_attachments_issue_record_id_fkey",
    ),
    (
        "legacy_issue_attachments",
        "lab_issue_attachments_workbook_row_id_fkey",
        "legacy_issue_attachments_workbook_row_id_fkey",
    ),
    (
        "legacy_issue_attachments",
        "lab_issue_attachments_embedded_object_id_fkey",
        "legacy_issue_attachments_embedded_object_id_fkey",
    ),
    (
        "legacy_issue_attachments",
        "lab_issue_attachments_artifact_id_fkey",
        "legacy_issue_attachments_artifact_id_fkey",
    ),
    (
        "legacy_issue_attachments",
        "uq_lab_issue_attachments_record_object",
        "uq_legacy_issue_attachments_record_object",
    ),
    ("legacy_issue_chunks", "lab_chunks_pkey", "legacy_issue_chunks_pkey"),
    (
        "legacy_issue_chunks",
        "lab_chunks_workspace_id_fkey",
        "legacy_issue_chunks_workspace_id_fkey",
    ),
    (
        "legacy_issue_chunks",
        "lab_chunks_ingestion_batch_id_fkey",
        "legacy_issue_chunks_dataset_id_fkey",
    ),
    (
        "legacy_issue_chunks",
        "lab_chunks_document_id_fkey",
        "legacy_issue_chunks_document_id_fkey",
    ),
    (
        "legacy_issue_chunks",
        "lab_chunks_workbook_row_id_fkey",
        "legacy_issue_chunks_workbook_row_id_fkey",
    ),
    (
        "legacy_issue_chunks",
        "lab_chunks_embedded_object_id_fkey",
        "legacy_issue_chunks_embedded_object_id_fkey",
    ),
    (
        "legacy_issue_chunks",
        "lab_chunks_artifact_id_fkey",
        "legacy_issue_chunks_artifact_id_fkey",
    ),
    (
        "legacy_issue_chunks",
        "uq_lab_chunks_document_chunk",
        "uq_legacy_issue_chunks_document_chunk",
    ),
    ("legacy_issue_jobs", "lab_jobs_pkey", "legacy_issue_jobs_pkey"),
    (
        "legacy_issue_jobs",
        "lab_jobs_workspace_id_fkey",
        "legacy_issue_jobs_workspace_id_fkey",
    ),
    (
        "legacy_issue_jobs",
        "lab_jobs_ingestion_batch_id_fkey",
        "legacy_issue_jobs_dataset_id_fkey",
    ),
)


INDEX_RENAMES: tuple[tuple[str, str], ...] = (
    ("ix_lab_ingestion_batches_workspace_created", "ix_legacy_issue_datasets_workspace_created"),
    ("ix_lab_ingestion_batches_workspace_id", "ix_legacy_issue_datasets_workspace_id"),
    ("ix_lab_ingestion_batches_status", "ix_legacy_issue_datasets_status"),
    ("ix_lab_ingestion_batches_created_by_id", "ix_legacy_issue_datasets_created_by_id"),
    ("ix_lab_documents_workspace_status", "ix_legacy_issue_documents_workspace_status"),
    ("ix_lab_documents_ingestion_batch_status", "ix_legacy_issue_documents_dataset_status"),
    ("ix_lab_documents_workspace_id", "ix_legacy_issue_documents_workspace_id"),
    ("ix_lab_documents_ingestion_batch_id", "ix_legacy_issue_documents_dataset_id"),
    ("ix_lab_documents_content_hash", "ix_legacy_issue_documents_content_hash"),
    ("ix_lab_documents_status", "ix_legacy_issue_documents_status"),
    ("ix_lab_documents_duplicate_of_document_id", "ix_legacy_issue_documents_duplicate_of_document_id"),
    ("ix_lab_sheets_document_order", "ix_legacy_issue_sheets_document_order"),
    ("ix_lab_workbook_sheets_document_id", "ix_legacy_issue_workbook_sheets_document_id"),
    ("ix_lab_rows_document_sheet_row", "ix_legacy_issue_rows_document_sheet_row"),
    ("ix_lab_workbook_rows_document_id", "ix_legacy_issue_workbook_rows_document_id"),
    ("ix_lab_workbook_rows_sheet_id", "ix_legacy_issue_workbook_rows_sheet_id"),
    ("ix_lab_objects_document_row", "ix_legacy_issue_objects_document_row"),
    ("ix_lab_embedded_objects_document_id", "ix_legacy_issue_embedded_objects_document_id"),
    ("ix_lab_embedded_objects_workbook_row_id", "ix_legacy_issue_embedded_objects_workbook_row_id"),
    ("ix_lab_embedded_objects_content_hash", "ix_legacy_issue_embedded_objects_content_hash"),
    ("ix_lab_artifacts_document_type", "ix_legacy_issue_artifacts_document_type"),
    ("ix_lab_artifacts_object_type", "ix_legacy_issue_artifacts_object_type"),
    ("ix_lab_artifacts_workspace_id", "ix_legacy_issue_artifacts_workspace_id"),
    ("ix_lab_artifacts_ingestion_batch_id", "ix_legacy_issue_artifacts_dataset_id"),
    ("ix_lab_artifacts_document_id", "ix_legacy_issue_artifacts_document_id"),
    ("ix_lab_artifacts_workbook_row_id", "ix_legacy_issue_artifacts_workbook_row_id"),
    ("ix_lab_artifacts_embedded_object_id", "ix_legacy_issue_artifacts_embedded_object_id"),
    ("ix_lab_artifacts_artifact_type", "ix_legacy_issue_artifacts_artifact_type"),
    ("ix_lab_artifacts_content_hash", "ix_legacy_issue_artifacts_content_hash"),
    ("ix_lab_issue_records_ingestion_batch_document", "ix_legacy_issue_records_dataset_document"),
    ("ix_lab_issue_records_document_row", "ix_legacy_issue_records_document_row"),
    ("ix_lab_issue_records_batch_lookup", "ix_legacy_issue_records_dataset_lookup"),
    ("ix_lab_issue_records_workspace_id", "ix_legacy_issue_records_workspace_id"),
    ("ix_lab_issue_records_ingestion_batch_id", "ix_legacy_issue_records_dataset_id"),
    ("ix_lab_issue_records_document_id", "ix_legacy_issue_records_document_id"),
    ("ix_lab_issue_records_workbook_row_id", "ix_legacy_issue_records_workbook_row_id"),
    ("ix_lab_issue_records_row_hash", "ix_legacy_issue_records_row_hash"),
    ("ix_lab_issue_attachments_ingestion_batch_document", "ix_legacy_issue_attachments_dataset_document"),
    ("ix_lab_issue_attachments_record", "ix_legacy_issue_attachments_record"),
    ("ix_lab_issue_attachments_workspace_id", "ix_legacy_issue_attachments_workspace_id"),
    ("ix_lab_issue_attachments_ingestion_batch_id", "ix_legacy_issue_attachments_dataset_id"),
    ("ix_lab_issue_attachments_document_id", "ix_legacy_issue_attachments_document_id"),
    ("ix_lab_issue_attachments_issue_record_id", "ix_legacy_issue_attachments_issue_record_id"),
    ("ix_lab_issue_attachments_workbook_row_id", "ix_legacy_issue_attachments_workbook_row_id"),
    ("ix_lab_issue_attachments_embedded_object_id", "ix_legacy_issue_attachments_embedded_object_id"),
    ("ix_lab_issue_attachments_artifact_id", "ix_legacy_issue_attachments_artifact_id"),
    ("ix_lab_chunks_ingestion_batch_document", "ix_legacy_issue_chunks_dataset_document"),
    ("ix_lab_chunks_object", "ix_legacy_issue_chunks_object"),
    ("ix_lab_chunks_row", "ix_legacy_issue_chunks_row"),
    ("ix_lab_chunks_workspace_id", "ix_legacy_issue_chunks_workspace_id"),
    ("ix_lab_chunks_ingestion_batch_id", "ix_legacy_issue_chunks_dataset_id"),
    ("ix_lab_chunks_document_id", "ix_legacy_issue_chunks_document_id"),
    ("ix_lab_chunks_workbook_row_id", "ix_legacy_issue_chunks_workbook_row_id"),
    ("ix_lab_chunks_embedded_object_id", "ix_legacy_issue_chunks_embedded_object_id"),
    ("ix_lab_chunks_artifact_id", "ix_legacy_issue_chunks_artifact_id"),
    ("ix_lab_chunks_vector_status", "ix_legacy_issue_chunks_vector_status"),
    ("ix_lab_jobs_workspace_status", "ix_legacy_issue_jobs_workspace_status"),
    ("ix_lab_jobs_ingestion_batch_status", "ix_legacy_issue_jobs_dataset_status"),
    ("ix_lab_jobs_workspace_id", "ix_legacy_issue_jobs_workspace_id"),
    ("ix_lab_jobs_ingestion_batch_id", "ix_legacy_issue_jobs_dataset_id"),
    ("ix_lab_jobs_status", "ix_legacy_issue_jobs_status"),
)


def _rename_constraint(table_name: str, old_name: str, new_name: str) -> None:
    op.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"')


def _rename_index(old_name: str, new_name: str) -> None:
    op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')


def upgrade() -> None:
    for old_name, new_name in TABLE_RENAMES:
        op.rename_table(old_name, new_name)
    for table_name in DATASET_COLUMN_TABLES:
        op.alter_column(table_name, "ingestion_batch_id", new_column_name="dataset_id")
    for table_name, old_name, new_name in CONSTRAINT_RENAMES:
        _rename_constraint(table_name, old_name, new_name)
    for old_name, new_name in INDEX_RENAMES:
        _rename_index(old_name, new_name)


def downgrade() -> None:
    for old_name, new_name in reversed(INDEX_RENAMES):
        _rename_index(new_name, old_name)
    for table_name, old_name, new_name in reversed(CONSTRAINT_RENAMES):
        _rename_constraint(table_name, new_name, old_name)
    for table_name in reversed(DATASET_COLUMN_TABLES):
        op.alter_column(table_name, "dataset_id", new_column_name="ingestion_batch_id")
    for old_name, new_name in reversed(TABLE_RENAMES):
        op.rename_table(new_name, old_name)
