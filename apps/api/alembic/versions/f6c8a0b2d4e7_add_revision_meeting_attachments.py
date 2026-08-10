"""add revision meeting attachments

Revision ID: f6c8a0b2d4e7
Revises: e4a7c9d2f6b1
Create Date: 2026-08-10 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6c8a0b2d4e7"
down_revision: str | Sequence[str] | None = "e4a7c9d2f6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ATTACHMENT_TABLE = "legacy_issue_revision_meeting_attachments"
CLEANUP_TABLE = "legacy_issue_revision_meeting_attachment_cleanups"
REVISION_MEETING_DATASET_SQL = (
    "('legacy_issue.common-master.aircon',"
    "'legacy_issue.common-master.compressor-electric',"
    "'legacy_issue.common-master.compressor-mechanical',"
    "'legacy_issue.common-master.heat-exchanger',"
    "'legacy_issue.common-master.interior',"
    "'legacy_issue.common-master.cooling-module',"
    "'legacy_issue.common-master.electrical-mechanical',"
    "'legacy_issue.common-master.electrical-control-hw',"
    "'legacy_issue.common-master.electrical-control-sw')"
)


def upgrade() -> None:
    _link_active_overview_rows()
    _backfill_missing_published_revision_overview_rows()

    op.create_table(
        ATTACHMENT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("overview_history_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=160),
            server_default=sa.text("'application/octet-stream'"),
            nullable=False,
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=True),
        sa.Column("client_request_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_legacy_issue_revision_meeting_attachments_size",
        ),
        sa.CheckConstraint(
            "length(client_request_id) BETWEEN 1 AND 64",
            name="ck_li_revision_meeting_attachment_request_length",
        ),
        sa.ForeignKeyConstraint(
            ["overview_history_id"],
            ["legacy_issue_revision_overview_history.id"],
            name="fk_li_revision_meeting_attachment_overview_history",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_id"],
            ["users.id"],
            name="fk_li_revision_meeting_attachment_uploader",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_li_revision_meeting_attachment_workspace",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_legacy_issue_revision_meeting_attachments"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_legacy_issue_revision_meeting_attachments_storage_key",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "dataset_key",
            "overview_history_id",
            "uploaded_by_id",
            "client_request_id",
            name="uq_li_revision_meeting_attachment_request",
        ),
    )
    op.create_index(
        "ix_li_revision_meeting_attachments_scope_history_created",
        ATTACHMENT_TABLE,
        ["workspace_id", "dataset_key", "overview_history_id", "created_at"],
    )

    op.create_table(
        CLEANUP_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=160), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_li_revision_meeting_cleanup_workspace",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_legacy_issue_revision_meeting_attachment_cleanups",
        ),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_li_revision_meeting_attachment_cleanups_storage_key",
        ),
    )
    op.create_index(
        "ix_li_revision_meeting_attachment_cleanups_pending",
        CLEANUP_TABLE,
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_li_revision_meeting_attachment_cleanups_pending",
        table_name=CLEANUP_TABLE,
    )
    op.drop_table(CLEANUP_TABLE)
    op.drop_index(
        "ix_li_revision_meeting_attachments_scope_history_created",
        table_name=ATTACHMENT_TABLE,
    )
    op.drop_table(ATTACHMENT_TABLE)


def _link_active_overview_rows() -> None:
    op.execute(
        sa.text(
            "UPDATE legacy_issue_revision_overview_history AS history "
            "SET linked_revision_id = revision.id, updated_at = CURRENT_TIMESTAMP "
            "FROM legacy_issue_data_revisions AS revision "
            "WHERE history.linked_revision_id IS NULL "
            "AND history.deleted_at IS NULL "
            "AND history.workspace_id = revision.workspace_id "
            "AND history.dataset_key = revision.dataset_key "
            "AND history.revision_no = revision.revision_no "
            "AND revision.status = 'published' "
            f"AND revision.dataset_key IN {REVISION_MEETING_DATASET_SQL}"
        )
    )


def _backfill_missing_published_revision_overview_rows() -> None:
    op.execute(
        sa.text(
            "WITH missing AS ("
            " SELECT revision.*,"
            " ROW_NUMBER() OVER ("
            "   PARTITION BY revision.workspace_id, revision.dataset_key"
            "   ORDER BY revision.revision_no ASC NULLS FIRST, revision.created_at ASC"
            " ) AS missing_order"
            " FROM legacy_issue_data_revisions AS revision"
            " WHERE revision.status = 'published'"
            f" AND revision.dataset_key IN {REVISION_MEETING_DATASET_SQL}"
            " AND NOT EXISTS ("
            "   SELECT 1 FROM legacy_issue_revision_overview_history AS linked_history"
            "   WHERE linked_history.workspace_id = revision.workspace_id"
            "   AND linked_history.dataset_key = revision.dataset_key"
            "   AND linked_history.linked_revision_id = revision.id"
            " )"
            ")"
            " INSERT INTO legacy_issue_revision_overview_history ("
            "   id, workspace_id, dataset_key, linked_revision_id, origin,"
            "   revision_no, revision_label, summary, revised_on, vehicle_models,"
            "   author_user_id, reviewer_user_id, approver_user_id,"
            "   author_name, reviewer_name, approver_name,"
            "   source_filename, source_sha256, source_sheet, source_row,"
            "   sort_order, deleted_at, deleted_by_id, created_at, updated_at"
            " )"
            " SELECT"
            "   'mtg-' || SUBSTRING(MD5('revision-overview:' || missing.id), 1, 32),"
            "   missing.workspace_id, missing.dataset_key, missing.id, 'system',"
            "   CASE WHEN EXISTS ("
            "     SELECT 1 FROM legacy_issue_revision_overview_history AS numbered_history"
            "     WHERE numbered_history.workspace_id = missing.workspace_id"
            "     AND numbered_history.dataset_key = missing.dataset_key"
            "     AND numbered_history.revision_no = missing.revision_no"
            "     AND numbered_history.deleted_at IS NULL"
            "   ) THEN NULL ELSE missing.revision_no END,"
            "   COALESCE(CAST(missing.revision_no AS VARCHAR), '-'),"
            "   missing.note, CAST(missing.published_at AS DATE), NULL,"
            "   COALESCE(missing.published_by_id, missing.created_by_id),"
            "   COALESCE(missing.reviewed_by_id, missing.reviewer_id),"
            "   COALESCE(missing.approved_by_id, missing.approver_id),"
            "   COALESCE(author.display_name, author.full_name, author.email),"
            "   COALESCE(reviewer.display_name, reviewer.full_name, reviewer.email),"
            "   COALESCE(approver.display_name, approver.full_name, approver.email),"
            "   NULL, NULL, NULL, NULL,"
            "   COALESCE(("
            "     SELECT MIN(existing_history.sort_order)"
            "     FROM legacy_issue_revision_overview_history AS existing_history"
            "     WHERE existing_history.workspace_id = missing.workspace_id"
            "     AND existing_history.dataset_key = missing.dataset_key"
            "   ), 0) - CAST(missing.missing_order AS INTEGER),"
            "   NULL, NULL,"
            "   COALESCE(missing.published_at, missing.created_at, CURRENT_TIMESTAMP),"
            "   COALESCE(missing.published_at, missing.updated_at, CURRENT_TIMESTAMP)"
            " FROM missing"
            " LEFT JOIN users AS author"
            "   ON author.id = COALESCE(missing.published_by_id, missing.created_by_id)"
            " LEFT JOIN users AS reviewer"
            "   ON reviewer.id = COALESCE(missing.reviewed_by_id, missing.reviewer_id)"
            " LEFT JOIN users AS approver"
            "   ON approver.id = COALESCE(missing.approved_by_id, missing.approver_id)"
        )
    )
