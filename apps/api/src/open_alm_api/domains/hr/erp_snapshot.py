from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import AuditLog
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.hr.history import (
    HR_CANONICALIZATION_VERSION,
    HR_SYNC_TERMINAL_RUN_STATUSES,
    begin_hr_sync_run,
    canonical_payload_hash,
    fail_hr_sync_run,
    list_hr_sync_runs,
    load_latest_succeeded_hr_sync_run,
    utcnow_naive,
)
from open_alm_api.domains.hr.models import (
    HR_SNAPSHOT_RETENTION_DAYS,
    HrSyncOrgSnapshotRow,
    HrSyncRun,
    HrSyncUserSnapshotRow,
)


ERP_SOURCE_SYSTEM = "erp"
ERP_EMPLOYEE_SCOPE_KEY = "erp:dbo.UV_H_EMPLOYEE_LIST_DWC"
ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION = "erp-employee-view-v1"
ERP_EMPLOYEE_SCHEMA_VERSION = "erp-employee-view-v2"
ERP_EMPLOYEE_TYPED_READER_SCHEMA_VERSIONS = frozenset(
    {
        ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION,
        ERP_EMPLOYEE_SCHEMA_VERSION,
    }
)
ERP_EMPLOYEE_SNAPSHOT_AUDIT_ACTION = "hr.erp.snapshot"
ERP_DEPARTMENT_COLUMNS = (
    "DEPT_CD",
    "DEPT_NM",
)
ERP_EMPLOYEE_COLUMNS = (
    "EMP_NO",
    "NAME",
    "NAT_NM",
    "BIRTHDAY",
    "SO_LU",
    "DEPT_NM",
    "DEPT_CD",
    "OCPT_NM",
    "INTERNAL_CD",
    "ROLL_PSTN",
    "ROLL_PSTN_NM",
    "FUNC_NM",
    "PAY_GRD1",
    "PAY_GRD1_NM",
    "PAY_GRD2",
    "ENTR_DT",
    "GROUP_ENTR_DT",
    "ORDER_CHANGE_DT",
    "PROMOTE_DT",
    "PLAN_PROMITE_DT",
    "RECENT_PROMOTE_DT",
    "EMAIL_ADDR",
    "HAND_TEL_NO",
)

_MASS_MISSING_MINIMUM = 10
_MASS_MISSING_RATIO = 0.20


class AcceptedErpEmployeeSnapshotError(RuntimeError):
    """A succeeded ERP run cannot be projected safely for an HR consumer.

    ``code`` is intentionally aggregate-only so callers can map the failure to a
    localized response without putting employee data in logs or API payloads.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AcceptedErpEmployee:
    snapshot_row_id: str
    employee_code: str
    name: str
    department_code: str
    department_name: str
    position: str | None
    occupation: str
    birth_date: date
    hire_date: date
    phone_number: str | None = None


@dataclass(frozen=True)
class AcceptedErpEmployeeSnapshot:
    run_id: str
    schema_version: str
    captured_at: datetime
    snapshot_hash: str
    employees: tuple[AcceptedErpEmployee, ...]


@dataclass(frozen=True)
class AcceptedErpEmployeeSnapshotMetadata:
    run_id: str
    schema_version: str
    captured_at: datetime
    snapshot_hash: str
    employee_count: int


def _clean_employee_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def _clean_department_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().upper()
    return cleaned or None


def _clean_department_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _derive_group_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility seam for callers that have not yet split the GROUP BY query."""

    distinct_pairs = {
        (
            _clean_department_code(row.get("DEPT_CD")),
            _clean_department_name(row.get("DEPT_NM")),
        )
        for row in rows
    }
    return [
        {"DEPT_CD": code, "DEPT_NM": name}
        for code, name in sorted(
            distinct_pairs,
            key=lambda pair: (pair[0] or "", pair[1] or ""),
        )
    ]


