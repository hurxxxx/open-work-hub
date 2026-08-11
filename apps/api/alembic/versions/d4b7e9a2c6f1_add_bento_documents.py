"""add workspace-managed bento documents

Revision ID: d4b7e9a2c6f1
Revises: c8a1e4f7b2d9
Create Date: 2026-08-11 11:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4b7e9a2c6f1"
down_revision: str | Sequence[str] | None = "c8a1e4f7b2d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bento_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "visibility in ('personal', 'workspace')",
            name="ck_bento_documents_visibility",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bento_documents_workspace_id", "bento_documents", ["workspace_id"])
    op.create_index("ix_bento_documents_owner_id", "bento_documents", ["owner_id"])
    op.create_index("ix_bento_documents_archived_at", "bento_documents", ["archived_at"])
    op.create_index("ix_bento_documents_updated_at", "bento_documents", ["updated_at"])
    op.create_index("ix_bento_documents_visibility", "bento_documents", ["visibility"])
    op.create_index(
        "ix_bento_documents_workspace_archived_updated",
        "bento_documents",
        ["workspace_id", "archived_at", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bento_documents_workspace_archived_updated",
        table_name="bento_documents",
    )
    op.drop_index("ix_bento_documents_visibility", table_name="bento_documents")
    op.drop_index("ix_bento_documents_updated_at", table_name="bento_documents")
    op.drop_index("ix_bento_documents_archived_at", table_name="bento_documents")
    op.drop_index("ix_bento_documents_owner_id", table_name="bento_documents")
    op.drop_index("ix_bento_documents_workspace_id", table_name="bento_documents")
    op.drop_table("bento_documents")
