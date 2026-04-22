"""add_rag_pending_unique_indexes

Revision ID: c1d2e3f4a5b6
Revises: fa12bc34de56
Create Date: 2026-04-22 18:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "fa12bc34de56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_rag_sync_jobs_pending_resource_lane",
        "rag_sync_jobs",
        ["workspace_id", "lane", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_rag_visibility_recompute_jobs_pending_scope",
        "rag_visibility_recompute_jobs",
        ["workspace_id", "scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_rag_visibility_recompute_jobs_pending_scope",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "uq_rag_sync_jobs_pending_resource_lane",
        table_name="rag_sync_jobs",
    )
