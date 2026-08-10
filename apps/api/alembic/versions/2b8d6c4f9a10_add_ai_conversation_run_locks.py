"""add_ai_conversation_run_locks

Revision ID: 2b8d6c4f9a10
Revises: 9f3a2b7c6d10
Create Date: 2026-05-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "2b8d6c4f9a10"
down_revision: str | Sequence[str] | None = "9f3a2b7c6d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversation_run_locks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=80), nullable=False),
        sa.Column(
            "lock_kind",
            sa.String(length=32),
            server_default=sa.text("'chat'"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "lock_kind IN ('chat')",
            name="ck_ai_conversation_run_locks_kind",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_conversation_run_locks_conversation_id",
        "ai_conversation_run_locks",
        ["conversation_id"],
    )
    op.create_index(
        "ix_ai_conversation_run_locks_expires_at",
        "ai_conversation_run_locks",
        ["expires_at"],
    )
    op.create_index(
        "ix_ai_conversation_run_locks_requested_by_user_id",
        "ai_conversation_run_locks",
        ["requested_by_user_id"],
    )
    op.create_index(
        "ix_ai_conversation_run_locks_workspace_expires",
        "ai_conversation_run_locks",
        ["workspace_id", "expires_at"],
    )
    op.create_index(
        "ix_ai_conversation_run_locks_workspace_id",
        "ai_conversation_run_locks",
        ["workspace_id"],
    )
    op.create_index(
        "uq_ai_conversation_run_locks_conversation",
        "ai_conversation_run_locks",
        ["conversation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_conversation_run_locks_conversation",
        table_name="ai_conversation_run_locks",
    )
    op.drop_index(
        "ix_ai_conversation_run_locks_workspace_id",
        table_name="ai_conversation_run_locks",
    )
    op.drop_index(
        "ix_ai_conversation_run_locks_workspace_expires",
        table_name="ai_conversation_run_locks",
    )
    op.drop_index(
        "ix_ai_conversation_run_locks_requested_by_user_id",
        table_name="ai_conversation_run_locks",
    )
    op.drop_index(
        "ix_ai_conversation_run_locks_expires_at",
        table_name="ai_conversation_run_locks",
    )
    op.drop_index(
        "ix_ai_conversation_run_locks_conversation_id",
        table_name="ai_conversation_run_locks",
    )
    op.drop_table("ai_conversation_run_locks")
