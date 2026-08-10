"""add legacy issue excel export jobs

Revision ID: d8e0f2a4b6c9
Revises: c7d9e1f3a5b8
Create Date: 2026-07-15 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8e0f2a4b6c9"
down_revision: str | Sequence[str] | None = "c7d9e1f3a5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE = "legacy_issue_excel_export_jobs"
JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=True),
        sa.Column("module_key", sa.String(length=80), nullable=True),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("checklist_id", sa.String(length=36), nullable=True),
        sa.Column("request_params", JSONB_COMPAT, nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("record_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("attachment_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("attachment_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "processed_attachment_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "processed_attachment_bytes",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("result_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("result_filename", sa.String(length=512), nullable=True),
        sa.Column("result_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('dataset','vehicle_module_checklist')",
            name="ck_legacy_issue_excel_export_jobs_source_kind",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','expired')",
            name="ck_legacy_issue_excel_export_jobs_status",
        ),
        sa.CheckConstraint(
            "record_count >= 0 AND attachment_count >= 0 "
            "AND attachment_bytes >= 0 AND processed_attachment_count >= 0 "
            "AND processed_attachment_bytes >= 0",
            name="ck_legacy_issue_excel_export_jobs_nonnegative_counts",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["legacy_issue_data_revisions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["checklist_id"],
            ["legacy_issue_vehicle_module_checklists.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "workspace_id",
        "requested_by_id",
        "source_kind",
        "dataset_key",
        "module_key",
        "revision_id",
        "checklist_id",
        "status",
    ):
        op.create_index(op.f(f"ix_{TABLE}_{column}"), TABLE, [column])
    op.create_index(
        "ix_legacy_issue_excel_export_jobs_requester_created",
        TABLE,
        ["workspace_id", "requested_by_id", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_excel_export_jobs_status_retry",
        TABLE,
        ["status", "next_retry_at"],
    )
    op.create_index(
        "ix_legacy_issue_excel_export_jobs_expiry",
        TABLE,
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_table(TABLE)
