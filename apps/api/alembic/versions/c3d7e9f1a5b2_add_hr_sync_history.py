"""add HR sync history

Revision ID: c3d7e9f1a5b2
Revises: ba2c4d6e8f10
Create Date: 2026-07-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c3d7e9f1a5b2"
down_revision: str | Sequence[str] | None = "ba2c4d6e8f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")
LIVE_RUN_STATUS_SQL = "status IN ('pending','capturing','validating','applying')"


def upgrade() -> None:
    op.create_table(
        "hr_sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_system", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=80), nullable=False),
        sa.Column("trigger_kind", sa.String(length=24), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("comparison_run_id", sa.String(length=36), nullable=True),
        sa.Column("blocked_by_run_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("schema_version", sa.String(length=80), nullable=True),
        sa.Column("canonicalization_version", sa.String(length=40), nullable=True),
        sa.Column("org_row_count", sa.Integer(), nullable=True),
        sa.Column("user_row_count", sa.Integer(), nullable=True),
        sa.Column("active_user_row_count", sa.Integer(), nullable=True),
        sa.Column("org_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("user_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("validation_payload", JSONB_COMPAT, nullable=True),
        sa.Column("result_payload", JSONB_COMPAT, nullable=True),
        sa.Column("error_phase", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("snapshot_purge_after", sa.DateTime(), nullable=False),
        sa.Column("snapshots_purged_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN "
            "('pending','capturing','validating','rejected','applying','succeeded',"
            "'failed','skipped','abandoned')",
            name="ck_hr_sync_runs_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_hr_sync_runs_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "org_row_count IS NULL OR org_row_count >= 0",
            name="ck_hr_sync_runs_org_row_count_nonnegative",
        ),
        sa.CheckConstraint(
            "user_row_count IS NULL OR user_row_count >= 0",
            name="ck_hr_sync_runs_user_row_count_nonnegative",
        ),
        sa.CheckConstraint(
            "active_user_row_count IS NULL OR active_user_row_count >= 0",
            name="ck_hr_sync_runs_active_user_row_count_nonnegative",
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR applied_at IS NOT NULL",
            name="ck_hr_sync_runs_succeeded_applied_at",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["comparison_run_id"],
            ["hr_sync_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["blocked_by_run_id"],
            ["hr_sync_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system",
            "scope_key",
            "idempotency_key",
            name="uq_hr_sync_runs_source_scope_idempotency",
        ),
    )
    op.create_index(
        "uq_hr_sync_runs_live_source_scope",
        "hr_sync_runs",
        ["source_system", "scope_key"],
        unique=True,
        postgresql_where=sa.text(LIVE_RUN_STATUS_SQL),
        sqlite_where=sa.text(LIVE_RUN_STATUS_SQL),
    )
    op.create_index(
        "ix_hr_sync_runs_latest_applied",
        "hr_sync_runs",
        ["source_system", "scope_key", "status", "applied_at", "id"],
    )
    op.create_index(
        "ix_hr_sync_runs_status_created",
        "hr_sync_runs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_hr_sync_runs_snapshot_purge",
        "hr_sync_runs",
        ["snapshot_purge_after", "snapshots_purged_at"],
    )
    op.create_index(
        "ix_hr_sync_runs_lease_expires",
        "hr_sync_runs",
        ["status", "lease_expires_at"],
    )
    for column_name in (
        "source_system",
        "scope_key",
        "trigger_kind",
        "requested_by_user_id",
        "celery_task_id",
        "comparison_run_id",
        "blocked_by_run_id",
        "status",
        "error_phase",
        "error_code",
        "started_at",
        "applied_at",
        "completed_at",
        "snapshot_purge_after",
        "snapshots_purged_at",
    ):
        op.create_index(op.f(f"ix_hr_sync_runs_{column_name}"), "hr_sync_runs", [column_name])

    op.create_table(
        "hr_user_snapshot_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_row_no", sa.Integer(), nullable=False),
        sa.Column("domain_num", sa.Integer(), nullable=True),
        sa.Column("user_num", sa.Integer(), nullable=True),
        sa.Column("source_identity", sa.String(length=160), nullable=True),
        sa.Column("employee_code", sa.String(length=40), nullable=True),
        sa.Column("raw_payload", JSONB_COMPAT, nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_row_no >= 0",
            name="ck_hr_user_snapshot_rows_source_row_nonnegative",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["hr_sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "source_row_no",
            name="uq_hr_user_snapshot_rows_run_source_row",
        ),
    )
    op.create_index(
        "ix_hr_user_snapshot_rows_run_identity",
        "hr_user_snapshot_rows",
        ["run_id", "domain_num", "user_num"],
    )
    op.create_index(
        "ix_hr_user_snapshot_rows_identity_captured",
        "hr_user_snapshot_rows",
        ["domain_num", "user_num", "created_at"],
    )
    op.create_index(
        "ix_hr_user_snapshot_rows_run_hash",
        "hr_user_snapshot_rows",
        ["run_id", "row_hash"],
    )
    for column_name in ("run_id", "source_identity", "employee_code", "created_at"):
        op.create_index(
            op.f(f"ix_hr_user_snapshot_rows_{column_name}"),
            "hr_user_snapshot_rows",
            [column_name],
        )

    op.create_table(
        "hr_org_snapshot_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source_row_no", sa.Integer(), nullable=False),
        sa.Column("domain_num", sa.Integer(), nullable=True),
        sa.Column("org_code", sa.String(length=80), nullable=True),
        sa.Column("source_identity", sa.String(length=160), nullable=True),
        sa.Column("raw_payload", JSONB_COMPAT, nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_row_no >= 0",
            name="ck_hr_org_snapshot_rows_source_row_nonnegative",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["hr_sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "source_row_no",
            name="uq_hr_org_snapshot_rows_run_source_row",
        ),
    )
    op.create_index(
        "ix_hr_org_snapshot_rows_run_identity",
        "hr_org_snapshot_rows",
        ["run_id", "domain_num", "org_code"],
    )
    op.create_index(
        "ix_hr_org_snapshot_rows_identity_captured",
        "hr_org_snapshot_rows",
        ["domain_num", "org_code", "created_at"],
    )
    op.create_index(
        "ix_hr_org_snapshot_rows_run_hash",
        "hr_org_snapshot_rows",
        ["run_id", "row_hash"],
    )
    for column_name in ("run_id", "source_identity", "created_at"):
        op.create_index(
            op.f(f"ix_hr_org_snapshot_rows_{column_name}"),
            "hr_org_snapshot_rows",
            [column_name],
        )

    op.create_table(
        "hr_sync_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("entity_kind", sa.String(length=24), nullable=False),
        sa.Column("source_identity", sa.String(length=160), nullable=False),
        sa.Column("domain_num", sa.Integer(), nullable=True),
        sa.Column("user_num", sa.Integer(), nullable=True),
        sa.Column("org_code", sa.String(length=80), nullable=True),
        sa.Column("employee_code", sa.String(length=40), nullable=True),
        sa.Column("change_kind", sa.String(length=24), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column(
            "outcome",
            sa.String(length=24),
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column("before_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("after_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("target_entity_id", sa.String(length=36), nullable=True),
        sa.Column("changed_fields", JSONB_COMPAT, nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", JSONB_COMPAT, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "entity_kind IN ('user','org_unit')",
            name="ck_hr_sync_changes_entity_kind",
        ),
        sa.CheckConstraint(
            "change_kind IN "
            "('baseline','hired','rehired','retired','created','updated','activated',"
            "'deactivated','unchanged','conflict')",
            name="ck_hr_sync_changes_change_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('planned','applied','skipped','blocked','failed')",
            name="ck_hr_sync_changes_outcome",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["hr_sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "entity_kind",
            "source_identity",
            name="uq_hr_sync_changes_run_entity_identity",
        ),
    )
    op.create_index(
        "ix_hr_sync_changes_run_kind_outcome",
        "hr_sync_changes",
        ["run_id", "change_kind", "outcome"],
    )
    op.create_index(
        "ix_hr_sync_changes_entity_identity_created",
        "hr_sync_changes",
        ["entity_kind", "source_identity", "created_at"],
    )
    op.create_index(
        "ix_hr_sync_changes_target_created",
        "hr_sync_changes",
        ["target_entity_id", "created_at"],
    )
    for column_name in (
        "run_id",
        "entity_kind",
        "source_identity",
        "employee_code",
        "change_kind",
        "action",
        "outcome",
        "before_snapshot_row_id",
        "after_snapshot_row_id",
        "target_entity_id",
        "created_at",
        "applied_at",
    ):
        op.create_index(
            op.f(f"ix_hr_sync_changes_{column_name}"),
            "hr_sync_changes",
            [column_name],
        )


def downgrade() -> None:
    for column_name in (
        "applied_at",
        "created_at",
        "target_entity_id",
        "after_snapshot_row_id",
        "before_snapshot_row_id",
        "outcome",
        "action",
        "change_kind",
        "employee_code",
        "source_identity",
        "entity_kind",
        "run_id",
    ):
        op.drop_index(op.f(f"ix_hr_sync_changes_{column_name}"), table_name="hr_sync_changes")
    op.drop_index("ix_hr_sync_changes_target_created", table_name="hr_sync_changes")
    op.drop_index("ix_hr_sync_changes_entity_identity_created", table_name="hr_sync_changes")
    op.drop_index("ix_hr_sync_changes_run_kind_outcome", table_name="hr_sync_changes")
    op.drop_table("hr_sync_changes")

    for column_name in ("created_at", "source_identity", "run_id"):
        op.drop_index(
            op.f(f"ix_hr_org_snapshot_rows_{column_name}"),
            table_name="hr_org_snapshot_rows",
        )
    op.drop_index("ix_hr_org_snapshot_rows_run_hash", table_name="hr_org_snapshot_rows")
    op.drop_index(
        "ix_hr_org_snapshot_rows_identity_captured",
        table_name="hr_org_snapshot_rows",
    )
    op.drop_index("ix_hr_org_snapshot_rows_run_identity", table_name="hr_org_snapshot_rows")
    op.drop_table("hr_org_snapshot_rows")

    for column_name in ("created_at", "employee_code", "source_identity", "run_id"):
        op.drop_index(
            op.f(f"ix_hr_user_snapshot_rows_{column_name}"),
            table_name="hr_user_snapshot_rows",
        )
    op.drop_index("ix_hr_user_snapshot_rows_run_hash", table_name="hr_user_snapshot_rows")
    op.drop_index(
        "ix_hr_user_snapshot_rows_identity_captured",
        table_name="hr_user_snapshot_rows",
    )
    op.drop_index("ix_hr_user_snapshot_rows_run_identity", table_name="hr_user_snapshot_rows")
    op.drop_table("hr_user_snapshot_rows")

    for column_name in (
        "snapshots_purged_at",
        "snapshot_purge_after",
        "completed_at",
        "applied_at",
        "started_at",
        "error_code",
        "error_phase",
        "status",
        "blocked_by_run_id",
        "comparison_run_id",
        "celery_task_id",
        "requested_by_user_id",
        "trigger_kind",
        "scope_key",
        "source_system",
    ):
        op.drop_index(op.f(f"ix_hr_sync_runs_{column_name}"), table_name="hr_sync_runs")
    op.drop_index("ix_hr_sync_runs_lease_expires", table_name="hr_sync_runs")
    op.drop_index("ix_hr_sync_runs_snapshot_purge", table_name="hr_sync_runs")
    op.drop_index("ix_hr_sync_runs_status_created", table_name="hr_sync_runs")
    op.drop_index("ix_hr_sync_runs_latest_applied", table_name="hr_sync_runs")
    op.drop_index("uq_hr_sync_runs_live_source_scope", table_name="hr_sync_runs")
    op.drop_table("hr_sync_runs")
