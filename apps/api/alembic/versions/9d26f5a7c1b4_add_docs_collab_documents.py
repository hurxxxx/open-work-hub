"""add_docs_collab_documents

Revision ID: 9d26f5a7c1b4
Revises: 1f6a67511c3e
Create Date: 2026-04-14 14:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d26f5a7c1b4"
down_revision: Union[str, Sequence[str], None] = "1f6a67511c3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "docs_collab_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("room_key", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_page_id", sa.String(length=36), nullable=False),
        sa.Column("yjs_state", sa.LargeBinary(), nullable=True),
        sa.Column("snapshot_content_blocks", sa.JSON(), nullable=True),
        sa.Column("last_snapshot_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("room_key", name="uq_docs_collab_documents_room_key"),
        sa.UniqueConstraint(
            "source_type",
            "source_page_id",
            name="uq_docs_collab_documents_source_page",
        ),
    )
    op.create_index(
        "ix_docs_collab_documents_source_page",
        "docs_collab_documents",
        ["source_type", "source_page_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_docs_collab_documents_source_page", table_name="docs_collab_documents")
    op.drop_table("docs_collab_documents")
