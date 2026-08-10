"""backfill legacy issue conversation reports into common AI artifacts

Revision ID: c6a9e2f4b8d1
Revises: b5f8d3a1c7e4
Create Date: 2026-07-26 17:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c6a9e2f4b8d1"
down_revision: str | Sequence[str] | None = "b5f8d3a1c7e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_BACKFILL_MARKER = revision


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f"""
            WITH legacy_reports AS (
                SELECT
                    concat(
                        substr(md5(turns.id || ':' || (artifact.value ->> 'id')), 1, 8),
                        '-',
                        substr(md5(turns.id || ':' || (artifact.value ->> 'id')), 9, 4),
                        '-',
                        substr(md5(turns.id || ':' || (artifact.value ->> 'id')), 13, 4),
                        '-',
                        substr(md5(turns.id || ':' || (artifact.value ->> 'id')), 17, 4),
                        '-',
                        substr(md5(turns.id || ':' || (artifact.value ->> 'id')), 21, 12)
                    ) AS artifact_id,
                    conversations.workspace_id,
                    conversations.user_id AS owner_user_id,
                    conversations.id AS conversation_id,
                    turns.id AS conversation_turn_id,
                    COALESCE(
                        NULLIF(artifact.value ->> 'title', ''),
                        '과거차 문제점 분석 보고서'
                    ) AS title,
                    artifact.value ->> 'content' AS content_text,
                    jsonb_build_object(
                        'migration', '{_BACKFILL_MARKER}',
                        'legacyArtifactId', artifact.value ->> 'id'
                    ) AS payload_json,
                    turns.created_at
                FROM public.conversation_turns AS turns
                JOIN public.conversations AS conversations
                  ON conversations.id = turns.conversation_id
                CROSS JOIN LATERAL jsonb_array_elements(
                    COALESCE(turns.meta::jsonb -> 'artifacts', '[]'::jsonb)
                ) AS artifact(value)
                WHERE conversations.scope_ref = 'legacy_issues'
                  AND conversations.scope_resource_id = 'workspace'
                  AND turns.role = 'assistant'
                  AND turns.meta::jsonb ->> 'policy' = 'scope_direct_response'
                  AND turns.meta::jsonb ->> 'decision_reason' =
                        'scope_direct_response'
                  AND turns.meta::jsonb ->> 'response_status' = 'done'
                  AND turns.meta::jsonb ->> 'finish_reason' = 'stop'
                  AND artifact.value ->> 'type' = 'document'
                  AND artifact.value ->> 'title' =
                        '과거차 문제점 근거 기반 보고서'
                  AND artifact.value ->> 'status' = 'closed'
                  AND NULLIF(artifact.value ->> 'id', '') IS NOT NULL
                  AND NULLIF(artifact.value ->> 'content', '') IS NOT NULL
            )
            INSERT INTO public.ai_artifacts (
                id,
                artifact_number,
                workspace_id,
                owner_user_id,
                graph_run_id,
                conversation_id,
                conversation_turn_id,
                supersedes_artifact_id,
                app_id,
                artifact_type,
                title,
                content_type,
                content_text,
                payload_json,
                schema_version,
                content_sha256,
                content_size_bytes,
                visibility,
                status,
                error_code,
                completed_at,
                created_at
            )
            SELECT
                reports.artifact_id,
                concat(
                    'AIR-',
                    to_char(reports.created_at, 'YYYYMMDD'),
                    '-',
                    lpad(
                        nextval('public.ai_report_artifact_number_seq')::text,
                        10,
                        '0'
                    )
                ),
                reports.workspace_id,
                reports.owner_user_id,
                NULL,
                reports.conversation_id,
                reports.conversation_turn_id,
                NULL,
                'legacy-issues',
                'report',
                reports.title,
                'text/markdown',
                reports.content_text,
                reports.payload_json,
                1,
                encode(
                    sha256(convert_to(reports.content_text, 'UTF8')),
                    'hex'
                ),
                octet_length(convert_to(reports.content_text, 'UTF8')),
                'private',
                'completed',
                NULL,
                reports.created_at,
                reports.created_at
            FROM legacy_reports AS reports
            ON CONFLICT (id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f"""
            DELETE FROM public.ai_artifacts
            WHERE payload_json ->> 'migration' = '{_BACKFILL_MARKER}'
            """
        )
    )
