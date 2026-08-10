"""normalize_lab_ingestion_batch_schema

Revision ID: f1a2b3c4d5e6
Revises: e6f7a8b9c0d1
Create Date: 2026-05-28 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RENAMED_COLUMNS: tuple[str, ...] = (
    "lab_documents",
    "lab_artifacts",
    "lab_chunks",
    "lab_jobs",
    "lab_issue_records",
    "lab_issue_attachments",
)


CONSTRAINT_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("lab_ingestion_batches", "lab_datasets_pkey", "lab_ingestion_batches_pkey"),
    (
        "lab_ingestion_batches",
        "lab_datasets_workspace_id_fkey",
        "lab_ingestion_batches_workspace_id_fkey",
    ),
    (
        "lab_ingestion_batches",
        "lab_datasets_created_by_id_fkey",
        "lab_ingestion_batches_created_by_id_fkey",
    ),
    (
        "lab_documents",
        "lab_documents_dataset_id_fkey",
        "lab_documents_ingestion_batch_id_fkey",
    ),
    (
        "lab_documents",
        "uq_lab_documents_dataset_source_path",
        "uq_lab_documents_ingestion_batch_source_path",
    ),
    (
        "lab_artifacts",
        "lab_artifacts_dataset_id_fkey",
        "lab_artifacts_ingestion_batch_id_fkey",
    ),
    (
        "lab_chunks",
        "lab_chunks_dataset_id_fkey",
        "lab_chunks_ingestion_batch_id_fkey",
    ),
    (
        "lab_jobs",
        "lab_jobs_dataset_id_fkey",
        "lab_jobs_ingestion_batch_id_fkey",
    ),
    (
        "lab_issue_records",
        "lab_issue_records_dataset_id_fkey",
        "lab_issue_records_ingestion_batch_id_fkey",
    ),
    (
        "lab_issue_records",
        "uq_lab_issue_records_dataset_record_key",
        "uq_lab_issue_records_ingestion_batch_record_key",
    ),
    (
        "lab_issue_attachments",
        "lab_issue_attachments_dataset_id_fkey",
        "lab_issue_attachments_ingestion_batch_id_fkey",
    ),
)


INDEX_RENAMES: tuple[tuple[str, str], ...] = (
    ("ix_lab_datasets_workspace_created", "ix_lab_ingestion_batches_workspace_created"),
    ("ix_lab_datasets_workspace_id", "ix_lab_ingestion_batches_workspace_id"),
    ("ix_lab_datasets_status", "ix_lab_ingestion_batches_status"),
    ("ix_lab_datasets_created_by_id", "ix_lab_ingestion_batches_created_by_id"),
    ("ix_lab_documents_dataset_status", "ix_lab_documents_ingestion_batch_status"),
    ("ix_lab_documents_dataset_id", "ix_lab_documents_ingestion_batch_id"),
    ("ix_lab_artifacts_dataset_id", "ix_lab_artifacts_ingestion_batch_id"),
    ("ix_lab_chunks_dataset_document", "ix_lab_chunks_ingestion_batch_document"),
    ("ix_lab_chunks_dataset_id", "ix_lab_chunks_ingestion_batch_id"),
    ("ix_lab_jobs_dataset_status", "ix_lab_jobs_ingestion_batch_status"),
    ("ix_lab_jobs_dataset_id", "ix_lab_jobs_ingestion_batch_id"),
    (
        "ix_lab_issue_records_dataset_document",
        "ix_lab_issue_records_ingestion_batch_document",
    ),
    ("ix_lab_issue_records_lookup", "ix_lab_issue_records_batch_lookup"),
    ("ix_lab_issue_records_dataset_id", "ix_lab_issue_records_ingestion_batch_id"),
    (
        "ix_lab_issue_attachments_dataset_document",
        "ix_lab_issue_attachments_ingestion_batch_document",
    ),
    (
        "ix_lab_issue_attachments_dataset_id",
        "ix_lab_issue_attachments_ingestion_batch_id",
    ),
)


def upgrade() -> None:
    op.rename_table("lab_datasets", "lab_ingestion_batches")
    for table_name in RENAMED_COLUMNS:
        op.alter_column(table_name, "dataset_id", new_column_name="ingestion_batch_id")
    for table_name, old_name, new_name in CONSTRAINT_RENAMES:
        op.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"')
    for old_name, new_name in INDEX_RENAMES:
        op.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')


def downgrade() -> None:
    for old_name, new_name in reversed(INDEX_RENAMES):
        op.execute(f'ALTER INDEX "{new_name}" RENAME TO "{old_name}"')
    for table_name, old_name, new_name in reversed(CONSTRAINT_RENAMES):
        op.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{new_name}" TO "{old_name}"')
    for table_name in RENAMED_COLUMNS:
        op.alter_column(table_name, "ingestion_batch_id", new_column_name="dataset_id")
    op.rename_table("lab_ingestion_batches", "lab_datasets")
