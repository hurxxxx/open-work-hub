"""add_ai_runtime_tables

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-04-27 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("legacy_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "runtime_profile",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'interactive_read'"),
        ),
        sa.Column("graph_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("model_profile_id", sa.String(length=128), nullable=True),
        sa.Column("fallback_reason", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','awaiting_approval','completed','failed','cancelled','abandoned')",
            name="ck_ai_agent_runs_status",
        ),
        sa.CheckConstraint(
            "runtime_profile IN ('interactive_read','grounded_report','long_doc','high_risk_action')",
            name="ck_ai_agent_runs_runtime_profile",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["legacy_snapshot_id"],
            ["ai_agent_run_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_agent_runs_workspace_id", "ai_agent_runs", ["workspace_id"])
    op.create_index("ix_ai_agent_runs_conversation_id", "ai_agent_runs", ["conversation_id"])
    op.create_index(
        "ix_ai_agent_runs_requested_by_user_id",
        "ai_agent_runs",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_ai_agent_runs_legacy_snapshot_id",
        "ai_agent_runs",
        ["legacy_snapshot_id"],
    )
    op.create_index(
        "ix_ai_agent_runs_conversation_status_created",
        "ai_agent_runs",
        ["conversation_id", "status", "created_at"],
    )
    op.create_index(
        "ix_ai_agent_runs_workspace_status_created",
        "ai_agent_runs",
        ["workspace_id", "status", "created_at"],
    )
    op.create_index(
        "uq_ai_agent_runs_live_conversation",
        "ai_agent_runs",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','running','awaiting_approval')"),
    )

    op.create_table(
        "ai_agent_invocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("invocation_seq", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("input_ref", sa.String(length=256), nullable=True),
        sa.Column("output_ref", sa.String(length=256), nullable=True),
        sa.Column("usage_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','awaiting_approval','resumed','completed','failed','cancelled','abandoned')",
            name="ck_ai_agent_invocations_status",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["ai_agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_agent_invocations_agent_run_id",
        "ai_agent_invocations",
        ["agent_run_id"],
    )
    op.create_index(
        "ix_ai_agent_invocations_workspace_id",
        "ai_agent_invocations",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ai_agent_invocations_conversation_id",
        "ai_agent_invocations",
        ["conversation_id"],
    )
    op.create_index(
        "uq_ai_agent_invocations_run_seq",
        "ai_agent_invocations",
        ["agent_run_id", "invocation_seq"],
        unique=True,
    )
    op.create_index(
        "uq_ai_agent_invocations_pending_approval_run",
        "ai_agent_invocations",
        ["agent_run_id"],
        unique=True,
        postgresql_where=sa.text("status = 'awaiting_approval'"),
    )
    op.create_index(
        "ix_ai_agent_invocations_run_status_seq",
        "ai_agent_invocations",
        ["agent_run_id", "status", "invocation_seq"],
    )
    op.create_index(
        "ix_ai_agent_invocations_workspace_status_created",
        "ai_agent_invocations",
        ["workspace_id", "status", "created_at"],
    )

    op.create_table(
        "ai_agent_trace_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("agent_invocation_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("run_seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("invocation_seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("run_seq >= 0", name="ck_ai_agent_trace_events_run_seq_nonnegative"),
        sa.CheckConstraint(
            "invocation_seq >= 0",
            name="ck_ai_agent_trace_events_invocation_seq_nonnegative",
        ),
        sa.CheckConstraint(
            "event_seq >= 0",
            name="ck_ai_agent_trace_events_event_seq_nonnegative",
        ),
        sa.ForeignKeyConstraint(["agent_run_id"], ["ai_agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_invocation_id"],
            ["ai_agent_invocations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_agent_trace_events_agent_run_id",
        "ai_agent_trace_events",
        ["agent_run_id"],
    )
    op.create_index(
        "ix_ai_agent_trace_events_agent_invocation_id",
        "ai_agent_trace_events",
        ["agent_invocation_id"],
    )
    op.create_index(
        "ix_ai_agent_trace_events_workspace_id",
        "ai_agent_trace_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ai_agent_trace_events_conversation_id",
        "ai_agent_trace_events",
        ["conversation_id"],
    )
    op.create_index(
        "uq_ai_agent_trace_events_run_event_seq",
        "ai_agent_trace_events",
        ["agent_run_id", "event_seq"],
        unique=True,
    )
    op.create_index(
        "ix_ai_agent_trace_events_run_order",
        "ai_agent_trace_events",
        ["agent_run_id", "run_seq", "invocation_seq", "event_seq"],
    )
    op.create_index(
        "ix_ai_agent_trace_events_workspace_created",
        "ai_agent_trace_events",
        ["workspace_id", "created_at"],
    )

    op.create_index(
        "uq_ai_tool_approvals_pending_agent_run",
        "ai_tool_approvals",
        ["agent_run_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_ai_tool_approvals_pending_agent_run", table_name="ai_tool_approvals")

    op.drop_index("ix_ai_agent_trace_events_workspace_created", table_name="ai_agent_trace_events")
    op.drop_index("ix_ai_agent_trace_events_run_order", table_name="ai_agent_trace_events")
    op.drop_index("uq_ai_agent_trace_events_run_event_seq", table_name="ai_agent_trace_events")
    op.drop_index("ix_ai_agent_trace_events_conversation_id", table_name="ai_agent_trace_events")
    op.drop_index("ix_ai_agent_trace_events_workspace_id", table_name="ai_agent_trace_events")
    op.drop_index(
        "ix_ai_agent_trace_events_agent_invocation_id", table_name="ai_agent_trace_events"
    )
    op.drop_index("ix_ai_agent_trace_events_agent_run_id", table_name="ai_agent_trace_events")
    op.drop_table("ai_agent_trace_events")

    op.drop_index(
        "ix_ai_agent_invocations_workspace_status_created", table_name="ai_agent_invocations"
    )
    op.drop_index("ix_ai_agent_invocations_run_status_seq", table_name="ai_agent_invocations")
    op.drop_index("uq_ai_agent_invocations_pending_approval_run", table_name="ai_agent_invocations")
    op.drop_index("uq_ai_agent_invocations_run_seq", table_name="ai_agent_invocations")
    op.drop_index("ix_ai_agent_invocations_conversation_id", table_name="ai_agent_invocations")
    op.drop_index("ix_ai_agent_invocations_workspace_id", table_name="ai_agent_invocations")
    op.drop_index("ix_ai_agent_invocations_agent_run_id", table_name="ai_agent_invocations")
    op.drop_table("ai_agent_invocations")

    op.drop_index("uq_ai_agent_runs_live_conversation", table_name="ai_agent_runs")
    op.drop_index("ix_ai_agent_runs_workspace_status_created", table_name="ai_agent_runs")
    op.drop_index("ix_ai_agent_runs_conversation_status_created", table_name="ai_agent_runs")
    op.drop_index("ix_ai_agent_runs_legacy_snapshot_id", table_name="ai_agent_runs")
    op.drop_index("ix_ai_agent_runs_requested_by_user_id", table_name="ai_agent_runs")
    op.drop_index("ix_ai_agent_runs_conversation_id", table_name="ai_agent_runs")
    op.drop_index("ix_ai_agent_runs_workspace_id", table_name="ai_agent_runs")
    op.drop_table("ai_agent_runs")
