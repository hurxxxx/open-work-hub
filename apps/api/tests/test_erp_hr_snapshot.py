from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import AuditLog, OrgUnit, User
from open_alm_api.domains.hr.erp_snapshot import (
    AcceptedErpEmployeeSnapshotError,
    ERP_EMPLOYEE_COLUMNS,
    ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION,
    ERP_EMPLOYEE_SCHEMA_VERSION,
    ERP_EMPLOYEE_SCOPE_KEY,
    ERP_EMPLOYEE_SNAPSHOT_AUDIT_ACTION,
    ERP_SOURCE_SYSTEM,
    load_latest_accepted_erp_employee_snapshot,
    load_latest_accepted_erp_employee_snapshot_metadata,
    load_latest_erp_hr_snapshot_run,
    run_erp_hr_snapshot,
)
from open_alm_api.domains.hr.groupware_sync import GroupwareOrgRow, GroupwareUserRow
from open_alm_api.domains.hr.history import prune_hr_history, run_groupware_hr_sync
from open_alm_api.domains.hr.models import (
    HrSyncChange,
    HrSyncOrgSnapshotRow,
    HrSyncRun,
    HrSyncUserSnapshotRow,
)
from open_alm_api.domains.management_tasks import service as health_checkup_service


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _erp_employee(employee_code: str | None, *, name: str = "ERP User") -> dict[str, object]:
    values: dict[str, object] = {
        "EMP_NO": employee_code,
        "NAME": name,
        "NAT_NM": None,
        "BIRTHDAY": "1990-01-01",
        "SO_LU": "A001",
        "DEPT_NM": "Research",
        "DEPT_CD": "D001",
        "OCPT_NM": "Engineer",
        "INTERNAL_CD": "I001",
        "ROLL_PSTN": "01",
        "ROLL_PSTN_NM": "Member",
        "FUNC_NM": "Development",
        "PAY_GRD1": "01",
        "PAY_GRD1_NM": "Grade 1",
        "PAY_GRD2": "001",
        "ENTR_DT": "2020-01-01",
        "GROUP_ENTR_DT": None,
        "ORDER_CHANGE_DT": None,
        "PROMOTE_DT": None,
        "PLAN_PROMITE_DT": None,
        "RECENT_PROMOTE_DT": None,
        "EMAIL_ADDR": "erp-user@example.test",
        "HAND_TEL_NO": "010-1111-2222",
    }
    assert tuple(values) == ERP_EMPLOYEE_COLUMNS
    return values


def _groupware_snapshot(db: Session, *, key: str, at: datetime) -> HrSyncRun:
    return run_groupware_hr_sync(
        db,
        departments=[GroupwareOrgRow(domain_num=1, org_code="RND", org_depart="Research")],
        users=[
            GroupwareUserRow(
                domain_num=1,
                user_num=100,
                user_id="groupware-user",
                kor_name="Groupware User",
                com_state=1,
                email="groupware-user@example.test",
                com_num="G100",
                org_code1="RND",
                org_level=1,
            )
        ],
        idempotency_key=key,
        synced_at=at,
    )


