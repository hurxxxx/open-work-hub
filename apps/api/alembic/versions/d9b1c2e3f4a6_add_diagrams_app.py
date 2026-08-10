"""add_diagrams_app

Revision ID: d9b1c2e3f4a6
Revises: d9a0b1c2d3e5
Create Date: 2026-06-26 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9b1c2e3f4a6"
down_revision: Union[str, Sequence[str], None] = "d9a0b1c2d3e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "diagrams",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_storage_key", sa.String(length=1024), nullable=False),
        sa.Column("preview_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("preview_storage_key", name="uq_diagrams_preview_storage_key"),
        sa.UniqueConstraint("source_storage_key", name="uq_diagrams_source_storage_key"),
    )
    op.create_index("ix_diagrams_archived_at", "diagrams", ["archived_at"])
    op.create_index("ix_diagrams_owner_id", "diagrams", ["owner_id"])
    op.create_index("ix_diagrams_updated_at", "diagrams", ["updated_at"])
    op.create_index("ix_diagrams_workspace_id", "diagrams", ["workspace_id"])
    op.create_index(
        "ix_diagrams_workspace_archived_updated",
        "diagrams",
        ["workspace_id", "archived_at", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_diagrams_workspace_archived_updated", table_name="diagrams")
    op.drop_index("ix_diagrams_workspace_id", table_name="diagrams")
    op.drop_index("ix_diagrams_updated_at", table_name="diagrams")
    op.drop_index("ix_diagrams_owner_id", table_name="diagrams")
    op.drop_index("ix_diagrams_archived_at", table_name="diagrams")
    op.drop_table("diagrams")
