"""add_docs_collections

Revision ID: 8a7c6e5d4b3f
Revises: 6c9a1f2b4d7e
Create Date: 2026-05-12 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a7c6e5d4b3f"
down_revision: Union[str, Sequence[str], None] = "6c9a1f2b4d7e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "docs_collections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("scope IN ('workspace', 'private')", name="ck_docs_collections_scope"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_docs_collections_name_not_blank"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_docs_collections_workspace_scope_owner",
        "docs_collections",
        ["workspace_id", "scope", "owner_id"],
        unique=False,
    )
    op.create_index(op.f("ix_docs_collections_workspace_id"), "docs_collections", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_docs_collections_scope"), "docs_collections", ["scope"], unique=False)
    op.create_index(op.f("ix_docs_collections_owner_id"), "docs_collections", ["owner_id"], unique=False)

    op.add_column("docs_native_docs", sa.Column("collection_id", sa.String(length=36), nullable=True))
    op.add_column(
        "docs_native_docs",
        sa.Column("doc_type", sa.String(length=40), server_default="general", nullable=False),
    )
    op.create_index(op.f("ix_docs_native_docs_collection_id"), "docs_native_docs", ["collection_id"], unique=False)
    op.create_index(op.f("ix_docs_native_docs_doc_type"), "docs_native_docs", ["doc_type"], unique=False)
    op.create_foreign_key(
        "fk_docs_native_docs_collection_id_docs_collections",
        "docs_native_docs",
        "docs_collections",
        ["collection_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE docs_native_docs
        SET doc_type = 'meeting_notes'
        WHERE source_app = 'meeting'
           OR source_kind = 'meeting_notes'
        """
    )
    op.alter_column("docs_native_docs", "doc_type", server_default=None)
    op.create_check_constraint(
        "ck_docs_native_docs_doc_type",
        "docs_native_docs",
        "doc_type IN ('general', 'meeting_notes', 'project_brief', 'spec', 'policy', 'guide', 'memo')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_docs_native_docs_doc_type", "docs_native_docs", type_="check")
    op.drop_constraint(
        "fk_docs_native_docs_collection_id_docs_collections",
        "docs_native_docs",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_docs_native_docs_doc_type"), table_name="docs_native_docs")
    op.drop_index(op.f("ix_docs_native_docs_collection_id"), table_name="docs_native_docs")
    op.drop_column("docs_native_docs", "doc_type")
    op.drop_column("docs_native_docs", "collection_id")

    op.drop_index(op.f("ix_docs_collections_owner_id"), table_name="docs_collections")
    op.drop_index(op.f("ix_docs_collections_scope"), table_name="docs_collections")
    op.drop_index(op.f("ix_docs_collections_workspace_id"), table_name="docs_collections")
    op.drop_index("ix_docs_collections_workspace_scope_owner", table_name="docs_collections")
    op.drop_table("docs_collections")
