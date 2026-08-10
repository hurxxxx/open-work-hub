"""rename_pms_issues_to_tasks_and_link_docs

Revision ID: d6e7f8a9b0c1
Revises: c2d3e4f5a6b7
Create Date: 2026-05-21 16:20:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d6e7f8a9b0c1"
down_revision: str | Sequence[str] | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_RENAMES = (
    ("pms_issues", "pms_tasks"),
    ("pms_issue_activity_logs", "pms_task_activity_logs"),
    ("pms_issue_assignees", "pms_task_assignees"),
    ("pms_issue_comments", "pms_task_comments"),
    ("pms_issue_followers", "pms_task_followers"),
    ("pms_issue_labels", "pms_task_labels"),
    ("pms_issue_user_access", "pms_task_user_access"),
)

TASK_COLUMN_RENAMES = (
    ("pms_tasks", "issue_number", "task_number", sa.Integer()),
    ("pms_attachments", "issue_id", "task_id", sa.String(length=36)),
    ("pms_checklist_items", "issue_id", "task_id", sa.String(length=36)),
    ("pms_custom_field_values", "issue_id", "task_id", sa.String(length=36)),
    ("pms_task_activity_logs", "issue_id", "task_id", sa.String(length=36)),
    ("pms_task_assignees", "issue_id", "task_id", sa.String(length=36)),
    ("pms_task_comments", "issue_id", "task_id", sa.String(length=36)),
    ("pms_task_followers", "issue_id", "task_id", sa.String(length=36)),
    ("pms_task_labels", "issue_id", "task_id", sa.String(length=36)),
    ("pms_task_user_access", "issue_id", "task_id", sa.String(length=36)),
    ("pms_time_entries", "issue_id", "task_id", sa.String(length=36)),
    ("meeting_task_links", "issue_id", "task_id", sa.String(length=36)),
)

TASK_INDEX_RENAMES = (
    ("ix_pms_issues_archived", "ix_pms_tasks_archived"),
    ("ix_pms_issues_assignee_id", "ix_pms_tasks_assignee_id"),
    ("ix_pms_issues_due_date", "ix_pms_tasks_due_date"),
    ("ix_pms_issues_list_id", "ix_pms_tasks_list_id"),
    ("ix_pms_issues_milestone_id", "ix_pms_tasks_milestone_id"),
    ("ix_pms_issues_parent_id", "ix_pms_tasks_parent_id"),
    ("ix_pms_issues_priority", "ix_pms_tasks_priority"),
    ("ix_pms_issues_reporter_id", "ix_pms_tasks_reporter_id"),
    ("ix_pms_issues_start_date", "ix_pms_tasks_start_date"),
    ("ix_pms_issues_status", "ix_pms_tasks_status"),
    ("ix_pms_issues_title", "ix_pms_tasks_title"),
    ("ix_pms_attachments_issue_id", "ix_pms_attachments_task_id"),
    ("ix_pms_checklist_items_issue_id", "ix_pms_checklist_items_task_id"),
    ("ix_pms_custom_field_values_issue_id", "ix_pms_custom_field_values_task_id"),
    ("ix_pms_issue_activity_logs_action", "ix_pms_task_activity_logs_action"),
    ("ix_pms_issue_activity_logs_actor_id", "ix_pms_task_activity_logs_actor_id"),
    ("ix_pms_issue_activity_logs_issue_id", "ix_pms_task_activity_logs_task_id"),
    ("ix_pms_issue_assignees_issue_id", "ix_pms_task_assignees_task_id"),
    ("ix_pms_issue_assignees_user_id", "ix_pms_task_assignees_user_id"),
    ("ix_pms_issue_comments_author_id", "ix_pms_task_comments_author_id"),
    ("ix_pms_issue_comments_issue_id", "ix_pms_task_comments_task_id"),
    ("ix_pms_issue_followers_issue_id", "ix_pms_task_followers_task_id"),
    ("ix_pms_issue_followers_user_id", "ix_pms_task_followers_user_id"),
    ("ix_pms_issue_labels_issue_id", "ix_pms_task_labels_task_id"),
    ("ix_pms_issue_labels_label_id", "ix_pms_task_labels_label_id"),
    ("ix_pms_issue_user_access_expires_active", "ix_pms_task_user_access_expires_active"),
    ("ix_pms_issue_user_access_granted_by_meeting_id", "ix_pms_task_user_access_granted_by_meeting_id"),
    ("ix_pms_issue_user_access_granted_by_user_id", "ix_pms_task_user_access_granted_by_user_id"),
    ("ix_pms_issue_user_access_issue_id", "ix_pms_task_user_access_task_id"),
    ("ix_pms_issue_user_access_meeting_revoked", "ix_pms_task_user_access_meeting_revoked"),
    ("ix_pms_issue_user_access_revoked_by_user_id", "ix_pms_task_user_access_revoked_by_user_id"),
    ("ix_pms_issue_user_access_user_id", "ix_pms_task_user_access_user_id"),
    ("ix_pms_issue_user_access_user_revoked", "ix_pms_task_user_access_user_revoked"),
    ("uq_pms_issue_user_access_active", "uq_pms_task_user_access_active"),
    ("ix_pms_time_entries_issue_id", "ix_pms_time_entries_task_id"),
    ("ix_meeting_task_links_issue_id", "ix_meeting_task_links_task_id"),
)

TASK_CONSTRAINT_RENAMES = (
    ("pms_tasks", "uq_pms_issue_number", "uq_pms_task_number"),
    ("pms_task_assignees", "uq_pms_issue_assignee", "uq_pms_task_assignee"),
    ("pms_task_followers", "uq_pms_issue_follower", "uq_pms_task_follower"),
    ("pms_task_labels", "uq_pms_issue_label", "uq_pms_task_label"),
)


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _rename_table(old: str, new: str) -> None:
    if _table_exists(old) and not _table_exists(new):
        op.rename_table(old, new)


def _rename_column(table: str, old: str, new: str, existing_type: sa.TypeEngine) -> None:
    if _column_exists(table, old) and not _column_exists(table, new):
        op.alter_column(table, old, new_column_name=new, existing_type=existing_type)


def _rename_indexes(pairs: Sequence[tuple[str, str]]) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for old, new in pairs:
        op.execute(f'ALTER INDEX IF EXISTS "{old}" RENAME TO "{new}"')


def _rename_constraints(pairs: Sequence[tuple[str, str, str]]) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, old, new in pairs:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF to_regclass('{table}') IS NOT NULL
                   AND EXISTS (
                       SELECT 1
                       FROM pg_constraint
                       WHERE conrelid = '{table}'::regclass
                         AND conname = '{old}'
                   ) THEN
                    ALTER TABLE "{table}" RENAME CONSTRAINT "{old}" TO "{new}";
                END IF;
            END
            $$;
            """
        )


