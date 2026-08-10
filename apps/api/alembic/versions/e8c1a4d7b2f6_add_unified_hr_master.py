"""add unified HR master

Revision ID: e8c1a4d7b2f6
Revises: d7b2e4f6a8c1
Create Date: 2026-07-29 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e8c1a4d7b2f6"
down_revision: str | Sequence[str] | None = "d7b2e4f6a8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "hr_master_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'building'"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("erp_run_id", sa.String(length=36), nullable=False),
        sa.Column("groupware_run_id", sa.String(length=36), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column(
            "person_row_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "group_row_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "conflict_row_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("result_payload", JSONB_COMPAT, nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("rows_purged_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('building','succeeded','failed')",
            name="ck_hr_master_runs_status",
        ),
        sa.CheckConstraint(
            "person_row_count >= 0",
            name="ck_hr_master_runs_person_count_nonnegative",
        ),
        sa.CheckConstraint(
            "group_row_count >= 0",
            name="ck_hr_master_runs_group_count_nonnegative",
        ),
        sa.CheckConstraint(
            "conflict_row_count >= 0",
            name="ck_hr_master_runs_conflict_count_nonnegative",
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR (checksum IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_hr_master_runs_succeeded_complete",
        ),
        sa.ForeignKeyConstraint(
            ["erp_run_id"],
            ["hr_sync_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["groupware_run_id"],
            ["hr_sync_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_master_runs_status", "hr_master_runs", ["status"])
    op.create_index("ix_hr_master_runs_erp_run_id", "hr_master_runs", ["erp_run_id"])
    op.create_index(
        "ix_hr_master_runs_groupware_run_id",
        "hr_master_runs",
        ["groupware_run_id"],
    )
    op.create_index("ix_hr_master_runs_checksum", "hr_master_runs", ["checksum"])
    op.create_index("ix_hr_master_runs_error_code", "hr_master_runs", ["error_code"])
    op.create_index("ix_hr_master_runs_started_at", "hr_master_runs", ["started_at"])
    op.create_index("ix_hr_master_runs_completed_at", "hr_master_runs", ["completed_at"])
    op.create_index("ix_hr_master_runs_rows_purged_at", "hr_master_runs", ["rows_purged_at"])
    op.create_index(
        "ix_hr_master_runs_latest_succeeded",
        "hr_master_runs",
        ["status", "completed_at", "id"],
    )
    op.create_index(
        "uq_hr_master_runs_succeeded_source_pair_schema",
        "hr_master_runs",
        ["erp_run_id", "groupware_run_id", "schema_version"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
        sqlite_where=sa.text("status = 'succeeded'"),
    )

    op.create_table(
        "hr_master_person_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("master_run_id", sa.String(length=36), nullable=False),
        sa.Column("employee_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("position", sa.String(length=160), nullable=True),
        sa.Column("occupation", sa.String(length=160), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("login_id", sa.String(length=120), nullable=True),
        sa.Column("group_source", sa.String(length=32), nullable=True),
        sa.Column("group_code", sa.String(length=80), nullable=True),
        sa.Column("group_name", sa.String(length=255), nullable=True),
        sa.Column("reconciliation_status", sa.String(length=32), nullable=False),
        sa.Column(
            "has_identity_conflict",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("erp_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("groupware_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "reconciliation_status IN ('matched','erp_only','groupware_only','identity_conflict')",
            name="ck_hr_master_person_rows_reconciliation_status",
        ),
        sa.CheckConstraint(
            "group_source IS NULL OR group_source IN ('erp','groupware')",
            name="ck_hr_master_person_rows_group_source",
        ),
        sa.CheckConstraint(
            "employee_code = upper(trim(employee_code)) AND length(employee_code) > 0",
            name="ck_hr_master_person_rows_normalized_employee_code",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id"],
            ["hr_master_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "master_run_id",
            "employee_code",
            name="uq_hr_master_person_rows_run_employee_code",
        ),
    )
    for column in (
        "master_run_id",
        "employee_code",
        "name",
        "email",
        "login_id",
        "group_source",
        "group_code",
        "group_name",
        "reconciliation_status",
        "has_identity_conflict",
        "erp_snapshot_row_id",
        "groupware_snapshot_row_id",
        "created_at",
    ):
        op.create_index(
            f"ix_hr_master_person_rows_{column}",
            "hr_master_person_rows",
            [column],
        )
    op.create_index(
        "ix_hr_master_person_rows_run_status_code",
        "hr_master_person_rows",
        ["master_run_id", "reconciliation_status", "employee_code"],
    )
    op.create_index(
        "ix_hr_master_person_rows_run_group",
        "hr_master_person_rows",
        ["master_run_id", "group_source", "group_code"],
    )

    op.create_table(
        "hr_master_group_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("master_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("source_code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_system IN ('erp','groupware')",
            name="ck_hr_master_group_rows_source_system",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id"],
            ["hr_master_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "master_run_id",
            "source_system",
            "source_code",
            name="uq_hr_master_group_rows_run_source_code",
        ),
    )
    for column in (
        "master_run_id",
        "source_system",
        "source_code",
        "name",
        "source_snapshot_row_id",
        "created_at",
    ):
        op.create_index(
            f"ix_hr_master_group_rows_{column}",
            "hr_master_group_rows",
            [column],
        )
    op.create_index(
        "ix_hr_master_group_rows_run_source_name",
        "hr_master_group_rows",
        ["master_run_id", "source_system", "name"],
    )

    op.create_table(
        "hr_master_conflict_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("master_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=120), nullable=False),
        sa.Column("normalized_employee_code", sa.String(length=40), nullable=True),
        sa.Column("source_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("details", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_system IN ('erp','groupware')",
            name="ck_hr_master_conflict_rows_source_system",
        ),
        sa.ForeignKeyConstraint(
            ["master_run_id"],
            ["hr_master_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "master_run_id",
        "source_system",
        "reason_code",
        "normalized_employee_code",
        "source_snapshot_row_id",
        "created_at",
    ):
        op.create_index(
            f"ix_hr_master_conflict_rows_{column}",
            "hr_master_conflict_rows",
            [column],
        )
    op.create_index(
        "ix_hr_master_conflict_rows_run_reason",
        "hr_master_conflict_rows",
        ["master_run_id", "reason_code"],
    )
    op.create_index(
        "ix_hr_master_conflict_rows_run_employee_code",
        "hr_master_conflict_rows",
        ["master_run_id", "normalized_employee_code"],
    )


def downgrade() -> None:
    op.drop_table("hr_master_conflict_rows")
    op.drop_table("hr_master_group_rows")
    op.drop_table("hr_master_person_rows")
    op.drop_table("hr_master_runs")
