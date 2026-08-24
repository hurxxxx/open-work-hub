"""Guard concurrent active Bento AI edits.

Revision ID: f6d2a4c8e1b3
Revises: e5c9a1b7d3f2
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6d2a4c8e1b3"
down_revision: str | Sequence[str] | None = "e5c9a1b7d3f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_bento_ai_jobs_active_target",
        "bento_ai_jobs",
        ["target_document_id"],
        unique=True,
        postgresql_where=sa.text(
            "target_document_id IS NOT NULL AND status IN ('queued', 'running')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_bento_ai_jobs_active_target", table_name="bento_ai_jobs")
