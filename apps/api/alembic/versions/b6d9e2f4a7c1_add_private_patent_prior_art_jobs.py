"""add private patent prior-art job lifecycle

Revision ID: b6d9e2f4a7c1
Revises: c8e4f0a2b6d3
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b6d9e2f4a7c1"
down_revision: str | Sequence[str] | None = "c8e4f0a2b6d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # Platform tenant/principal identities are opaque app-scope references.
    # The API and worker revalidate them through Core before every operation;
    # this app-owned migration therefore creates no shared-table dependency.
    op.create_table(
        "patent_prior_art_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_scope_id", sa.String(length=36), nullable=False),
        sa.Column("owner_principal_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "stage",
            sa.String(length=40),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "progress_percent",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("jurisdictions", JSONB_COMPAT, nullable=False),
        sa.Column("plan_payload", JSONB_COMPAT, nullable=False),
        sa.Column("input_storage_key", sa.String(length=320), nullable=False),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column(
            "dispatch_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("dispatch_published_at", sa.DateTime(), nullable=True),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("deletion_requested_at", sa.DateTime(), nullable=True),
        sa.Column("cleanup_failure_code", sa.String(length=80), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_patent_prior_art_jobs_status",
        ),
        sa.CheckConstraint(
            "stage IN ("
            "'queued','loading_input','searching','ranking','assessing','reporting',"
            "'persisting','completed','failed','cancelled','cleanup_pending'"
            ")",
            name="ck_patent_prior_art_jobs_stage",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_patent_prior_art_jobs_progress",
        ),
        sa.CheckConstraint(
            "dispatch_attempts >= 0",
            name="ck_patent_prior_art_jobs_dispatch_attempts",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_scope_id",
            "owner_principal_id",
            "idempotency_key",
            name="uq_patent_prior_art_jobs_owner_idempotency",
        ),
    )
    op.create_index(
        "ix_patent_prior_art_jobs_tenant_owner_created",
        "patent_prior_art_jobs",
        ["tenant_scope_id", "owner_principal_id", "created_at"],
    )
    op.create_index(
        "ix_patent_prior_art_jobs_tenant_status_created",
        "patent_prior_art_jobs",
        ["tenant_scope_id", "status", "created_at"],
    )
    op.create_index(
        "ix_patent_prior_art_jobs_dispatch_pending",
        "patent_prior_art_jobs",
        ["status", "dispatch_published_at", "updated_at"],
    )
    for column in (
        "tenant_scope_id",
        "owner_principal_id",
        "status",
        "deletion_requested_at",
    ):
        op.create_index(
            op.f(f"ix_patent_prior_art_jobs_{column}"),
            "patent_prior_art_jobs",
            [column],
        )

    op.create_table(
        "patent_prior_art_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_scope_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("publication_number", sa.String(length=96), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("assignees", JSONB_COMPAT, nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("filing_date", sa.String(length=32), nullable=True),
        sa.Column("publication_date", sa.String(length=32), nullable=True),
        sa.Column("classification_codes", JSONB_COMPAT, nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "relevance_band",
            sa.String(length=16),
            server_default=sa.text("'unrated'"),
            nullable=False,
        ),
        sa.Column("match_reasons", JSONB_COMPAT, nullable=False),
        sa.Column("external_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "relevance_band IN ('high','medium','low','unrated')",
            name="ck_patent_prior_art_candidates_relevance_band",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "rank",
            name="uq_patent_prior_art_candidates_job_rank",
        ),
    )
    op.create_index(
        "ix_patent_prior_art_candidates_tenant_job",
        "patent_prior_art_candidates",
        ["tenant_scope_id", "job_id"],
    )

    op.create_table(
        "patent_prior_art_executed_queries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_scope_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("source_label", sa.String(length=160), nullable=False),
        sa.Column("jurisdiction", sa.String(length=8), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "position",
            name="uq_patent_prior_art_queries_job_position",
        ),
    )
    op.create_index(
        "ix_patent_prior_art_queries_tenant_job",
        "patent_prior_art_executed_queries",
        ["tenant_scope_id", "job_id"],
    )

    op.create_table(
        "patent_prior_art_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_scope_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=180), nullable=False),
        sa.Column("mime_type", sa.String(length=96), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('result_json','report_markdown')",
            name="ck_patent_prior_art_artifacts_kind",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["patent_prior_art_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "kind",
            name="uq_patent_prior_art_artifacts_job_kind",
        ),
    )
    op.create_index(
        "ix_patent_prior_art_artifacts_tenant_job",
        "patent_prior_art_artifacts",
        ["tenant_scope_id", "job_id"],
    )


def downgrade() -> None:
    op.drop_table("patent_prior_art_artifacts")
    op.drop_table("patent_prior_art_executed_queries")
    op.drop_table("patent_prior_art_candidates")
    op.drop_table("patent_prior_art_jobs")