def test_erp_run_preserves_all_raw_columns_without_applying_the_platform_projection(
    db: Session,
) -> None:
    rows = [
        _erp_employee("E100"),
        _erp_employee("E101", name="Second ERP User"),
    ]

    run = run_erp_hr_snapshot(
        db,
        rows=rows,
        idempotency_key="erp-2026-07-21",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    assert run.status == "succeeded"
    assert run.source_system == ERP_SOURCE_SYSTEM
    assert run.scope_key == ERP_EMPLOYEE_SCOPE_KEY
    assert run.schema_version == ERP_EMPLOYEE_SCHEMA_VERSION
    assert run.user_row_count == 2
    assert run.org_row_count == 1
    assert run.org_snapshot_hash
    assert run.user_snapshot_hash
    assert run.result_payload == {
        "mode": "snapshot_only",
        "rows_seen": 2,
        "groups_seen": 1,
        "distinct_employee_codes": 2,
        "projection_applied": False,
        "master_rows_applied": 0,
    }

    snapshots = list(
        db.scalars(
            select(HrSyncUserSnapshotRow)
            .where(HrSyncUserSnapshotRow.run_id == run.id)
            .order_by(HrSyncUserSnapshotRow.source_row_no)
        ).all()
    )
    assert [row.raw_payload for row in snapshots] == rows
    assert tuple(snapshots[0].raw_payload) == ERP_EMPLOYEE_COLUMNS
    assert [row.employee_code for row in snapshots] == ["E100", "E101"]
    groups = list(
        db.scalars(select(HrSyncOrgSnapshotRow).where(HrSyncOrgSnapshotRow.run_id == run.id)).all()
    )
    assert [row.raw_payload for row in groups] == [{"DEPT_CD": "D001", "DEPT_NM": "Research"}]
    assert not db.scalars(select(HrSyncChange).where(HrSyncChange.run_id == run.id)).all()
    assert not db.scalars(select(User)).all()
    assert not db.scalars(select(OrgUnit)).all()
    audit = db.scalar(select(AuditLog).where(AuditLog.action == ERP_EMPLOYEE_SNAPSHOT_AUDIT_ACTION))
    assert audit is not None
    assert audit.entity_id == run.id
    assert audit.payload["projection_applied"] is False


def test_latest_accepted_erp_snapshot_has_a_typed_employee_projection(
    db: Session,
) -> None:
    run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        idempotency_key="erp-typed-reader",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    snapshot = load_latest_accepted_erp_employee_snapshot(db)

    assert snapshot is not None
    assert snapshot.run_id == run.id
    assert snapshot.schema_version == ERP_EMPLOYEE_SCHEMA_VERSION
    assert snapshot.captured_at == datetime(2026, 7, 21, 3, 20)
    assert snapshot.snapshot_hash == run.user_snapshot_hash
    assert len(snapshot.employees) == 1
    employee = snapshot.employees[0]
    assert employee.employee_code == "E100"
    assert employee.name == "ERP User"
    assert employee.department_code == "D001"
    assert employee.department_name == "Research"
    assert employee.position == "Member"
    assert employee.occupation == "Engineer"
    assert employee.birth_date.isoformat() == "1990-01-01"
    assert employee.hire_date.isoformat() == "2020-01-01"
    assert employee.phone_number == "010-1111-2222"


def test_v1_source_reader_remains_available_but_health_checkup_requires_master(
    db: Session,
) -> None:
    run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        idempotency_key="erp-v1-before-v2-deploy",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )
    run.schema_version = ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION
    db.commit()

    metadata = load_latest_accepted_erp_employee_snapshot_metadata(db)
    snapshot = load_latest_accepted_erp_employee_snapshot(db)
    source_status = health_checkup_service.get_source_status(db)

    assert metadata is not None
    assert metadata.run_id == run.id
    assert metadata.schema_version == ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION
    assert snapshot is not None
    assert snapshot.run_id == run.id
    assert snapshot.schema_version == ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION
    assert [employee.employee_code for employee in snapshot.employees] == ["E100"]
    assert source_status.available is False
    assert source_status.reason == "integrated_hr_erp_snapshot_not_found"
    assert source_status.run_id is None


def test_typed_erp_reader_rejects_an_unsupported_newer_snapshot(
    db: Session,
) -> None:
    v1_run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        idempotency_key="erp-compatible-v1",
        captured_at=datetime(2026, 7, 20, 3, 20),
    )
    v1_run.schema_version = ERP_EMPLOYEE_LEGACY_SCHEMA_VERSION
    db.commit()
    v2_run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E200")],
        idempotency_key="erp-compatible-v2",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )
    future_run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E300")],
        idempotency_key="erp-incompatible-v3",
        captured_at=datetime(2026, 7, 22, 3, 20),
    )
    future_run.schema_version = "erp-employee-view-v3"
    db.commit()

    with pytest.raises(AcceptedErpEmployeeSnapshotError) as error:
        load_latest_accepted_erp_employee_snapshot(db)

    assert v2_run.schema_version == ERP_EMPLOYEE_SCHEMA_VERSION
    assert error.value.code == "unsupported_schema_version"


