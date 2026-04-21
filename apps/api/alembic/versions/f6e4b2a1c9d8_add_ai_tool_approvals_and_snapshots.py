"""add_ai_tool_approvals_and_snapshots

Revision ID: f6e4b2a1c9d8
Revises: e1f2a3b4c5d6
Create Date: 2026-04-21 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f6e4b2a1c9d8"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_run_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'awaiting_approval'"),
        ),
        sa.Column("messages_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("blocked_call_id", sa.String(length=80), nullable=False),
        sa.Column("model_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("scrubbed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('awaiting_approval','resumed','completed','abandoned')",
            name="ck_ai_agent_run_snapshots_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_agent_run_snapshots_conversation_id",
        "ai_agent_run_snapshots",
        ["conversation_id"],
    )
    op.create_index(
        "ix_ai_agent_run_snapshots_workspace_id",
        "ai_agent_run_snapshots",
        ["workspace_id"],
    )
    op.create_index(
        "ix_ai_agent_run_snapshots_requested_by_user_id",
        "ai_agent_run_snapshots",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_ai_agent_run_snapshots_conversation_status_created",
        "ai_agent_run_snapshots",
        ["conversation_id", "status", "created_at"],
    )
    op.create_index(
        "ix_ai_agent_run_snapshots_workspace_status_created",
        "ai_agent_run_snapshots",
        ["workspace_id", "status", "created_at"],
    )
    op.create_index(
        "uq_ai_agent_run_snapshots_live_conversation",
        "ai_agent_run_snapshots",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'awaiting_approval'"),
    )

    op.create_table(
        "ai_tool_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("agent_run_id", sa.String(length=36), nullable=False),
        sa.Column("tool_call_id", sa.String(length=80), nullable=False),
        sa.Column("tool_name", sa.String(length=80), nullable=False),
        sa.Column("arguments_json", sa.Text(), nullable=False),
        sa.Column("resource_preview", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("resolved_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("execution_result_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled','expired','executed','failed')",
            name="ck_ai_tool_approvals_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["ai_agent_run_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_tool_approvals_workspace_id", "ai_tool_approvals", ["workspace_id"])
    op.create_index("ix_ai_tool_approvals_conversation_id", "ai_tool_approvals", ["conversation_id"])
    op.create_index("ix_ai_tool_approvals_requested_by_user_id", "ai_tool_approvals", ["requested_by_user_id"])
    op.create_index("ix_ai_tool_approvals_resolved_by_user_id", "ai_tool_approvals", ["resolved_by_user_id"])
    op.create_index("ix_ai_tool_approvals_agent_run_id", "ai_tool_approvals", ["agent_run_id"])
    op.create_index(
        "ix_ai_tool_approvals_workspace_status",
        "ai_tool_approvals",
        ["workspace_id", "status"],
    )
    op.create_index(
        "ix_ai_tool_approvals_conversation_status",
        "ai_tool_approvals",
        ["conversation_id", "status"],
    )
    op.create_index(
        "uq_ai_tool_approvals_agent_run_tool_call",
        "ai_tool_approvals",
        ["agent_run_id", "tool_call_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ai_tool_approvals_agent_run_tool_call", table_name="ai_tool_approvals")
    op.drop_index("ix_ai_tool_approvals_conversation_status", table_name="ai_tool_approvals")
    op.drop_index("ix_ai_tool_approvals_workspace_status", table_name="ai_tool_approvals")
    op.drop_index("ix_ai_tool_approvals_agent_run_id", table_name="ai_tool_approvals")
    op.drop_index("ix_ai_tool_approvals_resolved_by_user_id", table_name="ai_tool_approvals")
    op.drop_index("ix_ai_tool_approvals_requested_by_user_id", table_name="ai_tool_approvals")
    op.drop_index("ix_ai_tool_approvals_conversation_id", table_name="ai_tool_approvals")
    op.drop_index("ix_ai_tool_approvals_workspace_id", table_name="ai_tool_approvals")
    op.drop_table("ai_tool_approvals")

    op.drop_index("uq_ai_agent_run_snapshots_live_conversation", table_name="ai_agent_run_snapshots")
    op.drop_index(
        "ix_ai_agent_run_snapshots_workspace_status_created",
        table_name="ai_agent_run_snapshots",
    )
    op.drop_index(
        "ix_ai_agent_run_snapshots_conversation_status_created",
        table_name="ai_agent_run_snapshots",
    )
    op.drop_index("ix_ai_agent_run_snapshots_requested_by_user_id", table_name="ai_agent_run_snapshots")
    op.drop_index("ix_ai_agent_run_snapshots_workspace_id", table_name="ai_agent_run_snapshots")
    op.drop_index("ix_ai_agent_run_snapshots_conversation_id", table_name="ai_agent_run_snapshots")
    op.drop_table("ai_agent_run_snapshots")
