"""add_search_index_jobs

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-04-25 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "search_index_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column(
            "operation",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'upsert'"),
        ),
        sa.Column("trace_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('doc','meeting','pms_issue','planner_event')",
            name="ck_search_index_jobs_entity_type",
        ),
        sa.CheckConstraint(
            "operation IN ('upsert','delete')",
            name="ck_search_index_jobs_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_search_index_jobs_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_index_jobs_workspace_id", "search_index_jobs", ["workspace_id"])
    op.create_index("ix_search_index_jobs_entity_type", "search_index_jobs", ["entity_type"])
    op.create_index("ix_search_index_jobs_entity_id", "search_index_jobs", ["entity_id"])
    op.create_index("ix_search_index_jobs_status", "search_index_jobs", ["status"])
    op.create_index("ix_search_index_jobs_next_retry_at", "search_index_jobs", ["next_retry_at"])
    op.create_index(
        "ix_search_index_jobs_workspace_status_retry",
        "search_index_jobs",
        ["workspace_id", "status", "next_retry_at"],
    )
    op.create_index(
        "ix_search_index_jobs_entity_status",
        "search_index_jobs",
        ["entity_type", "entity_id", "status"],
    )
    op.create_index(
        "uq_search_index_jobs_pending_entity",
        "search_index_jobs",
        ["workspace_id", "entity_type", "entity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_search_index_jobs_pending_entity", table_name="search_index_jobs")
    op.drop_index("ix_search_index_jobs_entity_status", table_name="search_index_jobs")
    op.drop_index("ix_search_index_jobs_workspace_status_retry", table_name="search_index_jobs")
    op.drop_index("ix_search_index_jobs_next_retry_at", table_name="search_index_jobs")
    op.drop_index("ix_search_index_jobs_status", table_name="search_index_jobs")
    op.drop_index("ix_search_index_jobs_entity_id", table_name="search_index_jobs")
    op.drop_index("ix_search_index_jobs_entity_type", table_name="search_index_jobs")
    op.drop_index("ix_search_index_jobs_workspace_id", table_name="search_index_jobs")
    op.drop_table("search_index_jobs")
