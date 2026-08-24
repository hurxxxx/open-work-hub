"""Add agent runtime routing and durable Bento AI jobs.

Revision ID: e5c9a1b7d3f2
Revises: d4b7e9a2c6f1
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e5c9a1b7d3f2"
down_revision: str | Sequence[str] | None = "d4b7e9a2c6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_model_route_overrides",
        sa.Column("runtime_adapter_id", sa.String(length=64), nullable=True),
    )
    op.create_table(
        "bento_ai_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("runtime_adapter_id", sa.String(length=64), nullable=False),
        sa.Column("target_document_id", sa.String(length=36), nullable=True),
        sa.Column("result_document_id", sa.String(length=36), nullable=True),
        sa.Column("base_version", sa.Integer(), nullable=True),
        sa.Column("result_version", sa.Integer(), nullable=True),
        sa.Column("visibility", sa.String(length=20), server_default="personal", nullable=False),
        sa.Column("slide_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=16), server_default="auto", nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('create', 'edit')", name="ck_bento_ai_jobs_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_bento_ai_jobs_status",
        ),
        sa.CheckConstraint(
            "visibility IN ('personal', 'workspace')",
            name="ck_bento_ai_jobs_visibility",
        ),
        sa.ForeignKeyConstraint(["id"], ["ai_graph_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["result_document_id"], ["bento_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_document_id"], ["bento_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bento_ai_jobs_workspace_user_created",
        "bento_ai_jobs",
        ["workspace_id", "requested_by_id", "created_at"],
    )
    op.create_index(
        "ix_bento_ai_jobs_workspace_status_created",
        "bento_ai_jobs",
        ["workspace_id", "status", "created_at"],
    )
    op.create_table(
        "bento_ai_job_inputs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("current_document_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["bento_ai_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id"),
    )


def downgrade() -> None:
    op.drop_table("bento_ai_job_inputs")
    op.drop_index("ix_bento_ai_jobs_workspace_status_created", table_name="bento_ai_jobs")
    op.drop_index("ix_bento_ai_jobs_workspace_user_created", table_name="bento_ai_jobs")
    op.drop_table("bento_ai_jobs")
    op.drop_column("ai_model_route_overrides", "runtime_adapter_id")
