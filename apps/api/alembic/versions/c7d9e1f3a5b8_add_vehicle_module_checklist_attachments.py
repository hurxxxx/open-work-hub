"""add vehicle module checklist attachments

Revision ID: c7d9e1f3a5b8
Revises: a6b8c0d2e4f7
Create Date: 2026-07-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c7d9e1f3a5b8"
down_revision: str | Sequence[str] | None = "a6b8c0d2e4f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ATTACHMENT_TABLE = "legacy_issue_vehicle_module_checklist_attachments"
CLEANUP_TABLE = "legacy_issue_vehicle_module_checklist_attachment_cleanups"


def upgrade() -> None:
    op.create_table(
        ATTACHMENT_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("checklist_id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=160),
            server_default=sa.text("'application/octet-stream'"),
            nullable=False,
        ),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("uploaded_by_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_li_vehicle_module_checklist_attachments_size",
        ),
        sa.ForeignKeyConstraint(
            ["checklist_id"],
            ["legacy_issue_vehicle_module_checklists.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["legacy_issue_vehicle_module_checklist_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_attachments_checklist_id"),
        ATTACHMENT_TABLE,
        ["checklist_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_attachments_record_id"),
        ATTACHMENT_TABLE,
        ["record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_attachments_uploaded_by_id"),
        ATTACHMENT_TABLE,
        ["uploaded_by_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_attachments_workspace_id"),
        ATTACHMENT_TABLE,
        ["workspace_id"],
    )
    op.create_index(
        "ix_li_vehicle_module_checklist_attachments_record_created",
        ATTACHMENT_TABLE,
        ["record_id", "created_at"],
    )
    op.create_index(
        "ix_li_vehicle_module_checklist_attachments_scope_created",
        ATTACHMENT_TABLE,
        ["workspace_id", "checklist_id", "created_at"],
    )

    op.create_table(
        CLEANUP_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.String(length=160), nullable=True),
        sa.Column("last_attempted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "storage_key",
            name="uq_li_vehicle_module_checklist_attachment_cleanups_storage_key",
        ),
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_attachment_cleanups_workspace_id"),
        CLEANUP_TABLE,
        ["workspace_id"],
    )
    op.create_index(
        "ix_li_vehicle_module_checklist_attachment_cleanups_pending",
        CLEANUP_TABLE,
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table(CLEANUP_TABLE)
    op.drop_table(ATTACHMENT_TABLE)
