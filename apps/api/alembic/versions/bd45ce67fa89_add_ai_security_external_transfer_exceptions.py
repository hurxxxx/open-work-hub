"""add ai security external transfer exceptions

Revision ID: bd45ce67fa89
Revises: ac34bd56ef78
Create Date: 2026-06-24 22:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "bd45ce67fa89"
down_revision: Union[str, Sequence[str], None] = "ac34bd56ef78"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "ai_security_external_transfer_exceptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("org_unit_id", sa.String(length=36), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("app_id", sa.String(length=64), nullable=True),
        sa.Column("task_kind", sa.String(length=128), nullable=True),
        sa.Column("capability", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("allowed_blocker_types_json", JSONB_COMPAT, nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_unit_id"], ["org_units.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column_name in (
        "app_id",
        "capability",
        "enabled",
        "expires_at",
        "org_unit_id",
        "provider",
        "task_kind",
        "user_id",
        "workspace_id",
    ):
        op.create_index(
            op.f(f"ix_ai_security_external_transfer_exceptions_{column_name}"),
            "ai_security_external_transfer_exceptions",
            [column_name],
            unique=False,
        )


def downgrade() -> None:
    for column_name in (
        "workspace_id",
        "user_id",
        "task_kind",
        "provider",
        "org_unit_id",
        "expires_at",
        "enabled",
        "capability",
        "app_id",
    ):
        op.drop_index(
            op.f(f"ix_ai_security_external_transfer_exceptions_{column_name}"),
            table_name="ai_security_external_transfer_exceptions",
        )
    op.drop_table("ai_security_external_transfer_exceptions")
