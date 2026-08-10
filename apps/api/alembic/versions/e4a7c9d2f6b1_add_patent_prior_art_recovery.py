"""add patent prior-art execution leases and durable recovery

Revision ID: e4a7c9d2f6b1
Revises: 8f5b2d1c3a7e
Create Date: 2026-07-31 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e4a7c9d2f6b1"
down_revision: str | Sequence[str] | None = "8f5b2d1c3a7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patent_prior_art_jobs",
        sa.Column(
            "execution_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "patent_prior_art_jobs",
        sa.Column(
            "automatic_restart_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "patent_prior_art_jobs",
        sa.Column("execution_lease_expires_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "patent_prior_art_jobs",
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE patent_prior_art_jobs "
            "SET execution_lease_expires_at = updated_at "
            "WHERE status = 'running' AND execution_lease_expires_at IS NULL"
        )
    )
    op.drop_constraint(
        "ck_patent_prior_art_jobs_stage",
        "patent_prior_art_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_patent_prior_art_jobs_stage",
        "patent_prior_art_jobs",
        "stage IN ("
        "'queued','retry_waiting','loading_input','searching','ranking','assessing','reporting',"
        "'persisting','completed','failed','cancelled','cleanup_pending'"
        ")",
    )
    op.create_check_constraint(
        "ck_patent_prior_art_jobs_execution_attempts",
        "patent_prior_art_jobs",
        "execution_attempts >= 0",
    )
    op.create_check_constraint(
        "ck_patent_prior_art_jobs_automatic_restart_count",
        "patent_prior_art_jobs",
        "automatic_restart_count >= 0 AND automatic_restart_count <= 1",
    )
    op.create_index(
        "ix_patent_prior_art_jobs_recovery_due",
        "patent_prior_art_jobs",
        [
            "status",
            "stage",
            "next_attempt_at",
            "execution_lease_expires_at",
        ],
    )

    op.add_column(
        "patent_prior_art_executed_queries",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'succeeded'"),
            nullable=False,
        ),
    )
    op.add_column(
        "patent_prior_art_executed_queries",
        sa.Column("failure_code", sa.String(length=80), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE patent_prior_art_executed_queries "
            "SET status = 'failed', failure_code = 'provider_unavailable' "
            "WHERE result_count IS NULL"
        )
    )
    op.create_check_constraint(
        "ck_patent_prior_art_queries_status",
        "patent_prior_art_executed_queries",
        "status IN ('succeeded','failed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_patent_prior_art_queries_status",
        "patent_prior_art_executed_queries",
        type_="check",
    )
    op.drop_column("patent_prior_art_executed_queries", "failure_code")
    op.drop_column("patent_prior_art_executed_queries", "status")

    op.drop_index(
        "ix_patent_prior_art_jobs_recovery_due",
        table_name="patent_prior_art_jobs",
    )
    op.drop_constraint(
        "ck_patent_prior_art_jobs_automatic_restart_count",
        "patent_prior_art_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_patent_prior_art_jobs_execution_attempts",
        "patent_prior_art_jobs",
        type_="check",
    )
    op.execute(
        sa.text(
            "UPDATE patent_prior_art_jobs "
            "SET stage = 'queued' "
            "WHERE stage = 'retry_waiting'"
        )
    )
    op.drop_constraint(
        "ck_patent_prior_art_jobs_stage",
        "patent_prior_art_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_patent_prior_art_jobs_stage",
        "patent_prior_art_jobs",
        "stage IN ("
        "'queued','loading_input','searching','ranking','assessing','reporting',"
        "'persisting','completed','failed','cancelled','cleanup_pending'"
        ")",
    )
    op.drop_column("patent_prior_art_jobs", "next_attempt_at")
    op.drop_column("patent_prior_art_jobs", "execution_lease_expires_at")
    op.drop_column("patent_prior_art_jobs", "automatic_restart_count")
    op.drop_column("patent_prior_art_jobs", "execution_attempts")