def test_latest_accepted_erp_snapshot_metadata_does_not_read_raw_employee_rows(
    db: Session,
) -> None:
    run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        idempotency_key="erp-metadata-reader",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )
    statements: list[str] = []

    def capture_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", capture_statement)
    try:
        metadata = load_latest_accepted_erp_employee_snapshot_metadata(db)
    finally:
        event.remove(bind, "before_cursor_execute", capture_statement)

    assert metadata is not None
    assert metadata.run_id == run.id
    assert metadata.schema_version == ERP_EMPLOYEE_SCHEMA_VERSION
    assert metadata.captured_at == datetime(2026, 7, 21, 3, 20)
    assert metadata.snapshot_hash == run.user_snapshot_hash
    assert metadata.employee_count == 1
    assert all("hr_user_snapshot_rows" not in statement for statement in statements)


def test_typed_erp_reader_rejects_missing_rows_without_exposing_payload(
    db: Session,
) -> None:
    run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("SENSITIVE-EMPLOYEE-CODE")],
        idempotency_key="erp-reader-missing-row",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )
    row = db.scalar(select(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id == run.id))
    assert row is not None
    db.delete(row)
    db.commit()

    with pytest.raises(AcceptedErpEmployeeSnapshotError) as captured:
        load_latest_accepted_erp_employee_snapshot(db)

    assert captured.value.code == "snapshot_row_count_mismatch"
    assert "SENSITIVE" not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("NAME", "", "invalid_required_value"),
        ("BIRTHDAY", "not-a-date", "invalid_date_value"),
        ("PAY_GRD2", 1, "snapshot_schema_mismatch"),
    ],
)
def test_typed_erp_reader_rejects_invalid_required_projection_values(
    db: Session,
    field: str,
    value: object,
    expected_code: str,
) -> None:
    run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        idempotency_key=f"erp-invalid-{field}",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )
    row = db.scalar(select(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id == run.id))
    assert row is not None
    row.raw_payload = {**row.raw_payload, field: value}
    db.add(row)
    db.commit()

    with pytest.raises(AcceptedErpEmployeeSnapshotError) as captured:
        load_latest_accepted_erp_employee_snapshot(db)

    assert captured.value.code == expected_code


