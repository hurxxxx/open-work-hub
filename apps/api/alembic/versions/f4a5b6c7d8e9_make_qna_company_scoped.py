"""make qna company scoped

Revision ID: f4a5b6c7d8e9
Revises: e2c4f6a8b0d3
Create Date: 2026-06-23 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: str | Sequence[str] | None = "e2c4f6a8b0d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if _table_exists("qna_documents"):
        _upgrade_qna_documents()
    if _table_exists("rag_sync_jobs"):
        _upgrade_rag_sync_jobs()


def downgrade() -> None:
    if _table_exists("rag_sync_jobs"):
        _downgrade_rag_sync_jobs()
    if _table_exists("qna_documents"):
        _downgrade_qna_documents()


def _upgrade_qna_documents() -> None:
    if not _column_exists("qna_documents", "scope_kind"):
        op.add_column(
            "qna_documents",
            sa.Column(
                "scope_kind",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'company'"),
            ),
        )
    if not _column_exists("qna_documents", "storage_key"):
        op.add_column(
            "qna_documents",
            sa.Column("storage_key", sa.String(length=1024), nullable=True),
        )
    op.execute("UPDATE qna_documents SET scope_kind = 'company' WHERE scope_kind IS NULL")
    op.alter_column(
        "qna_documents",
        "workspace_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.execute(
        """
        UPDATE qna_documents
        SET workspace_id = NULL
        WHERE scope_kind = 'company'
        """
    )
    if _unique_constraint_exists("qna_documents", "uq_qna_doc_workspace_kind_external"):
        op.drop_constraint(
            "uq_qna_doc_workspace_kind_external",
            "qna_documents",
            type_="unique",
        )
    if not _unique_constraint_exists("qna_documents", "uq_qna_doc_scope_kind_external"):
        op.create_unique_constraint(
            "uq_qna_doc_scope_kind_external",
            "qna_documents",
            ["scope_kind", "kind", "external_id"],
        )
    if not _index_exists("qna_documents", "ix_qna_documents_scope_kind"):
        op.create_index("ix_qna_documents_scope_kind", "qna_documents", ["scope_kind"])
    if not _index_exists("qna_documents", "ix_qna_documents_scope_kind_kind"):
        op.create_index(
            "ix_qna_documents_scope_kind_kind",
            "qna_documents",
            ["scope_kind", "kind"],
        )


def _upgrade_rag_sync_jobs() -> None:
    if not _column_exists("rag_sync_jobs", "scope_kind"):
        op.add_column(
            "rag_sync_jobs",
            sa.Column(
                "scope_kind",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'workspace'"),
            ),
        )
    op.execute(
        """
        UPDATE rag_sync_jobs
        SET scope_kind = 'workspace'
        WHERE scope_kind IS NULL
        """
    )
    op.alter_column(
        "rag_sync_jobs",
        "workspace_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.execute(
        """
        UPDATE rag_sync_jobs
        SET scope_kind = 'company', workspace_id = NULL
        WHERE resource_type = 'qna_document'
        """
    )
    if _table_exists("qna_documents"):
        _enqueue_qna_company_backfill()
    if not _check_constraint_exists("rag_sync_jobs", "ck_rag_sync_jobs_scope_kind"):
        op.create_check_constraint(
            "ck_rag_sync_jobs_scope_kind",
            "rag_sync_jobs",
            "scope_kind IN ('workspace','company')",
        )
    if not _index_exists("rag_sync_jobs", "ix_rag_sync_jobs_scope_kind"):
        op.create_index("ix_rag_sync_jobs_scope_kind", "rag_sync_jobs", ["scope_kind"])
    if _index_exists("rag_sync_jobs", "ix_rag_sync_jobs_workspace_lane_status_retry"):
        op.drop_index("ix_rag_sync_jobs_workspace_lane_status_retry", table_name="rag_sync_jobs")
    op.create_index(
        "ix_rag_sync_jobs_workspace_lane_status_retry",
        "rag_sync_jobs",
        ["scope_kind", "workspace_id", "lane", "status", "next_retry_at"],
    )
    if _index_exists("rag_sync_jobs", "uq_rag_sync_jobs_pending_resource_lane"):
        op.drop_index("uq_rag_sync_jobs_pending_resource_lane", table_name="rag_sync_jobs")
    if not _index_exists("rag_sync_jobs", "uq_rag_sync_jobs_pending_workspace_resource_lane"):
        op.create_index(
            "uq_rag_sync_jobs_pending_workspace_resource_lane",
            "rag_sync_jobs",
            ["scope_kind", "workspace_id", "lane", "resource_type", "resource_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending' AND workspace_id IS NOT NULL"),
            sqlite_where=sa.text("status = 'pending' AND workspace_id IS NOT NULL"),
        )
    if not _index_exists("rag_sync_jobs", "uq_rag_sync_jobs_pending_company_resource_lane"):
        op.create_index(
            "uq_rag_sync_jobs_pending_company_resource_lane",
            "rag_sync_jobs",
            ["scope_kind", "lane", "resource_type", "resource_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending' AND workspace_id IS NULL"),
            sqlite_where=sa.text("status = 'pending' AND workspace_id IS NULL"),
        )


def _downgrade_rag_sync_jobs() -> None:
    if _table_exists("qna_documents"):
        op.execute(
            """
            DELETE FROM rag_sync_jobs
            WHERE resource_type = 'qna_document'
              AND scope_kind = 'company'
              AND lane = 'backfill'
              AND status = 'pending'
              AND workspace_id IS NULL
              AND id IN (
                SELECT (
                  substring(digest for 8) || '-' ||
                  substring(digest from 9 for 4) || '-' ||
                  substring(digest from 13 for 4) || '-' ||
                  substring(digest from 17 for 4) || '-' ||
                  substring(digest from 21 for 12)
                )
                FROM (
                  SELECT md5(id || '-qna-company-scope-backfill') AS digest
                  FROM qna_documents
                ) qna_backfill_ids
              )
            """
        )
    for index_name in (
        "uq_rag_sync_jobs_pending_company_resource_lane",
        "uq_rag_sync_jobs_pending_workspace_resource_lane",
    ):
        if _index_exists("rag_sync_jobs", index_name):
            op.drop_index(index_name, table_name="rag_sync_jobs")
    _assign_null_rag_workspaces()
    if _index_exists("rag_sync_jobs", "ix_rag_sync_jobs_workspace_lane_status_retry"):
        op.drop_index("ix_rag_sync_jobs_workspace_lane_status_retry", table_name="rag_sync_jobs")
    op.create_index(
        "ix_rag_sync_jobs_workspace_lane_status_retry",
        "rag_sync_jobs",
        ["workspace_id", "lane", "status", "next_retry_at"],
    )
    if not _index_exists("rag_sync_jobs", "uq_rag_sync_jobs_pending_resource_lane"):
        op.create_index(
            "uq_rag_sync_jobs_pending_resource_lane",
            "rag_sync_jobs",
            ["workspace_id", "lane", "resource_type", "resource_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
            sqlite_where=sa.text("status = 'pending'"),
        )
    if _check_constraint_exists("rag_sync_jobs", "ck_rag_sync_jobs_scope_kind"):
        op.drop_constraint("ck_rag_sync_jobs_scope_kind", "rag_sync_jobs", type_="check")
    op.alter_column(
        "rag_sync_jobs",
        "workspace_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    if _index_exists("rag_sync_jobs", "ix_rag_sync_jobs_scope_kind"):
        op.drop_index("ix_rag_sync_jobs_scope_kind", table_name="rag_sync_jobs")
    if _column_exists("rag_sync_jobs", "scope_kind"):
        op.drop_column("rag_sync_jobs", "scope_kind")


def _downgrade_qna_documents() -> None:
    _assign_null_qna_workspaces()
    if _unique_constraint_exists("qna_documents", "uq_qna_doc_scope_kind_external"):
        op.drop_constraint("uq_qna_doc_scope_kind_external", "qna_documents", type_="unique")
    if not _unique_constraint_exists("qna_documents", "uq_qna_doc_workspace_kind_external"):
        op.create_unique_constraint(
            "uq_qna_doc_workspace_kind_external",
            "qna_documents",
            ["workspace_id", "kind", "external_id"],
        )
    op.alter_column(
        "qna_documents",
        "workspace_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    for index_name in ("ix_qna_documents_scope_kind_kind", "ix_qna_documents_scope_kind"):
        if _index_exists("qna_documents", index_name):
            op.drop_index(index_name, table_name="qna_documents")
    if _column_exists("qna_documents", "storage_key"):
        op.drop_column("qna_documents", "storage_key")
    if _column_exists("qna_documents", "scope_kind"):
        op.drop_column("qna_documents", "scope_kind")


def _assign_null_qna_workspaces() -> None:
    op.execute(
        """
        UPDATE qna_documents
        SET workspace_id = (SELECT id FROM workspaces ORDER BY name ASC LIMIT 1)
        WHERE workspace_id IS NULL
        """
    )


def _assign_null_rag_workspaces() -> None:
    op.execute(
        """
        UPDATE rag_sync_jobs
        SET workspace_id = (SELECT id FROM workspaces ORDER BY name ASC LIMIT 1)
        WHERE workspace_id IS NULL
        """
    )


def _enqueue_qna_company_backfill() -> None:
    op.execute(
        """
        WITH qna_backfill AS (
          SELECT
            qna_documents.id AS resource_id,
            qna_documents.content_checksum AS content_checksum,
            md5(qna_documents.id || '-qna-company-scope-backfill') AS digest
          FROM qna_documents
          WHERE qna_documents.scope_kind = 'company'
            AND COALESCE(qna_documents.body_text, '') <> ''
            AND NOT EXISTS (
              SELECT 1
              FROM rag_sync_jobs existing_pending
              WHERE existing_pending.scope_kind = 'company'
                AND existing_pending.workspace_id IS NULL
                AND existing_pending.lane = 'backfill'
                AND existing_pending.resource_type = 'qna_document'
                AND existing_pending.resource_id = qna_documents.id
                AND existing_pending.status = 'pending'
            )
        )
        INSERT INTO rag_sync_jobs (
          id,
          scope_kind,
          workspace_id,
          lane,
          resource_type,
          resource_id,
          operation,
          content_checksum,
          status,
          attempts,
          created_at,
          updated_at
        )
        SELECT
          substring(digest for 8) || '-' ||
            substring(digest from 9 for 4) || '-' ||
            substring(digest from 13 for 4) || '-' ||
            substring(digest from 17 for 4) || '-' ||
            substring(digest from 21 for 12),
          'company',
          NULL,
          'backfill',
          'qna_document',
          resource_id,
          'upsert',
          content_checksum,
          'pending',
          0,
          CURRENT_TIMESTAMP,
          CURRENT_TIMESTAMP
        FROM qna_backfill
        WHERE NOT EXISTS (
          SELECT 1
          FROM rag_sync_jobs existing_id
          WHERE existing_id.id = (
            substring(qna_backfill.digest for 8) || '-' ||
            substring(qna_backfill.digest from 9 for 4) || '-' ||
            substring(qna_backfill.digest from 13 for 4) || '-' ||
            substring(qna_backfill.digest from 17 for 4) || '-' ||
            substring(qna_backfill.digest from 21 for 12)
          )
        )
        """
    )


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _unique_constraint_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        constraint["name"] == constraint_name
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)
    )


def _check_constraint_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        constraint["name"] == constraint_name
        for constraint in sa.inspect(op.get_bind()).get_check_constraints(table_name)
    )
