"""add_spec_compare_jobs

Revision ID: 3a9c7e5d1b20
Revises: 2b8d6c4f9a10
Create Date: 2026-05-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "3a9c7e5d1b20"
down_revision: str | Sequence[str] | None = "2b8d6c4f9a10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "spec_compare_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status_message", sa.String(length=300), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("base_file_name", sa.String(length=512), nullable=False),
        sa.Column("base_mime_type", sa.String(length=160), nullable=False),
        sa.Column("base_size_bytes", sa.Integer(), nullable=False),
        sa.Column("base_storage_key", sa.String(length=1024), nullable=False),
        sa.Column("target_file_name", sa.String(length=512), nullable=False),
        sa.Column("target_mime_type", sa.String(length=160), nullable=False),
        sa.Column("target_size_bytes", sa.Integer(), nullable=False),
        sa.Column("target_storage_key", sa.String(length=1024), nullable=False),
        sa.Column("result_json_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("report_markdown_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("result_summary", JSONB, nullable=True),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_spec_compare_jobs_status",
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_spec_compare_jobs_progress",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_spec_compare_jobs_owner_id",
        "spec_compare_jobs",
        ["owner_id"],
    )
    op.create_index(
        "ix_spec_compare_jobs_status",
        "spec_compare_jobs",
        ["status"],
    )
    op.create_index(
        "ix_spec_compare_jobs_workspace_id",
        "spec_compare_jobs",
        ["workspace_id"],
    )
    op.create_index(
        "ix_spec_compare_jobs_workspace_owner_created",
        "spec_compare_jobs",
        ["workspace_id", "owner_id", "created_at"],
    )
    op.create_index(
        "ix_spec_compare_jobs_workspace_status_created",
        "spec_compare_jobs",
        ["workspace_id", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_spec_compare_jobs_workspace_status_created",
        table_name="spec_compare_jobs",
    )
    op.drop_index(
        "ix_spec_compare_jobs_workspace_owner_created",
        table_name="spec_compare_jobs",
    )
    op.drop_index("ix_spec_compare_jobs_workspace_id", table_name="spec_compare_jobs")
    op.drop_index("ix_spec_compare_jobs_status", table_name="spec_compare_jobs")
    op.drop_index("ix_spec_compare_jobs_owner_id", table_name="spec_compare_jobs")
    op.drop_table("spec_compare_jobs")
