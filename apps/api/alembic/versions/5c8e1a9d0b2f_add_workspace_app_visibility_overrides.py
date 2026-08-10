"""add_workspace_app_visibility_overrides

Revision ID: 5c8e1a9d0b2f
Revises: e2a4b6c8d0f2
Create Date: 2026-06-11 15:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5c8e1a9d0b2f"
down_revision: Union[str, Sequence[str], None] = "e2a4b6c8d0f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_platform_app_visibility_app_id",
        "platform_app_visibility",
        type_="unique",
    )
    op.add_column(
        "workspace_app_entitlements",
        sa.Column("visibility_override", sa.Boolean(), nullable=True),
    )
    op.create_index(
        op.f("ix_workspace_app_entitlements_visibility_override"),
        "workspace_app_entitlements",
        ["visibility_override"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            UPDATE workspace_app_entitlements
            SET visibility_override = false
            WHERE enabled = false
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workspace_app_entitlements_visibility_override"),
        table_name="workspace_app_entitlements",
    )
    op.drop_column("workspace_app_entitlements", "visibility_override")
    op.create_unique_constraint(
        "uq_platform_app_visibility_app_id",
        "platform_app_visibility",
        ["app_id"],
    )
