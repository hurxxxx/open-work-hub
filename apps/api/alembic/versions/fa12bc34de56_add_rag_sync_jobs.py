"""add_rag_sync_jobs

Revision ID: fa12bc34de56
Revises: b7e3c1d2f4a5
Create Date: 2026-04-22 16:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "fa12bc34de56"
down_revision: Union[str, Sequence[str], None] = "b7e3c1d2f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rag_sync_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "lane",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'realtime'"),
        ),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column(
            "operation",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'upsert'"),
        ),
        sa.Column("content_checksum", sa.String(length=128), nullable=True),
        sa.Column("visibility_checksum", sa.String(length=128), nullable=True),
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
            "lane IN ('realtime','backfill')",
            name="ck_rag_sync_jobs_lane",
        ),
        sa.CheckConstraint(
            "operation IN ('upsert','delete','visibility_update')",
            name="ck_rag_sync_jobs_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_rag_sync_jobs_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rag_sync_jobs_workspace_id", "rag_sync_jobs", ["workspace_id"])
    op.create_index("ix_rag_sync_jobs_lane", "rag_sync_jobs", ["lane"])
    op.create_index("ix_rag_sync_jobs_resource_type", "rag_sync_jobs", ["resource_type"])
    op.create_index("ix_rag_sync_jobs_resource_id", "rag_sync_jobs", ["resource_id"])
    op.create_index("ix_rag_sync_jobs_status", "rag_sync_jobs", ["status"])
    op.create_index("ix_rag_sync_jobs_next_retry_at", "rag_sync_jobs", ["next_retry_at"])
    op.create_index(
        "ix_rag_sync_jobs_workspace_lane_status_retry",
        "rag_sync_jobs",
        ["workspace_id", "lane", "status", "next_retry_at"],
    )
    op.create_index(
        "ix_rag_sync_jobs_resource_status",
        "rag_sync_jobs",
        ["resource_type", "resource_id", "status"],
    )

    op.create_table(
        "rag_visibility_recompute_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column("trace_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cursor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_rag_visibility_recompute_jobs_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_visibility_recompute_jobs_workspace_id",
        "rag_visibility_recompute_jobs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_rag_visibility_recompute_jobs_scope_type",
        "rag_visibility_recompute_jobs",
        ["scope_type"],
    )
    op.create_index(
        "ix_rag_visibility_recompute_jobs_scope_id",
        "rag_visibility_recompute_jobs",
        ["scope_id"],
    )
    op.create_index(
        "ix_rag_visibility_recompute_jobs_status",
        "rag_visibility_recompute_jobs",
        ["status"],
    )
    op.create_index(
        "ix_rag_visibility_recompute_jobs_next_retry_at",
        "rag_visibility_recompute_jobs",
        ["next_retry_at"],
    )
    op.create_index(
        "ix_rag_visibility_recompute_jobs_workspace_status_retry",
        "rag_visibility_recompute_jobs",
        ["workspace_id", "status", "next_retry_at"],
    )
    op.create_index(
        "ix_rag_visibility_recompute_jobs_scope_status",
        "rag_visibility_recompute_jobs",
        ["scope_type", "scope_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rag_visibility_recompute_jobs_scope_status",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "ix_rag_visibility_recompute_jobs_workspace_status_retry",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "ix_rag_visibility_recompute_jobs_next_retry_at",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "ix_rag_visibility_recompute_jobs_status",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "ix_rag_visibility_recompute_jobs_scope_id",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "ix_rag_visibility_recompute_jobs_scope_type",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_index(
        "ix_rag_visibility_recompute_jobs_workspace_id",
        table_name="rag_visibility_recompute_jobs",
    )
    op.drop_table("rag_visibility_recompute_jobs")

    op.drop_index("ix_rag_sync_jobs_resource_status", table_name="rag_sync_jobs")
    op.drop_index("ix_rag_sync_jobs_workspace_lane_status_retry", table_name="rag_sync_jobs")
    op.drop_index("ix_rag_sync_jobs_next_retry_at", table_name="rag_sync_jobs")
    op.drop_index("ix_rag_sync_jobs_status", table_name="rag_sync_jobs")
    op.drop_index("ix_rag_sync_jobs_resource_id", table_name="rag_sync_jobs")
    op.drop_index("ix_rag_sync_jobs_resource_type", table_name="rag_sync_jobs")
    op.drop_index("ix_rag_sync_jobs_lane", table_name="rag_sync_jobs")
    op.drop_index("ix_rag_sync_jobs_workspace_id", table_name="rag_sync_jobs")
    op.drop_table("rag_sync_jobs")
