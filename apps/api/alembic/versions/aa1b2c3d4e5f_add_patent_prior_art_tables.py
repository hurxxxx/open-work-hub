"""add_patent_prior_art_tables

Revision ID: aa1b2c3d4e5f
Revises: a6b7c8d9e0f2
Create Date: 2026-06-30 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "aa1b2c3d4e5f"
down_revision: str | Sequence[str] | None = "a6b7c8d9e0f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "patent_prior_art_jobs",
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
        sa.Column("requested_countries", JSONB_COMPAT, nullable=True),
        sa.Column("max_results", sa.Integer(), nullable=False),
        sa.Column("raw_limit", sa.Integer(), nullable=False),
        sa.Column("include_drawings", sa.Boolean(), nullable=False),
        sa.Column("result_summary", JSONB_COMPAT, nullable=True),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_patent_prior_art_jobs_status",
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_patent_prior_art_jobs_progress",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patent_prior_art_jobs_workspace_owner_created",
        "patent_prior_art_jobs",
        ["workspace_id", "owner_id", "created_at"],
    )
    op.create_index(
        "ix_patent_prior_art_jobs_workspace_status_created",
        "patent_prior_art_jobs",
        ["workspace_id", "status", "created_at"],
    )
    op.create_index(
        op.f("ix_patent_prior_art_jobs_workspace_id"),
        "patent_prior_art_jobs",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_patent_prior_art_jobs_owner_id"),
        "patent_prior_art_jobs",
        ["owner_id"],
    )
    op.create_index(
        op.f("ix_patent_prior_art_jobs_status"),
        "patent_prior_art_jobs",
        ["status"],
    )

    op.create_table(
        "patent_prior_art_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "position",
            name="uq_patent_prior_art_attachments_job_position",
        ),
    )
    op.create_index(
        "ix_patent_prior_art_attachments_job",
        "patent_prior_art_attachments",
        ["job_id"],
    )
    op.create_index(
        "ix_patent_prior_art_attachments_workspace",
        "patent_prior_art_attachments",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_patent_prior_art_attachments_workspace_id"),
        "patent_prior_art_attachments",
        ["workspace_id"],
    )

    op.create_table(
        "patent_prior_art_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("artifact_metadata", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "kind",
            "file_name",
            name="uq_patent_prior_art_artifacts_job_kind_name",
        ),
    )
    op.create_index(
        "ix_patent_prior_art_artifacts_job",
        "patent_prior_art_artifacts",
        ["job_id"],
    )
    op.create_index(
        "ix_patent_prior_art_artifacts_workspace",
        "patent_prior_art_artifacts",
        ["workspace_id"],
    )
    op.create_index(
        "ix_patent_prior_art_artifacts_kind",
        "patent_prior_art_artifacts",
        ["kind"],
    )
    op.create_index(
        op.f("ix_patent_prior_art_artifacts_workspace_id"),
        "patent_prior_art_artifacts",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_table("patent_prior_art_artifacts")
    op.drop_table("patent_prior_art_attachments")
    op.drop_table("patent_prior_art_jobs")
