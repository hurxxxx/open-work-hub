"""rename_pms_list_to_task_list

Revision ID: 3e4983704c82
Revises: 9d26f5a7c1b4
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "3e4983704c82"
down_revision: Union[str, Sequence[str], None] = "9d26f5a7c1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_RENAMES: tuple[tuple[str, str], ...] = (
    ("pms_lists", "pms_task_lists"),
    ("pms_project_statuses", "pms_task_list_statuses"),
)

INDEX_RENAMES: tuple[tuple[str, str], ...] = (
    ("ix_pms_lists_archived", "ix_pms_task_lists_archived"),
    ("ix_pms_lists_created_by_id", "ix_pms_task_lists_created_by_id"),
    ("ix_pms_lists_folder_id", "ix_pms_task_lists_folder_id"),
    ("ix_pms_lists_key", "ix_pms_task_lists_key"),
    ("ix_pms_lists_name", "ix_pms_task_lists_name"),
    ("ix_pms_lists_status", "ix_pms_task_lists_status"),
    ("ix_pms_lists_team_id", "ix_pms_task_lists_team_id"),
    ("ix_pms_project_statuses_list_id", "ix_pms_task_list_statuses_list_id"),
    ("ix_pms_project_statuses_slug", "ix_pms_task_list_statuses_slug"),
)

CONSTRAINT_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("pms_task_list_statuses", "uq_pms_project_status_slug", "uq_pms_task_list_status_slug"),
)


def _rename_indexes(pairs: tuple[tuple[str, str], ...]) -> None:
    for old_name, new_name in pairs:
        op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')


def _rename_constraints(pairs: tuple[tuple[str, str, str], ...]) -> None:
    for table_name, old_name, new_name in pairs:
        op.execute(
            f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"'
        )


def upgrade() -> None:
    for old_name, new_name in TABLE_RENAMES:
        op.rename_table(old_name, new_name)
    _rename_indexes(INDEX_RENAMES)
    _rename_constraints(CONSTRAINT_RENAMES)


def downgrade() -> None:
    _rename_constraints(
        tuple(
            (table_name, new, old)
            for table_name, old, new in CONSTRAINT_RENAMES
        )
    )
    _rename_indexes(tuple((new, old) for old, new in INDEX_RENAMES))
    for old_name, new_name in reversed(TABLE_RENAMES):
        op.rename_table(new_name, old_name)