def test_invalid_erp_identity_rows_are_preserved_and_rejected(db: Session) -> None:
    rows = [
        _erp_employee("E100"),
        _erp_employee("E100", name="Duplicate"),
        _erp_employee(None, name="Missing"),
    ]

    run = run_erp_hr_snapshot(
        db,
        rows=rows,
        idempotency_key="erp-invalid-2026-07-21",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    assert run.status == "rejected"
    assert run.result_payload["rows_seen"] == 3
    assert run.result_payload["projection_applied"] is False
    error_codes = {item["code"] for item in run.validation_payload["errors"]}
    assert error_codes == {"missing_employee_code", "duplicate_employee_code"}
    assert (
        len(
            db.scalars(
                select(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id == run.id)
            ).all()
        )
        == 3
    )


def test_erp_employee_identity_duplicate_check_is_trimmed_and_case_insensitive(
    db: Session,
) -> None:
    rows = [
        _erp_employee("e100"),
        _erp_employee(" E100 ", name="Duplicate"),
    ]

    run = run_erp_hr_snapshot(
        db,
        rows=rows,
        idempotency_key="erp-case-folded-duplicate",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    assert run.status == "rejected"
    error_codes = {item["code"] for item in run.validation_payload["errors"]}
    assert "duplicate_employee_code" in error_codes
    snapshots = list(
        db.scalars(
            select(HrSyncUserSnapshotRow)
            .where(HrSyncUserSnapshotRow.run_id == run.id)
            .order_by(HrSyncUserSnapshotRow.source_row_no)
        ).all()
    )
    assert [row.raw_payload for row in snapshots] == rows
    assert [row.source_identity for row in snapshots] == ["E100", "E100"]
    assert [row.employee_code for row in snapshots] == ["E100", "E100"]


def test_erp_snapshot_rejects_numeric_employee_values_without_coercing_raw_payload(
    db: Session,
) -> None:
    employee = _erp_employee("E100")
    employee["EMP_NO"] = 100

    run = run_erp_hr_snapshot(
        db,
        rows=[employee],
        idempotency_key="erp-numeric-employee-value",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    assert run.status == "rejected"
    errors_by_code = {item["code"]: item for item in run.validation_payload["errors"]}
    assert errors_by_code["invalid_employee_column_types"]["rows"] == [
        {"source_row": 0, "columns": ["EMP_NO"]}
    ]
    snapshot = db.scalar(
        select(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id == run.id)
    )
    assert snapshot is not None
    assert snapshot.raw_payload["EMP_NO"] == 100
    assert snapshot.source_identity is None
    assert snapshot.employee_code is None


def test_erp_snapshot_rejects_numeric_department_group_values(
    db: Session,
) -> None:
    run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        group_rows=[{"DEPT_CD": 100, "DEPT_NM": "Research"}],
        idempotency_key="erp-numeric-group-value",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    assert run.status == "rejected"
    errors_by_code = {item["code"]: item for item in run.validation_payload["errors"]}
    assert errors_by_code["invalid_department_group_column_types"]["rows"] == [
        {"source_row": 0, "columns": ["DEPT_CD"]}
    ]
    group_snapshot = db.scalar(
        select(HrSyncOrgSnapshotRow).where(HrSyncOrgSnapshotRow.run_id == run.id)
    )
    assert group_snapshot is not None
    assert group_snapshot.raw_payload["DEPT_CD"] == 100
    assert group_snapshot.source_identity is None


def test_erp_group_snapshot_rejects_conflicting_names_and_missing_employee_group(
    db: Session,
) -> None:
    run = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        group_rows=[
            {"DEPT_CD": "d001", "DEPT_NM": "First Name"},
            {"DEPT_CD": " D001 ", "DEPT_NM": "Different Name"},
        ],
        idempotency_key="erp-invalid-groups",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    assert run.status == "rejected"
    assert run.org_row_count == 2
    error_codes = {item["code"] for item in run.validation_payload["errors"]}
    assert error_codes == {
        "conflicting_department_group_name",
        "missing_employee_department_group",
    }


def test_erp_redelivery_is_idempotent_and_unsafe_drop_does_not_replace_baseline(
    db: Session,
) -> None:
    baseline_rows = [_erp_employee(f"E{index:03d}") for index in range(20)]
    baseline = run_erp_hr_snapshot(
        db,
        rows=baseline_rows,
        idempotency_key="erp-baseline",
        captured_at=datetime(2026, 7, 20, 3, 20),
    )
    redelivery = run_erp_hr_snapshot(
        db,
        rows=[],
        idempotency_key="erp-baseline",
        captured_at=datetime(2026, 7, 20, 3, 21),
    )
    rejected = run_erp_hr_snapshot(
        db,
        rows=baseline_rows[:5],
        idempotency_key="erp-unsafe-drop",
        captured_at=datetime(2026, 7, 21, 3, 20),
    )

    assert redelivery.id == baseline.id
    assert rejected.status == "rejected"
    assert rejected.result_payload["rejection_reason"] == "unsafe_employee_volume_drop"
    latest = load_latest_erp_hr_snapshot_run(db)
    assert latest is not None
    assert latest.id == baseline.id


def test_retention_protects_latest_success_for_each_hr_source_scope(db: Session) -> None:
    erp_old = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        idempotency_key="erp-old",
        captured_at=datetime(2025, 6, 1, 3, 20),
    )
    erp_latest = run_erp_hr_snapshot(
        db,
        rows=[_erp_employee("E100")],
        idempotency_key="erp-latest",
        captured_at=datetime(2025, 6, 2, 3, 20),
    )
    groupware_old = _groupware_snapshot(
        db,
        key="groupware-old",
        at=datetime(2025, 6, 1, 3, 10),
    )
    groupware_latest = _groupware_snapshot(
        db,
        key="groupware-latest",
        at=datetime(2025, 6, 2, 3, 10),
    )

    deleted = prune_hr_history(db, now=datetime(2026, 7, 21, 3, 20))

    assert deleted["user_snapshots_deleted"] == 2
    for run in (erp_latest, groupware_latest):
        assert db.scalars(
            select(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id == run.id)
        ).all()
    for run in (erp_old, groupware_old):
        assert not db.scalars(
            select(HrSyncUserSnapshotRow).where(HrSyncUserSnapshotRow.run_id == run.id)
        ).all()
