"""add_patent_automation_tables

Revision ID: 9a1f7c3e5d2b
Revises: f4a5b6c7d8e9
Create Date: 2026-06-16 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9a1f7c3e5d2b"
down_revision: str | Sequence[str] | None = "f4a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # --- patent_data_revisions -------------------------------------------------
    op.create_table(
        "patent_data_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "dataset_key",
            sa.String(length=120),
            nullable=False,
            server_default=sa.text("'patent_status'"),
        ),
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
        sa.ForeignKeyConstraint(["base_revision_id"], ["patent_data_revisions.id"]),
        sa.ForeignKeyConstraint(["canceled_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["locked_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["published_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patent_revision_workspace_dataset_status",
        "patent_data_revisions",
        ["workspace_id", "dataset_key", "status"],
    )
    op.create_index(
        "ix_patent_revision_workspace_dataset_no",
        "patent_data_revisions",
        ["workspace_id", "dataset_key", "revision_no"],
        unique=True,
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_index(
            "ux_patent_revision_active_draft",
            "patent_data_revisions",
            ["workspace_id", "dataset_key"],
            unique=True,
            postgresql_where=sa.text("status = 'draft'"),
        )
    else:
        op.create_index(
            "ux_patent_revision_active_draft",
            "patent_data_revisions",
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
        op.create_index(
            op.f(f"ix_patent_data_revisions_{column}"),
            "patent_data_revisions",
            [column],
        )

    # --- patent_records --------------------------------------------------------
    op.create_table(
        "patent_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("revision_id", sa.String(length=36), nullable=True),
        sa.Column("stable_record_id", sa.String(length=36), nullable=True),
        sa.Column("application_no", sa.String(length=80), nullable=True),
        sa.Column("application_no_norm", sa.String(length=40), nullable=True),
        sa.Column("registration_no", sa.String(length=80), nullable=True),
        sa.Column("invention_title", sa.String(length=512), nullable=True),
        sa.Column("inventors", sa.Text(), nullable=True),
        sa.Column("disclosure_date", sa.String(length=10), nullable=True),
        sa.Column("disclosure_year", sa.Integer(), nullable=True),
        sa.Column("application_date", sa.String(length=10), nullable=True),
        sa.Column("application_year", sa.Integer(), nullable=True),
        sa.Column("patent_status", sa.String(length=40), nullable=True),
        sa.Column("current_stage", sa.String(length=120), nullable=True),
        sa.Column("lifecycle_phase", sa.String(length=40), nullable=True),
        sa.Column("source_sheet", sa.String(length=20), nullable=True),
        sa.Column("field_values", JSONB_COMPAT, nullable=True),
        sa.Column("raw_fields", JSONB_COMPAT, nullable=True),
        sa.Column("imported_source_filename", sa.String(length=512), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["patent_data_revisions.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patent_records_workspace_updated", "patent_records", ["workspace_id", "updated_at"]
    )
    op.create_index(
        "ix_patent_records_workspace_app_no",
        "patent_records",
        ["workspace_id", "application_no_norm"],
    )
    op.create_index(
        "ix_patent_records_workspace_reg_no", "patent_records", ["workspace_id", "registration_no"]
    )
    op.create_index(
        "ix_patent_records_workspace_disclosure_year",
        "patent_records",
        ["workspace_id", "disclosure_year"],
    )
    op.create_index(
        "ix_patent_records_workspace_stage", "patent_records", ["workspace_id", "current_stage"]
    )
    op.create_index(
        "ix_patent_records_workspace_lifecycle",
        "patent_records",
        ["workspace_id", "lifecycle_phase"],
    )
    op.create_index(
        "ix_patent_records_workspace_revision", "patent_records", ["workspace_id", "revision_id"]
    )
    op.create_index(
        "ix_patent_records_workspace_stable", "patent_records", ["workspace_id", "stable_record_id"]
    )
    for column in ("workspace_id", "revision_id", "stable_record_id", "created_by_id"):
        op.create_index(op.f(f"ix_patent_records_{column}"), "patent_records", [column])

    # --- patent_progress_events ------------------------------------------------
    op.create_table(
        "patent_progress_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("event_date", sa.String(length=10), nullable=True),
        sa.Column("stage", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["patent_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patent_progress_record_kind_seq", "patent_progress_events", ["record_id", "kind", "seq"]
    )
    op.create_index(
        "ix_patent_progress_workspace", "patent_progress_events", ["workspace_id", "kind"]
    )
    for column in ("workspace_id", "record_id"):
        op.create_index(
            op.f(f"ix_patent_progress_events_{column}"), "patent_progress_events", [column]
        )

    # --- patent_cost_runs ------------------------------------------------------
    op.create_table(
        "patent_cost_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("fiscal_period", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source_filenames", JSONB_COMPAT, nullable=True),
        sa.Column("warnings", JSONB_COMPAT, nullable=True),
        sa.Column("industrial_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("overseas_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("industrial_total", sa.Integer(), nullable=True),
        sa.Column("overseas_total", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patent_cost_runs_workspace_period",
        "patent_cost_runs",
        ["workspace_id", "fiscal_period"],
    )
    op.create_index(
        "ix_patent_cost_runs_workspace_created", "patent_cost_runs", ["workspace_id", "created_at"]
    )
    for column in ("workspace_id", "created_by_id"):
        op.create_index(op.f(f"ix_patent_cost_runs_{column}"), "patent_cost_runs", [column])

    # --- patent_cost_lines -----------------------------------------------------
    op.create_table(
        "patent_cost_lines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=True),
        sa.Column("region", sa.String(length=20), nullable=False),
        sa.Column("section", sa.String(length=40), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=True),
        sa.Column("vendor", sa.String(length=40), nullable=True),
        sa.Column("invoice_no", sa.String(length=60), nullable=True),
        sa.Column("application_no", sa.String(length=80), nullable=True),
        sa.Column("registration_no", sa.String(length=80), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("inventors", sa.Text(), nullable=True),
        sa.Column("application_date", sa.String(length=10), nullable=True),
        sa.Column("registration_date", sa.String(length=10), nullable=True),
        sa.Column("annuity_year", sa.String(length=20), nullable=True),
        sa.Column("supply_amount", sa.Integer(), nullable=True),
        sa.Column("vat", sa.Integer(), nullable=True),
        sa.Column("gov_fee", sa.Integer(), nullable=True),
        sa.Column("line_total", sa.Integer(), nullable=True),
        sa.Column("foreign_currency", sa.String(length=8), nullable=True),
        sa.Column("foreign_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("fx_rate", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("foreign_cost_krw", sa.Integer(), nullable=True),
        sa.Column("reconciled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cost_details", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["patent_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["patent_cost_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_patent_cost_lines_run", "patent_cost_lines", ["run_id", "section"])
    op.create_index(
        "ix_patent_cost_lines_workspace_record", "patent_cost_lines", ["workspace_id", "record_id"]
    )
    for column in ("workspace_id", "run_id", "record_id"):
        op.create_index(op.f(f"ix_patent_cost_lines_{column}"), "patent_cost_lines", [column])

    # --- patent_record_history -------------------------------------------------
    op.create_table(
        "patent_record_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("field_key", sa.String(length=160), nullable=True),
        sa.Column("field_label", sa.String(length=255), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("details", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patent_history_record",
        "patent_record_history",
        ["workspace_id", "record_id", "created_at"],
    )
    for column in ("workspace_id", "record_id", "action", "actor_user_id"):
        op.create_index(
            op.f(f"ix_patent_record_history_{column}"), "patent_record_history", [column]
        )


def downgrade() -> None:
    for column in reversed(("workspace_id", "record_id", "action", "actor_user_id")):
        op.drop_index(
            op.f(f"ix_patent_record_history_{column}"), table_name="patent_record_history"
        )
    op.drop_index("ix_patent_history_record", table_name="patent_record_history")
    op.drop_table("patent_record_history")

    for column in reversed(("workspace_id", "run_id", "record_id")):
        op.drop_index(op.f(f"ix_patent_cost_lines_{column}"), table_name="patent_cost_lines")
    op.drop_index("ix_patent_cost_lines_workspace_record", table_name="patent_cost_lines")
    op.drop_index("ix_patent_cost_lines_run", table_name="patent_cost_lines")
    op.drop_table("patent_cost_lines")

    for column in reversed(("workspace_id", "created_by_id")):
        op.drop_index(op.f(f"ix_patent_cost_runs_{column}"), table_name="patent_cost_runs")
    op.drop_index("ix_patent_cost_runs_workspace_created", table_name="patent_cost_runs")
    op.drop_index("ix_patent_cost_runs_workspace_period", table_name="patent_cost_runs")
    op.drop_table("patent_cost_runs")

    for column in reversed(("workspace_id", "record_id")):
        op.drop_index(
            op.f(f"ix_patent_progress_events_{column}"), table_name="patent_progress_events"
        )
    op.drop_index("ix_patent_progress_workspace", table_name="patent_progress_events")
    op.drop_index("ix_patent_progress_record_kind_seq", table_name="patent_progress_events")
    op.drop_table("patent_progress_events")

    for column in reversed(("workspace_id", "revision_id", "stable_record_id", "created_by_id")):
        op.drop_index(op.f(f"ix_patent_records_{column}"), table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_stable", table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_revision", table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_lifecycle", table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_stage", table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_disclosure_year", table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_reg_no", table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_app_no", table_name="patent_records")
    op.drop_index("ix_patent_records_workspace_updated", table_name="patent_records")
    op.drop_table("patent_records")

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
            op.f(f"ix_patent_data_revisions_{column}"), table_name="patent_data_revisions"
        )
    op.drop_index("ux_patent_revision_active_draft", table_name="patent_data_revisions")
    op.drop_index("ix_patent_revision_workspace_dataset_no", table_name="patent_data_revisions")
    op.drop_index("ix_patent_revision_workspace_dataset_status", table_name="patent_data_revisions")
    op.drop_table("patent_data_revisions")
