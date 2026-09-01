"""Add the Hermes headless agent control plane.

Revision ID: f4a8c2d6e1b9
Revises: e3b1c7d9a4f2
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f4a8c2d6e1b9"
down_revision: str | Sequence[str] | None = "e3b1c7d9a4f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "hermes_profile_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("profile_name", sa.String(length=63), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'provisioning'"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column(
            "policy_revision",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("last_error_code", sa.String(length=160), nullable=True),
        sa.Column("provisioned_at", sa.DateTime(), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "policy_revision >= 1",
            name="ck_hermes_profile_bindings_policy_revision",
        ),
        sa.CheckConstraint(
            "status IN ('provisioning','active','error','disabled')",
            name="ck_hermes_profile_bindings_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_name"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_hermes_profile_bindings_workspace_user",
        ),
    )
    op.create_index(
        "ix_hermes_profile_bindings_status_updated",
        "hermes_profile_bindings",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_hermes_profile_bindings_user_id",
        "hermes_profile_bindings",
        ["user_id"],
    )
    op.create_index(
        "ix_hermes_profile_bindings_workspace_id",
        "hermes_profile_bindings",
        ["workspace_id"],
    )

    op.create_table(
        "hermes_session_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_binding_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("hermes_session_id", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=True),
        sa.Column("scope_ref", sa.String(length=160), nullable=True),
        sa.Column("scope_resource_id", sa.String(length=256), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','archived','deleted')",
            name="ck_hermes_session_bindings_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_binding_id"],
            ["hermes_profile_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_binding_id",
            "hermes_session_id",
            name="uq_hermes_session_bindings_profile_session",
        ),
    )
    op.create_index(
        "ix_hermes_session_bindings_owner_updated",
        "hermes_session_bindings",
        ["workspace_id", "user_id", "updated_at"],
    )
    op.create_index(
        "ix_hermes_session_bindings_profile_binding_id",
        "hermes_session_bindings",
        ["profile_binding_id"],
    )
    op.create_index(
        "ix_hermes_session_bindings_user_id",
        "hermes_session_bindings",
        ["user_id"],
    )
    op.create_index(
        "ix_hermes_session_bindings_workspace_id",
        "hermes_session_bindings",
        ["workspace_id"],
    )

    op.create_table(
        "hermes_run_projections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_binding_id", sa.String(length=36), nullable=False),
        sa.Column("session_binding_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("hermes_run_id", sa.String(length=80), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("workload_id", sa.String(length=160), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=160), nullable=True),
        sa.Column(
            "progress_percent",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("current_activity", sa.Text(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column(
            "usage",
            JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("allowed_app_ids", JSONB, nullable=True),
        sa.Column("pending_approval", JSONB, nullable=True),
        sa.Column("error_code", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "execution_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("execution_claim_token", sa.String(length=64), nullable=True),
        sa.Column("execution_claimed_at", sa.DateTime(), nullable=True),
        sa.Column("execution_claim_expires_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "execution_attempts >= 0",
            name="ck_hermes_run_projections_attempts",
        ),
        sa.CheckConstraint(
            "kind IN ('interactive','workload','scheduled')",
            name="ck_hermes_run_projections_kind",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_hermes_run_projections_progress",
        ),
        sa.CheckConstraint(
            "status IN ('pending','dispatching','queued','running',"
            "'awaiting_approval','stopping','completed','failed','cancelled',"
            "'interrupted','invalid_output')",
            name="ck_hermes_run_projections_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_binding_id"],
            ["hermes_profile_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_binding_id"],
            ["hermes_session_bindings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hermes_run_projections_hermes_run_id",
        "hermes_run_projections",
        ["hermes_run_id"],
        unique=True,
    )
    op.create_index(
        "ix_hermes_run_projections_owner_created",
        "hermes_run_projections",
        ["workspace_id", "user_id", "created_at"],
    )
    op.create_index(
        "ix_hermes_run_projections_profile_binding_id",
        "hermes_run_projections",
        ["profile_binding_id"],
    )
    op.create_index(
        "ix_hermes_run_projections_session_binding_id",
        "hermes_run_projections",
        ["session_binding_id"],
    )
    op.create_index(
        "ix_hermes_run_projections_session_created",
        "hermes_run_projections",
        ["session_binding_id", "created_at"],
    )
    op.create_index(
        "ix_hermes_run_projections_status_updated",
        "hermes_run_projections",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_hermes_run_projections_user_id",
        "hermes_run_projections",
        ["user_id"],
    )
    op.create_index(
        "ix_hermes_run_projections_workload_id",
        "hermes_run_projections",
        ["workload_id"],
    )
    op.create_index(
        "ix_hermes_run_projections_workspace_id",
        "hermes_run_projections",
        ["workspace_id"],
    )

    op.create_table(
        "hermes_run_inputs",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column(
            "conversation_history",
            JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["hermes_run_projections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )

    op.create_table(
        "hermes_dispatch_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(), nullable=True),
        sa.Column("claim_token", sa.String(length=64), nullable=True),
        sa.Column("celery_task_id", sa.String(length=128), nullable=True),
        sa.Column("last_error_code", sa.String(length=160), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_hermes_dispatch_outbox_attempts",
        ),
        sa.CheckConstraint(
            "status IN ('pending','claimed','dispatched','dead_letter','cancelled')",
            name="ck_hermes_dispatch_outbox_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["hermes_run_projections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hermes_dispatch_outbox_due",
        "hermes_dispatch_outbox",
        ["status", "available_at", "created_at"],
    )
    op.create_index(
        "ix_hermes_dispatch_outbox_run_id",
        "hermes_dispatch_outbox",
        ["run_id"],
        unique=True,
    )

    op.create_table(
        "hermes_run_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=160), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["hermes_run_projections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_hermes_run_events_sequence",
        ),
    )
    op.create_index(
        "ix_hermes_run_events_run_id",
        "hermes_run_events",
        ["run_id"],
    )
    op.create_index(
        "ix_hermes_run_events_run_sequence",
        "hermes_run_events",
        ["run_id", "sequence"],
    )

    op.create_table(
        "hermes_tool_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=256), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("request_payload", JSONB, nullable=False),
        sa.Column("choice", sa.String(length=24), nullable=True),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','approved','denied','expired')",
            name="ck_hermes_tool_approvals_status",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["hermes_run_projections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "request_id",
            name="uq_hermes_tool_approvals_run_request",
        ),
    )
    op.create_index(
        "ix_hermes_tool_approvals_run_id",
        "hermes_tool_approvals",
        ["run_id"],
    )
    op.create_index(
        "ix_hermes_tool_approvals_status_created",
        "hermes_tool_approvals",
        ["status", "created_at"],
    )

    op.create_table(
        "hermes_job_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("profile_binding_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("hermes_job_id", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('active','paused','deleted','error')",
            name="ck_hermes_job_bindings_status",
        ),
        sa.ForeignKeyConstraint(
            ["profile_binding_id"],
            ["hermes_profile_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_binding_id",
            "hermes_job_id",
            name="uq_hermes_job_bindings_profile_job",
        ),
    )
    op.create_index(
        "ix_hermes_job_bindings_owner_updated",
        "hermes_job_bindings",
        ["workspace_id", "user_id", "updated_at"],
    )
    op.create_index(
        "ix_hermes_job_bindings_profile_binding_id",
        "hermes_job_bindings",
        ["profile_binding_id"],
    )
    op.create_index(
        "ix_hermes_job_bindings_user_id",
        "hermes_job_bindings",
        ["user_id"],
    )
    op.create_index(
        "ix_hermes_job_bindings_workspace_id",
        "hermes_job_bindings",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_hermes_job_bindings_workspace_id", table_name="hermes_job_bindings")
    op.drop_index("ix_hermes_job_bindings_user_id", table_name="hermes_job_bindings")
    op.drop_index(
        "ix_hermes_job_bindings_profile_binding_id",
        table_name="hermes_job_bindings",
    )
    op.drop_index("ix_hermes_job_bindings_owner_updated", table_name="hermes_job_bindings")
    op.drop_table("hermes_job_bindings")
    op.drop_index(
        "ix_hermes_tool_approvals_status_created",
        table_name="hermes_tool_approvals",
    )
    op.drop_index("ix_hermes_tool_approvals_run_id", table_name="hermes_tool_approvals")
    op.drop_table("hermes_tool_approvals")
    op.drop_index("ix_hermes_run_events_run_sequence", table_name="hermes_run_events")
    op.drop_index("ix_hermes_run_events_run_id", table_name="hermes_run_events")
    op.drop_table("hermes_run_events")
    op.drop_index("ix_hermes_dispatch_outbox_run_id", table_name="hermes_dispatch_outbox")
    op.drop_index("ix_hermes_dispatch_outbox_due", table_name="hermes_dispatch_outbox")
    op.drop_table("hermes_dispatch_outbox")
    op.drop_table("hermes_run_inputs")
    op.drop_index(
        "ix_hermes_run_projections_workspace_id",
        table_name="hermes_run_projections",
    )
    op.drop_index(
        "ix_hermes_run_projections_workload_id",
        table_name="hermes_run_projections",
    )
    op.drop_index("ix_hermes_run_projections_user_id", table_name="hermes_run_projections")
    op.drop_index(
        "ix_hermes_run_projections_status_updated",
        table_name="hermes_run_projections",
    )
    op.drop_index(
        "ix_hermes_run_projections_session_created",
        table_name="hermes_run_projections",
    )
    op.drop_index(
        "ix_hermes_run_projections_session_binding_id",
        table_name="hermes_run_projections",
    )
    op.drop_index(
        "ix_hermes_run_projections_profile_binding_id",
        table_name="hermes_run_projections",
    )
    op.drop_index(
        "ix_hermes_run_projections_owner_created",
        table_name="hermes_run_projections",
    )
    op.drop_index(
        "ix_hermes_run_projections_hermes_run_id",
        table_name="hermes_run_projections",
    )
    op.drop_table("hermes_run_projections")
    op.drop_index(
        "ix_hermes_session_bindings_workspace_id",
        table_name="hermes_session_bindings",
    )
    op.drop_index("ix_hermes_session_bindings_user_id", table_name="hermes_session_bindings")
    op.drop_index(
        "ix_hermes_session_bindings_profile_binding_id",
        table_name="hermes_session_bindings",
    )
    op.drop_index(
        "ix_hermes_session_bindings_owner_updated",
        table_name="hermes_session_bindings",
    )
    op.drop_table("hermes_session_bindings")
    op.drop_index(
        "ix_hermes_profile_bindings_workspace_id",
        table_name="hermes_profile_bindings",
    )
    op.drop_index("ix_hermes_profile_bindings_user_id", table_name="hermes_profile_bindings")
    op.drop_index(
        "ix_hermes_profile_bindings_status_updated",
        table_name="hermes_profile_bindings",
    )
    op.drop_table("hermes_profile_bindings")
