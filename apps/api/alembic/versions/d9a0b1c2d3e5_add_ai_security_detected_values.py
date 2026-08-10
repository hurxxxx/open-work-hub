"""add_ai_security_detected_values

Revision ID: d9a0b1c2d3e5
Revises: d8e9f0a1b3c4
Create Date: 2026-06-25 17:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9a0b1c2d3e5"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_security_detected_values",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("audit_log_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("app_id", sa.String(length=64), nullable=True),
        sa.Column("task_kind", sa.String(length=128), nullable=True),
        sa.Column("capability", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("reason_code", sa.String(length=120), nullable=True),
        sa.Column("detector", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("blocker_type", sa.String(length=80), nullable=False),
        sa.Column("detected_value", sa.Text(), nullable=True),
        sa.Column("value_hash", sa.String(length=64), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["audit_log_id"],
            ["audit_logs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_security_detected_values_action",
        "ai_security_detected_values",
        ["action"],
    )
    op.create_index(
        "ix_ai_security_detected_values_actor_user_id",
        "ai_security_detected_values",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_ai_security_detected_values_app_id",
        "ai_security_detected_values",
        ["app_id"],
    )
    op.create_index(
        "ix_ai_security_detected_values_audit_log_id",
        "ai_security_detected_values",
        ["audit_log_id"],
    )
    op.create_index(
        "ix_ai_security_detected_values_blocker_type",
        "ai_security_detected_values",
        ["blocker_type"],
    )
    op.create_index(
        "ix_ai_security_detected_values_capability",
        "ai_security_detected_values",
        ["capability"],
    )
    op.create_index(
        "ix_ai_security_detected_values_detector",
        "ai_security_detected_values",
        ["detector"],
    )
    op.create_index(
        "ix_ai_security_detected_values_entity_type",
        "ai_security_detected_values",
        ["entity_type"],
    )
    op.create_index(
        "ix_ai_security_detected_values_period_detector",
        "ai_security_detected_values",
        ["created_at", "detector"],
    )
    op.create_index(
        "ix_ai_security_detected_values_period_type_hash",
        "ai_security_detected_values",
        ["created_at", "entity_type", "value_hash"],
    )
    op.create_index(
        "ix_ai_security_detected_values_provider",
        "ai_security_detected_values",
        ["provider"],
    )
    op.create_index(
        "ix_ai_security_detected_values_reason_code",
        "ai_security_detected_values",
        ["reason_code"],
    )
    op.create_index(
        "ix_ai_security_detected_values_source",
        "ai_security_detected_values",
        ["source"],
    )
    op.create_index(
        "ix_ai_security_detected_values_task_kind",
        "ai_security_detected_values",
        ["task_kind"],
    )
    op.create_index(
        "ix_ai_security_detected_values_value_hash",
        "ai_security_detected_values",
        ["value_hash"],
    )
    op.create_index(
        "ix_ai_security_detected_values_workspace_id",
        "ai_security_detected_values",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_security_detected_values_workspace_id",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_value_hash",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_task_kind",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_source",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_reason_code",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_provider",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_period_type_hash",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_period_detector",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_entity_type",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_detector",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_capability",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_blocker_type",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_audit_log_id",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_app_id",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_actor_user_id",
        table_name="ai_security_detected_values",
    )
    op.drop_index(
        "ix_ai_security_detected_values_action",
        table_name="ai_security_detected_values",
    )
    op.drop_table("ai_security_detected_values")
