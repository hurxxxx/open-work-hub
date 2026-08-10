from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")
HR_SNAPSHOT_RETENTION_DAYS = 365

HR_SYNC_RUN_STATUSES = (
    "pending",
    "capturing",
    "validating",
    "rejected",
    "applying",
    "succeeded",
    "failed",
    "skipped",
    "abandoned",
)
HR_SYNC_LIVE_RUN_STATUSES = (
    "pending",
    "capturing",
    "validating",
    "applying",
)
HR_SYNC_ENTITY_KINDS = ("user", "org_unit")
HR_SYNC_CHANGE_KINDS = (
    "baseline",
    "hired",
    "rehired",
    "retired",
    "created",
    "updated",
    "activated",
    "deactivated",
    "unchanged",
    "conflict",
)
HR_SYNC_CHANGE_OUTCOMES = ("planned", "applied", "skipped", "blocked", "failed")
HR_MASTER_RUN_STATUSES = ("building", "succeeded", "failed")
HR_MASTER_RECONCILIATION_STATUSES = (
    "matched",
    "erp_only",
    "groupware_only",
    "identity_conflict",
)
HR_MASTER_SOURCE_SYSTEMS = ("erp", "groupware")
HR_MASTER_WORKFORCE_CATEGORIES = (
    "internal",
    "field",
    "external",
    "unresolved",
)
HR_MASTER_IDENTITY_RESOLUTION_KINDS = ("employee_code", "manual", "none")
HR_MANUAL_IDENTITY_LINK_STATUSES = ("active", "revoked")
HR_WORKFORCE_ASSIGNMENT_STATUSES = ("active", "revoked")
HR_WORKFORCE_ASSIGNMENT_SUBJECT_KINDS = ("erp_employee", "groupware_identity")
HR_WORKFORCE_CATEGORY_RESOLUTION_KINDS = ("inferred", "manual")


def _sql_in_clause(column_name: str, values: tuple[str, ...]) -> str:
    quoted_values = ",".join(f"'{value}'" for value in values)
    return f"{column_name} IN ({quoted_values})"


def default_hr_snapshot_purge_after() -> datetime:
    return utcnow_naive() + timedelta(days=HR_SNAPSHOT_RETENTION_DAYS)


