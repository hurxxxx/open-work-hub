"""add_workspace_app_entitlements

Revision ID: f5b4e3c2d1a0
Revises: c7a2f1e8b3d4
Create Date: 2026-04-18 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5b4e3c2d1a0"
down_revision: Union[str, Sequence[str], None] = "c7a2f1e8b3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_app_entitlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "app_id", name="uq_workspace_app_entitlement"),
    )
    op.create_index(
        op.f("ix_workspace_app_entitlements_workspace_id"),
        "workspace_app_entitlements",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_app_entitlements_app_id"),
        "workspace_app_entitlements",
        ["app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_app_entitlements_enabled"),
        "workspace_app_entitlements",
        ["enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workspace_app_entitlements_enabled"),
        table_name="workspace_app_entitlements",
    )
    op.drop_index(
        op.f("ix_workspace_app_entitlements_app_id"),
        table_name="workspace_app_entitlements",
    )
    op.drop_index(
        op.f("ix_workspace_app_entitlements_workspace_id"),
        table_name="workspace_app_entitlements",
    )
    op.drop_table("workspace_app_entitlements")
