"""add RAG queue health indexes

Revision ID: b9d1e3f5a7c0
Revises: a8c0d2e4f6b9
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op


revision: str = "b9d1e3f5a7c0"
down_revision: str | None = "a8c0d2e4f6b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_rag_sync_jobs_lane_status_updated",
        "rag_sync_jobs",
        ["lane", "status", "updated_at"],
    )
    op.create_index(
        "ix_rag_visibility_jobs_status_updated",
        "rag_visibility_recompute_jobs",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rag_visibility_jobs_status_updated",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "ix_rag_sync_jobs_lane_status_updated",
        table_name="rag_sync_jobs",
    )
