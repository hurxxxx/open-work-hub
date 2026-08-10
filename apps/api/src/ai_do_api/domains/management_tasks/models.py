from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class ManagementHealthCheckupSettings(Base):
    __tablename__ = "management_health_checkup_settings"
    __table_args__ = (
        CheckConstraint(
            "age_calc_method IN ('korean','international')",
            name="ck_management_health_settings_age_method",
        ),
        CheckConstraint(
            "senior_age BETWEEN 1 AND 120 AND adult_age BETWEEN 1 AND 120",
            name="ck_management_health_settings_age_bounds",
        ),
        CheckConstraint(
            "service_years_threshold BETWEEN 0 AND 80",
            name="ck_management_health_settings_service_bounds",
        ),
        CheckConstraint(
            "senior_age >= adult_age",
            name="ck_management_health_settings_age_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(16), primary_key=True, default="company")
    age_calc_method: Mapped[str] = mapped_column(String(16), default="korean", nullable=False)
    senior_age: Mapped[int] = mapped_column(Integer, default=57, nullable=False)
    adult_age: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    service_years_threshold: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    updated_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow_naive, onupdate=utcnow_naive, nullable=False
    )


class ManagementHealthCheckupSettingsHistory(Base):
    __tablename__ = "management_health_checkup_settings_history"
    __table_args__ = (Index("ix_management_health_settings_history_created", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_by_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class ManagementHealthPriorUpload(Base):
    __tablename__ = "management_health_prior_uploads"
    __table_args__ = (
        Index(
            "ix_management_health_prior_upload_year_created",
            "exam_year",
            "uploaded_at",
        ),
        CheckConstraint(
            "status IN ('accepted')",
            name="ck_management_health_prior_upload_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exam_year: Mapped[int] = mapped_column(Integer, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="accepted", nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_erp_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False)
    dependent_excluded_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unresolved_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class ManagementHealthPriorRow(Base):
    __tablename__ = "management_health_prior_rows"
    __table_args__ = (
        UniqueConstraint("upload_id", "row_ordinal", name="uq_management_health_prior_row_order"),
        Index("ix_management_health_prior_row_upload", "upload_id"),
        CheckConstraint(
            "relation_kind IN ('self','dependent')",
            name="ck_management_health_prior_row_relation",
        ),
        CheckConstraint(
            "match_status IN ('matched','unmatched','ambiguous','spouse_excluded')",
            name="ck_management_health_prior_row_match",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("management_health_prior_uploads.id", ondelete="RESTRICT"),
        nullable=False,
    )
    row_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_dept_name: Mapped[str] = mapped_column(String(255), nullable=False)
    person_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_relation: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    relation_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    provided_employee_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    match_status: Mapped[str] = mapped_column(String(24), nullable=False)
    matched_snapshot_row_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    matched_employee_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    matched_employee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    matched_department_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_employee_codes: Mapped[list] = mapped_column(
        JSONB_COMPAT, default=list, nullable=False
    )
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class ManagementHealthDecisionRun(Base):
    __tablename__ = "management_health_decision_runs"
    __table_args__ = (
        Index("ix_management_health_decision_year_created", "target_year", "created_at"),
        CheckConstraint(
            "status IN ('preview','ready')",
            name="ck_management_health_decision_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_year: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_exam_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    publishable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    publish_blockers: Mapped[list] = mapped_column(JSONB_COMPAT, nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_erp_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_employee_count: Mapped[int] = mapped_column(Integer, nullable=False)
    prior_upload_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("management_health_prior_uploads.id", ondelete="RESTRICT"),
        nullable=True,
    )
    settings_snapshot: Mapped[dict] = mapped_column(JSONB_COMPAT, nullable=False)
    settings_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class ManagementHealthDecisionRow(Base):
    __tablename__ = "management_health_decision_rows"
    __table_args__ = (
        UniqueConstraint(
            "decision_run_id",
            "employee_code",
            name="uq_management_health_decision_employee",
        ),
        Index("ix_management_health_decision_row_run", "decision_run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("management_health_decision_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_snapshot_row_id: Mapped[str] = mapped_column(String(36), nullable=False)
    employee_code: Mapped[str] = mapped_column(String(120), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_code: Mapped[str] = mapped_column(String(120), nullable=False)
    department_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occupation: Mapped[str] = mapped_column(String(255), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    service_years: Mapped[int] = mapped_column(Integer, nullable=False)
    is_senior: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_adult: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_long_service: Mapped[bool] = mapped_column(Boolean, nullable=False)
    prior_year_examined: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_target: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
