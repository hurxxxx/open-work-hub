"""add_legacy_issue_search_index_types

Revision ID: d1f2a3b4c5e6
Revises: c9f0a1b2d3e4
Create Date: 2026-06-01 20:10:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "d1f2a3b4c5e6"
down_revision: str | Sequence[str] | None = "c9f0a1b2d3e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_ENTITY_TYPE_CHECK = (
    "entity_type IN "
    "('doc','legacy_issue_chunk','legacy_issue_record','meeting','pms_task','planner_event')"
)
_OLD_ENTITY_TYPE_CHECK = "entity_type IN ('doc','meeting','pms_task','planner_event')"


def upgrade() -> None:
    _replace_entity_type_check(_NEW_ENTITY_TYPE_CHECK)


def downgrade() -> None:
    _replace_entity_type_check(_OLD_ENTITY_TYPE_CHECK)


def _replace_entity_type_check(condition: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("search_index_jobs", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_search_index_jobs_entity_type", type_="check")
            batch_op.create_check_constraint("ck_search_index_jobs_entity_type", condition)
        return
    op.drop_constraint(
        "ck_search_index_jobs_entity_type",
        "search_index_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_search_index_jobs_entity_type",
        "search_index_jobs",
        condition,
    )
