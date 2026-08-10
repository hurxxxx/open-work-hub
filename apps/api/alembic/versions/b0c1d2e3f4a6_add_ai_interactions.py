"""add_ai_interactions

Revision ID: b0c1d2e3f4a6
Revises: 9a1f7c3e5d2b
Create Date: 2026-06-24 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b0c1d2e3f4a6"
down_revision: str | Sequence[str] | None = "9a1f7c3e5d2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "ai_interactions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("principal_kind", sa.String(length=32), nullable=True),
        sa.Column("principal_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("task_kind", sa.String(length=128), nullable=True),
        sa.Column("capability", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("pool", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("usage_json", JSONB_COMPAT, nullable=True),
        sa.Column("input_text_count", sa.Integer(), nullable=True),
        sa.Column("input_char_count", sa.Integer(), nullable=True),
        sa.Column("pii_hits_json", JSONB_COMPAT, nullable=True),
        sa.Column("metadata_json", JSONB_COMPAT, nullable=True),
        sa.Column("conversation_id", sa.String(length=36), nullable=True),
        sa.Column("entity_kind", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=128), nullable=True),
        sa.Column("agent_run_id", sa.String(length=36), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_interactions_action", "ai_interactions", ["action"])
    op.create_index("ix_ai_interactions_agent_run_id", "ai_interactions", ["agent_run_id"])
    op.create_index("ix_ai_interactions_actor_user_id", "ai_interactions", ["actor_user_id"])
    op.create_index(
        "ix_ai_interactions_actor_created", "ai_interactions", ["actor_user_id", "created_at"]
    )
    op.create_index("ix_ai_interactions_capability", "ai_interactions", ["capability"])
    op.create_index("ix_ai_interactions_conversation_id", "ai_interactions", ["conversation_id"])
    op.create_index(
        "ix_ai_interactions_conversation_created",
        "ai_interactions",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_ai_interactions_entity_id", "ai_interactions", ["entity_id"])
    op.create_index("ix_ai_interactions_entity_kind", "ai_interactions", ["entity_kind"])
    op.create_index("ix_ai_interactions_model", "ai_interactions", ["model"])
    op.create_index("ix_ai_interactions_pool", "ai_interactions", ["pool"])
    op.create_index("ix_ai_interactions_principal_id", "ai_interactions", ["principal_id"])
    op.create_index("ix_ai_interactions_provider", "ai_interactions", ["provider"])
    op.create_index("ix_ai_interactions_source", "ai_interactions", ["source"])
    op.create_index("ix_ai_interactions_status", "ai_interactions", ["status"])
    op.create_index("ix_ai_interactions_task_kind", "ai_interactions", ["task_kind"])
    op.create_index(
        "ix_ai_interactions_task_created", "ai_interactions", ["task_kind", "created_at"]
    )
    op.create_index("ix_ai_interactions_trace_id", "ai_interactions", ["trace_id"])
    op.create_index("ix_ai_interactions_workspace_id", "ai_interactions", ["workspace_id"])
    op.create_index(
        "ix_ai_interactions_workspace_created",
        "ai_interactions",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_interactions_workspace_created", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_workspace_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_trace_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_task_created", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_task_kind", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_status", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_source", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_provider", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_principal_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_pool", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_model", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_entity_kind", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_entity_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_conversation_created", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_conversation_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_capability", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_actor_created", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_actor_user_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_agent_run_id", table_name="ai_interactions")
    op.drop_index("ix_ai_interactions_action", table_name="ai_interactions")
    op.drop_table("ai_interactions")
