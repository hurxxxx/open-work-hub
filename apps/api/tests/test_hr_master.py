from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.hr.erp_snapshot import run_erp_hr_snapshot
from open_alm_api.domains.hr.groupware_sync import GroupwareOrgRow, GroupwareUserRow
from open_alm_api.domains.hr.history import (
    canonical_payload_hash,
    prune_hr_history,
    run_groupware_hr_sync,
)
from open_alm_api.domains.hr.identity_resolution import (
    advance_identity_resolution_revision,
)
from open_alm_api.domains.hr.master import (
    HR_MASTER_ERP_VIEW_SCHEMA_VERSION,
    HR_MASTER_SCHEMA_VERSION,
    HrMasterErpEmployeeSnapshotError,
    build_hr_master_run,
    build_latest_hr_master_run,
    load_latest_hr_master_erp_employee_snapshot,
    load_latest_hr_master_erp_employee_snapshot_metadata,
    load_latest_hr_master_snapshot,
    load_latest_succeeded_hr_master_run,
    prune_hr_master_history,
)
from open_alm_api.domains.hr.models import (
    HrMasterConflictRow,
    HrMasterGroupRow,
    HrMasterPersonRow,
    HrMasterRun,
    HrManualIdentityLink,
    HrSyncOrgSnapshotRow,
    HrSyncUserSnapshotRow,
    HrWorkforceCategory,
    HrWorkforceCategoryAssignment,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _erp_employee(
    employee_code: str,
    *,
    name: str,
    department_code: str = "D001",
    department_name: str = "ERP Research",
    email: str | None = "erp@example.test",
    phone_number: str | None = "010-1111-2222",
) -> dict[str, object]:
    return {
        "EMP_NO": employee_code,
        "NAME": name,
        "NAT_NM": None,
        "BIRTHDAY": "1990-01-01",
        "SO_LU": "A001",
        "DEPT_NM": department_name,
        "DEPT_CD": department_code,
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
        "EMAIL_ADDR": email,
        "HAND_TEL_NO": phone_number,
    }


def _groupware_user(
    employee_code: str | None,
    *,
    user_num: int,
    login_id: str,
    name: str,
    email: str | None = None,
    com_state: int = 1,
) -> GroupwareUserRow:
    return GroupwareUserRow(
        domain_num=1,
        user_num=user_num,
        user_id=login_id,
        kor_name=name,
        com_state=com_state,
        email=email,
        com_num=employee_code,
        com_position="GW Position",
        org_code1="GW-RND",
        org_level=1,
    )


def _source_pair(
    db: Session,
    *,
    at: datetime,
    erp_users: list[dict[str, object]],
    groupware_users: list[GroupwareUserRow],
    key: str,
):
    groupware_run = run_groupware_hr_sync(
        db,
        departments=[
            GroupwareOrgRow(
                domain_num=1,
                org_code="GW-RND",
                org_depart="Groupware Research",
            )
        ],
        users=groupware_users,
        idempotency_key=f"gw-{key}",
        synced_at=at,
    )
    erp_groups = sorted({(str(row["DEPT_CD"]), str(row["DEPT_NM"])) for row in erp_users})
    erp_run = run_erp_hr_snapshot(
        db,
        rows=erp_users,
        group_rows=[
            {"DEPT_CD": department_code, "DEPT_NM": department_name}
            for department_code, department_name in erp_groups
        ],
        idempotency_key=f"erp-{key}",
        captured_at=at,
    )
    assert groupware_run.status == "succeeded"
    assert erp_run.status == "succeeded"
    return erp_run, groupware_run


def test_master_exact_employee_code_union_and_canonical_field_precedence(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[
            _erp_employee(" e100 ", name="ERP Matched", email="erp-fallback@example.test"),
            _erp_employee("E200", name="ERP Only"),
        ],
        groupware_users=[
            _groupware_user(
                "e100",
                user_num=100,
                login_id="matched-user",
                name="Groupware Matched",
                email="gw@example.test",
            ),
            _groupware_user(
                "G300",
                user_num=300,
                login_id="gw-only",
                name="Groupware Only",
                email=None,
            ),
        ],
        key="union",
    )

    run = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key="master-union",
        built_at=datetime(2026, 7, 29, 3, 30),
    )

    assert run.status == "succeeded"
    assert run.person_row_count == 3
    assert run.group_row_count == 2
    assert run.conflict_row_count == 0
    assert run.checksum
    assert run.erp_projection_hash
    assert run.result_payload["status_counts"] == {
        "erp_only": 1,
        "groupware_only": 1,
        "matched": 1,
    }
    snapshot = load_latest_hr_master_snapshot(db)
    assert snapshot is not None
    people = {person.employee_code: person for person in snapshot.people}
    assert set(people) == {"E100", "E200", "G300"}
    matched = people["E100"]
    assert matched.reconciliation_status == "matched"
    assert matched.name == "ERP Matched"
    assert matched.position == "Member"
    assert matched.occupation == "Engineer"
    assert matched.birth_date == date(1990, 1, 1)
    assert matched.hire_date == date(2020, 1, 1)
    assert matched.phone_number == "010-1111-2222"
    assert matched.login_id == "matched-user"
    assert matched.email == "gw@example.test"
    assert matched.group_source == "erp"
    assert matched.group_code == "D001"
    assert people["G300"].group_source == "groupware"
    assert people["G300"].group_name == "Groupware Research"
    assert people["G300"].birth_date is None
    assert people["G300"].hire_date is None
    assert people["G300"].phone_number is None

    redelivered = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key="different-task-id",
    )
    assert redelivered.id == run.id
    assert redelivered.checksum == run.checksum


