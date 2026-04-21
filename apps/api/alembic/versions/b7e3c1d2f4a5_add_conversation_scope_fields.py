"""add_conversation_scope_fields

Revision ID: b7e3c1d2f4a5
Revises: a9c4d7e1f2b3
Create Date: 2026-04-21 23:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e3c1d2f4a5"
down_revision: Union[str, Sequence[str], None] = "a9c4d7e1f2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("scope_ref", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("scope_resource_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_conversations_workspace_scope_resource",
        "conversations",
        ["workspace_id", "scope_ref", "scope_resource_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_workspace_scope_resource", table_name="conversations")
    op.drop_column("conversations", "scope_resource_id")
    op.drop_column("conversations", "scope_ref")
