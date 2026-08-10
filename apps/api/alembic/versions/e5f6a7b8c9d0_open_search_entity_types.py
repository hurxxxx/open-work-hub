"""open_search_entity_types

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b9c0
Create Date: 2026-06-02 19:58:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CONSTRAINT_NAME = "ck_search_index_jobs_entity_type"
_TABLE_NAME = "search_index_jobs"
_LEGACY_CONDITION = (
    "entity_type IN "
    "('doc','legacy_issue_chunk','legacy_issue_record','meeting','pms_task','planner_event')"
)


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.drop_constraint(_CONSTRAINT_NAME, _TABLE_NAME, type_="check")


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.execute(
        "DELETE FROM search_index_jobs WHERE entity_type NOT IN "
        "('doc','legacy_issue_chunk','legacy_issue_record','meeting','pms_task','planner_event')"
    )
    op.create_check_constraint(_CONSTRAINT_NAME, _TABLE_NAME, _LEGACY_CONDITION)
