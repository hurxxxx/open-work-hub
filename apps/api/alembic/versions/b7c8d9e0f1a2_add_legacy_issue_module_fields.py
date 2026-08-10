"""add legacy issue module fields

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f2
Create Date: 2026-06-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7c8d9e0f1a2"
down_revision: str | Sequence[str] | None = "a6b7c8d9e0f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "legacy_issue_module_fields",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("field_key", sa.String(length=160), nullable=False),
        sa.Column("label_ko", sa.String(length=120), nullable=False),
        sa.Column("label_en", sa.String(length=120), nullable=False),
        sa.Column("field_type", sa.String(length=24), nullable=False),
        sa.Column("options", JSONB_COMPAT, nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "field_type IN ('text', 'longText', 'number', 'date', 'select', 'boolean')",
            name="ck_legacy_issue_module_fields_type",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "module_key",
            "field_key",
            name="uq_legacy_issue_module_fields_workspace_module_key",
        ),
    )
    op.create_index(
        "ix_legacy_issue_module_fields_workspace_id",
        "legacy_issue_module_fields",
        ["workspace_id"],
    )
    op.create_index(
        "ix_legacy_issue_module_fields_module_key",
        "legacy_issue_module_fields",
        ["module_key"],
    )
    op.create_index(
        "ix_legacy_issue_module_fields_field_key",
        "legacy_issue_module_fields",
        ["field_key"],
    )
    op.create_index(
        "ix_legacy_issue_module_fields_active",
        "legacy_issue_module_fields",
        ["active"],
    )
    op.create_index(
        "ix_legacy_issue_module_fields_created_by_id",
        "legacy_issue_module_fields",
        ["created_by_id"],
    )
    op.create_index(
        "ix_legacy_issue_module_fields_workspace_module_active_order",
        "legacy_issue_module_fields",
        ["workspace_id", "module_key", "active", "sort_order"],
    )

    op.create_table(
        "legacy_issue_module_access_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('user', 'org_unit', 'team')",
            name="ck_legacy_issue_module_access_subject_type",
        ),
        sa.CheckConstraint(
            "role IN ('viewer', 'editor', 'manager')",
            name="ck_legacy_issue_module_access_role",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "module_key",
            "subject_type",
            "subject_id",
            name="uq_legacy_issue_module_access_subject",
        ),
    )
    op.create_index(
        "ix_legacy_issue_module_access_rules_workspace_id",
        "legacy_issue_module_access_rules",
        ["workspace_id"],
    )
    op.create_index(
        "ix_legacy_issue_module_access_rules_module_key",
        "legacy_issue_module_access_rules",
        ["module_key"],
    )
    op.create_index(
        "ix_legacy_issue_module_access_rules_subject_type",
        "legacy_issue_module_access_rules",
        ["subject_type"],
    )
    op.create_index(
        "ix_legacy_issue_module_access_rules_subject_id",
        "legacy_issue_module_access_rules",
        ["subject_id"],
    )
    op.create_index(
        "ix_legacy_issue_module_access_rules_role",
        "legacy_issue_module_access_rules",
        ["role"],
    )
    op.create_index(
        "ix_legacy_issue_module_access_rules_active",
        "legacy_issue_module_access_rules",
        ["active"],
    )
    op.create_index(
        "ix_legacy_issue_module_access_rules_created_by_id",
        "legacy_issue_module_access_rules",
        ["created_by_id"],
    )
    op.create_index(
        "ix_legacy_issue_module_access_workspace_module_active",
        "legacy_issue_module_access_rules",
        ["workspace_id", "module_key", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legacy_issue_module_access_workspace_module_active",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_index(
        "ix_legacy_issue_module_access_rules_created_by_id",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_index(
        "ix_legacy_issue_module_access_rules_active",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_index(
        "ix_legacy_issue_module_access_rules_role",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_index(
        "ix_legacy_issue_module_access_rules_subject_id",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_index(
        "ix_legacy_issue_module_access_rules_subject_type",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_index(
        "ix_legacy_issue_module_access_rules_module_key",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_index(
        "ix_legacy_issue_module_access_rules_workspace_id",
        table_name="legacy_issue_module_access_rules",
    )
    op.drop_table("legacy_issue_module_access_rules")

    op.drop_index(
        "ix_legacy_issue_module_fields_workspace_module_active_order",
        table_name="legacy_issue_module_fields",
    )
    op.drop_index(
        "ix_legacy_issue_module_fields_created_by_id",
        table_name="legacy_issue_module_fields",
    )
    op.drop_index("ix_legacy_issue_module_fields_active", table_name="legacy_issue_module_fields")
    op.drop_index(
        "ix_legacy_issue_module_fields_field_key",
        table_name="legacy_issue_module_fields",
    )
    op.drop_index(
        "ix_legacy_issue_module_fields_module_key",
        table_name="legacy_issue_module_fields",
    )
    op.drop_index(
        "ix_legacy_issue_module_fields_workspace_id",
        table_name="legacy_issue_module_fields",
    )
    op.drop_table("legacy_issue_module_fields")
