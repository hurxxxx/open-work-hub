"""add legacy issue vehicle checklists

Revision ID: c9a0b1c2d3e5
Revises: c8d9e0f1a2b3
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c9a0b1c2d3e5"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legacy_issue_vehicle_models",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("vehicle_code", sa.String(length=80), nullable=False),
        sa.Column("vehicle_code_normalized", sa.String(length=80), nullable=False),
        sa.Column("vehicle_name", sa.String(length=160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "vehicle_code_normalized",
            name="uq_legacy_issue_vehicle_models_workspace_code",
        ),
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_models_active"),
        "legacy_issue_vehicle_models",
        ["active"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_models_created_by_id"),
        "legacy_issue_vehicle_models",
        ["created_by_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_models_vehicle_code_normalized"),
        "legacy_issue_vehicle_models",
        ["vehicle_code_normalized"],
    )
    op.create_index(
        "ix_legacy_issue_vehicle_models_workspace_active_code",
        "legacy_issue_vehicle_models",
        ["workspace_id", "active", "vehicle_code_normalized"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_models_workspace_id"),
        "legacy_issue_vehicle_models",
        ["workspace_id"],
    )

    op.create_table(
        "legacy_issue_vehicle_checklist_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("vehicle_model_id", sa.String(length=36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=24), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("source_dataset_key", sa.String(length=80), nullable=False),
        sa.Column("source_master_revision_id", sa.String(), nullable=False),
        sa.Column("source_master_revision_no", sa.Integer(), nullable=True),
        sa.Column("definition_snapshot", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_id", sa.String(), nullable=True),
        sa.Column("completed_by_id", sa.String(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'completed')",
            name="ck_legacy_issue_vehicle_checklist_revisions_status",
        ),
        sa.ForeignKeyConstraint(["completed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["source_master_revision_id"],
            ["legacy_issue_data_revisions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_model_id"],
            ["legacy_issue_vehicle_models.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "revision_no",
            name="uq_legacy_issue_vehicle_checklist_revisions_vehicle_no",
        ),
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_completed_by_id"),
        "legacy_issue_vehicle_checklist_revisions",
        ["completed_by_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_created_by_id"),
        "legacy_issue_vehicle_checklist_revisions",
        ["created_by_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_source_master_revision_id"),
        "legacy_issue_vehicle_checklist_revisions",
        ["source_master_revision_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_status"),
        "legacy_issue_vehicle_checklist_revisions",
        ["status"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_vehicle_model_id"),
        "legacy_issue_vehicle_checklist_revisions",
        ["vehicle_model_id"],
    )
    op.create_index(
        "ix_legacy_issue_vehicle_checklist_revisions_source_revision",
        "legacy_issue_vehicle_checklist_revisions",
        ["workspace_id", "source_master_revision_id"],
    )
    op.create_index(
        "ix_legacy_issue_vehicle_checklist_revisions_workspace_vehicle",
        "legacy_issue_vehicle_checklist_revisions",
        ["workspace_id", "vehicle_model_id", "revision_no"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_workspace_id"),
        "legacy_issue_vehicle_checklist_revisions",
        ["workspace_id"],
    )

    op.create_table(
        "legacy_issue_vehicle_checklist_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("checklist_revision_id", sa.String(length=36), nullable=False),
        sa.Column("source_record_id", sa.String(length=36), nullable=False),
        sa.Column("source_stable_record_id", sa.String(length=36), nullable=True),
        sa.Column("source_module_key", sa.String(length=80), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("field_values", sa.JSON(), nullable=True),
        sa.Column("updated_by_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["checklist_revision_id"],
            ["legacy_issue_vehicle_checklist_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checklist_revision_id",
            "source_record_id",
            name="uq_legacy_issue_vehicle_checklist_records_source",
        ),
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_checklist_revision_id"),
        "legacy_issue_vehicle_checklist_records",
        ["checklist_revision_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_source_module_key"),
        "legacy_issue_vehicle_checklist_records",
        ["source_module_key"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_source_record_id"),
        "legacy_issue_vehicle_checklist_records",
        ["source_record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_source_stable_record_id"),
        "legacy_issue_vehicle_checklist_records",
        ["source_stable_record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_updated_by_id"),
        "legacy_issue_vehicle_checklist_records",
        ["updated_by_id"],
    )
    op.create_index(
        "ix_legacy_issue_vehicle_checklist_records_revision_module",
        "legacy_issue_vehicle_checklist_records",
        ["checklist_revision_id", "source_module_key"],
    )
    op.create_index(
        "ix_legacy_issue_vehicle_checklist_records_source_stable",
        "legacy_issue_vehicle_checklist_records",
        ["workspace_id", "source_stable_record_id"],
    )
    op.create_index(
        "ix_legacy_issue_vehicle_checklist_records_workspace_revision",
        "legacy_issue_vehicle_checklist_records",
        ["workspace_id", "checklist_revision_id", "sort_order"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_workspace_id"),
        "legacy_issue_vehicle_checklist_records",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_workspace_id"),
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        "ix_legacy_issue_vehicle_checklist_records_workspace_revision",
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        "ix_legacy_issue_vehicle_checklist_records_source_stable",
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        "ix_legacy_issue_vehicle_checklist_records_revision_module",
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_updated_by_id"),
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_source_stable_record_id"),
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_source_record_id"),
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_source_module_key"),
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_records_checklist_revision_id"),
        table_name="legacy_issue_vehicle_checklist_records",
    )
    op.drop_table("legacy_issue_vehicle_checklist_records")

    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_workspace_id"),
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_index(
        "ix_legacy_issue_vehicle_checklist_revisions_workspace_vehicle",
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_index(
        "ix_legacy_issue_vehicle_checklist_revisions_source_revision",
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_vehicle_model_id"),
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_status"),
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_source_master_revision_id"),
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_created_by_id"),
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_checklist_revisions_completed_by_id"),
        table_name="legacy_issue_vehicle_checklist_revisions",
    )
    op.drop_table("legacy_issue_vehicle_checklist_revisions")

    op.drop_index(
        op.f("ix_legacy_issue_vehicle_models_workspace_id"),
        table_name="legacy_issue_vehicle_models",
    )
    op.drop_index(
        "ix_legacy_issue_vehicle_models_workspace_active_code",
        table_name="legacy_issue_vehicle_models",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_models_vehicle_code_normalized"),
        table_name="legacy_issue_vehicle_models",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_models_created_by_id"),
        table_name="legacy_issue_vehicle_models",
    )
    op.drop_index(
        op.f("ix_legacy_issue_vehicle_models_active"),
        table_name="legacy_issue_vehicle_models",
    )
    op.drop_table("legacy_issue_vehicle_models")
