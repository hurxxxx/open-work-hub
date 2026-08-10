"""add_user_default_workspace

Revision ID: c6a0b7d8e9f1
Revises: a1b2c3d4e5f7
Create Date: 2026-05-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6a0b7d8e9f1"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("default_workspace_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_users_default_workspace_id"),
        "users",
        ["default_workspace_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_users_default_workspace_id_workspaces",
        "users",
        "workspaces",
        ["default_workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_users_default_workspace_id_workspaces",
        "users",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_users_default_workspace_id"), table_name="users")
    op.drop_column("users", "default_workspace_id")
