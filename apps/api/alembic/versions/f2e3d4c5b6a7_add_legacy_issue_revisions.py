"""add_legacy_issue_revisions

Revision ID: f2e3d4c5b6a7
Revises: f1e2d3c4b5a6
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2e3d4c5b6a7"
down_revision: str | Sequence[str] | None = "f1e2d3c4b5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


AIRCON_TABLE = "legacy_issue_aircon_records"
AIRCON_ATTACHMENT_TABLE = "legacy_issue_aircon_attachments"
MODULE_ATTACHMENT_TABLE = "legacy_issue_module_attachments"
MODULE_TABLES = (
    ("legacy_issue_electrical_mechanical_records", "legacy_issue.module.electrical-mechanical"),
    ("legacy_issue_electrical_control_hw_records", "legacy_issue.module.electrical-control-hw"),
    ("legacy_issue_electrical_control_sw_records", "legacy_issue.module.electrical-control-sw"),
    ("legacy_issue_interior_records", "legacy_issue.module.interior"),
    ("legacy_issue_cooling_module_records", "legacy_issue.module.cooling-module"),
)
RECORD_TABLES = ((AIRCON_TABLE, "legacy_issue.aircon"), *MODULE_TABLES)


def upgrade() -> None:
    op.create_table(
        "legacy_issue_data_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("base_revision_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("locked_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("published_by_id", sa.String(length=36), nullable=True),
        sa.Column("canceled_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("canceled_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["base_revision_id"], ["legacy_issue_data_revisions.id"]),
        sa.ForeignKeyConstraint(["canceled_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["locked_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_revision_workspace_dataset_status",
        "legacy_issue_data_revisions",
        ["workspace_id", "dataset_key", "status"],
    )
    op.create_index(
        "ix_legacy_issue_revision_workspace_dataset_no",
        "legacy_issue_data_revisions",
        ["workspace_id", "dataset_key", "revision_no"],
        unique=True,
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "ux_legacy_issue_revision_active_draft",
            "legacy_issue_data_revisions",
            ["workspace_id", "dataset_key"],
            unique=True,
            postgresql_where=sa.text("status = 'draft'"),
        )
    else:
        op.create_index(
            "ux_legacy_issue_revision_active_draft",
            "legacy_issue_data_revisions",
            ["workspace_id", "dataset_key"],
        )
    for column in (
        "workspace_id",
        "dataset_key",
        "status",
        "base_revision_id",
        "locked_by_id",
        "created_by_id",
        "published_by_id",
        "canceled_by_id",
    ):
        op.create_index(op.f(f"ix_legacy_issue_data_revisions_{column}"), "legacy_issue_data_revisions", [column])

    op.create_table(
        "legacy_issue_data_revision_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=False),
        sa.Column("dataset_key", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("details", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["legacy_issue_data_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_legacy_issue_revision_event_revision",
        "legacy_issue_data_revision_events",
        ["revision_id", "created_at"],
    )
    op.create_index(
        "ix_legacy_issue_revision_event_workspace_dataset",
        "legacy_issue_data_revision_events",
        ["workspace_id", "dataset_key", "created_at"],
    )
    for column in ("workspace_id", "revision_id", "dataset_key", "action", "actor_user_id"):
        op.create_index(
            op.f(f"ix_legacy_issue_data_revision_events_{column}"),
            "legacy_issue_data_revision_events",
            [column],
        )

    for table_name, _dataset_key in RECORD_TABLES:
        op.add_column(table_name, sa.Column("revision_id", sa.String(length=36), nullable=True))
        op.add_column(table_name, sa.Column("stable_record_id", sa.String(length=36), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table_name}_revision_id_legacy_issue_data_revisions"),
            table_name,
            "legacy_issue_data_revisions",
            ["revision_id"],
            ["id"],
        )
        op.create_index(op.f(f"ix_{table_name}_revision_id"), table_name, ["revision_id"])
        op.create_index(op.f(f"ix_{table_name}_stable_record_id"), table_name, ["stable_record_id"])
        if table_name == AIRCON_TABLE:
            op.create_index(
                "ix_legacy_issue_aircon_workspace_revision",
                table_name,
                ["workspace_id", "revision_id"],
            )
            op.create_index(
                "ix_legacy_issue_aircon_workspace_stable",
                table_name,
                ["workspace_id", "stable_record_id"],
            )

    for table_name in (AIRCON_ATTACHMENT_TABLE, MODULE_ATTACHMENT_TABLE):
        op.add_column(table_name, sa.Column("revision_id", sa.String(length=36), nullable=True))
        op.add_column(table_name, sa.Column("stable_record_id", sa.String(length=36), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table_name}_revision_id_legacy_issue_data_revisions"),
            table_name,
            "legacy_issue_data_revisions",
            ["revision_id"],
            ["id"],
        )
        op.create_index(op.f(f"ix_{table_name}_revision_id"), table_name, ["revision_id"])
        op.create_index(op.f(f"ix_{table_name}_stable_record_id"), table_name, ["stable_record_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint(
            "legacy_issue_aircon_attachments_storage_key_key",
            AIRCON_ATTACHMENT_TABLE,
            type_="unique",
        )
        op.drop_constraint(
            "legacy_issue_module_attachments_storage_key_key",
            MODULE_ATTACHMENT_TABLE,
            type_="unique",
        )

def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint(
            "legacy_issue_aircon_attachments_storage_key_key",
            AIRCON_ATTACHMENT_TABLE,
            ["storage_key"],
        )
        op.create_unique_constraint(
            "legacy_issue_module_attachments_storage_key_key",
            MODULE_ATTACHMENT_TABLE,
            ["storage_key"],
        )

    for table_name in reversed((AIRCON_ATTACHMENT_TABLE, MODULE_ATTACHMENT_TABLE)):
        op.drop_index(op.f(f"ix_{table_name}_stable_record_id"), table_name=table_name)
        op.drop_index(op.f(f"ix_{table_name}_revision_id"), table_name=table_name)
        op.drop_constraint(
            op.f(f"fk_{table_name}_revision_id_legacy_issue_data_revisions"),
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "stable_record_id")
        op.drop_column(table_name, "revision_id")

    for table_name, _dataset_key in reversed(RECORD_TABLES):
        if table_name == AIRCON_TABLE:
            op.drop_index("ix_legacy_issue_aircon_workspace_stable", table_name=table_name)
            op.drop_index("ix_legacy_issue_aircon_workspace_revision", table_name=table_name)
        op.drop_index(op.f(f"ix_{table_name}_stable_record_id"), table_name=table_name)
        op.drop_index(op.f(f"ix_{table_name}_revision_id"), table_name=table_name)
        op.drop_constraint(
            op.f(f"fk_{table_name}_revision_id_legacy_issue_data_revisions"),
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "stable_record_id")
        op.drop_column(table_name, "revision_id")

    for column in reversed(("workspace_id", "revision_id", "dataset_key", "action", "actor_user_id")):
        op.drop_index(op.f(f"ix_legacy_issue_data_revision_events_{column}"), table_name="legacy_issue_data_revision_events")
    op.drop_index("ix_legacy_issue_revision_event_workspace_dataset", table_name="legacy_issue_data_revision_events")
    op.drop_index("ix_legacy_issue_revision_event_revision", table_name="legacy_issue_data_revision_events")
    op.drop_table("legacy_issue_data_revision_events")

    for column in reversed(
        (
            "workspace_id",
            "dataset_key",
            "status",
            "base_revision_id",
            "locked_by_id",
            "created_by_id",
            "published_by_id",
            "canceled_by_id",
        )
    ):
        op.drop_index(
            op.f(f"ix_legacy_issue_data_revisions_{column}"),
            table_name="legacy_issue_data_revisions",
        )
    op.drop_index("ux_legacy_issue_revision_active_draft", table_name="legacy_issue_data_revisions")
    op.drop_index("ix_legacy_issue_revision_workspace_dataset_no", table_name="legacy_issue_data_revisions")
    op.drop_index("ix_legacy_issue_revision_workspace_dataset_status", table_name="legacy_issue_data_revisions")
    op.drop_table("legacy_issue_data_revisions")
