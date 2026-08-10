"""add legacy issue vehicle module checklists

Revision ID: a6b8c0d2e4f7
Revises: 4a9c1e6f2b3d
Create Date: 2026-07-15 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a6b8c0d2e4f7"
down_revision: str | Sequence[str] | None = "4a9c1e6f2b3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_CHECKLIST_TABLE = "legacy_issue_vehicle_checklist_revisions"
LEGACY_CHECKLIST_RECORD_TABLE = "legacy_issue_vehicle_checklist_records"
MODULE_CHECKLIST_TABLE = "legacy_issue_vehicle_module_checklists"
MODULE_CHECKLIST_RECORD_TABLE = "legacy_issue_vehicle_module_checklist_records"

JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "LOCK TABLE "
            f"{LEGACY_CHECKLIST_TABLE}, {LEGACY_CHECKLIST_RECORD_TABLE} "
            "IN SHARE ROW EXCLUSIVE MODE"
        )
    )
    checklist_count = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {LEGACY_CHECKLIST_TABLE}")
    ).scalar_one()
    record_count = bind.execute(
        sa.text(f"SELECT COUNT(*) FROM {LEGACY_CHECKLIST_RECORD_TABLE}")
    ).scalar_one()
    if checklist_count or record_count:
        raise RuntimeError(
            "Cannot create module-specific vehicle checklist tables while legacy "
            "aggregate checklist data exists: "
            f"{LEGACY_CHECKLIST_TABLE}={checklist_count}, "
            f"{LEGACY_CHECKLIST_RECORD_TABLE}={record_count}. "
            "Delete only the generated legacy checklist data before retrying."
        )

    op.create_table(
        MODULE_CHECKLIST_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("vehicle_model_id", sa.String(length=36), nullable=False),
        sa.Column("module_key", sa.String(length=80), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column("source_dataset_key", sa.String(length=80), nullable=False),
        sa.Column("source_master_revision_id", sa.String(), nullable=False),
        sa.Column("source_master_revision_no", sa.Integer(), nullable=True),
        sa.Column("definition_snapshot", JSONB_COMPAT, nullable=False),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_id", sa.String(), nullable=True),
        sa.Column("completed_by_id", sa.String(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'completed')",
            name="ck_li_vehicle_module_checklists_status",
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
            "module_key",
            "source_master_revision_id",
            name="uq_li_vehicle_module_checklists_scope_master",
        ),
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklists_completed_by_id"),
        MODULE_CHECKLIST_TABLE,
        ["completed_by_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklists_created_by_id"),
        MODULE_CHECKLIST_TABLE,
        ["created_by_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklists_module_key"),
        MODULE_CHECKLIST_TABLE,
        ["module_key"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklists_source_master_revision_id"),
        MODULE_CHECKLIST_TABLE,
        ["source_master_revision_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklists_status"),
        MODULE_CHECKLIST_TABLE,
        ["status"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklists_vehicle_model_id"),
        MODULE_CHECKLIST_TABLE,
        ["vehicle_model_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklists_workspace_id"),
        MODULE_CHECKLIST_TABLE,
        ["workspace_id"],
    )
    op.create_index(
        "ix_li_vehicle_module_checklists_source_revision",
        MODULE_CHECKLIST_TABLE,
        ["workspace_id", "source_master_revision_id"],
    )
    op.create_index(
        "ix_li_vehicle_module_checklists_workspace_vehicle_module",
        MODULE_CHECKLIST_TABLE,
        ["workspace_id", "vehicle_model_id", "module_key"],
    )

    op.create_table(
        MODULE_CHECKLIST_RECORD_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("checklist_id", sa.String(length=36), nullable=False),
        sa.Column("source_record_id", sa.String(length=36), nullable=False),
        sa.Column("source_stable_record_id", sa.String(length=36), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("field_values", JSONB_COMPAT, nullable=True),
        sa.Column("updated_by_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["checklist_id"],
            [f"{MODULE_CHECKLIST_TABLE}.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checklist_id",
            "source_record_id",
            name="uq_li_vehicle_module_checklist_records_source",
        ),
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_records_checklist_id"),
        MODULE_CHECKLIST_RECORD_TABLE,
        ["checklist_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_records_source_record_id"),
        MODULE_CHECKLIST_RECORD_TABLE,
        ["source_record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_records_source_stable_record_id"),
        MODULE_CHECKLIST_RECORD_TABLE,
        ["source_stable_record_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_records_updated_by_id"),
        MODULE_CHECKLIST_RECORD_TABLE,
        ["updated_by_id"],
    )
    op.create_index(
        op.f("ix_legacy_issue_vehicle_module_checklist_records_workspace_id"),
        MODULE_CHECKLIST_RECORD_TABLE,
        ["workspace_id"],
    )
    op.create_index(
        "ix_li_vehicle_module_checklist_records_source_stable",
        MODULE_CHECKLIST_RECORD_TABLE,
        ["workspace_id", "source_stable_record_id"],
    )
    op.create_index(
        "ix_li_vehicle_module_checklist_records_workspace_checklist",
        MODULE_CHECKLIST_RECORD_TABLE,
        ["workspace_id", "checklist_id", "sort_order"],
    )


def downgrade() -> None:
    op.drop_table(MODULE_CHECKLIST_RECORD_TABLE)
    op.drop_table(MODULE_CHECKLIST_TABLE)
