"""normalize workspace app deep links

Revision ID: b3f4c5d6e7a9
Revises: a2d4f6b8c0e2
Create Date: 2026-07-09 00:00:00.000000
"""

from __future__ import annotations

import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f4c5d6e7a9"
down_revision: Union[str, Sequence[str], None] = "a2d4f6b8c0e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE_APP_ROUTE_BASES = (
    "home",
    "pms",
    "docs",
    "files",
    "mail",
    "meeting",
    "planner",
    "whiteboard",
    "diagrams",
    "recording",
    "community",
    "video-chat",
    "plm",
    "learning",
    "news",
    "drafting",
    "document-translate",
    "spec-compare",
    "fmea-compare",
    "imds-minerals",
    "image-wizard",
    "email-assistant",
    "ppt-assistant",
    "retrieval-search",
    "law-search",
    "patent-compose",
    "patent-analysis",
    "patent-report",
    "patent-automation",
    "data-viz",
    "legacy-issues",
    "chatbot",
    "qa-assistant",
    "web-search",
    "research-trends",
    "standards-monitor",
)


def upgrade() -> None:
    _reconcile_existing_model_drift()
    _normalize_platform_app_bar_constraints()
    _normalize_notification_action_urls()


def downgrade() -> None:
    # Data normalization is intentionally not reversible.
    pass


def _reconcile_existing_model_drift() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE ai_security_detected_values
            ALTER COLUMN occurrence_count DROP DEFAULT
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE diagrams
            ALTER COLUMN visibility DROP DEFAULT
            """
        )
    )
    for table_name, index_name, columns in (
        (
            "legacy_issue_ai_chunks",
            "ix_legacy_issue_ai_chunks_attachment_id",
            ("attachment_id",),
        ),
        (
            "legacy_issue_attachment_artifacts",
            "ix_legacy_issue_attachment_artifacts_artifact_kind",
            ("artifact_kind",),
        ),
        (
            "legacy_issue_attachment_artifacts",
            "ix_legacy_issue_attachment_artifacts_attachment_id",
            ("attachment_id",),
        ),
        (
            "legacy_issue_attachment_artifacts",
            "ix_legacy_issue_attachment_artifacts_dataset_key",
            ("dataset_key",),
        ),
        (
            "legacy_issue_attachment_artifacts",
            "ix_legacy_issue_attachment_artifacts_workspace_id",
            ("workspace_id",),
        ),
        (
            "legacy_issue_attachment_index_jobs",
            "ix_legacy_issue_attachment_index_jobs_attachment_id",
            ("attachment_id",),
        ),
        (
            "legacy_issue_attachment_index_jobs",
            "ix_legacy_issue_attachment_index_jobs_next_retry_at",
            ("next_retry_at",),
        ),
        (
            "legacy_issue_attachment_index_jobs",
            "ix_legacy_issue_attachment_index_jobs_status",
            ("status",),
        ),
    ):
        _create_index_if_not_exists(table_name, index_name, columns)


def _create_index_if_not_exists(
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
) -> None:
    rendered_columns = ", ".join(columns)
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name} ({rendered_columns})
            """
        )
    )


def _normalize_platform_app_bar_constraints() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE platform_app_bar_categories
            DROP CONSTRAINT IF EXISTS uq_platform_app_bar_categories_key
            """
        )
    )
    op.execute(sa.text("DROP INDEX IF EXISTS ix_platform_app_bar_category_apps_app_id"))
    op.create_index(
        op.f("ix_platform_app_bar_category_apps_app_id"),
        "platform_app_bar_category_apps",
        ["app_id"],
        unique=False,
    )


def _normalize_notification_action_urls() -> None:
    for route_base in _WORKSPACE_APP_ROUTE_BASES:
        escaped_route_base = re.escape(route_base)
        pattern = rf"(/w/[^/?#]+/{escaped_route_base})/{escaped_route_base}($|[/?#])"
        replacement = r"\1\2"
        for _ in range(3):
            op.execute(
                sa.text(
                    """
                    UPDATE pms_notifications
                    SET action_url = regexp_replace(action_url, :pattern, :replacement, 'g')
                    WHERE action_url IS NOT NULL
                      AND action_url ~ :pattern
                    """
                ).bindparams(
                    pattern=pattern,
                    replacement=replacement,
                )
            )