def test_latest_master_erp_view_reads_every_erp_connected_person(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[
            _erp_employee("E100", name="Matched"),
            _erp_employee("E200", name="ERP Only"),
            _erp_employee("E300", name="Identity Conflict"),
        ],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=801,
                login_id="matched",
                name="Matched",
            ),
            _groupware_user(
                "E300",
                user_num=802,
                login_id="duplicate-one",
                name="Duplicate One",
            ),
            _groupware_user(
                " e300 ",
                user_num=803,
                login_id="duplicate-two",
                name="Duplicate Two",
            ),
            _groupware_user(
                "G400",
                user_num=804,
                login_id="groupware-only",
                name="Groupware Only",
            ),
        ],
        key="erp-view",
    )
    run = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key="master-erp-view",
        built_at=datetime(2026, 7, 29, 3, 30),
    )

    metadata = load_latest_hr_master_erp_employee_snapshot_metadata(db)
    snapshot = load_latest_hr_master_erp_employee_snapshot(db)

    assert metadata is not None
    assert snapshot is not None
    assert metadata.run_id == run.id
    assert metadata.erp_run_id == erp_run.id
    assert metadata.captured_at == datetime(2026, 7, 29, 3, 20)
    assert metadata.schema_version == HR_MASTER_ERP_VIEW_SCHEMA_VERSION
    assert metadata.snapshot_hash == run.erp_projection_hash
    assert metadata.employee_count == 3
    assert snapshot.run_id == metadata.run_id
    assert snapshot.erp_run_id == metadata.erp_run_id
    assert snapshot.captured_at == metadata.captured_at
    assert snapshot.schema_version == metadata.schema_version
    assert snapshot.snapshot_hash == metadata.snapshot_hash
    assert [employee.employee_code for employee in snapshot.employees] == [
        "E100",
        "E200",
        "E300",
    ]
    people = {
        person.employee_code: person
        for person in db.scalars(
            select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == run.id)
        ).all()
    }
    assert people["E300"].reconciliation_status == "identity_conflict"
    assert snapshot.employees[2].snapshot_row_id == (people["E300"].erp_snapshot_row_id)
    assert snapshot.employees[0].birth_date == date(1990, 1, 1)
    assert snapshot.employees[0].hire_date == date(2020, 1, 1)
    assert snapshot.employees[0].phone_number == "010-1111-2222"
    expected_projection_hash = canonical_payload_hash(
        [
            {
                "employee_code": employee_code,
                "name": name,
                "department_code": "D001",
                "department_name": "ERP Research",
                "position": "Member",
                "occupation": "Engineer",
                "birth_date": "1990-01-01",
                "hire_date": "2020-01-01",
                "phone_number": "010-1111-2222",
            }
            for employee_code, name in (
                ("E100", "Matched"),
                ("E200", "ERP Only"),
                ("E300", "Identity Conflict"),
            )
        ]
    )
    assert snapshot.snapshot_hash == expected_projection_hash

    db.delete(people["E200"])
    db.commit()
    with pytest.raises(HrMasterErpEmployeeSnapshotError) as error:
        load_latest_hr_master_erp_employee_snapshot_metadata(db)
    assert error.value.code == "snapshot_row_count_mismatch"