def list_erp_hr_snapshot_runs(db: Session, *, limit: int = 50) -> list[HrSyncRun]:
    return list_hr_sync_runs(
        db,
        source_system=ERP_SOURCE_SYSTEM,
        scope_key=ERP_EMPLOYEE_SCOPE_KEY,
        limit=limit,
    )


def load_latest_erp_hr_snapshot_run(
    db: Session,
    *,
    before_run_id: str | None = None,
) -> HrSyncRun | None:
    return load_latest_succeeded_hr_sync_run(
        db,
        source_system=ERP_SOURCE_SYSTEM,
        scope_key=ERP_EMPLOYEE_SCOPE_KEY,
        before_run_id=before_run_id,
    )


def _required_projection_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise AcceptedErpEmployeeSnapshotError("invalid_required_value")
    projected = value.strip()
    if not projected:
        raise AcceptedErpEmployeeSnapshotError("invalid_required_value")
    return projected


def _optional_projection_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AcceptedErpEmployeeSnapshotError("snapshot_schema_mismatch")
    projected = value.strip()
    return projected or None


def _projection_date(payload: Mapping[str, Any], key: str) -> date:
    value = _required_projection_text(payload, key)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as error:
        raise AcceptedErpEmployeeSnapshotError("invalid_date_value") from error


def _load_latest_accepted_erp_employee_snapshot_metadata(
    db: Session,
) -> tuple[HrSyncRun, AcceptedErpEmployeeSnapshotMetadata] | None:
    run = load_latest_erp_hr_snapshot_run(db)
    if run is None:
        return None
    if run.schema_version not in ERP_EMPLOYEE_TYPED_READER_SCHEMA_VERSIONS:
        raise AcceptedErpEmployeeSnapshotError("unsupported_schema_version")
    if run.snapshots_purged_at is not None:
        raise AcceptedErpEmployeeSnapshotError("snapshot_rows_unavailable")
    if run.captured_at is None or not run.user_snapshot_hash or run.user_row_count is None:
        raise AcceptedErpEmployeeSnapshotError("snapshot_metadata_incomplete")

    return run, AcceptedErpEmployeeSnapshotMetadata(
        run_id=run.id,
        schema_version=run.schema_version,
        captured_at=run.captured_at,
        snapshot_hash=run.user_snapshot_hash,
        employee_count=run.user_row_count,
    )


def load_latest_accepted_erp_employee_snapshot_metadata(
    db: Session,
) -> AcceptedErpEmployeeSnapshotMetadata | None:
    """Return accepted ERP run metadata without materializing raw employee rows."""

    accepted = _load_latest_accepted_erp_employee_snapshot_metadata(db)
    return accepted[1] if accepted is not None else None


def load_latest_accepted_erp_employee_snapshot(
    db: Session,
) -> AcceptedErpEmployeeSnapshot | None:
    """Project the latest accepted ERP raw snapshot into a typed read model.

    This is the only supported seam for a domain that needs the accepted ERP
    employee roster without creating an HR master. The raw snapshot stays
    immutable and this function performs no platform-user or organization write.
    """

    accepted = _load_latest_accepted_erp_employee_snapshot_metadata(db)
    if accepted is None:
        return None
    run, metadata = accepted

    rows = list(
        db.scalars(
            select(HrSyncUserSnapshotRow)
            .where(HrSyncUserSnapshotRow.run_id == run.id)
            .order_by(HrSyncUserSnapshotRow.source_row_no)
        ).all()
    )
    if len(rows) != metadata.employee_count:
        raise AcceptedErpEmployeeSnapshotError("snapshot_row_count_mismatch")

    employees: list[AcceptedErpEmployee] = []
    employee_codes: set[str] = set()
    for row in rows:
        payload = row.raw_payload
        if set(payload) != set(ERP_EMPLOYEE_COLUMNS):
            raise AcceptedErpEmployeeSnapshotError("snapshot_schema_mismatch")
        if any(value is not None and not isinstance(value, str) for value in payload.values()):
            raise AcceptedErpEmployeeSnapshotError("snapshot_schema_mismatch")
        employee_code = _required_projection_text(payload, "EMP_NO").upper()
        if employee_code in employee_codes:
            raise AcceptedErpEmployeeSnapshotError("duplicate_employee_code")
        employee_codes.add(employee_code)
        employees.append(
            AcceptedErpEmployee(
                snapshot_row_id=row.id,
                employee_code=employee_code,
                name=_required_projection_text(payload, "NAME"),
                department_code=_required_projection_text(payload, "DEPT_CD"),
                department_name=_required_projection_text(payload, "DEPT_NM"),
                position=_optional_projection_text(payload, "ROLL_PSTN_NM"),
                occupation=_required_projection_text(payload, "OCPT_NM"),
                birth_date=_projection_date(payload, "BIRTHDAY"),
                hire_date=_projection_date(payload, "ENTR_DT"),
                phone_number=_optional_projection_text(payload, "HAND_TEL_NO"),
            )
        )

    return AcceptedErpEmployeeSnapshot(
        run_id=metadata.run_id,
        schema_version=metadata.schema_version,
        captured_at=metadata.captured_at,
        snapshot_hash=metadata.snapshot_hash,
        employees=tuple(employees),
    )


