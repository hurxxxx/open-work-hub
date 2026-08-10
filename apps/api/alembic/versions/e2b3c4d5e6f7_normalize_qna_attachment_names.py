"""normalize qna attachment names

Revision ID: e2b3c4d5e6f7
Revises: e1b2c3d4e5f6
Create Date: 2026-06-22 00:00:00.000000

Groupware attachment links may expose the same file both as ``name.ext`` and
``/name.ext``. The storage layer strips the leading slash, but the DB list kept
both values, which made duplicate buttons and broke path-based downloads for
the slash-prefixed entry.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
import re
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "e2b3c4d5e6f7"
down_revision: str | Sequence[str] | None = "e1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ATTACHMENT_CONTROL_CHARS_RE = re.compile(r"[\r\n\t]+")


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "qna_documents"):
        return

    has_jobs = _table_exists(bind, "rag_sync_jobs")
    rows = bind.execute(
        sa.text(
            """
            SELECT id, workspace_id, title, body_text, attachments
            FROM qna_documents
            WHERE kind = 'notice'
              AND attachments IS NOT NULL
            """
        )
    ).mappings()

    for row in rows:
        raw_attachments = _as_list(row["attachments"])
        normalized_attachments = _normalize_attachment_names(raw_attachments)
        body_text = row["body_text"] or ""
        normalized_body = body_text.replace("[첨부: /", "[첨부: ")
        if raw_attachments == normalized_attachments and body_text == normalized_body:
            continue

        checksum = _checksum(row["title"], normalized_body, sorted(normalized_attachments))
        bind.execute(
            sa.text(
                """
                UPDATE qna_documents
                SET
                    attachments = CAST(:attachments AS jsonb),
                    body_text = :body_text,
                    char_count = :char_count,
                    content_checksum = :content_checksum,
                    rag_status = CASE
                        WHEN COALESCE(NULLIF(:body_text, ''), '') = '' THEN 'skipped'
                        ELSE 'pending'
                    END,
                    last_error = CASE
                        WHEN COALESCE(NULLIF(:body_text, ''), '') = '' THEN 'no extractable text'
                        ELSE NULL
                    END,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "attachments": json.dumps(normalized_attachments, ensure_ascii=False),
                "body_text": normalized_body,
                "char_count": len(normalized_body),
                "content_checksum": checksum,
            },
        )
        if has_jobs and normalized_body:
            _enqueue_qna_upsert(
                bind,
                workspace_id=row["workspace_id"],
                resource_id=row["id"],
                content_checksum=checksum,
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
              AND trace_context @> '{"source":"migration.e2b3c4d5e6f7"}'::jsonb
            """
        )
    )


def _enqueue_qna_upsert(
    bind: sa.engine.Connection,
    *,
    workspace_id: str,
    resource_id: str,
    content_checksum: str,
) -> None:
    job_id = str(uuid.UUID(hashlib.md5(f"{resource_id}-qna-attachment-normalize".encode()).hexdigest()))
    bind.execute(
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
                CAST(:id AS varchar),
                CAST(:workspace_id AS varchar),
                'backfill',
                'qna_document',
                CAST(:resource_id AS varchar),
                'upsert',
                CAST(:content_checksum AS varchar),
                '{"source":"migration.e2b3c4d5e6f7"}'::jsonb,
                'pending',
                0,
                now(),
                now()
            WHERE NOT EXISTS (
                SELECT 1 FROM rag_sync_jobs WHERE id = CAST(:id AS varchar)
            )
            """
        ),
        {
            "id": job_id,
            "workspace_id": workspace_id,
            "resource_id": resource_id,
            "content_checksum": content_checksum,
        },
    )


def _normalize_attachment_name(filename: str) -> str:
    normalized = (filename or "").replace("\\", "/").strip()
    normalized = normalized.split("?", 1)[0].split("#", 1)[0].strip().strip("/")
    normalized = normalized.rsplit("/", 1)[-1].strip()
    normalized = _ATTACHMENT_CONTROL_CHARS_RE.sub(" ", normalized).strip()
    return normalized or "attachment"


def _normalize_attachment_names(filenames: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_name in filenames:
        name = _normalize_attachment_name(str(raw_name))
        if name in seen:
            continue
        seen.add(name)
        normalized.append(name)
    return normalized


def _checksum(*parts: object) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(str(part or "").encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT to_regclass(:table_name) IS NOT NULL"),
            {"table_name": table_name},
        ).scalar()
    )