def test_groupware_blank_is_external_and_duplicate_real_codes_are_quarantined(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[_erp_employee("E100", name="ERP Conflict")],
        groupware_users=[
            _groupware_user(
                "e100",
                user_num=101,
                login_id="duplicate-one",
                name="Duplicate One",
            ),
            _groupware_user(
                " E100 ",
                user_num=102,
                login_id="duplicate-two",
                name="Duplicate Two",
            ),
            _groupware_user(
                None,
                user_num=103,
                login_id="missing-code",
                name="Missing Code",
            ),
        ],
        key="conflict",
    )

    run = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key="master-conflict",
    )

    assert run.status == "succeeded"
    assert run.person_row_count == 1
    assert run.external_row_count == 1
    assert run.conflict_row_count == 2
    person = db.scalar(select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == run.id))
    assert person is not None
    assert person.employee_code == "E100"
    assert person.reconciliation_status == "identity_conflict"
    assert person.has_identity_conflict is True
    assert person.groupware_snapshot_row_id is None
    conflicts = list(
        db.scalars(
            select(HrMasterConflictRow)
            .where(HrMasterConflictRow.master_run_id == run.id)
            .order_by(HrMasterConflictRow.reason_code)
        ).all()
    )
    assert [row.reason_code for row in conflicts] == [
        "duplicate_employee_code",
        "duplicate_employee_code",
    ]
    assert all(row.source_snapshot_row_id for row in conflicts)
    snapshot = load_latest_hr_master_snapshot(db)
    assert snapshot is not None
    assert [(row.employee_code, row.name) for row in snapshot.external_people] == [
        (None, "Missing Code")
    ]


def test_names_never_merge_different_employee_codes(db: Session) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[_erp_employee("ERP-1", name="Same Person")],
        groupware_users=[
            _groupware_user(
                "GW-9",
                user_num=109,
                login_id="same-name",
                name="Same Person",
            )
        ],
        key="no-name-match",
    )

    run = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key="master-no-name-match",
    )

    people = list(
        db.scalars(
            select(HrMasterPersonRow)
            .where(HrMasterPersonRow.master_run_id == run.id)
            .order_by(HrMasterPersonRow.employee_code)
        ).all()
    )
    assert [(row.employee_code, row.reconciliation_status) for row in people] == [
        ("ERP-1", "erp_only"),
        ("GW-9", "groupware_only"),
    ]


def test_placeholder_employee_codes_are_materialized_as_external_people(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[_erp_employee("E100", name="Same Name")],
        groupware_users=[
            _groupware_user("Z0000", user_num=201, login_id="external-1", name="Same Name"),
            _groupware_user("Z0000", user_num=202, login_id="external-2", name="External Two"),
            _groupware_user("Z00000", user_num=203, login_id="external-3", name="External Three"),
            _groupware_user(None, user_num=204, login_id="external-4", name="External Four"),
        ],
        key="external-placeholders",
    )

    run = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
    )

    assert run.status == "succeeded"
    assert run.external_row_count == 4
    assert run.conflict_row_count == 0
    snapshot = load_latest_hr_master_snapshot(db)
    assert snapshot is not None
    assert {row.groupware_source_identity for row in snapshot.external_people} == {
        "1:201",
        "1:202",
        "1:203",
        "1:204",
    }
    erp_person = next(person for person in snapshot.people if person.employee_code == "E100")
    assert erp_person.workforce_category == "field"


