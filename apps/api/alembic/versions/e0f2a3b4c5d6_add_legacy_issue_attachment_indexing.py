"""add legacy issue attachment indexing

Revision ID: e0f2a3b4c5d6
Revises: d9d1e2f3a4b5
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e0f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d9d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "legacy_issue_attachments",
        sa.Column(
            "index_status",
            sa.String(length=32),
            server_default=sa.text("'not_indexed'"),
            nullable=False,
        ),
    )
    op.add_column("legacy_issue_attachments", sa.Column("index_error", sa.Text(), nullable=True))
    op.add_column("legacy_issue_attachments", sa.Column("indexed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "legacy_issue_attachments",
        sa.Column(
            "index_version",
            sa.String(length=80),
            server_default=sa.text("'legacy_issue_attachment_index.v1'"),
            nullable=False,
        ),
    )
    op.add_column(
        "legacy_issue_attachments",
        sa.Column("chunk_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "legacy_issue_attachments",
        sa.Column("artifact_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.create_index(
        "ix_legacy_issue_attachments_index_status",
        "legacy_issue_attachments",
        ["workspace_id", "index_status"],
    )

    op.add_column(
        "legacy_issue_ai_chunks",
        sa.Column("attachment_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "legacy_issue_ai_chunks",
        sa.Column("attachment_filename", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "legacy_issue_ai_chunks",
        sa.Column("attachment_page", sa.Integer(), nullable=True),
    )
    op.add_column(
        "legacy_issue_ai_chunks",
        sa.Column("attachment_artifact_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "legacy_issue_ai_chunks",
        sa.Column("search_terms", _json_type(), nullable=True),
    )
    op.create_foreign_key(
        "fk_legacy_issue_ai_chunks_attachment_id",
        "legacy_issue_ai_chunks",
        "legacy_issue_attachments",
        ["attachment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_legacy_issue_ai_chunks_attachment",
        "legacy_issue_ai_chunks",
        ["attachment_id", "chunk_kind"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_legacy_issue_ai_chunks_search_terms_gin
            ON legacy_issue_ai_chunks
            USING gin (search_terms)
            """
        )

    op.create_table(
        "legacy_issue_attachment_index_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("attachment_id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=16), server_default=sa.text("'upsert'"), nullable=False),
        sa.Column("trigger", sa.String(length=40), server_default=sa.text("'upload'"), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("trace_context", _json_type(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('upsert','delete')",
            name="ck_legacy_issue_attachment_index_jobs_operation",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_legacy_issue_attachment_index_jobs_status",
        ),
        sa.ForeignKeyConstraint(["attachment_id"], ["legacy_issue_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["legacy_issue_data_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_attachment_index_jobs_workspace_status_retry",
        "legacy_issue_attachment_index_jobs",
        ["workspace_id", "status", "next_retry_at"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_index_jobs_attachment_status",
        "legacy_issue_attachment_index_jobs",
        ["attachment_id", "status"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_index_jobs_dataset_key",
        "legacy_issue_attachment_index_jobs",
        ["dataset_key"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_index_jobs_revision_id",
        "legacy_issue_attachment_index_jobs",
        ["revision_id"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_index_jobs_workspace_id",
        "legacy_issue_attachment_index_jobs",
        ["workspace_id"],
    )
    op.create_index(
        "uq_legacy_issue_attachment_index_jobs_pending_attachment",
        "legacy_issue_attachment_index_jobs",
        ["workspace_id", "attachment_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "legacy_issue_attachment_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("stable_record_id", sa.String(length=36), nullable=True),
        sa.Column("attachment_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_kind", sa.String(length=64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("metadata", _json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attachment_id"], ["legacy_issue_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["legacy_issue_attachment_index_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["record_id"], ["legacy_issue_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["legacy_issue_data_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_attachment_artifacts_attachment",
        "legacy_issue_attachment_artifacts",
        ["attachment_id", "artifact_kind"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_artifacts_workspace_dataset",
        "legacy_issue_attachment_artifacts",
        ["workspace_id", "dataset_key", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_artifacts_record_id",
        "legacy_issue_attachment_artifacts",
        ["record_id"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_artifacts_revision_id",
        "legacy_issue_attachment_artifacts",
        ["revision_id"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_artifacts_stable_record_id",
        "legacy_issue_attachment_artifacts",
        ["stable_record_id"],
    )
    op.create_index(
        "ix_legacy_issue_attachment_artifacts_job_id",
        "legacy_issue_attachment_artifacts",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_legacy_issue_attachment_artifacts_job_id", table_name="legacy_issue_attachment_artifacts")
    op.drop_index("ix_legacy_issue_attachment_artifacts_stable_record_id", table_name="legacy_issue_attachment_artifacts")
    op.drop_index("ix_legacy_issue_attachment_artifacts_revision_id", table_name="legacy_issue_attachment_artifacts")
    op.drop_index("ix_legacy_issue_attachment_artifacts_record_id", table_name="legacy_issue_attachment_artifacts")
    op.drop_index("ix_legacy_issue_attachment_artifacts_workspace_dataset", table_name="legacy_issue_attachment_artifacts")
    op.drop_index("ix_legacy_issue_attachment_artifacts_attachment", table_name="legacy_issue_attachment_artifacts")
    op.drop_table("legacy_issue_attachment_artifacts")

    op.drop_index(
        "uq_legacy_issue_attachment_index_jobs_pending_attachment",
        table_name="legacy_issue_attachment_index_jobs",
    )
    op.drop_index("ix_legacy_issue_attachment_index_jobs_workspace_id", table_name="legacy_issue_attachment_index_jobs")
    op.drop_index("ix_legacy_issue_attachment_index_jobs_revision_id", table_name="legacy_issue_attachment_index_jobs")
    op.drop_index("ix_legacy_issue_attachment_index_jobs_dataset_key", table_name="legacy_issue_attachment_index_jobs")
    op.drop_index("ix_legacy_issue_attachment_index_jobs_attachment_status", table_name="legacy_issue_attachment_index_jobs")
    op.drop_index("ix_legacy_issue_attachment_index_jobs_workspace_status_retry", table_name="legacy_issue_attachment_index_jobs")
    op.drop_table("legacy_issue_attachment_index_jobs")

    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_legacy_issue_ai_chunks_search_terms_gin")
    op.drop_index("ix_legacy_issue_ai_chunks_attachment", table_name="legacy_issue_ai_chunks")
    op.drop_constraint(
        "fk_legacy_issue_ai_chunks_attachment_id",
        "legacy_issue_ai_chunks",
        type_="foreignkey",
    )
    op.drop_column("legacy_issue_ai_chunks", "search_terms")
    op.drop_column("legacy_issue_ai_chunks", "attachment_artifact_type")
    op.drop_column("legacy_issue_ai_chunks", "attachment_page")
    op.drop_column("legacy_issue_ai_chunks", "attachment_filename")
    op.drop_column("legacy_issue_ai_chunks", "attachment_id")

    op.drop_index("ix_legacy_issue_attachments_index_status", table_name="legacy_issue_attachments")
    op.drop_column("legacy_issue_attachments", "artifact_count")
    op.drop_column("legacy_issue_attachments", "chunk_count")
    op.drop_column("legacy_issue_attachments", "index_version")
    op.drop_column("legacy_issue_attachments", "indexed_at")
    op.drop_column("legacy_issue_attachments", "index_error")
    op.drop_column("legacy_issue_attachments", "index_status")
