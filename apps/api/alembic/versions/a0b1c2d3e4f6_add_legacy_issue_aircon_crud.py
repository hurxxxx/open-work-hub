"""add_legacy_issue_aircon_crud

Revision ID: a0b1c2d3e4f6
Revises: 9d0e1f2a3b4c
Create Date: 2026-06-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a0b1c2d3e4f6"
down_revision: str | Sequence[str] | None = "9d0e1f2a3b4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "legacy_issue_aircon_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("row_no", sa.String(length=64), nullable=True),
        sa.Column("legacy_issue_number", sa.String(length=160), nullable=True),
        sa.Column("occurrence_stage", sa.String(length=160), nullable=True),
        sa.Column("occurrence_type", sa.String(length=160), nullable=True),
        sa.Column("vehicle_model", sa.String(length=255), nullable=True),
        sa.Column("item", sa.String(length=255), nullable=True),
        sa.Column("sub_item", sa.String(length=255), nullable=True),
        sa.Column("occurrence_source", sa.String(length=255), nullable=True),
        sa.Column("defect_type", sa.String(length=255), nullable=True),
        sa.Column("supplier", sa.String(length=255), nullable=True),
        sa.Column("problem", sa.Text(), nullable=True),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("countermeasure", sa.Text(), nullable=True),
        sa.Column("attachment_note", sa.Text(), nullable=True),
        sa.Column("check_legacy_master", sa.Text(), nullable=True),
        sa.Column("check_design_check_sheet", sa.Text(), nullable=True),
        sa.Column("check_design_fmea", sa.Text(), nullable=True),
        sa.Column("check_design_standard", sa.Text(), nullable=True),
        sa.Column("design_reflect_spec_diff", sa.Text(), nullable=True),
        sa.Column("design_reflect_process", sa.Text(), nullable=True),
        sa.Column("design_reflect_under_review", sa.Text(), nullable=True),
        sa.Column("design_reflected", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("raw_fields", JSONB_COMPAT, nullable=True),
        sa.Column("imported_source_filename", sa.String(length=512), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_aircon_workspace_updated",
        "legacy_issue_aircon_records",
        ["workspace_id", "updated_at"],
    )
    op.create_index(
        "ix_legacy_issue_aircon_workspace_number",
        "legacy_issue_aircon_records",
        ["workspace_id", "legacy_issue_number"],
    )
    op.create_index(
        "ix_legacy_issue_aircon_workspace_vehicle",
        "legacy_issue_aircon_records",
        ["workspace_id", "vehicle_model"],
    )
    op.create_index(
        op.f("ix_legacy_issue_aircon_records_workspace_id"),
        "legacy_issue_aircon_records",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_aircon_records_created_by_id"),
        "legacy_issue_aircon_records",
        ["created_by_id"],
    )

    op.create_table(
        "legacy_issue_aircon_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "content_type",
            sa.String(length=160),
            server_default="application/octet-stream",
            nullable=False,
        ),
        sa.Column("size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("uploaded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["legacy_issue_aircon_records.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_legacy_issue_aircon_attachments_record",
        "legacy_issue_aircon_attachments",
        ["record_id", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_aircon_attachments_workspace",
        "legacy_issue_aircon_attachments",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        op.f("ix_legacy_issue_aircon_attachments_workspace_id"),
        "legacy_issue_aircon_attachments",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_aircon_attachments_record_id"),
        "legacy_issue_aircon_attachments",
        ["record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_aircon_attachments_uploaded_by_id"),
        "legacy_issue_aircon_attachments",
        ["uploaded_by_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_legacy_issue_aircon_attachments_uploaded_by_id"),
        table_name="legacy_issue_aircon_attachments",
    )
    op.drop_index(
        op.f("ix_legacy_issue_aircon_attachments_record_id"),
        table_name="legacy_issue_aircon_attachments",
    )
    op.drop_index(
        op.f("ix_legacy_issue_aircon_attachments_workspace_id"),
        table_name="legacy_issue_aircon_attachments",
    )
    op.drop_index(
        "ix_legacy_issue_aircon_attachments_workspace",
        table_name="legacy_issue_aircon_attachments",
    )
    op.drop_index(
        "ix_legacy_issue_aircon_attachments_record",
        table_name="legacy_issue_aircon_attachments",
    )
    op.drop_table("legacy_issue_aircon_attachments")

    op.drop_index(
        op.f("ix_legacy_issue_aircon_records_created_by_id"),
        table_name="legacy_issue_aircon_records",
    )
    op.drop_index(
        op.f("ix_legacy_issue_aircon_records_workspace_id"),
        table_name="legacy_issue_aircon_records",
    )
    op.drop_index(
        "ix_legacy_issue_aircon_workspace_vehicle",
        table_name="legacy_issue_aircon_records",
    )
    op.drop_index(
        "ix_legacy_issue_aircon_workspace_number",
        table_name="legacy_issue_aircon_records",
    )
    op.drop_index(
        "ix_legacy_issue_aircon_workspace_updated",
        table_name="legacy_issue_aircon_records",
    )
    op.drop_table("legacy_issue_aircon_records")