def test_exact_name_candidates_remain_unresolved_until_manual_match(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[
            _erp_employee("E100", name="Candidate"),
            _erp_employee("E200", name="ERP Only"),
        ],
        groupware_users=[
            _groupware_user("G900", user_num=301, login_id="candidate", name="Candidate")
        ],
        key="candidate-classification",
    )

    run = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
    )

    assert run.status == "succeeded"
    snapshot = load_latest_hr_master_snapshot(db)
    assert snapshot is not None
    people = {person.employee_code: person for person in snapshot.people}
    assert people["E100"].workforce_category == "unresolved"
    assert people["G900"].workforce_category == "unresolved"
    assert people["E200"].workforce_category == "field"
    assert people["E100"].identity_resolution_kind == "none"
    assert people["G900"].identity_resolution_kind == "none"


def test_manual_match_and_revoke_create_new_immutable_revisions(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[_erp_employee("E100", name="ERP Candidate")],
        groupware_users=[
            _groupware_user(
                "G900",
                user_num=401,
                login_id="candidate",
                name="Groupware Candidate",
            )
        ],
        key="manual-match",
    )
    initial = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        built_at=datetime(2026, 7, 29, 3, 30),
    )
    initial_rows = list(
        db.scalars(
            select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == initial.id)
        ).all()
    )
    assert len(initial_rows) == 2

    assert (
        advance_identity_resolution_revision(
            db,
            now=datetime(2026, 7, 29, 3, 31),
        )
        == 1
    )
    link = HrManualIdentityLink(
        id="manual-link-1",
        groupware_source_identity="1:401",
        groupware_employee_code="G900",
        erp_employee_code="E100",
        matched_name="Groupware Candidate",
        status="active",
        activated_revision=1,
        created_at=datetime(2026, 7, 29, 3, 31),
    )
    db.add(link)
    db.commit()

    matched = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        built_at=datetime(2026, 7, 29, 3, 32),
    )
    assert matched.id != initial.id
    assert matched.identity_resolution_revision == 1
    assert matched.erp_projection_hash == initial.erp_projection_hash
    matched_rows = list(
        db.scalars(
            select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == matched.id)
        ).all()
    )
    assert len(matched_rows) == 1
    assert matched_rows[0].employee_code == "E100"
    assert matched_rows[0].groupware_source_identity == "1:401"
    assert matched_rows[0].identity_resolution_kind == "manual"
    assert matched_rows[0].manual_identity_link_id == link.id
    assert matched_rows[0].workforce_category == "internal"

    assert (
        advance_identity_resolution_revision(
            db,
            now=datetime(2026, 7, 29, 3, 33),
        )
        == 2
    )
    link.status = "revoked"
    link.revoked_revision = 2
    link.revoked_at = datetime(2026, 7, 29, 3, 33)
    db.commit()
    separated = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        built_at=datetime(2026, 7, 29, 3, 34),
    )
    assert separated.id not in {initial.id, matched.id}
    assert separated.identity_resolution_revision == 2
    assert separated.erp_projection_hash == initial.erp_projection_hash
    assert (
        len(
            db.scalars(
                select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == initial.id)
            ).all()
        )
        == 2
    )
    assert load_latest_succeeded_hr_master_run(db).id == separated.id


