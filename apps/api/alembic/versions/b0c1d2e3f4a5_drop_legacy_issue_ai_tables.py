"""drop_legacy_issue_ai_tables

Revision ID: b0c1d2e3f4a5
Revises: a0b1c2d3e4f6
Create Date: 2026-06-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b0c1d2e3f4a5"
down_revision: str | Sequence[str] | None = "a0b1c2d3e4f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_LEGACY_ISSUE_TABLES = (
    "legacy_issue_chunks",
    "legacy_issue_attachments",
    "legacy_issue_artifacts",
    "legacy_issue_embedded_objects",
    "legacy_issue_records",
    "legacy_issue_workbook_rows",
    "legacy_issue_workbook_sheets",
    "legacy_issue_documents",
    "legacy_issue_jobs",
    "legacy_issue_datasets",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_legacy_issue_records_ai_search_text_trgm")

    for table_name in OLD_LEGACY_ISSUE_TABLES:
        if table_name in existing_tables:
            op.drop_table(table_name)


def downgrade() -> None:
    # The deleted AI legacy-issue workbook ingestion schema is intentionally
    # not recreated. Restoring it would require resurrecting the removed app
    # code and historical data-loading pipeline.
    pass
