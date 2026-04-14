"""add_meeting_notes_fields

Revision ID: 1f6a67511c3e
Revises: 4f9f9d0c2b1e
Create Date: 2026-04-14 11:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1f6a67511c3e"
down_revision: Union[str, Sequence[str], None] = "4f9f9d0c2b1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("notes_doc_id", sa.String(length=36), nullable=True))
    op.add_column("meetings", sa.Column("notes_page_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_meetings_notes_doc_id",
        "meetings",
        "docs_native_docs",
        ["notes_doc_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_meetings_notes_page_id",
        "meetings",
        "docs_native_doc_pages",
        ["notes_page_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_meetings_notes_page_id", "meetings", type_="foreignkey")
    op.drop_constraint("fk_meetings_notes_doc_id", "meetings", type_="foreignkey")
    op.drop_column("meetings", "notes_page_id")
    op.drop_column("meetings", "notes_doc_id")