def test_workforce_override_materializes_without_changing_erp_projection(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 40),
        erp_users=[_erp_employee("E100", name="Employee")],
        groupware_users=[
            _groupware_user("E100", user_num=402, login_id="employee", name="Employee")
        ],
        key="workforce-override",
    )
    initial = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        built_at=datetime(2026, 7, 29, 3, 41),
    )
    initial_person = db.scalar(
        select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == initial.id)
    )
    assert initial_person is not None
    assert initial_person.inferred_workforce_category == "internal"
    assert initial_person.workforce_category == "internal"

    changed_at = datetime(2026, 7, 29, 3, 42)
    assert advance_identity_resolution_revision(db, now=changed_at) == 1
    category = HrWorkforceCategory(
        code="project",
        name="Project",
        is_system=False,
        is_active=True,
        sort_order=100,
        created_at=changed_at,
        updated_at=changed_at,
    )
    assignment = HrWorkforceCategoryAssignment(
        id="workforce-assignment-1",
        subject_kind="erp_employee",
        subject_key="E100",
        category_code=category.code,
        status="active",
        activated_revision=1,
        created_at=changed_at,
    )
    db.add_all([category, assignment])
    db.commit()

    overridden = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        built_at=datetime(2026, 7, 29, 3, 43),
    )
    overridden_person = db.scalar(
        select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == overridden.id)
    )
    assert overridden_person is not None
    assert overridden_person.inferred_workforce_category == "internal"
    assert overridden_person.workforce_category == "project"
    assert overridden_person.workforce_category_resolution_kind == "manual"
    assert overridden_person.workforce_assignment_id == assignment.id
    assert overridden.erp_projection_hash == initial.erp_projection_hash

    assert (
        advance_identity_resolution_revision(
            db,
            now=datetime(2026, 7, 29, 3, 44),
        )
        == 2
    )
    assignment.status = "revoked"
    assignment.revoked_revision = 2
    assignment.revoked_at = datetime(2026, 7, 29, 3, 44)
    db.commit()

    reset = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        built_at=datetime(2026, 7, 29, 3, 45),
    )
    reset_person = db.scalar(
        select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == reset.id)
    )
    assert reset_person is not None
    assert reset_person.workforce_category == "internal"
    assert reset_person.workforce_category_resolution_kind == "inferred"
    assert reset_person.workforce_assignment_id is None
    assert reset.erp_projection_hash == initial.erp_projection_hash


def test_inactive_groupware_user_does_not_prevent_field_classification(
    db: Session,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[_erp_employee("E100", name="Inactive")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=501,
                login_id="inactive",
                name="Inactive",
                com_state=0,
            )
        ],
        key="inactive-groupware",
    )

    run = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
    )
    person = db.scalar(select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == run.id))
    assert person is not None
    assert person.reconciliation_status == "erp_only"
    assert person.workforce_category == "field"


def test_structural_failure_does_not_replace_latest_succeeded_master(
    db: Session,
) -> None:
    good_erp, good_groupware = _source_pair(
        db,
        at=datetime(2026, 7, 28, 3, 20),
        erp_users=[_erp_employee("E100", name="Good")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=201,
                login_id="good-user",
                name="Good",
            )
        ],
        key="good",
    )
    good_master = build_hr_master_run(
        db,
        erp_run_id=good_erp.id,
        groupware_run_id=good_groupware.id,
        idempotency_key="master-good",
        built_at=datetime(2026, 7, 28, 3, 30),
    )

    bad_erp, bad_groupware = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[
            _erp_employee("E200", name="First"),
            _erp_employee("E201", name="Second"),
        ],
        groupware_users=[
            _groupware_user(
                "E300",
                user_num=301,
                login_id="other-user",
                name="Other",
            )
        ],
        key="bad",
    )
    bad_erp_rows = list(
        db.scalars(
            select(HrSyncUserSnapshotRow)
            .where(HrSyncUserSnapshotRow.run_id == bad_erp.id)
            .order_by(HrSyncUserSnapshotRow.source_row_no)
        ).all()
    )
    duplicate_payload = dict(bad_erp_rows[1].raw_payload)
    duplicate_payload["EMP_NO"] = " e200 "
    bad_erp_rows[1].raw_payload = duplicate_payload
    bad_erp.user_snapshot_hash = canonical_payload_hash([row.raw_payload for row in bad_erp_rows])
    db.commit()
    failed = build_hr_master_run(
        db,
        erp_run_id=bad_erp.id,
        groupware_run_id=bad_groupware.id,
        idempotency_key="master-bad",
        built_at=datetime(2026, 7, 29, 3, 30),
    )

    assert failed.status == "failed"
    assert failed.error_code == "duplicate_normalized_erp_employee_code"
    assert failed.person_row_count == 0
    assert load_latest_succeeded_hr_master_run(db).id == good_master.id