def _drop_search_entity_type_check() -> None:
    if op.get_bind().dialect.name == "postgresql" and _table_exists("search_index_jobs"):
        op.execute(
            "ALTER TABLE search_index_jobs "
            "DROP CONSTRAINT IF EXISTS ck_search_index_jobs_entity_type"
        )


def _create_search_entity_type_check(entity_type: str) -> None:
    if op.get_bind().dialect.name == "postgresql" and _table_exists("search_index_jobs"):
        op.execute(
            "ALTER TABLE search_index_jobs "
            "ADD CONSTRAINT ck_search_index_jobs_entity_type "
            f"CHECK (entity_type IN ('doc','meeting','{entity_type}','planner_event'))"
        )


def _replace_jsonb_key(table: str, column: str, old: str, new: str) -> None:
    if op.get_bind().dialect.name != "postgresql" or not _column_exists(table, column):
        return
    op.execute(
        f"""
        UPDATE {table}
        SET {column} = replace({column}::text, '"{old}"', '"{new}"')::jsonb
        WHERE {column}::text LIKE '%"{old}"%'
        """
    )


def upgrade() -> None:
    if _table_exists("pms_schedule_dependencies"):
        op.drop_table("pms_schedule_dependencies")

    for old, new in TABLE_RENAMES:
        _rename_table(old, new)
    for table, old, new, existing_type in TASK_COLUMN_RENAMES:
        _rename_column(table, old, new, existing_type)

    _rename_indexes(TASK_INDEX_RENAMES)
    _rename_constraints(TASK_CONSTRAINT_RENAMES)

    if not _table_exists("pms_task_doc_links"):
        op.create_table(
            "pms_task_doc_links",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("task_id", sa.String(length=36), nullable=False),
            sa.Column("doc_id", sa.String(length=36), nullable=False),
            sa.Column("created_by_id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["doc_id"], ["docs_native_docs.id"]),
            sa.ForeignKeyConstraint(["task_id"], ["pms_tasks.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("task_id", "doc_id", name="uq_pms_task_doc_link"),
        )
        op.create_index(op.f("ix_pms_task_doc_links_created_by_id"), "pms_task_doc_links", ["created_by_id"])
        op.create_index(op.f("ix_pms_task_doc_links_doc_id"), "pms_task_doc_links", ["doc_id"])
        op.create_index(op.f("ix_pms_task_doc_links_task_id"), "pms_task_doc_links", ["task_id"])

    _drop_search_entity_type_check()
    if _column_exists("search_index_jobs", "entity_type"):
        op.execute("UPDATE search_index_jobs SET entity_type = 'pms_task' WHERE entity_type = 'pms_issue'")
    _create_search_entity_type_check("pms_task")

    if _column_exists("rag_sync_jobs", "resource_type"):
        op.execute("UPDATE rag_sync_jobs SET resource_type = 'pms_task' WHERE resource_type = 'pms_issue'")
    if _column_exists("pms_notifications", "reference_type"):
        op.execute("UPDATE pms_notifications SET reference_type = 'task' WHERE reference_type = 'issue'")
    if _column_exists("media_files", "resource_type"):
        op.execute("UPDATE media_files SET resource_type = 'task' WHERE resource_type = 'issue'")
    if _column_exists("knowledge_source_documents", "origin_ref_type"):
        op.execute(
            "UPDATE knowledge_source_documents "
            "SET origin_ref_type = 'pms_task' WHERE origin_ref_type = 'pms_issue'"
        )
    _replace_jsonb_key("rag_visibility_recompute_jobs", "cursor", "issue_ids", "task_ids")


def downgrade() -> None:
    _drop_search_entity_type_check()
    if _column_exists("search_index_jobs", "entity_type"):
        op.execute("UPDATE search_index_jobs SET entity_type = 'pms_issue' WHERE entity_type = 'pms_task'")
    _create_search_entity_type_check("pms_issue")

    if _column_exists("rag_sync_jobs", "resource_type"):
        op.execute("UPDATE rag_sync_jobs SET resource_type = 'pms_issue' WHERE resource_type = 'pms_task'")
    if _column_exists("pms_notifications", "reference_type"):
        op.execute("UPDATE pms_notifications SET reference_type = 'issue' WHERE reference_type = 'task'")
    if _column_exists("media_files", "resource_type"):
        op.execute("UPDATE media_files SET resource_type = 'issue' WHERE resource_type = 'task'")
    if _column_exists("knowledge_source_documents", "origin_ref_type"):
        op.execute(
            "UPDATE knowledge_source_documents "
            "SET origin_ref_type = 'pms_issue' WHERE origin_ref_type = 'pms_task'"
        )
    _replace_jsonb_key("rag_visibility_recompute_jobs", "cursor", "task_ids", "issue_ids")

    if _table_exists("pms_task_doc_links"):
        op.drop_index(op.f("ix_pms_task_doc_links_task_id"), table_name="pms_task_doc_links")
        op.drop_index(op.f("ix_pms_task_doc_links_doc_id"), table_name="pms_task_doc_links")
        op.drop_index(op.f("ix_pms_task_doc_links_created_by_id"), table_name="pms_task_doc_links")
        op.drop_table("pms_task_doc_links")

    _rename_constraints([(table, new, old) for table, old, new in reversed(TASK_CONSTRAINT_RENAMES)])
    _rename_indexes([(new, old) for old, new in reversed(TASK_INDEX_RENAMES)])

    for table, old, new, existing_type in reversed(TASK_COLUMN_RENAMES):
        _rename_column(table, new, old, existing_type)
    for old, new in reversed(TABLE_RENAMES):
        _rename_table(new, old)

    if not _table_exists("pms_schedule_dependencies"):
        op.create_table(
            "pms_schedule_dependencies",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("list_id", sa.String(length=36), nullable=False),
            sa.Column("predecessor_kind", sa.String(length=24), nullable=False),
            sa.Column("predecessor_id", sa.String(length=36), nullable=False),
            sa.Column("successor_kind", sa.String(length=24), nullable=False),
            sa.Column("successor_id", sa.String(length=36), nullable=False),
            sa.Column("relation_type", sa.String(length=24), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["list_id"], ["pms_task_lists.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_pms_schedule_dependencies_list_id"), "pms_schedule_dependencies", ["list_id"])
        op.create_index(op.f("ix_pms_schedule_dependencies_predecessor_id"), "pms_schedule_dependencies", ["predecessor_id"])
        op.create_index(op.f("ix_pms_schedule_dependencies_successor_id"), "pms_schedule_dependencies", ["successor_id"])
