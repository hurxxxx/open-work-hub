"""add bulk query indexes

Revision ID: c8d9e0f1a2b3
Revises: b3f4c5d6e7a9
Create Date: 2026-07-09 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b3f4c5d6e7a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("auth_sessions", "ix_auth_sessions_user_created", ("user_id", "created_at")),
    ("auth_sessions", "ix_auth_sessions_user_last_seen", ("user_id", "last_seen_at")),
    ("docs_native_docs", "ix_docs_native_docs_owner_created", ("owner_id", "created_at")),
    (
        "docs_native_docs",
        "ix_docs_native_docs_workspace_updated",
        ("workspace_id", "updated_at"),
    ),
    (
        "dm_messages",
        "ix_dm_messages_conversation_created_sequence",
        ("conversation_id", "created_at", "sequence"),
    ),
    ("image_generations", "ix_image_generations_owner_created", ("owner_id", "created_at")),
    (
        "legacy_issue_records",
        "ix_legacy_issue_records_scope_revision_updated_created",
        ("workspace_id", "dataset_key", "revision_id", "updated_at", "created_at"),
    ),
    ("meeting_doc_links", "ix_meeting_doc_links_added_by", ("added_by_id",)),
    ("meeting_recording_staging", "ix_meeting_recording_staging_linked_task", ("linked_task_id",)),
    (
        "meeting_recording_staging",
        "ix_meeting_recording_staging_promoted_recording",
        ("promoted_recording_id",),
    ),
    ("meeting_recording_staging", "ix_meeting_recording_staging_uploaded_by", ("uploaded_by_id",)),
    ("meeting_recordings", "ix_meeting_recordings_linked_doc_id", ("linked_doc_id",)),
    ("meeting_recordings", "ix_meeting_recordings_uploaded_by", ("uploaded_by_id",)),
    ("meeting_task_links", "ix_meeting_task_links_added_by", ("added_by_id",)),
    ("meetings", "ix_meetings_notes_doc_id", ("notes_doc_id",)),
    ("meetings", "ix_meetings_notes_page_id", ("notes_page_id",)),
    ("meetings", "ix_meetings_organizer_created", ("organizer_id", "created_at")),
    ("meetings", "ix_meetings_workspace_start", ("workspace_id", "start_at")),
    (
        "news_articles",
        "ix_news_articles_channel_published_collected",
        ("channel", "published_date", "collected_at"),
    ),
    (
        "news_recommended_articles",
        "ix_news_recommended_origin_date",
        ("origin", "published_date", "recommended_at"),
    ),
    (
        "notification_dm_deliveries",
        "ix_notification_dm_deliveries_user_conversation",
        ("user_id", "conversation_id", "notification_id"),
    ),
    (
        "patent_records",
        "ix_patent_records_workspace_disclosure_updated",
        ("workspace_id", "disclosure_date", "updated_at"),
    ),
    ("pms_attachments", "ix_pms_attachments_uploaded_created", ("uploaded_by_id", "created_at")),
    (
        "pms_task_activity_logs",
        "ix_pms_task_activity_logs_actor_created",
        ("actor_id", "created_at"),
    ),
    ("pms_task_assignees", "ix_pms_task_assignees_user_task", ("user_id", "task_id")),
    ("pms_task_comments", "ix_pms_task_comments_author_created", ("author_id", "created_at")),
    ("pms_task_doc_links", "ix_pms_task_doc_links_doc_created", ("doc_id", "created_at")),
    ("pms_task_doc_links", "ix_pms_task_doc_links_task_created", ("task_id", "created_at")),
    ("pms_task_labels", "ix_pms_task_labels_label_task", ("label_id", "task_id")),
    (
        "pms_tasks",
        "ix_pms_tasks_list_archived_board",
        ("list_id", "archived", "board_position", "task_number"),
    ),
    (
        "pms_tasks",
        "ix_pms_tasks_list_archived_updated",
        ("list_id", "archived", "updated_at"),
    ),
    (
        "pms_tasks",
        "ix_pms_tasks_reporter_archived_created",
        ("reporter_id", "archived", "created_at"),
    ),
    ("recording_staging", "ix_recording_staging_promoted_recording", ("promoted_recording_id",)),
    ("recordings", "ix_recordings_minutes_doc_id", ("minutes_doc_id",)),
    ("recordings", "ix_recordings_raw_transcript_doc_id", ("raw_transcript_doc_id",)),
    (
        "rag_sync_jobs",
        "ix_rag_sync_jobs_workspace_lane_status_created",
        ("scope_kind", "workspace_id", "lane", "status", "created_at"),
    ),
    (
        "usage_events",
        "ix_usage_events_type_kind_occurred_user",
        ("event_type", "content_kind", "occurred_at", "actor_user_id"),
    ),
    ("usage_events", "ix_usage_events_workspace_occurred", ("workspace_id", "occurred_at")),
    ("whiteboards", "ix_whiteboards_owner_created", ("owner_id", "created_at")),
    ("whiteboards", "ix_whiteboards_workspace_updated", ("workspace_id", "updated_at")),
)

_PARTIAL_INDEXES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "legacy_issue_ai_chunks",
        "ix_legacy_issue_ai_chunks_pending_embedding_scope_updated",
        ("workspace_id", "dataset_key", "revision_id", "updated_at", "created_at"),
        "embedding_vector IS NULL OR embedding_status <> 'embedded'",
    ),
    (
        "news_articles",
        "ix_news_articles_unevaluated_channel_date",
        ("channel", "published_date", "collected_at"),
        "ai_evaluated = false",
    ),
    (
        "pms_notifications",
        "ix_pms_notifications_dm_thread_unread",
        ("user_id", "reference_type", "reference_id"),
        "is_read = false",
    ),
    (
        "pms_notifications",
        "ix_pms_notifications_user_created_global",
        ("user_id", "created_at"),
        "type <> 'dm_message'",
    ),
    (
        "pms_notifications",
        "ix_pms_notifications_user_unread_global",
        ("user_id",),
        "is_read = false AND type <> 'dm_message'",
    ),
    (
        "search_index_jobs",
        "ix_search_index_jobs_entity_created_active",
        ("workspace_id", "entity_type", "entity_id", "created_at", "id"),
        "status <> 'cancelled'",
    ),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for table_name, index_name, columns in _INDEXES:
            _create_index_if_not_exists(table_name, index_name, columns)
        for table_name, index_name, columns, where_clause in _PARTIAL_INDEXES:
            _create_index_if_not_exists(
                table_name,
                index_name,
                columns,
                where_clause=where_clause,
            )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for _table_name, index_name, _columns, _where_clause in reversed(_PARTIAL_INDEXES):
            op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"))
        for _table_name, index_name, _columns in reversed(_INDEXES):
            op.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {index_name}"))


def _create_index_if_not_exists(
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
    *,
    where_clause: str | None = None,
) -> None:
    rendered_columns = ", ".join(columns)
    rendered_where = f" WHERE {where_clause}" if where_clause else ""
    op.execute(
        sa.text(
            f"""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
            ON {table_name} ({rendered_columns}){rendered_where}
            """
        )
    )
