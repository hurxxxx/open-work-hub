"""Enforce app-scoped runtime, notification, and recording boundaries.

Revision ID: d6a9f4c2b8e1
Revises: c5f8a2d1e7b4
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d6a9f4c2b8e1"
down_revision: str | Sequence[str] | None = "c5f8a2d1e7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _upgrade_ai_graph_dispatch_status()
    _upgrade_notifications()
    _upgrade_recordings()


def downgrade() -> None:
    _downgrade_recordings()
    _downgrade_notifications()
    _downgrade_ai_graph_dispatch_status()


def _upgrade_ai_graph_dispatch_status() -> None:
    op.drop_constraint(
        "ck_ai_graph_dispatch_outbox_status",
        "ai_graph_dispatch_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_graph_dispatch_outbox_status",
        "ai_graph_dispatch_outbox",
        "status IN ('pending','claimed','dispatched','dead_letter','cancelled')",
    )


def _downgrade_ai_graph_dispatch_status() -> None:
    op.execute(
        "UPDATE ai_graph_dispatch_outbox SET status = 'dead_letter' "
        "WHERE status = 'cancelled'"
    )
    op.drop_constraint(
        "ck_ai_graph_dispatch_outbox_status",
        "ai_graph_dispatch_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_ai_graph_dispatch_outbox_status",
        "ai_graph_dispatch_outbox",
        "status IN ('pending','claimed','dispatched','dead_letter')",
    )


def _upgrade_notifications() -> None:
    # The following revision removes the complete legacy notification-DM channel.
    # Do not delete individual messages here: participant read pointers can still
    # reference them until their bot-owned conversations are removed as a unit.
    op.drop_index(
        "ix_pms_notifications_dm_thread_unread",
        table_name="pms_notifications",
    )
    op.drop_index(
        "ix_pms_notifications_reference_id",
        table_name="pms_notifications",
    )
    op.alter_column(
        "pms_notifications",
        "reference_type",
        new_column_name="source_type",
        existing_type=sa.String(length=24),
        type_=sa.String(length=40),
        existing_nullable=False,
    )
    op.alter_column(
        "pms_notifications",
        "reference_id",
        new_column_name="source_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
    )
    op.add_column(
        "pms_notifications",
        sa.Column("origin_app_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "pms_notifications",
        sa.Column("origin_workspace_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_pms_notifications_origin_workspace",
        "pms_notifications",
        "workspaces",
        ["origin_workspace_id"],
        ["id"],
    )

    op.execute(
        "UPDATE pms_notifications AS n SET "
        "origin_app_id = 'pms', source_type = 'pms_task', "
        "origin_workspace_id = ("
        "SELECT tm.workspace_id FROM pms_tasks t "
        "JOIN pms_task_lists l ON l.id = t.list_id "
        "JOIN teams tm ON tm.id = l.team_id "
        "WHERE t.id = n.source_id"
        ") WHERE n.type <> 'dm_message' AND EXISTS "
        "(SELECT 1 FROM pms_tasks t WHERE t.id = n.source_id)"
    )
    op.execute(
        "UPDATE pms_notifications SET origin_app_id = 'community', "
        "source_type = 'community_post', origin_workspace_id = NULL "
        "WHERE type <> 'dm_message' AND source_type = 'community_post' "
        "AND EXISTS (SELECT 1 FROM community_posts p WHERE p.id = source_id)"
    )
    op.execute(
        "DELETE FROM pms_notifications WHERE type <> 'dm_message' "
        "AND (origin_app_id IS NULL OR source_id IS NULL)"
    )
    op.create_index(
        "ix_pms_notifications_source_id",
        "pms_notifications",
        ["source_id"],
    )
    op.create_index(
        "ix_pms_notifications_origin_app_id",
        "pms_notifications",
        ["origin_app_id"],
    )
    op.create_index(
        "ix_pms_notifications_origin_workspace_id",
        "pms_notifications",
        ["origin_workspace_id"],
    )
    op.create_index(
        "ix_pms_notifications_dm_thread_unread",
        "pms_notifications",
        ["user_id", "source_type", "source_id"],
        postgresql_where=sa.text("is_read = false"),
    )
    op.create_check_constraint(
        "ck_pms_notifications_global_origin",
        "pms_notifications",
        "type = 'dm_message' OR (origin_app_id IS NOT NULL AND source_id IS NOT NULL)",
    )


def _downgrade_notifications() -> None:
    op.drop_constraint(
        "ck_pms_notifications_global_origin",
        "pms_notifications",
        type_="check",
    )
    op.drop_index(
        "ix_pms_notifications_dm_thread_unread",
        table_name="pms_notifications",
    )
    op.drop_index(
        "ix_pms_notifications_origin_workspace_id",
        table_name="pms_notifications",
    )
    op.drop_index(
        "ix_pms_notifications_origin_app_id",
        table_name="pms_notifications",
    )
    op.drop_index(
        "ix_pms_notifications_source_id",
        table_name="pms_notifications",
    )
    op.drop_constraint(
        "fk_pms_notifications_origin_workspace",
        "pms_notifications",
        type_="foreignkey",
    )
    op.drop_column("pms_notifications", "origin_workspace_id")
    op.drop_column("pms_notifications", "origin_app_id")
    op.alter_column(
        "pms_notifications",
        "source_type",
        new_column_name="reference_type",
        existing_type=sa.String(length=40),
        type_=sa.String(length=24),
        existing_nullable=False,
    )
    op.alter_column(
        "pms_notifications",
        "source_id",
        new_column_name="reference_id",
        existing_type=sa.String(length=36),
        existing_nullable=True,
    )
    op.create_index(
        "ix_pms_notifications_reference_id",
        "pms_notifications",
        ["reference_id"],
    )
    op.create_index(
        "ix_pms_notifications_dm_thread_unread",
        "pms_notifications",
        ["user_id", "reference_type", "reference_id"],
        postgresql_where=sa.text("is_read = false"),
    )


def _upgrade_recordings() -> None:
    op.add_column(
        "recordings",
        sa.Column(
            "summary_status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_recordings_summary_status",
        "recordings",
        ["summary_status"],
    )
    op.create_index(
        "ix_recordings_workspace_summary_status",
        "recordings",
        ["workspace_id", "summary_status"],
    )
    op.create_table(
        "recording_results",
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("verifier_note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_recording_results_version"),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("recording_id"),
    )
    op.execute(
        "INSERT INTO recording_results "
        "(recording_id, transcript_text, summary_text, verifier_note, version, "
        "generated_at, created_at, updated_at) "
        "SELECT id, transcript_text, NULL, NULL, 1, NULL, created_at, updated_at "
        "FROM recordings WHERE transcript_text IS NOT NULL "
        "AND TRIM(transcript_text) <> ''"
    )
    op.create_table(
        "recording_publications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recording_id", sa.String(length=36), nullable=False),
        sa.Column("target_app", sa.String(length=64), nullable=False),
        sa.Column("target_resource_id", sa.String(length=128), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("published_by_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "result_version >= 1",
            name="ck_recording_publications_result_version",
        ),
        sa.ForeignKeyConstraint(
            ["recording_id"],
            ["recordings.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["published_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recording_id",
            "target_app",
            "result_version",
            name="uq_recording_publication_result_version",
        ),
    )
    op.create_index(
        "ix_recording_publications_recording_id",
        "recording_publications",
        ["recording_id"],
    )
    op.create_index(
        "ix_recording_publications_published_by_id",
        "recording_publications",
        ["published_by_id"],
    )
    op.create_index(
        "ix_recording_publications_target",
        "recording_publications",
        ["target_app", "target_resource_id"],
    )

    op.drop_index("ix_recordings_minutes_doc_id", table_name="recordings")
    op.drop_index("ix_recordings_minutes_doc_status", table_name="recordings")
    op.drop_index("ix_recordings_raw_transcript_doc_id", table_name="recordings")
    op.drop_index("ix_recordings_raw_transcript_doc_status", table_name="recordings")
    op.drop_constraint(
        "recordings_minutes_doc_id_fkey",
        "recordings",
        type_="foreignkey",
    )
    op.drop_constraint(
        "recordings_raw_transcript_doc_id_fkey",
        "recordings",
        type_="foreignkey",
    )
    op.drop_column("recordings", "minutes_doc_id")
    op.drop_column("recordings", "raw_transcript_doc_id")
    op.drop_column("recordings", "minutes_doc_status")
    op.drop_column("recordings", "raw_transcript_doc_status")
    op.drop_column("recordings", "transcript_text")
    op.alter_column("recordings", "summary_status", server_default=None)


def _downgrade_recordings() -> None:
    op.add_column(
        "recordings",
        sa.Column("transcript_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "recordings",
        sa.Column(
            "raw_transcript_doc_status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.add_column(
        "recordings",
        sa.Column(
            "minutes_doc_status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.add_column(
        "recordings",
        sa.Column("raw_transcript_doc_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "recordings",
        sa.Column("minutes_doc_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "recordings_raw_transcript_doc_id_fkey",
        "recordings",
        "docs_native_docs",
        ["raw_transcript_doc_id"],
        ["id"],
    )
    op.create_foreign_key(
        "recordings_minutes_doc_id_fkey",
        "recordings",
        "docs_native_docs",
        ["minutes_doc_id"],
        ["id"],
    )
    op.execute(
        "UPDATE recordings SET transcript_text = "
        "(SELECT r.transcript_text FROM recording_results r "
        "WHERE r.recording_id = recordings.id)"
    )
    op.create_index(
        "ix_recordings_raw_transcript_doc_status",
        "recordings",
        ["raw_transcript_doc_status"],
    )
    op.create_index(
        "ix_recordings_minutes_doc_status",
        "recordings",
        ["minutes_doc_status"],
    )
    op.create_index(
        "ix_recordings_raw_transcript_doc_id",
        "recordings",
        ["raw_transcript_doc_id"],
    )
    op.create_index(
        "ix_recordings_minutes_doc_id",
        "recordings",
        ["minutes_doc_id"],
    )
    op.drop_index(
        "ix_recording_publications_target",
        table_name="recording_publications",
    )
    op.drop_index(
        "ix_recording_publications_published_by_id",
        table_name="recording_publications",
    )
    op.drop_index(
        "ix_recording_publications_recording_id",
        table_name="recording_publications",
    )
    op.drop_table("recording_publications")
    op.drop_table("recording_results")
    op.drop_index(
        "ix_recordings_workspace_summary_status",
        table_name="recordings",
    )
    op.drop_index("ix_recordings_summary_status", table_name="recordings")
    op.drop_column("recordings", "summary_status")