@pytest.mark.parametrize("prior_status", ["building", "failed"])
def test_non_succeeded_attempt_does_not_block_redelivery(
    db: Session,
    prior_status: str,
) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[_erp_employee("E100", name="Retry")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=601,
                login_id="retry-user",
                name="Retry",
            )
        ],
        key=f"retry-{prior_status}",
    )
    prior = HrMasterRun(
        id=f"prior-{prior_status}",
        status=prior_status,
        idempotency_key="redelivered-task",
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        schema_version=HR_MASTER_SCHEMA_VERSION,
        started_at=datetime(2026, 7, 29, 3, 30),
        completed_at=(datetime(2026, 7, 29, 3, 31) if prior_status == "failed" else None),
        error_code="worker_terminated" if prior_status == "failed" else None,
        error_summary="worker_terminated" if prior_status == "failed" else None,
        created_at=datetime(2026, 7, 29, 3, 30),
    )
    db.add(prior)
    db.commit()

    recovered = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key="redelivered-task",
        built_at=datetime(2026, 7, 29, 3, 35),
    )

    assert recovered.status == "succeeded"
    assert recovered.id != prior.id
    assert db.get(HrMasterRun, prior.id).status == prior_status


def test_source_pair_allows_only_one_succeeded_master(db: Session) -> None:
    erp_run, groupware_run = _source_pair(
        db,
        at=datetime(2026, 7, 29, 3, 20),
        erp_users=[_erp_employee("E100", name="Unique")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=602,
                login_id="unique-user",
                name="Unique",
            )
        ],
        key="unique-success",
    )
    succeeded = build_hr_master_run(
        db,
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        idempotency_key="unique-success-first",
    )
    duplicate = HrMasterRun(
        id="duplicate-success",
        status="succeeded",
        idempotency_key="unique-success-second",
        erp_run_id=erp_run.id,
        groupware_run_id=groupware_run.id,
        schema_version=HR_MASTER_SCHEMA_VERSION,
        checksum="0" * 64,
        started_at=datetime(2026, 7, 29, 3, 31),
        completed_at=datetime(2026, 7, 29, 3, 31),
        created_at=datetime(2026, 7, 29, 3, 31),
    )
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assert db.get(HrMasterRun, succeeded.id) is not None


def test_build_latest_requires_a_same_kst_day_source_pair(db: Session) -> None:
    _source_pair(
        db,
        # Source timestamps are UTC-naive; 16:20 UTC is 01:20 KST the next day.
        at=datetime(2026, 7, 28, 16, 20),
        erp_users=[_erp_employee("E100", name="Today")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=401,
                login_id="today-user",
                name="Today",
            )
        ],
        key="today",
    )

    built = build_latest_hr_master_run(
        db,
        now=datetime(2026, 7, 29, 3, 30, tzinfo=ZoneInfo("Asia/Seoul")),
        idempotency_key="latest-today",
    )
    unavailable = build_latest_hr_master_run(
        db,
        now=datetime(2026, 7, 30, 3, 30, tzinfo=ZoneInfo("Asia/Seoul")),
        idempotency_key="latest-tomorrow",
    )

    assert built is not None
    assert built.status == "succeeded"
    assert built.completed_at == datetime(2026, 7, 28, 18, 30)
    assert unavailable is None


def test_master_retention_purges_expired_rows_but_protects_latest_success(
    db: Session,
) -> None:
    old_erp, old_groupware = _source_pair(
        db,
        at=datetime(2026, 7, 28, 0, 20),
        erp_users=[_erp_employee("E100", name="Old")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=501,
                login_id="old-user",
                name="Old",
            )
        ],
        key="retention-old",
    )
    old_master = build_hr_master_run(
        db,
        erp_run_id=old_erp.id,
        groupware_run_id=old_groupware.id,
        idempotency_key="retention-old-master",
        built_at=datetime(2026, 7, 28, 0, 30),
    )
    latest_erp, latest_groupware = _source_pair(
        db,
        at=datetime(2026, 7, 29, 0, 20),
        erp_users=[_erp_employee("E200", name="Latest")],
        groupware_users=[
            _groupware_user(
                "E200",
                user_num=502,
                login_id="latest-user",
                name="Latest",
            )
        ],
        key="retention-latest",
    )
    latest_master = build_hr_master_run(
        db,
        erp_run_id=latest_erp.id,
        groupware_run_id=latest_groupware.id,
        idempotency_key="retention-latest-master",
        built_at=datetime(2026, 7, 29, 0, 30),
    )

    result = prune_hr_master_history(
        db,
        now=datetime(2027, 8, 1, 0, 30),
    )

    assert result == {
        "runs_deleted": 0,
        "people_deleted": 1,
        "external_people_deleted": 0,
        "groups_deleted": 2,
        "conflicts_deleted": 0,
    }
    assert db.get(HrMasterRun, old_master.id).rows_purged_at == datetime(
        2027,
        8,
        1,
        0,
        30,
    )
    assert db.get(HrMasterRun, latest_master.id).rows_purged_at is None
    assert (
        db.scalar(select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == old_master.id))
        is None
    )
    assert db.scalar(
        select(HrMasterGroupRow).where(HrMasterGroupRow.master_run_id == latest_master.id)
    )


