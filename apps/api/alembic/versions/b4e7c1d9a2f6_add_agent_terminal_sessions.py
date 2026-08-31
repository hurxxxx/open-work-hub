"""Add platform-admin agent terminal session metadata.

Revision ID: b4e7c1d9a2f6
Revises: a7c4e9f2b6d1
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b4e7c1d9a2f6"
down_revision: str | Sequence[str] | None = "a7c4e9f2b6d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_terminal_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("tool", sa.String(length=24), server_default="codex", nullable=False),
        sa.Column("root_key", sa.String(length=64), nullable=False),
        sa.Column("root_path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="starting", nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=120), nullable=True),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("tool IN ('codex')", name="ck_agent_terminal_sessions_tool"),
        sa.CheckConstraint(
            "status IN ('starting', 'running', 'exited', 'terminated', 'failed')",
            name="ck_agent_terminal_sessions_status",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_terminal_sessions_owner_created",
        "agent_terminal_sessions",
        ["owner_id", "created_at"],
    )
    op.create_index(
        "ix_agent_terminal_sessions_status_updated",
        "agent_terminal_sessions",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_terminal_sessions_status_updated",
        table_name="agent_terminal_sessions",
    )
    op.drop_index(
        "ix_agent_terminal_sessions_owner_created",
        table_name="agent_terminal_sessions",
    )
    op.drop_table("agent_terminal_sessions")
