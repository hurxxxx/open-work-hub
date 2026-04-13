"""rename_pms_project_to_list

Revision ID: 5f2f47dc2d11
Revises: 2d4f6c9ab1ef
Create Date: 2026-04-13 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "5f2f47dc2d11"
down_revision: Union[str, Sequence[str], None] = "2d4f6c9ab1ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_COLUMN_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("pms_project_statuses", "project_id", "list_id"),
    ("pms_milestones", "project_id", "list_id"),
    ("pms_labels", "project_id", "list_id"),
    ("pms_issues", "project_id", "list_id"),
    ("pms_schedule_dependencies", "project_id", "list_id"),
    ("pms_task_templates", "project_id", "list_id"),
    ("pms_custom_fields", "project_id", "list_id"),
)

INDEX_RENAMES: tuple[tuple[str, str], ...] = (
    ("ix_pms_projects_archived", "ix_pms_lists_archived"),
    ("ix_pms_projects_created_by_id", "ix_pms_lists_created_by_id"),
    ("ix_pms_projects_folder_id", "ix_pms_lists_folder_id"),
    ("ix_pms_projects_key", "ix_pms_lists_key"),
    ("ix_pms_projects_name", "ix_pms_lists_name"),
    ("ix_pms_projects_status", "ix_pms_lists_status"),
    ("ix_pms_projects_team_id", "ix_pms_lists_team_id"),
    ("ix_pms_project_statuses_project_id", "ix_pms_project_statuses_list_id"),
    ("ix_pms_milestones_project_id", "ix_pms_milestones_list_id"),
    ("ix_pms_labels_project_id", "ix_pms_labels_list_id"),
    ("ix_pms_issues_project_id", "ix_pms_issues_list_id"),
    ("ix_pms_schedule_dependencies_project_id", "ix_pms_schedule_dependencies_list_id"),
    ("ix_pms_task_templates_project_id", "ix_pms_task_templates_list_id"),
    ("ix_pms_custom_fields_project_id", "ix_pms_custom_fields_list_id"),
)


def _rename_indexes(pairs: tuple[tuple[str, str], ...]) -> None:
    for old_name, new_name in pairs:
        op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')


def upgrade() -> None:
    op.rename_table("pms_projects", "pms_lists")
    _rename_indexes(INDEX_RENAMES)
    for table_name, old_name, new_name in TABLE_COLUMN_RENAMES:
        op.alter_column(table_name, old_name, new_column_name=new_name)


def downgrade() -> None:
    for table_name, old_name, new_name in reversed(TABLE_COLUMN_RENAMES):
        op.alter_column(table_name, new_name, new_column_name=old_name)
    _rename_indexes(tuple((new, old) for old, new in INDEX_RENAMES))
    op.rename_table("pms_lists", "pms_projects")
