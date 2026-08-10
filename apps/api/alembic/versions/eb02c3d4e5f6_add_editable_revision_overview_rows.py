"""add editable revision overview rows

Revision ID: eb02c3d4e5f6
Revises: eaf1b2c3d4e5
Create Date: 2026-07-14 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "eb02c3d4e5f6"
down_revision: str | Sequence[str] | None = "eaf1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "legacy_issue_revision_overview_history",
        sa.Column("linked_revision_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "legacy_issue_revision_overview_history",
        sa.Column(
            "origin",
            sa.String(length=20),
            server_default="imported",
            nullable=False,
        ),
    )
    op.add_column(
        "legacy_issue_revision_overview_history",
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "legacy_issue_revision_overview_history",
        sa.Column("deleted_by_id", sa.String(length=36), nullable=True),
    )
    for column_name, column_type in (
        ("source_filename", sa.String(length=512)),
        ("source_sha256", sa.String(length=64)),
        ("source_sheet", sa.String(length=255)),
        ("source_row", sa.Integer()),
    ):
        op.alter_column(
            "legacy_issue_revision_overview_history",
            column_name,
            existing_type=column_type,
            nullable=True,
        )
    op.create_foreign_key(
        "fk_legacy_issue_revision_overview_history_linked_revision",
        "legacy_issue_revision_overview_history",
        "legacy_issue_data_revisions",
        ["linked_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_legacy_issue_revision_overview_history_deleted_by",
        "legacy_issue_revision_overview_history",
        "users",
        ["deleted_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_legacy_issue_revision_overview_history_linked_revision_id",
        "legacy_issue_revision_overview_history",
        ["linked_revision_id"],
        unique=False,
    )
    op.create_index(
        "ix_legacy_issue_revision_overview_history_deleted_by_id",
        "legacy_issue_revision_overview_history",
        ["deleted_by_id"],
        unique=False,
    )
    op.execute(
        "UPDATE legacy_issue_revision_overview_history AS history "
        "SET linked_revision_id = revision.id "
        "FROM legacy_issue_data_revisions AS revision "
        "WHERE history.linked_revision_id IS NULL "
        "AND history.workspace_id = revision.workspace_id "
        "AND history.dataset_key = revision.dataset_key "
        "AND history.revision_no = revision.revision_no "
        "AND revision.status = 'published'"
    )
    op.create_index(
        "ux_legacy_issue_revision_overview_history_active_number",
        "legacy_issue_revision_overview_history",
        ["workspace_id", "dataset_key", "revision_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND revision_no IS NOT NULL"),
    )
    op.create_index(
        "ux_legacy_issue_revision_overview_history_active_link",
        "legacy_issue_revision_overview_history",
        ["workspace_id", "dataset_key", "linked_revision_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND linked_revision_id IS NOT NULL"),
    )
    op.alter_column(
        "legacy_issue_revision_overview_history",
        "origin",
        existing_type=sa.String(length=20),
        server_default=None,
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM legacy_issue_revision_overview_history AS history "
        "WHERE history.deleted_at IS NOT NULL OR history.origin <> 'imported') "
        "OR EXISTS (SELECT 1 FROM legacy_issue_revision_overview_history AS history "
        "LEFT JOIN legacy_issue_data_revisions AS revision "
        "ON revision.id = history.linked_revision_id "
        "WHERE history.linked_revision_id IS NOT NULL "
        "AND (revision.id IS NULL "
        "OR history.revision_no IS DISTINCT FROM revision.revision_no)) THEN "
        "RAISE EXCEPTION 'Cannot downgrade after editable overview rows have changed'; "
        "END IF; END $$"
    )
    op.execute(
        "UPDATE legacy_issue_revision_overview_history SET "
        "source_filename = COALESCE(source_filename, 'manual:' || id), "
        "source_sha256 = COALESCE(source_sha256, ''), "
        "source_sheet = COALESCE(source_sheet, origin), "
        "source_row = COALESCE(source_row, 0) "
        "WHERE source_filename IS NULL OR source_sha256 IS NULL "
        "OR source_sheet IS NULL OR source_row IS NULL"
    )
    op.drop_index(
        "ux_legacy_issue_revision_overview_history_active_link",
        table_name="legacy_issue_revision_overview_history",
    )
    op.drop_index(
        "ux_legacy_issue_revision_overview_history_active_number",
        table_name="legacy_issue_revision_overview_history",
    )
    op.drop_index(
        "ix_legacy_issue_revision_overview_history_deleted_by_id",
        table_name="legacy_issue_revision_overview_history",
    )
    op.drop_index(
        "ix_legacy_issue_revision_overview_history_linked_revision_id",
        table_name="legacy_issue_revision_overview_history",
    )
    op.drop_constraint(
        "fk_legacy_issue_revision_overview_history_deleted_by",
        "legacy_issue_revision_overview_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_legacy_issue_revision_overview_history_linked_revision",
        "legacy_issue_revision_overview_history",
        type_="foreignkey",
    )
    for column_name, column_type in (
        ("source_filename", sa.String(length=512)),
        ("source_sha256", sa.String(length=64)),
        ("source_sheet", sa.String(length=255)),
        ("source_row", sa.Integer()),
    ):
        op.alter_column(
            "legacy_issue_revision_overview_history",
            column_name,
            existing_type=column_type,
            nullable=False,
        )
    op.drop_column("legacy_issue_revision_overview_history", "deleted_by_id")
    op.drop_column("legacy_issue_revision_overview_history", "deleted_at")
    op.drop_column("legacy_issue_revision_overview_history", "origin")
    op.drop_column("legacy_issue_revision_overview_history", "linked_revision_id")
