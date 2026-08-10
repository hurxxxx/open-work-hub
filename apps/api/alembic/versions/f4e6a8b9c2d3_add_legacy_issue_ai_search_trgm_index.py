"""add_legacy_issue_ai_search_trgm_index

Revision ID: f4e6a8b9c2d3
Revises: d1f2a3b4c5e6
Create Date: 2026-06-02 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "f4e6a8b9c2d3"
down_revision: str | Sequence[str] | None = "d1f2a3b4c5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_INDEX_NAME = "ix_legacy_issue_records_ai_search_text_trgm"
_SEARCH_TEXT_EXPRESSION = """
lower(
  coalesce(issue_no, '') || ' ' ||
  coalesce(vehicle, '') || ' ' ||
  coalesce(category, '') || ' ' ||
  coalesce(classification, '') || ' ' ||
  coalesce(subsystem, '') || ' ' ||
  coalesce(symptom, '') || ' ' ||
  coalesce(cause, '') || ' ' ||
  coalesce(countermeasure, '') || ' ' ||
  coalesce(result, '') || ' ' ||
  coalesce(notes, '') || ' ' ||
  coalesce(attachment_note, '') || ' ' ||
  coalesce(action_owner, '') || ' ' ||
  coalesce(action_status, '') || ' ' ||
  coalesce(apply_status, '') || ' ' ||
  coalesce(issue_frequency, '') || ' ' ||
  coalesce(issue_status, '') || ' ' ||
  coalesce(source_filename, '') || ' ' ||
  coalesce(sheet_name, '')
)
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {_INDEX_NAME}
        ON legacy_issue_records
        USING gin (({_SEARCH_TEXT_EXPRESSION}) gin_trgm_ops)
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"DROP INDEX IF EXISTS {_INDEX_NAME}")