def begin_erp_hr_snapshot_run(
    db: Session,
    *,
    idempotency_key: str | None,
    trigger_kind: str = "scheduled",
    requested_by_user_id: str | None = None,
    captured_at: datetime | None = None,
) -> HrSyncRun:
    return begin_hr_sync_run(
        db,
        source_system=ERP_SOURCE_SYSTEM,
        scope_key=ERP_EMPLOYEE_SCOPE_KEY,
        schema_version=ERP_EMPLOYEE_SCHEMA_VERSION,
        canonicalization_version=HR_CANONICALIZATION_VERSION,
        idempotency_key=idempotency_key,
        trigger_kind=trigger_kind,
        requested_by_user_id=requested_by_user_id,
        synced_at=captured_at,
    )


def _capture_erp_rows(
    db: Session,
    *,
    run: HrSyncRun,
    rows: list[Mapping[str, Any]],
    group_rows: list[Mapping[str, Any]],
    captured_at: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payloads = [dict(row) for row in rows]
    group_payloads = [dict(row) for row in group_rows]
    for source_row_no, raw_payload in enumerate(payloads):
        employee_code = _clean_employee_code(raw_payload.get("EMP_NO"))
        db.add(
            HrSyncUserSnapshotRow(
                id=new_id(),
                run_id=run.id,
                source_row_no=source_row_no,
                domain_num=None,
                user_num=None,
                source_identity=employee_code,
                employee_code=employee_code,
                raw_payload=raw_payload,
                row_hash=canonical_payload_hash(raw_payload),
                created_at=captured_at,
            )
        )
    for source_row_no, raw_payload in enumerate(group_payloads):
        department_code = _clean_department_code(raw_payload.get("DEPT_CD"))
        db.add(
            HrSyncOrgSnapshotRow(
                id=new_id(),
                run_id=run.id,
                source_row_no=source_row_no,
                domain_num=None,
                org_code=department_code,
                source_identity=department_code,
                raw_payload=raw_payload,
                row_hash=canonical_payload_hash(raw_payload),
                created_at=captured_at,
            )
        )

    run.status = "validating"
    run.org_row_count = len(group_payloads)
    run.user_row_count = len(payloads)
    run.active_user_row_count = None
    run.org_snapshot_hash = canonical_payload_hash(group_payloads)
    run.user_snapshot_hash = canonical_payload_hash(payloads)
    run.captured_at = captured_at
    run.updated_at = captured_at
    db.commit()
    return payloads, group_payloads


def _validate_erp_rows(
    *,
    rows: list[dict[str, Any]],
    group_rows: list[dict[str, Any]],
    baseline_rows: list[HrSyncUserSnapshotRow],
    allow_large_changes: bool,
) -> list[dict[str, object]]:
    errors: list[dict[str, object]] = []
    if not rows:
        return [{"code": "empty_snapshot"}]

    required_columns = set(ERP_EMPLOYEE_COLUMNS)
    schema_error_rows = [
        {
            "source_row": index,
            "missing_columns": sorted(required_columns - set(row)),
        }
        for index, row in enumerate(rows)
        if required_columns - set(row)
    ]
    if schema_error_rows:
        errors.append(
            {
                "code": "missing_required_columns",
                "rows": schema_error_rows[:20],
                "affected_row_count": len(schema_error_rows),
            }
        )

    value_type_error_rows = [
        {
            "source_row": index,
            "columns": sorted(
                column
                for column in required_columns.intersection(row)
                if row[column] is not None and not isinstance(row[column], str)
            ),
        }
        for index, row in enumerate(rows)
        if any(
            row[column] is not None and not isinstance(row[column], str)
            for column in required_columns.intersection(row)
        )
    ]
    if value_type_error_rows:
        errors.append(
            {
                "code": "invalid_employee_column_types",
                "rows": value_type_error_rows[:20],
                "affected_row_count": len(value_type_error_rows),
            }
        )

    required_group_columns = set(ERP_DEPARTMENT_COLUMNS)
    group_schema_error_rows = [
        {
            "source_row": index,
            "missing_columns": sorted(required_group_columns - set(row)),
        }
        for index, row in enumerate(group_rows)
        if required_group_columns - set(row)
    ]
    if group_schema_error_rows:
        errors.append(
            {
                "code": "missing_required_group_columns",
                "rows": group_schema_error_rows[:20],
                "affected_row_count": len(group_schema_error_rows),
            }
        )

    group_value_type_error_rows = [
        {
            "source_row": index,
            "columns": sorted(
                column
                for column in required_group_columns.intersection(row)
                if row[column] is not None and not isinstance(row[column], str)
            ),
        }
        for index, row in enumerate(group_rows)
        if any(
            row[column] is not None and not isinstance(row[column], str)
            for column in required_group_columns.intersection(row)
        )
    ]
    if group_value_type_error_rows:
        errors.append(
            {
                "code": "invalid_department_group_column_types",
                "rows": group_value_type_error_rows[:20],
                "affected_row_count": len(group_value_type_error_rows),
            }
        )

    group_names_by_code: dict[str, set[str]] = defaultdict(set)
    invalid_group_rows: list[int] = []
    normalized_group_pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(group_rows):
        department_code = _clean_department_code(row.get("DEPT_CD"))
        department_name = _clean_department_name(row.get("DEPT_NM"))
        if department_code is None or department_name is None:
            invalid_group_rows.append(index)
            continue
        group_names_by_code[department_code].add(department_name)
        normalized_group_pairs.add((department_code, department_name))
    if invalid_group_rows:
        errors.append(
            {
                "code": "invalid_department_group",
                "source_rows": invalid_group_rows[:20],
                "affected_row_count": len(invalid_group_rows),
            }
        )
    conflicting_group_codes = sorted(
        code for code, names in group_names_by_code.items() if len(names) > 1
    )
    if conflicting_group_codes:
        errors.append(
            {
                "code": "conflicting_department_group_name",
                "department_codes": conflicting_group_codes[:20],
                "affected_code_count": len(conflicting_group_codes),
            }
        )

    employee_rows: dict[str, list[int]] = defaultdict(list)
    missing_employee_rows: list[int] = []
    missing_group_references: list[int] = []
    for index, row in enumerate(rows):
        employee_code = _clean_employee_code(row.get("EMP_NO"))
        if employee_code is None:
            missing_employee_rows.append(index)
        else:
            employee_rows[employee_code].append(index)
        department_pair = (
            _clean_department_code(row.get("DEPT_CD")),
            _clean_department_name(row.get("DEPT_NM")),
        )
        if department_pair not in normalized_group_pairs:
            missing_group_references.append(index)
    if missing_employee_rows:
        errors.append(
            {
                "code": "missing_employee_code",
                "source_rows": missing_employee_rows[:20],
                "affected_row_count": len(missing_employee_rows),
            }
        )
    duplicate_groups = [indices for indices in employee_rows.values() if len(indices) > 1]
    if duplicate_groups:
        errors.append(
            {
                "code": "duplicate_employee_code",
                "source_row_groups": duplicate_groups[:20],
                "affected_code_count": len(duplicate_groups),
            }
        )
    if missing_group_references:
        errors.append(
            {
                "code": "missing_employee_department_group",
                "source_rows": missing_group_references[:20],
                "affected_row_count": len(missing_group_references),
            }
        )

    if baseline_rows:
        previous_codes = {
            row.employee_code.strip().upper()
            for row in baseline_rows
            if row.employee_code is not None and row.employee_code.strip()
        }
        current_codes = set(employee_rows)
        missing_count = len(previous_codes - current_codes)
        missing_ratio = missing_count / len(previous_codes) if previous_codes else 0.0
        if (
            not allow_large_changes
            and missing_count >= _MASS_MISSING_MINIMUM
            and missing_ratio > _MASS_MISSING_RATIO
        ):
            errors.append(
                {
                    "code": "unsafe_employee_volume_drop",
                    "missing_count": missing_count,
                    "previous_count": len(previous_codes),
                    "missing_ratio": round(missing_ratio, 4),
                }
            )
    return errors


def process_erp_hr_snapshot_run(
    db: Session,
    *,
    run_id: str,
    rows: list[Mapping[str, Any]],
    group_rows: list[Mapping[str, Any]] | None = None,
    captured_at: datetime | None = None,
    allow_large_changes: bool = False,
) -> HrSyncRun:
    now = captured_at or utcnow_naive()
    run = db.get(HrSyncRun, run_id)
    if run is None:
        raise ValueError(f"Unknown HR sync run: {run_id}")
    if run.source_system != ERP_SOURCE_SYSTEM or run.scope_key != ERP_EMPLOYEE_SCOPE_KEY:
        raise ValueError(f"HR sync run is not an ERP employee snapshot: {run_id}")
    if run.status in HR_SYNC_TERMINAL_RUN_STATUSES:
        return run

    if run.captured_at is None:
        run.status = "capturing"
        run.updated_at = now
        db.commit()
        effective_group_rows = (
            list(group_rows) if group_rows is not None else _derive_group_rows(rows)
        )
        payloads, group_payloads = _capture_erp_rows(
            db,
            run=run,
            rows=rows,
            group_rows=effective_group_rows,
            captured_at=now,
        )
    else:
        payloads = [
            dict(row.raw_payload)
            for row in db.scalars(
                select(HrSyncUserSnapshotRow)
                .where(HrSyncUserSnapshotRow.run_id == run.id)
                .order_by(HrSyncUserSnapshotRow.source_row_no)
            ).all()
        ]
        group_payloads = [
            dict(row.raw_payload)
            for row in db.scalars(
                select(HrSyncOrgSnapshotRow)
                .where(HrSyncOrgSnapshotRow.run_id == run.id)
                .order_by(HrSyncOrgSnapshotRow.source_row_no)
            ).all()
        ]

    baseline = load_latest_erp_hr_snapshot_run(db, before_run_id=run.id)
    baseline_rows = (
        list(
            db.scalars(
                select(HrSyncUserSnapshotRow)
                .where(HrSyncUserSnapshotRow.run_id == baseline.id)
                .order_by(HrSyncUserSnapshotRow.source_row_no)
            ).all()
        )
        if baseline is not None
        else []
    )
    errors = _validate_erp_rows(
        rows=payloads,
        group_rows=group_payloads,
        baseline_rows=baseline_rows,
        allow_large_changes=allow_large_changes,
    )
    run.comparison_run_id = baseline.id if baseline is not None else None
    run.validation_payload = {
        "valid": not errors,
        "errors": errors,
        "comparison_run_id": run.comparison_run_id,
        "large_change_override": allow_large_changes,
    }
    result_payload: dict[str, object] = {
        "mode": "snapshot_only",
        "rows_seen": len(payloads),
        "groups_seen": len(group_payloads),
        "distinct_employee_codes": len(
            {
                code
                for row in payloads
                if (code := _clean_employee_code(row.get("EMP_NO"))) is not None
            }
        ),
        "projection_applied": False,
        "master_rows_applied": 0,
    }
    if errors:
        run.status = "rejected"
        result_payload["rejection_reason"] = errors[0]["code"]
        run.result_payload = result_payload
        run.completed_at = now
        run.snapshot_purge_after = now + timedelta(days=HR_SNAPSHOT_RETENTION_DAYS)
        run.lease_owner = None
        run.lease_expires_at = None
        run.updated_at = now
        db.commit()
        return run

    run.status = "succeeded"
    run.result_payload = result_payload
    # The shared run schema requires applied_at for succeeded. For this source it
    # means the immutable snapshot was accepted; no HR master projection was applied.
    run.applied_at = now
    run.completed_at = now
    run.snapshot_purge_after = now + timedelta(days=HR_SNAPSHOT_RETENTION_DAYS)
    run.lease_owner = None
    run.lease_expires_at = None
    run.updated_at = now
    db.add(
        AuditLog(
            id=new_id(),
            actor_user_id=run.requested_by_user_id,
            action=ERP_EMPLOYEE_SNAPSHOT_AUDIT_ACTION,
            entity_kind="hr_sync",
            entity_id=run.id,
            summary="ERP employee snapshot captured",
            payload={"run_id": run.id, "status": run.status, **result_payload},
            created_at=now,
        )
    )
    db.commit()
    return run


def fail_erp_hr_snapshot_run(
    db: Session,
    *,
    run_id: str,
    phase: str,
    error: Exception,
    failed_at: datetime | None = None,
) -> HrSyncRun:
    return fail_hr_sync_run(
        db,
        run_id=run_id,
        phase=phase,
        error=error,
        failed_at=failed_at,
    )


def run_erp_hr_snapshot(
    db: Session,
    *,
    rows: list[Mapping[str, Any]],
    group_rows: list[Mapping[str, Any]] | None = None,
    idempotency_key: str,
    trigger_kind: str = "scheduled",
    requested_by_user_id: str | None = None,
    captured_at: datetime | None = None,
    allow_large_changes: bool = False,
) -> HrSyncRun:
    run = begin_erp_hr_snapshot_run(
        db,
        idempotency_key=idempotency_key,
        trigger_kind=trigger_kind,
        requested_by_user_id=requested_by_user_id,
        captured_at=captured_at,
    )
    if run.status in HR_SYNC_TERMINAL_RUN_STATUSES:
        return run
    try:
        return process_erp_hr_snapshot_run(
            db,
            run_id=run.id,
            rows=rows,
            group_rows=group_rows,
            captured_at=captured_at,
            allow_large_changes=allow_large_changes,
        )
    except Exception as error:
        fail_erp_hr_snapshot_run(
            db,
            run_id=run.id,
            phase="capture",
            error=error,
            failed_at=captured_at,
        )
        raise


__all__ = [
    "AcceptedErpEmployee",
    "AcceptedErpEmployeeSnapshot",
    "AcceptedErpEmployeeSnapshotMetadata",
    "AcceptedErpEmployeeSnapshotError",
    "ERP_DEPARTMENT_COLUMNS",
    "ERP_EMPLOYEE_COLUMNS",
    "ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION",
    "ERP_EMPLOYEE_SCHEMA_VERSION",
    "ERP_EMPLOYEE_SCOPE_KEY",
    "ERP_EMPLOYEE_SNAPSHOT_AUDIT_ACTION",
    "ERP_SOURCE_SYSTEM",
    "begin_erp_hr_snapshot_run",
    "fail_erp_hr_snapshot_run",
    "list_erp_hr_snapshot_runs",
    "load_latest_accepted_erp_employee_snapshot",
    "load_latest_accepted_erp_employee_snapshot_metadata",
    "load_latest_erp_hr_snapshot_run",
    "process_erp_hr_snapshot_run",
    "run_erp_hr_snapshot",
]
