"""add legacy issue vehicle development stages

Revision ID: a3f6c9e1b4d8
Revises: f8c0e2a4b6d9
Create Date: 2026-07-30 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "a3f6c9e1b4d8"
down_revision: str | Sequence[str] | None = "f8c0e2a4b6d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECKLIST_TABLE = "legacy_issue_vehicle_module_checklists"
_STAGE_TABLE = "legacy_issue_vehicle_stages"
_CHECKLIST_SCOPE_CONSTRAINT = "uq_li_vehicle_module_checklists_scope_master"


def upgrade() -> None:
    op.create_table(
        _STAGE_TABLE,
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_model_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("name_normalized", sa.String(length=80), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("previous_stage_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["previous_stage_id"],
            [f"{_STAGE_TABLE}.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(
            ["vehicle_model_id"],
            ["legacy_issue_vehicle_models.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "name_normalized",
            name="uq_li_vehicle_stages_vehicle_name",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "vehicle_model_id",
            "sequence_no",
            name="uq_li_vehicle_stages_vehicle_sequence",
        ),
    )
    op.create_index(
        "ix_legacy_issue_vehicle_stages_created_by_id",
        _STAGE_TABLE,
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        "ix_legacy_issue_vehicle_stages_previous_stage_id",
        _STAGE_TABLE,
        ["previous_stage_id"],
        unique=False,
    )
    op.create_index(
        "ix_legacy_issue_vehicle_stages_vehicle_model_id",
        _STAGE_TABLE,
        ["vehicle_model_id"],
        unique=False,
    )
    op.create_index(
        "ix_legacy_issue_vehicle_stages_workspace_id",
        _STAGE_TABLE,
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_li_vehicle_stages_workspace_vehicle_sequence",
        _STAGE_TABLE,
        ["workspace_id", "vehicle_model_id", "sequence_no"],
        unique=False,
    )

    op.add_column(
        _CHECKLIST_TABLE,
        sa.Column("vehicle_stage_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        _CHECKLIST_TABLE,
        sa.Column("seeded_from_checklist_id", sa.String(length=36), nullable=True),
    )

    connection = op.get_bind()
    vehicles = connection.execute(
        sa.text(
            """
            SELECT
                id,
                workspace_id,
                created_by_id,
                created_at,
                updated_at
            FROM legacy_issue_vehicle_models
            ORDER BY workspace_id, id
            """
        )
    ).mappings()
    for vehicle in vehicles:
        stage_id = str(uuid4())
        connection.execute(
            sa.text(
                f"""
                INSERT INTO {_STAGE_TABLE} (
                    id,
                    workspace_id,
                    vehicle_model_id,
                    name,
                    name_normalized,
                    sequence_no,
                    previous_stage_id,
                    created_by_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :workspace_id,
                    :vehicle_model_id,
                    :name,
                    :name_normalized,
                    1,
                    NULL,
                    :created_by_id,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "id": stage_id,
                "workspace_id": vehicle["workspace_id"],
                "vehicle_model_id": vehicle["id"],
                "name": "기존",
                "name_normalized": "기존",
                "created_by_id": vehicle["created_by_id"],
                "created_at": vehicle["created_at"],
                "updated_at": vehicle["updated_at"],
            },
        )
        connection.execute(
            sa.text(
                f"""
                UPDATE {_CHECKLIST_TABLE}
                SET vehicle_stage_id = :stage_id
                WHERE workspace_id = :workspace_id
                  AND vehicle_model_id = :vehicle_model_id
                  AND vehicle_stage_id IS NULL
                """
            ),
            {
                "stage_id": stage_id,
                "workspace_id": vehicle["workspace_id"],
                "vehicle_model_id": vehicle["id"],
            },
        )

    missing_stage_count = connection.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM {_CHECKLIST_TABLE}
            WHERE vehicle_stage_id IS NULL
            """
        )
    ).scalar_one()
    if missing_stage_count:
        raise RuntimeError("Legacy issue vehicle checklist stage backfill left rows unassigned.")

    op.alter_column(
        _CHECKLIST_TABLE,
        "vehicle_stage_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_li_vehicle_module_checklists_vehicle_stage_id",
        _CHECKLIST_TABLE,
        _STAGE_TABLE,
        ["vehicle_stage_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_li_vehicle_module_checklists_seeded_from_checklist_id",
        _CHECKLIST_TABLE,
        _CHECKLIST_TABLE,
        ["seeded_from_checklist_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_legacy_issue_vehicle_module_checklists_vehicle_stage_id",
        _CHECKLIST_TABLE,
        ["vehicle_stage_id"],
        unique=False,
    )
    op.create_index(
        "ix_li_vehicle_module_checklists_seeded_from",
        _CHECKLIST_TABLE,
        ["seeded_from_checklist_id"],
        unique=False,
    )
    op.drop_constraint(
        _CHECKLIST_SCOPE_CONSTRAINT,
        _CHECKLIST_TABLE,
        type_="unique",
    )
    op.create_unique_constraint(
        _CHECKLIST_SCOPE_CONSTRAINT,
        _CHECKLIST_TABLE,
        [
            "workspace_id",
            "vehicle_model_id",
            "vehicle_stage_id",
            "module_key",
            "source_master_revision_id",
        ],
    )


def downgrade() -> None:
    connection = op.get_bind()
    duplicate_scope = connection.execute(
        sa.text(
            f"""
            SELECT 1
            FROM {_CHECKLIST_TABLE}
            GROUP BY
                workspace_id,
                vehicle_model_id,
                module_key,
                source_master_revision_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_scope is not None:
        raise RuntimeError(
            "Cannot remove vehicle stages while multiple stages contain the "
            "same vehicle/module/master-revision checklist."
        )

    op.drop_constraint(
        _CHECKLIST_SCOPE_CONSTRAINT,
        _CHECKLIST_TABLE,
        type_="unique",
    )
    op.create_unique_constraint(
        _CHECKLIST_SCOPE_CONSTRAINT,
        _CHECKLIST_TABLE,
        [
            "workspace_id",
            "vehicle_model_id",
            "module_key",
            "source_master_revision_id",
        ],
    )
    op.drop_index(
        "ix_li_vehicle_module_checklists_seeded_from",
        table_name=_CHECKLIST_TABLE,
    )
    op.drop_index(
        "ix_legacy_issue_vehicle_module_checklists_vehicle_stage_id",
        table_name=_CHECKLIST_TABLE,
    )
    op.drop_constraint(
        "fk_li_vehicle_module_checklists_seeded_from_checklist_id",
        _CHECKLIST_TABLE,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_li_vehicle_module_checklists_vehicle_stage_id",
        _CHECKLIST_TABLE,
        type_="foreignkey",
    )
    op.drop_column(_CHECKLIST_TABLE, "seeded_from_checklist_id")
    op.drop_column(_CHECKLIST_TABLE, "vehicle_stage_id")
    op.drop_table(_STAGE_TABLE)
