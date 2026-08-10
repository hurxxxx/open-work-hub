"""add management health checkup workflow

Revision ID: e5f7a9b1c3d4
Revises: d4e8f2a6b0c3
Create Date: 2026-07-22 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e5f7a9b1c3d4"
down_revision: str | Sequence[str] | None = "d4e8f2a6b0c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JSONB_COMPAT = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "management_health_checkup_settings",
        sa.Column("id", sa.String(length=16), nullable=False),
        sa.Column("age_calc_method", sa.String(length=16), nullable=False),
        sa.Column("senior_age", sa.Integer(), nullable=False),
        sa.Column("adult_age", sa.Integer(), nullable=False),
        sa.Column("service_years_threshold", sa.Integer(), nullable=False),
        sa.Column("updated_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "age_calc_method IN ('korean','international')",
            name="ck_management_health_settings_age_method",
        ),
        sa.CheckConstraint(
            "senior_age BETWEEN 1 AND 120 AND adult_age BETWEEN 1 AND 120",
            name="ck_management_health_settings_age_bounds",
        ),
        sa.CheckConstraint(
            "service_years_threshold BETWEEN 0 AND 80",
            name="ck_management_health_settings_service_bounds",
        ),
        sa.CheckConstraint(
            "senior_age >= adult_age",
            name="ck_management_health_settings_age_order",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    settings_table = sa.table(
        "management_health_checkup_settings",
        sa.column("id", sa.String(length=16)),
        sa.column("age_calc_method", sa.String(length=16)),
        sa.column("senior_age", sa.Integer()),
        sa.column("adult_age", sa.Integer()),
        sa.column("service_years_threshold", sa.Integer()),
        sa.column("updated_by_user_id", sa.String(length=36)),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "id": "company",
                "age_calc_method": "korean",
                "senior_age": 57,
                "adult_age": 40,
                "service_years_threshold": 10,
                "updated_by_user_id": None,
                "updated_at": datetime(2026, 7, 22),
            }
        ],
    )
    op.create_table(
        "management_health_checkup_settings_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("field_key", sa.String(length=64), nullable=False),
        sa.Column("old_value", sa.String(length=64), nullable=True),
        sa.Column("new_value", sa.String(length=64), nullable=True),
        sa.Column("changed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_management_health_settings_history_created",
        "management_health_checkup_settings_history",
        ["created_at"],
    )

    op.create_table(
        "management_health_prior_uploads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("exam_year", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("content_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_schema_version", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("source_captured_at", sa.DateTime(), nullable=False),
        sa.Column("total_row_count", sa.Integer(), nullable=False),
        sa.Column("matched_count", sa.Integer(), nullable=False),
        sa.Column("dependent_excluded_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('accepted')",
            name="ck_management_health_prior_upload_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_management_health_prior_upload_year_created",
        "management_health_prior_uploads",
        ["exam_year", "uploaded_at"],
    )

    op.create_table(
        "management_health_prior_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("upload_id", sa.String(length=36), nullable=False),
        sa.Column("row_ordinal", sa.Integer(), nullable=False),
        sa.Column("sheet_name", sa.String(length=120), nullable=True),
        sa.Column("file_dept_name", sa.String(length=255), nullable=False),
        sa.Column("person_name", sa.String(length=255), nullable=False),
        sa.Column("raw_relation", sa.String(length=1000), nullable=True),
        sa.Column("relation_kind", sa.String(length=16), nullable=False),
        sa.Column("provided_employee_code", sa.String(length=120), nullable=True),
        sa.Column("match_status", sa.String(length=24), nullable=False),
        sa.Column("matched_snapshot_row_id", sa.String(length=36), nullable=True),
        sa.Column("matched_employee_code", sa.String(length=120), nullable=True),
        sa.Column("matched_employee_name", sa.String(length=255), nullable=True),
        sa.Column("matched_department_name", sa.String(length=255), nullable=True),
        sa.Column("candidate_employee_codes", JSONB_COMPAT, nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "relation_kind IN ('self','dependent')",
            name="ck_management_health_prior_row_relation",
        ),
        sa.CheckConstraint(
            "match_status IN ('matched','unmatched','ambiguous','spouse_excluded')",
            name="ck_management_health_prior_row_match",
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["management_health_prior_uploads.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "upload_id",
            "row_ordinal",
            name="uq_management_health_prior_row_order",
        ),
    )
    op.create_index(
        "ix_management_health_prior_row_upload",
        "management_health_prior_rows",
        ["upload_id"],
    )

    op.create_table(
        "management_health_decision_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("target_year", sa.Integer(), nullable=False),
        sa.Column("prior_exam_year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("publishable", sa.Boolean(), nullable=False),
        sa.Column("publish_blockers", JSONB_COMPAT, nullable=False),
        sa.Column("source_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_schema_version", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("source_captured_at", sa.DateTime(), nullable=False),
        sa.Column("source_employee_count", sa.Integer(), nullable=False),
        sa.Column("prior_upload_id", sa.String(length=36), nullable=True),
        sa.Column("settings_snapshot", JSONB_COMPAT, nullable=False),
        sa.Column("settings_hash", sa.String(length=64), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('preview','ready')",
            name="ck_management_health_decision_status",
        ),
        sa.ForeignKeyConstraint(
            ["prior_upload_id"],
            ["management_health_prior_uploads.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_management_health_decision_year_created",
        "management_health_decision_runs",
        ["target_year", "created_at"],
    )

    op.create_table(
        "management_health_decision_rows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("decision_run_id", sa.String(length=36), nullable=False),
        sa.Column("source_snapshot_row_id", sa.String(length=36), nullable=False),
        sa.Column("employee_code", sa.String(length=120), nullable=False),
        sa.Column("employee_name", sa.String(length=255), nullable=False),
        sa.Column("department_code", sa.String(length=120), nullable=False),
        sa.Column("department_name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=255), nullable=True),
        sa.Column("occupation", sa.String(length=255), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("service_years", sa.Integer(), nullable=False),
        sa.Column("is_senior", sa.Boolean(), nullable=False),
        sa.Column("is_adult", sa.Boolean(), nullable=False),
        sa.Column("is_long_service", sa.Boolean(), nullable=False),
        sa.Column("prior_year_examined", sa.Boolean(), nullable=False),
        sa.Column("is_target", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["decision_run_id"],
            ["management_health_decision_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_run_id",
            "employee_code",
            name="uq_management_health_decision_employee",
        ),
    )
    op.create_index(
        "ix_management_health_decision_row_run",
        "management_health_decision_rows",
        ["decision_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_management_health_decision_row_run",
        table_name="management_health_decision_rows",
    )
    op.drop_table("management_health_decision_rows")
    op.drop_index(
        "ix_management_health_decision_year_created",
        table_name="management_health_decision_runs",
    )
    op.drop_table("management_health_decision_runs")
    op.drop_index(
        "ix_management_health_prior_row_upload",
        table_name="management_health_prior_rows",
    )
    op.drop_table("management_health_prior_rows")
    op.drop_index(
        "ix_management_health_prior_upload_year_created",
        table_name="management_health_prior_uploads",
    )
    op.drop_table("management_health_prior_uploads")
    op.drop_index(
        "ix_management_health_settings_history_created",
        table_name="management_health_checkup_settings_history",
    )
    op.drop_table("management_health_checkup_settings_history")
    op.drop_table("management_health_checkup_settings")
