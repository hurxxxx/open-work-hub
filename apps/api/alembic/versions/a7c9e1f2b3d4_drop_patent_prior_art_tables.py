"""drop patent prior art tables

Revision ID: a7c9e1f2b3d4
Revises: c0d1e2f3a5b7
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "a7c9e1f2b3d4"
down_revision: str | Sequence[str] | None = "c0d1e2f3a5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES = (
    "patent_prior_art_refinement_rounds",
    "patent_prior_art_job_candidates",
    "patent_prior_art_query_results",
    "patent_prior_art_query_executions",
    "patent_prior_art_source_aliases",
    "patent_prior_art_source_documents",
    "patent_prior_art_artifacts",
    "patent_prior_art_attachments",
    "patent_prior_art_jobs",
)


def upgrade() -> None:
    for table_name in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")


def downgrade() -> None:
    # Historical create migrations remain in the migration graph; this removal
    # migration intentionally does not recreate retired application tables.
    pass
