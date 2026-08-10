"""add legacy issue system field settings

Revision ID: b9c0d1e2f3a5
Revises: a9b0c1d2e3f4
Create Date: 2026-07-06 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b9c0d1e2f3a5"
down_revision: str | Sequence[str] | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "legacy_issue_system_field_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=80), nullable=False),
        sa.Column("field_key", sa.String(length=160), nullable=False),
        sa.Column("label_ko", sa.String(length=120), nullable=False),
        sa.Column("label_en", sa.String(length=120), nullable=False),
        sa.Column("field_type", sa.String(length=24), nullable=False),
        sa.Column("options", JSONB_COMPAT, nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("updated_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "field_type IN ('text', 'longText', 'number', 'date', 'select', 'boolean')",
            name="ck_legacy_issue_system_field_settings_type",
        ),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "dataset_key",
            "field_key",
            name="uq_legacy_issue_system_field_settings_workspace_field",
        ),
    )
    op.create_index(
        "ix_legacy_issue_system_field_settings_workspace_id",
        "legacy_issue_system_field_settings",
        ["workspace_id"],
    )
    op.create_index(
        "ix_legacy_issue_system_field_settings_dataset_key",
        "legacy_issue_system_field_settings",
        ["dataset_key"],
    )
    op.create_index(
        "ix_legacy_issue_system_field_settings_field_key",
        "legacy_issue_system_field_settings",
        ["field_key"],
    )
    op.create_index(
        "ix_legacy_issue_system_field_settings_updated_by_id",
        "legacy_issue_system_field_settings",
        ["updated_by_id"],
    )
    op.create_index(
        "ix_legacy_issue_system_field_settings_workspace_dataset",
        "legacy_issue_system_field_settings",
        ["workspace_id", "dataset_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_legacy_issue_system_field_settings_workspace_dataset",
        table_name="legacy_issue_system_field_settings",
    )
    op.drop_index(
        "ix_legacy_issue_system_field_settings_updated_by_id",
        table_name="legacy_issue_system_field_settings",
    )
    op.drop_index(
        "ix_legacy_issue_system_field_settings_field_key",
        table_name="legacy_issue_system_field_settings",
    )
    op.drop_index(
        "ix_legacy_issue_system_field_settings_dataset_key",
        table_name="legacy_issue_system_field_settings",
    )
    op.drop_index(
        "ix_legacy_issue_system_field_settings_workspace_id",
        table_name="legacy_issue_system_field_settings",
    )
    op.drop_table("legacy_issue_system_field_settings")
