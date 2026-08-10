"""enqueue missing qna rag sync jobs

Revision ID: e1b2c3d4e5f6
Revises: e0a1b2c3d4f5
Create Date: 2026-06-22 00:00:00.000000

Some migrated Q&A board documents exist as ``qna_documents`` rows with
``rag_status='pending'`` but without a corresponding ``rag_sync_jobs`` row.
The assistant can list those documents, but grounded Q&A returns no hits until
they are indexed. This repair is idempotent and only queues documents with
extractable text.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e0a1b2c3d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "qna_documents") or not _table_exists(bind, "rag_sync_jobs"):
        return

    op.execute(
        sa.text(
            """
            UPDATE qna_documents
            SET
                rag_status = 'skipped',
                last_error = 'no extractable text',
                updated_at = now()
            WHERE rag_status = 'pending'
              AND COALESCE(NULLIF(body_text, ''), '') = ''
            """
        )
    )

    op.execute(
        sa.text(
            """
            INSERT INTO rag_sync_jobs (
                id,
                workspace_id,
                lane,
                resource_type,
                resource_id,
                operation,
                content_checksum,
                trace_context,
                status,
                attempts,
                created_at,
                updated_at
            )
            SELECT
                substr(md5(q.id || '-qna-rag-upsert'), 1, 8)
                || '-' || substr(md5(q.id || '-qna-rag-upsert'), 9, 4)
                || '-' || substr(md5(q.id || '-qna-rag-upsert'), 13, 4)
                || '-' || substr(md5(q.id || '-qna-rag-upsert'), 17, 4)
                || '-' || substr(md5(q.id || '-qna-rag-upsert'), 21, 12),
                q.workspace_id,
                'backfill',
                'qna_document',
                q.id,
                'upsert',
                q.content_checksum,
                '{"source":"migration.e1b2c3d4e5f6"}'::jsonb,
                'pending',
                0,
                now(),
                now()
            FROM qna_documents q
            WHERE COALESCE(NULLIF(q.body_text, ''), '') <> ''
              AND NOT EXISTS (
                  SELECT 1
                  FROM rag_sync_jobs j
                  WHERE j.resource_type = 'qna_document'
                    AND j.resource_id = q.id
                    AND j.operation = 'upsert'
                    AND j.status IN ('pending', 'processing', 'succeeded')
              )
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "rag_sync_jobs"):
        return
    op.execute(
        sa.text(
            """
            DELETE FROM rag_sync_jobs
            WHERE resource_type = 'qna_document'
              AND operation = 'upsert'
              AND status = 'pending'
              AND trace_context @> '{"source":"migration.e1b2c3d4e5f6"}'::jsonb
            """
        )
    )


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": table_name},
        ).scalar()
    )
