"""drop_workspace_app_access_tables

Revision ID: 4f9f9d0c2b1e
Revises: c3e67d4f1a2b
Create Date: 2026-04-13 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f9f9d0c2b1e"
down_revision: Union[str, Sequence[str], None] = "c3e67d4f1a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f("ix_workspace_enabled_apps_app_code"), table_name="workspace_enabled_apps")
    op.drop_index(op.f("ix_workspace_enabled_apps_workspace_id"), table_name="workspace_enabled_apps")
    op.drop_table("workspace_enabled_apps")

    op.drop_index(op.f("ix_feature_policies_enabled"), table_name="feature_policies")
    op.drop_index(op.f("ix_feature_policies_code"), table_name="feature_policies")
    op.drop_table("feature_policies")


def downgrade() -> None:
    op.create_table(
        "feature_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("required_permissions", sa.JSON(), nullable=False),
        sa.Column("allowed_workspace_keys", sa.JSON(), nullable=False),
        sa.Column("allowed_group_slugs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_feature_policies_code"), "feature_policies", ["code"], unique=True)
    op.create_index(op.f("ix_feature_policies_enabled"), "feature_policies", ["enabled"], unique=False)

    op.create_table(
        "workspace_enabled_apps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("app_code", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "app_code", name="uq_workspace_enabled_app"),
    )
    op.create_index(
        op.f("ix_workspace_enabled_apps_workspace_id"),
        "workspace_enabled_apps",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_enabled_apps_app_code"),
        "workspace_enabled_apps",
        ["app_code"],
        unique=False,
    )
