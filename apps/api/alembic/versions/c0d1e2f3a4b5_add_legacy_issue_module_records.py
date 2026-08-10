"""add_legacy_issue_module_records

Revision ID: c0d1e2f3a4b5
Revises: b0c1d2e3f4a5
Create Date: 2026-06-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c0d1e2f3a4b5"
down_revision: str | Sequence[str] | None = "b0c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


RECORD_TABLES = (
    ("legacy_issue_electrical_mechanical_records", "ix_legacy_issue_electrical_mechanical_workspace_updated"),
    ("legacy_issue_electrical_control_hw_records", "ix_legacy_issue_electrical_control_hw_workspace_updated"),
    ("legacy_issue_electrical_control_sw_records", "ix_legacy_issue_electrical_control_sw_workspace_updated"),
    ("legacy_issue_interior_records", "ix_legacy_issue_interior_workspace_updated"),
    ("legacy_issue_cooling_module_records", "ix_legacy_issue_cooling_module_workspace_updated"),
)


def upgrade() -> None:
    for table_name, updated_index_name in RECORD_TABLES:
        op.create_table(
            table_name,
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("workspace_id", sa.String(length=36), nullable=False),
            sa.Column("field_values", JSONB_COMPAT, nullable=True),
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
        op.create_index(updated_index_name, table_name, ["workspace_id", "updated_at"])
        op.create_index(op.f(f"ix_{table_name}_workspace_id"), table_name, ["workspace_id"])
        op.create_index(op.f(f"ix_{table_name}_created_by_id"), table_name, ["created_by_id"])

    op.create_table(
        "legacy_issue_module_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
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
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_legacy_issue_module_attachments_record",
        "legacy_issue_module_attachments",
        ["module_key", "record_id", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_module_attachments_workspace",
        "legacy_issue_module_attachments",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        op.f("ix_legacy_issue_module_attachments_workspace_id"),
        "legacy_issue_module_attachments",
        ["workspace_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_module_attachments_module_key"),
        "legacy_issue_module_attachments",
        ["module_key"],
    )
    op.create_index(
        op.f("ix_legacy_issue_module_attachments_record_id"),
        "legacy_issue_module_attachments",
        ["record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_module_attachments_uploaded_by_id"),
        "legacy_issue_module_attachments",
        ["uploaded_by_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_legacy_issue_module_attachments_uploaded_by_id"),
        table_name="legacy_issue_module_attachments",
    )
    op.drop_index(
        op.f("ix_legacy_issue_module_attachments_record_id"),
        table_name="legacy_issue_module_attachments",
    )
    op.drop_index(
        op.f("ix_legacy_issue_module_attachments_module_key"),
        table_name="legacy_issue_module_attachments",
    )
    op.drop_index(
        op.f("ix_legacy_issue_module_attachments_workspace_id"),
        table_name="legacy_issue_module_attachments",
    )
    op.drop_index(
        "ix_legacy_issue_module_attachments_workspace",
        table_name="legacy_issue_module_attachments",
    )
    op.drop_index(
        "ix_legacy_issue_module_attachments_record",
        table_name="legacy_issue_module_attachments",
    )
    op.drop_table("legacy_issue_module_attachments")

    for table_name, updated_index_name in reversed(RECORD_TABLES):
        op.drop_index(op.f(f"ix_{table_name}_created_by_id"), table_name=table_name)
        op.drop_index(op.f(f"ix_{table_name}_workspace_id"), table_name=table_name)
        op.drop_index(updated_index_name, table_name=table_name)
        op.drop_table(table_name)