class HrSyncRun(Base):
    """One durable HR source capture, validation, and optional apply execution."""

    __tablename__ = "hr_sync_runs"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", HR_SYNC_RUN_STATUSES),
            name="ck_hr_sync_runs_status",
        ),
        CheckConstraint("attempts >= 0", name="ck_hr_sync_runs_attempts_nonnegative"),
        CheckConstraint(
            "org_row_count IS NULL OR org_row_count >= 0",
            name="ck_hr_sync_runs_org_row_count_nonnegative",
        ),
        CheckConstraint(
            "user_row_count IS NULL OR user_row_count >= 0",
            name="ck_hr_sync_runs_user_row_count_nonnegative",
        ),
        CheckConstraint(
            "active_user_row_count IS NULL OR active_user_row_count >= 0",
            name="ck_hr_sync_runs_active_user_row_count_nonnegative",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR applied_at IS NOT NULL",
            name="ck_hr_sync_runs_succeeded_applied_at",
        ),
        UniqueConstraint(
            "source_system",
            "scope_key",
            "idempotency_key",
            name="uq_hr_sync_runs_source_scope_idempotency",
        ),
        Index(
            "uq_hr_sync_runs_live_source_scope",
            "source_system",
            "scope_key",
            unique=True,
            postgresql_where=text(_sql_in_clause("status", HR_SYNC_LIVE_RUN_STATUSES)),
            sqlite_where=text(_sql_in_clause("status", HR_SYNC_LIVE_RUN_STATUSES)),
        ),
        Index(
            "ix_hr_sync_runs_latest_applied",
            "source_system",
            "scope_key",
            "status",
            "applied_at",
            "id",
        ),
        Index(
            "ix_hr_sync_runs_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_hr_sync_runs_snapshot_purge",
            "snapshot_purge_after",
            "snapshots_purged_at",
        ),
        Index(
            "ix_hr_sync_runs_lease_expires",
            "status",
            "lease_expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scope_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    trigger_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    comparison_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("hr_sync_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    blocked_by_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("hr_sync_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
        index=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canonicalization_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    org_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_user_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB_COMPAT,
        nullable=True,
    )
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    error_phase: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    snapshot_purge_after: Mapped[datetime] = mapped_column(
        DateTime,
        default=default_hr_snapshot_purge_after,
        nullable=False,
        index=True,
    )
    snapshots_purged_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class HrSyncUserSnapshotRow(Base):
    """An immutable raw employee/user row observed during an HR source run."""

    __tablename__ = "hr_user_snapshot_rows"
    __table_args__ = (
        CheckConstraint(
            "source_row_no >= 0",
            name="ck_hr_user_snapshot_rows_source_row_nonnegative",
        ),
        UniqueConstraint(
            "run_id",
            "source_row_no",
            name="uq_hr_user_snapshot_rows_run_source_row",
        ),
        Index(
            "ix_hr_user_snapshot_rows_run_identity",
            "run_id",
            "domain_num",
            "user_num",
        ),
        Index(
            "ix_hr_user_snapshot_rows_identity_captured",
            "domain_num",
            "user_num",
            "created_at",
        ),
        Index(
            "ix_hr_user_snapshot_rows_run_hash",
            "run_id",
            "row_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    domain_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_identity: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB_COMPAT, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )


class HrSyncOrgSnapshotRow(Base):
    """An immutable raw organization row observed during an HR sync run."""

    __tablename__ = "hr_org_snapshot_rows"
    __table_args__ = (
        CheckConstraint(
            "source_row_no >= 0",
            name="ck_hr_org_snapshot_rows_source_row_nonnegative",
        ),
        UniqueConstraint(
            "run_id",
            "source_row_no",
            name="uq_hr_org_snapshot_rows_run_source_row",
        ),
        Index(
            "ix_hr_org_snapshot_rows_run_identity",
            "run_id",
            "domain_num",
            "org_code",
        ),
        Index(
            "ix_hr_org_snapshot_rows_identity_captured",
            "domain_num",
            "org_code",
            "created_at",
        ),
        Index(
            "ix_hr_org_snapshot_rows_run_hash",
            "run_id",
            "row_hash",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    domain_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_identity: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB_COMPAT, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )


class HrSyncChange(Base):
    """A durable row-level comparison decision and its apply outcome."""

    __tablename__ = "hr_sync_changes"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("entity_kind", HR_SYNC_ENTITY_KINDS),
            name="ck_hr_sync_changes_entity_kind",
        ),
        CheckConstraint(
            _sql_in_clause("change_kind", HR_SYNC_CHANGE_KINDS),
            name="ck_hr_sync_changes_change_kind",
        ),
        CheckConstraint(
            _sql_in_clause("outcome", HR_SYNC_CHANGE_OUTCOMES),
            name="ck_hr_sync_changes_outcome",
        ),
        UniqueConstraint(
            "run_id",
            "entity_kind",
            "source_identity",
            name="uq_hr_sync_changes_run_entity_identity",
        ),
        Index(
            "ix_hr_sync_changes_run_kind_outcome",
            "run_id",
            "change_kind",
            "outcome",
        ),
        Index(
            "ix_hr_sync_changes_entity_identity_created",
            "entity_kind",
            "source_identity",
            "created_at",
        ),
        Index(
            "ix_hr_sync_changes_target_created",
            "target_entity_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_sync_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    source_identity: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    domain_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    org_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    change_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="planned",
        server_default=text("'planned'"),
        index=True,
    )
    before_snapshot_row_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    after_snapshot_row_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    target_entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    changed_fields: Mapped[list[str] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class HrMasterRun(Base):
    """One immutable, versioned projection over exact ERP and groupware snapshots."""

    __tablename__ = "hr_master_runs"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", HR_MASTER_RUN_STATUSES),
            name="ck_hr_master_runs_status",
        ),
        CheckConstraint(
            "person_row_count >= 0",
            name="ck_hr_master_runs_person_count_nonnegative",
        ),
        CheckConstraint(
            "group_row_count >= 0",
            name="ck_hr_master_runs_group_count_nonnegative",
        ),
        CheckConstraint(
            "conflict_row_count >= 0",
            name="ck_hr_master_runs_conflict_count_nonnegative",
        ),
        CheckConstraint(
            "external_row_count >= 0",
            name="ck_hr_master_runs_external_count_nonnegative",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR (checksum IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_hr_master_runs_succeeded_complete",
        ),
        Index(
            "uq_hr_master_runs_succeeded_source_pair_schema",
            "erp_run_id",
            "groupware_run_id",
            "schema_version",
            "identity_resolution_revision",
            unique=True,
            postgresql_where=text("status = 'succeeded'"),
            sqlite_where=text("status = 'succeeded'"),
        ),
        Index(
            "ix_hr_master_runs_latest_succeeded",
            "status",
            "completed_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="building",
        server_default=text("'building'"),
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    erp_run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_sync_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    groupware_run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_sync_runs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    identity_resolution_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    identity_resolution_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        server_default=text("'4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945'"),
    )
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    erp_projection_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    person_row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    group_row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    conflict_row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    external_row_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    rows_purged_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class HrMasterPersonRow(Base):
    """A canonical person in one succeeded HR master version."""

    __tablename__ = "hr_master_person_rows"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("reconciliation_status", HR_MASTER_RECONCILIATION_STATUSES),
            name="ck_hr_master_person_rows_reconciliation_status",
        ),
        CheckConstraint(
            "group_source IS NULL OR " + _sql_in_clause("group_source", HR_MASTER_SOURCE_SYSTEMS),
            name="ck_hr_master_person_rows_group_source",
        ),
        CheckConstraint(
            _sql_in_clause(
                "identity_resolution_kind",
                HR_MASTER_IDENTITY_RESOLUTION_KINDS,
            ),
            name="ck_hr_master_person_rows_identity_resolution_kind",
        ),
        CheckConstraint(
            _sql_in_clause(
                "workforce_category_resolution_kind",
                HR_WORKFORCE_CATEGORY_RESOLUTION_KINDS,
            ),
            name="ck_hr_master_person_rows_workforce_category_resolution_kind",
        ),
        CheckConstraint(
            "(workforce_category_resolution_kind = 'inferred' "
            "AND workforce_assignment_id IS NULL "
            "AND workforce_category = inferred_workforce_category) "
            "OR (workforce_category_resolution_kind = 'manual' "
            "AND workforce_assignment_id IS NOT NULL)",
            name="ck_hr_master_person_rows_workforce_resolution",
        ),
        CheckConstraint(
            "employee_code = upper(trim(employee_code)) AND length(employee_code) > 0",
            name="ck_hr_master_person_rows_normalized_employee_code",
        ),
        UniqueConstraint(
            "master_run_id",
            "employee_code",
            name="uq_hr_master_person_rows_run_employee_code",
        ),
        Index(
            "ix_hr_master_person_rows_run_status_code",
            "master_run_id",
            "reconciliation_status",
            "employee_code",
        ),
        Index(
            "ix_hr_master_person_rows_run_group",
            "master_run_id",
            "group_source",
            "group_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    master_run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_master_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    position: Mapped[str | None] = mapped_column(String(160), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(160), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    login_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    group_source: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    group_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reconciliation_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    inferred_workforce_category: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("hr_workforce_categories.code", ondelete="RESTRICT"),
        nullable=False,
        default="unresolved",
        server_default=text("'unresolved'"),
        index=True,
    )
    workforce_category: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("hr_workforce_categories.code", ondelete="RESTRICT"),
        nullable=False,
        default="unresolved",
        server_default=text("'unresolved'"),
        index=True,
    )
    workforce_category_resolution_kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="inferred",
        server_default=text("'inferred'"),
        index=True,
    )
    workforce_assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("hr_workforce_category_assignments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    identity_resolution_kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="none",
        server_default=text("'none'"),
        index=True,
    )
    has_identity_conflict: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )
    # These IDs are immutable provenance, not live relationships. Source snapshot
    # retention may delete the referenced rows while the master remains current.
    erp_snapshot_row_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    groupware_snapshot_row_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    groupware_source_identity: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    manual_identity_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("hr_manual_identity_links.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class HrMasterExternalPersonRow(Base):
    """A groupware external/overseas person keyed by stable source identity."""

    __tablename__ = "hr_master_external_person_rows"
    __table_args__ = (
        CheckConstraint(
            "length(trim(groupware_source_identity)) > 0",
            name="ck_hr_master_external_rows_groupware_identity",
        ),
        CheckConstraint(
            "employee_code IS NULL OR "
            "(employee_code = upper(trim(employee_code)) AND length(employee_code) > 0)",
            name="ck_hr_master_external_rows_employee_code",
        ),
        CheckConstraint(
            _sql_in_clause(
                "workforce_category_resolution_kind",
                HR_WORKFORCE_CATEGORY_RESOLUTION_KINDS,
            ),
            name="ck_hr_master_external_rows_workforce_category_resolution_kind",
        ),
        CheckConstraint(
            "(workforce_category_resolution_kind = 'inferred' "
            "AND workforce_assignment_id IS NULL "
            "AND workforce_category = inferred_workforce_category) "
            "OR (workforce_category_resolution_kind = 'manual' "
            "AND workforce_assignment_id IS NOT NULL)",
            name="ck_hr_master_external_rows_workforce_resolution",
        ),
        UniqueConstraint(
            "master_run_id",
            "groupware_source_identity",
            name="uq_hr_master_external_rows_run_identity",
        ),
        Index(
            "ix_hr_master_external_rows_run_code",
            "master_run_id",
            "employee_code",
        ),
        Index(
            "ix_hr_master_external_rows_run_group",
            "master_run_id",
            "group_code",
        ),
        Index(
            "ix_hr_master_external_rows_category_resolution",
            "workforce_category_resolution_kind",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    master_run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_master_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    groupware_source_identity: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
        index=True,
    )
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    position: Mapped[str | None] = mapped_column(String(160), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    login_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    group_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    inferred_workforce_category: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("hr_workforce_categories.code", ondelete="RESTRICT"),
        nullable=False,
        default="external",
        server_default=text("'external'"),
        index=True,
    )
    workforce_category: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("hr_workforce_categories.code", ondelete="RESTRICT"),
        nullable=False,
        default="external",
        server_default=text("'external'"),
        index=True,
    )
    workforce_category_resolution_kind: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="inferred",
        server_default=text("'inferred'"),
    )
    workforce_assignment_id: Mapped[str | None] = mapped_column(
        ForeignKey("hr_workforce_category_assignments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    groupware_snapshot_row_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class HrMasterGroupRow(Base):
    """A source-qualified group available in one HR master version."""

    __tablename__ = "hr_master_group_rows"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("source_system", HR_MASTER_SOURCE_SYSTEMS),
            name="ck_hr_master_group_rows_source_system",
        ),
        UniqueConstraint(
            "master_run_id",
            "source_system",
            "source_code",
            name="uq_hr_master_group_rows_run_source_code",
        ),
        Index(
            "ix_hr_master_group_rows_run_source_name",
            "master_run_id",
            "source_system",
            "name",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    master_run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_master_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_snapshot_row_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class HrMasterConflictRow(Base):
    """A quarantined source row that cannot safely become a master person."""

    __tablename__ = "hr_master_conflict_rows"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("source_system", HR_MASTER_SOURCE_SYSTEMS),
            name="ck_hr_master_conflict_rows_source_system",
        ),
        Index(
            "ix_hr_master_conflict_rows_run_reason",
            "master_run_id",
            "reason_code",
        ),
        Index(
            "ix_hr_master_conflict_rows_run_employee_code",
            "master_run_id",
            "normalized_employee_code",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    master_run_id: Mapped[str] = mapped_column(
        ForeignKey("hr_master_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_system: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    normalized_employee_code: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        index=True,
    )
    source_snapshot_row_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB_COMPAT, nullable=True)
    workforce_category: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("hr_workforce_categories.code", ondelete="RESTRICT"),
        nullable=False,
        default="unresolved",
        server_default=text("'unresolved'"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class HrIdentityResolutionState(Base):
    """Singleton revision fence for manual integrated-HR projection decisions."""

    __tablename__ = "hr_identity_resolution_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_hr_identity_resolution_state_singleton"),
        CheckConstraint(
            "revision >= 0",
            name="ck_hr_identity_resolution_state_revision_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
    )


class HrWorkforceCategory(Base):
    """Administrator-managed workforce category definition."""

    __tablename__ = "hr_workforce_categories"
    __table_args__ = (
        CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_hr_workforce_categories_code",
        ),
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_hr_workforce_categories_name",
        ),
        CheckConstraint(
            "sort_order >= 0",
            name="ck_hr_workforce_categories_sort_order_nonnegative",
        ),
        Index(
            "ix_hr_workforce_categories_active_sort",
            "is_active",
            "sort_order",
            "code",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default=text("100"),
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )


class HrWorkforceCategoryAssignment(Base):
    """Auditable manual category override for one stable HR identity."""

    __tablename__ = "hr_workforce_category_assignments"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("subject_kind", HR_WORKFORCE_ASSIGNMENT_SUBJECT_KINDS),
            name="ck_hr_workforce_assignments_subject_kind",
        ),
        CheckConstraint(
            _sql_in_clause("status", HR_WORKFORCE_ASSIGNMENT_STATUSES),
            name="ck_hr_workforce_assignments_status",
        ),
        CheckConstraint(
            "length(trim(subject_key)) > 0",
            name="ck_hr_workforce_assignments_subject_key",
        ),
        CheckConstraint(
            "activated_revision >= 0",
            name="ck_hr_workforce_assignments_activated_revision",
        ),
        CheckConstraint(
            "revoked_revision IS NULL OR revoked_revision >= activated_revision",
            name="ck_hr_workforce_assignments_revoked_revision",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_revision IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL "
            "AND revoked_revision IS NOT NULL)",
            name="ck_hr_workforce_assignments_revocation",
        ),
        Index(
            "uq_hr_workforce_assignments_active_subject",
            "subject_kind",
            "subject_key",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    category_code: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("hr_workforce_categories.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        index=True,
    )
    activated_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )
    revoked_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class HrManualIdentityLink(Base):
    """Auditable manual link from one stable groupware identity to one ERP employee."""

    __tablename__ = "hr_manual_identity_links"
    __table_args__ = (
        CheckConstraint(
            _sql_in_clause("status", HR_MANUAL_IDENTITY_LINK_STATUSES),
            name="ck_hr_manual_identity_links_status",
        ),
        CheckConstraint(
            "length(trim(groupware_source_identity)) > 0",
            name="ck_hr_manual_identity_links_groupware_identity",
        ),
        CheckConstraint(
            "erp_employee_code = upper(trim(erp_employee_code)) AND length(erp_employee_code) > 0",
            name="ck_hr_manual_identity_links_erp_code",
        ),
        CheckConstraint(
            "activated_revision >= 0",
            name="ck_hr_manual_identity_links_activated_revision",
        ),
        CheckConstraint(
            "revoked_revision IS NULL OR revoked_revision >= activated_revision",
            name="ck_hr_manual_identity_links_revoked_revision",
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL AND revoked_revision IS NULL) "
            "OR (status = 'revoked' AND revoked_at IS NOT NULL "
            "AND revoked_revision IS NOT NULL)",
            name="ck_hr_manual_identity_links_revocation",
        ),
        Index(
            "uq_hr_manual_identity_links_active_groupware",
            "groupware_source_identity",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
        Index(
            "uq_hr_manual_identity_links_active_erp",
            "erp_employee_code",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    groupware_source_identity: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
        index=True,
    )
    groupware_employee_code: Mapped[str] = mapped_column(String(40), nullable=False)
    erp_employee_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    matched_name: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="active",
        server_default=text("'active'"),
        index=True,
    )
    activated_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        nullable=False,
        index=True,
    )
    revoked_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revoked_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