def test_source_retention_preserves_current_master_provenance_ids(
    db: Session,
) -> None:
    old_erp, old_groupware = _source_pair(
        db,
        at=datetime(2025, 7, 1, 0, 20),
        erp_users=[_erp_employee("E100", name="Current")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=701,
                login_id="current-user",
                name="Current",
            )
        ],
        key="provenance-old",
    )
    current = build_hr_master_run(
        db,
        erp_run_id=old_erp.id,
        groupware_run_id=old_groupware.id,
        idempotency_key="provenance-master",
        built_at=datetime(2025, 7, 1, 0, 30),
    )
    person = db.scalar(
        select(HrMasterPersonRow).where(HrMasterPersonRow.master_run_id == current.id)
    )
    group = db.scalar(
        select(HrMasterGroupRow)
        .where(HrMasterGroupRow.master_run_id == current.id)
        .order_by(HrMasterGroupRow.source_system)
    )
    assert person is not None
    assert group is not None
    erp_snapshot_row_id = person.erp_snapshot_row_id
    groupware_snapshot_row_id = person.groupware_snapshot_row_id
    group_snapshot_row_id = group.source_snapshot_row_id

    _source_pair(
        db,
        at=datetime(2026, 7, 29, 0, 20),
        erp_users=[_erp_employee("E100", name="Current")],
        groupware_users=[
            _groupware_user(
                "E100",
                user_num=701,
                login_id="current-user",
                name="Current",
            )
        ],
        key="provenance-new",
    )

    result = prune_hr_history(db, now=datetime(2026, 7, 29, 0, 30))

    assert result["user_snapshots_deleted"] == 2
    assert result["department_snapshots_deleted"] == 2
    assert db.get(HrSyncUserSnapshotRow, erp_snapshot_row_id) is None
    assert db.get(HrSyncUserSnapshotRow, groupware_snapshot_row_id) is None
    assert db.get(HrSyncOrgSnapshotRow, group_snapshot_row_id) is None
    db.refresh(person)
    db.refresh(group)
    assert person.erp_snapshot_row_id == erp_snapshot_row_id
    assert person.groupware_snapshot_row_id == groupware_snapshot_row_id
    assert group.source_snapshot_row_id == group_snapshot_row_id
    metadata = load_latest_hr_master_erp_employee_snapshot_metadata(db)
    snapshot = load_latest_hr_master_erp_employee_snapshot(db)
    assert metadata is not None
    assert snapshot is not None
    assert metadata.erp_run_id == old_erp.id
    assert metadata.captured_at == datetime(2025, 7, 1, 0, 20)
    assert snapshot.employees[0].snapshot_row_id == erp_snapshot_row_id

    for table_name in (
        "hr_master_person_rows",
        "hr_master_group_rows",
        "hr_master_conflict_rows",
    ):
        source_foreign_keys = [
            foreign_key
            for foreign_key in inspect(db.get_bind()).get_foreign_keys(table_name)
            if "source_snapshot_row_id" in foreign_key["constrained_columns"]
            or "erp_snapshot_row_id" in foreign_key["constrained_columns"]
            or "groupware_snapshot_row_id" in foreign_key["constrained_columns"]
        ]
        assert source_foreign_keys == []