__all__ = [
    "HR_MASTER_RECONCILIATION_STATUSES",
    "HR_MASTER_IDENTITY_RESOLUTION_KINDS",
    "HR_MASTER_RUN_STATUSES",
    "HR_MASTER_SOURCE_SYSTEMS",
    "HR_MASTER_WORKFORCE_CATEGORIES",
    "HR_MANUAL_IDENTITY_LINK_STATUSES",
    "HR_WORKFORCE_ASSIGNMENT_STATUSES",
    "HR_WORKFORCE_ASSIGNMENT_SUBJECT_KINDS",
    "HR_WORKFORCE_CATEGORY_RESOLUTION_KINDS",
    "HR_SNAPSHOT_RETENTION_DAYS",
    "HR_SYNC_CHANGE_KINDS",
    "HR_SYNC_CHANGE_OUTCOMES",
    "HR_SYNC_ENTITY_KINDS",
    "HR_SYNC_LIVE_RUN_STATUSES",
    "HR_SYNC_RUN_STATUSES",
    "HrMasterConflictRow",
    "HrMasterExternalPersonRow",
    "HrMasterGroupRow",
    "HrMasterPersonRow",
    "HrMasterRun",
    "HrIdentityResolutionState",
    "HrManualIdentityLink",
    "HrWorkforceCategory",
    "HrWorkforceCategoryAssignment",
    "HrSyncOrgSnapshotRow",
    "HrSyncChange",
    "HrSyncRun",
    "HrSyncUserSnapshotRow",
    "default_hr_snapshot_purge_after",
]
