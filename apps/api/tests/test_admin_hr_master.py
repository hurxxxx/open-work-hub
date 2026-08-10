from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.auth.models import AuditLog
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.hr.erp_snapshot import (
    ERP_EMPLOYEE_SCHEMA_VERSION,
    ERP_EMPLOYEE_SCOPE_KEY,
    ERP_SOURCE_SYSTEM,
)
from open_alm_api.domains.hr.groupware_sync import GROUPWARE_SOURCE_SYSTEM
from open_alm_api.domains.hr.history import GROUPWARE_SCOPE_KEY, HR_SNAPSHOT_SCHEMA_VERSION
from open_alm_api.domains.hr.master import HR_MASTER_SCHEMA_VERSION
from open_alm_api.domains.hr.models import (
    HrIdentityResolutionState,
    HrMasterConflictRow,
    HrMasterGroupRow,
    HrMasterPersonRow,
    HrMasterRun,
    HrManualIdentityLink,
    HrSyncOrgSnapshotRow,
    HrSyncRun,
    HrSyncUserSnapshotRow,
    HrWorkforceCategoryAssignment,
)


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open ALM Admin",
            "email": "admin@open-alm.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_hr_master() -> dict[str, str]:
    captured_at = datetime(2026, 7, 29, 0, 20)
    completed_at = datetime(2026, 7, 29, 0, 30)
    erp_run_id = new_id()
    groupware_run_id = new_id()
    master_run_id = new_id()
    erp_snapshot_id = new_id()
    groupware_snapshot_id = new_id()
    conflict_snapshot_id = new_id()
    groupware_org_snapshot_id = new_id()
    person_id = new_id()
    conflict_id = new_id()

    source_runs = [
        HrSyncRun(
            id=erp_run_id,
            source_system=ERP_SOURCE_SYSTEM,
            scope_key=ERP_EMPLOYEE_SCOPE_KEY,
            trigger_kind="scheduled",
            idempotency_key="admin-hr-erp",
            status="succeeded",
            attempts=1,
            schema_version=ERP_EMPLOYEE_SCHEMA_VERSION,
            canonicalization_version="json-sort-keys-v1",
            org_row_count=1,
            user_row_count=1,
            org_snapshot_hash="a" * 64,
            user_snapshot_hash="b" * 64,
            started_at=captured_at,
            captured_at=captured_at,
            applied_at=captured_at,
            completed_at=captured_at,
            snapshot_purge_after=datetime(2027, 7, 29, 0, 20),
            created_at=captured_at,
            updated_at=captured_at,
        ),
        HrSyncRun(
            id=groupware_run_id,
            source_system=GROUPWARE_SOURCE_SYSTEM,
            scope_key=GROUPWARE_SCOPE_KEY,
            trigger_kind="scheduled",
            idempotency_key="admin-hr-groupware",
            status="succeeded",
            attempts=1,
            schema_version=HR_SNAPSHOT_SCHEMA_VERSION,
            canonicalization_version="json-sort-keys-v1",
            org_row_count=1,
            user_row_count=2,
            org_snapshot_hash="c" * 64,
            user_snapshot_hash="d" * 64,
            started_at=captured_at,
            captured_at=captured_at,
            applied_at=captured_at,
            completed_at=captured_at,
            snapshot_purge_after=datetime(2027, 7, 29, 0, 20),
            created_at=captured_at,
            updated_at=captured_at,
        ),
    ]
    snapshot_rows = [
        HrSyncUserSnapshotRow(
            id=erp_snapshot_id,
            run_id=erp_run_id,
            source_row_no=0,
            source_identity="E100",
            employee_code="E100",
            raw_payload={
                "EMP_NO": "E100",
                "NAME": "ERP Name",
                "EMAIL_ADDR": "erp@example.test",
                "ROLL_PSTN_NM": "Manager",
                "OCPT_NM": "Engineer",
                "DEPT_CD": "D001",
                "DEPT_NM": "Research",
                "BIRTHDAY": "1990-01-01",
                "HAND_TEL_NO": "010-0000-0000",
                "PAY_GRD1": "SECRET-GRADE",
            },
            row_hash="e" * 64,
            created_at=captured_at,
        ),
        HrSyncUserSnapshotRow(
            id=groupware_snapshot_id,
            run_id=groupware_run_id,
            source_row_no=0,
            domain_num=1,
            user_num=100,
            source_identity="1:100",
            employee_code="E100",
            raw_payload={
                "domain_num": 1,
                "user_num": 100,
                "com_num": "E100",
                "user_id": "erp-name",
                "kor_name": "Groupware Name",
                "email": "groupware@example.test",
                "com_position": "Lead",
                "org_code1": "GW-D001",
                "org_level": 1,
            },
            row_hash="f" * 64,
            created_at=captured_at,
        ),
        HrSyncUserSnapshotRow(
            id=conflict_snapshot_id,
            run_id=groupware_run_id,
            source_row_no=1,
            domain_num=1,
            user_num=101,
            source_identity="1:101",
            employee_code=None,
            raw_payload={
                "domain_num": 1,
                "user_num": 101,
                "com_num": None,
                "user_id": "missing-number",
                "kor_name": "Missing Number",
                "email": "missing@example.test",
                "org_code1": "GW-D001",
                "org_level": 1,
            },
            row_hash="1" * 64,
            created_at=captured_at,
        ),
        HrSyncOrgSnapshotRow(
            id=groupware_org_snapshot_id,
            run_id=groupware_run_id,
            source_row_no=0,
            domain_num=1,
            org_code="GW-D001",
            source_identity="1:GW-D001",
            raw_payload={
                "domain_num": 1,
                "org_code": "GW-D001",
                "org_depart": "Groupware Research",
                "p_org_code": None,
            },
            row_hash="3" * 64,
            created_at=captured_at,
        ),
    ]
    master_run = HrMasterRun(
        id=master_run_id,
        status="succeeded",
        idempotency_key="admin-hr-master",
        erp_run_id=erp_run_id,
        groupware_run_id=groupware_run_id,
        schema_version=HR_MASTER_SCHEMA_VERSION,
        checksum="2" * 64,
        person_row_count=1,
        group_row_count=1,
        conflict_row_count=1,
        started_at=completed_at,
        completed_at=completed_at,
        created_at=completed_at,
    )
    person = HrMasterPersonRow(
        id=person_id,
        master_run_id=master_run_id,
        employee_code="E100",
        name="ERP Name",
        position="Manager",
        occupation="Engineer",
        email="groupware@example.test",
        login_id="erp-name",
        group_source="erp",
        group_code="D001",
        group_name="Research",
        reconciliation_status="matched",
        identity_resolution_kind="employee_code",
        has_identity_conflict=False,
        erp_snapshot_row_id=erp_snapshot_id,
        groupware_snapshot_row_id=groupware_snapshot_id,
        created_at=completed_at,
    )
    group = HrMasterGroupRow(
        id=new_id(),
        master_run_id=master_run_id,
        source_system="erp",
        source_code="D001",
        name="Research",
        created_at=completed_at,
    )
    conflict = HrMasterConflictRow(
        id=conflict_id,
        master_run_id=master_run_id,
        source_system="groupware",
        reason_code="missing_employee_code",
        normalized_employee_code=None,
        source_snapshot_row_id=conflict_snapshot_id,
        details={"source_row_no": 1},
        created_at=completed_at,
    )
    with get_session_factory()() as db:
        db.add_all(source_runs)
        db.flush()
        db.add_all([*snapshot_rows, master_run])
        db.flush()
        db.add_all([person, group, conflict])
        db.commit()
    return {
        "master_run_id": master_run_id,
        "erp_run_id": erp_run_id,
        "groupware_run_id": groupware_run_id,
        "erp_snapshot_id": erp_snapshot_id,
        "groupware_snapshot_id": groupware_snapshot_id,
        "conflict_snapshot_id": conflict_snapshot_id,
        "person_id": person_id,
        "conflict_id": conflict_id,
    }


def test_admin_hr_master_grid_and_detail_expose_only_safe_fields(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    seeded = _seed_hr_master()
    headers = _auth_headers(session["token"])

    response = client.get("/api/v1/admin/hr/employees", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["latest_run"] == {
        "id": seeded["master_run_id"],
        "status": "succeeded",
        "completed_at": "2026-07-29T00:30:00",
        "source_erp_run_id": seeded["erp_run_id"],
        "source_groupware_run_id": seeded["groupware_run_id"],
        "identity_resolution_revision": 0,
        "error_code": None,
    }
    assert payload["status_counts"] == {"matched": 1, "identity_conflict": 1}
    assert payload["groups"] == [{"code": "D001", "name": "Research", "source": "erp"}]
    assert [(item["record_kind"], item["employee_code"]) for item in payload["items"]] == [
        ("person", "E100"),
        ("conflict", None),
    ]
    serialized_list = str(payload)
    assert "010-0000-0000" not in serialized_list
    assert "SECRET-GRADE" not in serialized_list
    assert "1990-01-01" not in serialized_list

    detail_response = client.get(
        f"/api/v1/admin/hr/employees/{seeded['person_id']}",
        headers=headers,
    )

    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["employee_code"] == "E100"
    assert detail["erp"]["name"] == "ERP Name"
    assert detail["groupware"]["login_id"] == "erp-name"
    assert detail["provenance"] == {
        "master_run_id": seeded["master_run_id"],
        "erp_run_id": seeded["erp_run_id"],
        "groupware_run_id": seeded["groupware_run_id"],
        "erp_snapshot_row_id": seeded["erp_snapshot_id"],
        "groupware_snapshot_row_id": seeded["groupware_snapshot_id"],
    }
    serialized_detail = str(detail)
    assert "010-0000-0000" not in serialized_detail
    assert "SECRET-GRADE" not in serialized_detail
    assert "1990-01-01" not in serialized_detail

    with get_session_factory()() as db:
        actions = set(
            db.scalars(
                select(AuditLog.action).where(
                    AuditLog.actor_user_id == session["user"]["id"],
                    AuditLog.action.in_({"hr.master.view", "hr.master.detail.view"}),
                )
            ).all()
        )
    assert actions == {"hr.master.view", "hr.master.detail.view"}


def test_admin_hr_master_grid_supports_status_and_search_filters(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    seeded = _seed_hr_master()
    headers = _auth_headers(session["token"])

    matched = client.get(
        "/api/v1/admin/hr/employees",
        params={"q": "research", "reconciliation_status": "matched"},
        headers=headers,
    )
    conflicts = client.get(
        "/api/v1/admin/hr/employees",
        params={
            "q": "missing@example.test",
            "reconciliation_status": "identity_conflict",
            "group_code": "gw-d001",
            "group_source": "groupware",
        },
        headers=headers,
    )
    second_page = client.get(
        "/api/v1/admin/hr/employees",
        params={"page": 2, "page_size": 1},
        headers=headers,
    )
    employee_code_matches = client.get(
        "/api/v1/admin/hr/employees",
        params={"identity_resolution_kind": "employee_code"},
        headers=headers,
    )
    manual_matches = client.get(
        "/api/v1/admin/hr/employees",
        params={"identity_resolution_kind": "manual"},
        headers=headers,
    )

    assert matched.status_code == 200, matched.text
    assert matched.json()["total"] == 1
    assert matched.json()["items"][0]["record_id"] == seeded["person_id"]
    assert conflicts.status_code == 200, conflicts.text
    assert conflicts.json()["total"] == 1
    assert conflicts.json()["items"][0]["record_id"] == seeded["conflict_id"]
    assert conflicts.json()["items"][0]["group_name"] == "Groupware Research"
    assert second_page.status_code == 200, second_page.text
    assert second_page.json()["total"] == 2
    assert second_page.json()["items"] == conflicts.json()["items"]
    assert employee_code_matches.status_code == 200, employee_code_matches.text
    assert employee_code_matches.json()["total"] == 1
    assert employee_code_matches.json()["items"][0]["record_id"] == seeded["person_id"]
    assert manual_matches.status_code == 200, manual_matches.text
    assert manual_matches.json()["total"] == 0


def test_admin_hr_master_status_exposes_failed_projection_attempt(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    seeded = _seed_hr_master()
    headers = _auth_headers(session["token"])
    failed_run_id = new_id()
    with get_session_factory()() as db:
        db.add(
            HrMasterRun(
                id=failed_run_id,
                status="failed",
                idempotency_key="failed-projection-attempt",
                erp_run_id=seeded["erp_run_id"],
                groupware_run_id=seeded["groupware_run_id"],
                schema_version=HR_MASTER_SCHEMA_VERSION,
                identity_resolution_revision=1,
                checksum=None,
                person_row_count=0,
                group_row_count=0,
                conflict_row_count=0,
                external_row_count=0,
                error_code="unexpected_build_error",
                started_at=datetime(2026, 7, 29, 0, 40),
                completed_at=datetime(2026, 7, 29, 0, 40),
                created_at=datetime(2026, 7, 29, 0, 40),
            )
        )
        db.commit()

    response = client.get("/api/v1/admin/hr/master-status", headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["latest_succeeded"]["id"] == seeded["master_run_id"]
    assert payload["latest_succeeded"]["identity_resolution_revision"] == 0
    assert payload["latest_attempt"] == {
        "id": failed_run_id,
        "status": "failed",
        "completed_at": "2026-07-29T00:40:00",
        "source_erp_run_id": seeded["erp_run_id"],
        "source_groupware_run_id": seeded["groupware_run_id"],
        "identity_resolution_revision": 1,
        "error_code": "unexpected_build_error",
    }


def test_admin_hr_master_detail_keeps_provenance_ids_after_source_retention(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    seeded = _seed_hr_master()
    headers = _auth_headers(session["token"])
    with get_session_factory()() as db:
        for snapshot_id in (
            seeded["erp_snapshot_id"],
            seeded["groupware_snapshot_id"],
            seeded["conflict_snapshot_id"],
        ):
            snapshot = db.get(HrSyncUserSnapshotRow, snapshot_id)
            assert snapshot is not None
            db.delete(snapshot)
        db.commit()

    person_response = client.get(
        f"/api/v1/admin/hr/employees/{seeded['person_id']}",
        headers=headers,
    )
    conflict_response = client.get(
        f"/api/v1/admin/hr/employees/{seeded['conflict_id']}",
        headers=headers,
    )

    assert person_response.status_code == 200, person_response.text
    assert person_response.json()["erp"] is None
    assert person_response.json()["groupware"] is None
    assert (
        person_response.json()["provenance"]["erp_snapshot_row_id"] == (seeded["erp_snapshot_id"])
    )
    assert (
        person_response.json()["provenance"]["groupware_snapshot_row_id"]
        == (seeded["groupware_snapshot_id"])
    )
    assert conflict_response.status_code == 200, conflict_response.text
    assert conflict_response.json()["groupware"] is None
    assert (
        conflict_response.json()["provenance"]["groupware_snapshot_row_id"]
        == seeded["conflict_snapshot_id"]
    )


def test_admin_can_directly_map_different_name_users_and_revoke(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _bootstrap_admin_session(client)
    seeded = _seed_hr_master()
    headers = _auth_headers(session["token"])
    erp_candidate_id = new_id()
    groupware_candidate_id = new_id()
    erp_candidate_snapshot_id = new_id()
    groupware_candidate_snapshot_id = new_id()
    with get_session_factory()() as db:
        db.add_all(
            [
                HrSyncUserSnapshotRow(
                    id=erp_candidate_snapshot_id,
                    run_id=seeded["erp_run_id"],
                    source_row_no=1,
                    source_identity="E200",
                    employee_code="E200",
                    raw_payload={"EMP_NO": "E200", "NAME": "ERP Candidate"},
                    row_hash="4" * 64,
                    created_at=datetime(2026, 7, 29, 0, 20),
                ),
                HrSyncUserSnapshotRow(
                    id=groupware_candidate_snapshot_id,
                    run_id=seeded["groupware_run_id"],
                    source_row_no=2,
                    domain_num=1,
                    user_num=200,
                    source_identity="1:200",
                    employee_code="G200",
                    raw_payload={
                        "domain_num": 1,
                        "user_num": 200,
                        "com_num": "G200",
                        "kor_name": "Groupware Candidate",
                    },
                    row_hash="5" * 64,
                    created_at=datetime(2026, 7, 29, 0, 20),
                ),
                HrMasterPersonRow(
                    id=erp_candidate_id,
                    master_run_id=seeded["master_run_id"],
                    employee_code="E200",
                    name="ERP Candidate",
                    group_source="erp",
                    group_code="D001",
                    group_name="Research",
                    reconciliation_status="erp_only",
                    workforce_category="unresolved",
                    identity_resolution_kind="none",
                    has_identity_conflict=False,
                    erp_snapshot_row_id=erp_candidate_snapshot_id,
                    created_at=datetime(2026, 7, 29, 0, 30),
                ),
                HrMasterPersonRow(
                    id=groupware_candidate_id,
                    master_run_id=seeded["master_run_id"],
                    employee_code="G200",
                    name="Groupware Candidate",
                    group_source="groupware",
                    group_code="GW-D001",
                    group_name="Groupware Research",
                    reconciliation_status="groupware_only",
                    workforce_category="unresolved",
                    identity_resolution_kind="none",
                    has_identity_conflict=False,
                    groupware_snapshot_row_id=groupware_candidate_snapshot_id,
                    groupware_source_identity="1:200",
                    created_at=datetime(2026, 7, 29, 0, 30),
                ),
            ]
        )
        master = db.get(HrMasterRun, seeded["master_run_id"])
        assert master is not None
        master.person_row_count += 2
        db.commit()

    detail = client.get(
        f"/api/v1/admin/hr/employees/{groupware_candidate_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["match_candidates"] == []

    erp_directory = client.get(
        "/api/v1/admin/hr/manual-match-candidates",
        params={"source": "erp", "q": "ERP Candidate"},
        headers=headers,
    )
    groupware_directory = client.get(
        "/api/v1/admin/hr/manual-match-candidates",
        params={"source": "groupware", "q": "Groupware Candidate"},
        headers=headers,
    )
    assert erp_directory.status_code == 200, erp_directory.text
    assert erp_directory.json()["items"][0]["record_id"] == erp_candidate_id
    assert groupware_directory.status_code == 200, groupware_directory.text
    assert groupware_directory.json()["items"][0]["record_id"] == groupware_candidate_id

    monkeypatch.setattr(
        "open_alm_api.domains.admin.router.dispatch_hr_master_build",
        lambda **kwargs: "task-1",
    )
    missing_reason = client.post(
        "/api/v1/admin/hr/manual-matches",
        headers=headers,
        json={
            "master_run_id": seeded["master_run_id"],
            "groupware_record_id": groupware_candidate_id,
            "erp_record_id": erp_candidate_id,
        },
    )
    assert missing_reason.status_code == 422, missing_reason.text
    assert missing_reason.json()["code"] == "admin.hr_manual_match_reason_required"

    for record_id, category_code in (
        (groupware_candidate_id, "field"),
        (erp_candidate_id, "internal"),
    ):
        assigned = client.put(
            f"/api/v1/admin/hr/employees/{record_id}/workforce-category",
            headers=headers,
            json={
                "master_run_id": seeded["master_run_id"],
                "category_code": category_code,
            },
        )
        assert assigned.status_code == 200, assigned.text
    conflicting_workforce = client.post(
        "/api/v1/admin/hr/manual-matches",
        headers=headers,
        json={
            "master_run_id": seeded["master_run_id"],
            "groupware_record_id": groupware_candidate_id,
            "erp_record_id": erp_candidate_id,
            "reason": "동일인 확인",
        },
    )
    assert conflicting_workforce.status_code == 409, conflicting_workforce.text
    assert conflicting_workforce.json()["code"] == "admin.hr_manual_match_workforce_conflict"
    for record_id in (groupware_candidate_id, erp_candidate_id):
        reset = client.request(
            "DELETE",
            f"/api/v1/admin/hr/employees/{record_id}/workforce-category",
            headers=headers,
            json={"master_run_id": seeded["master_run_id"]},
        )
        assert reset.status_code == 200, reset.text

    created = client.post(
        "/api/v1/admin/hr/manual-matches",
        headers=headers,
        json={
            "master_run_id": seeded["master_run_id"],
            "groupware_record_id": groupware_candidate_id,
            "erp_record_id": erp_candidate_id,
            "reason": "동일인 확인",
        },
    )
    assert created.status_code == 201, created.text
    created_payload = created.json()
    assert created_payload["identity_resolution_revision"] == 5
    assert created_payload["rebuild_queued"] is True
    link_id = created_payload["link_id"]

    revoked = client.post(
        f"/api/v1/admin/hr/manual-matches/{link_id}/revoke",
        headers=headers,
        json={
            "master_run_id": seeded["master_run_id"],
            "reason": "연결 재검토",
        },
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["identity_resolution_revision"] == 6
    with get_session_factory()() as db:
        link = db.get(HrManualIdentityLink, link_id)
        state = db.get(HrIdentityResolutionState, 1)
        assert link is not None
        assert link.status == "revoked"
        assert link.activated_revision == 5
        assert link.revoked_revision == 6
        assert link.revocation_reason == "연결 재검토"
        assert state is not None
        assert state.revision == 6


def test_admin_manages_workforce_categories_and_person_override(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _bootstrap_admin_session(client)
    seeded = _seed_hr_master()
    headers = _auth_headers(session["token"])
    monkeypatch.setattr(
        "open_alm_api.domains.admin.router.dispatch_hr_master_build",
        lambda **kwargs: "task-1",
    )

    categories = client.get(
        "/api/v1/admin/hr/workforce-categories",
        headers=headers,
    )
    assert categories.status_code == 200, categories.text
    assert {item["code"] for item in categories.json()["items"]} >= {
        "internal",
        "field",
        "external",
        "unresolved",
    }

    created = client.post(
        "/api/v1/admin/hr/workforce-categories",
        headers=headers,
        json={"name": "프로젝트 인력", "description": "프로젝트 전담"},
    )
    assert created.status_code == 201, created.text
    category_code = created.json()["code"]
    assert category_code.startswith("custom-")

    updated = client.patch(
        f"/api/v1/admin/hr/workforce-categories/{category_code}",
        headers=headers,
        json={"name": "프로젝트 전담", "description": "관리자 지정"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "프로젝트 전담"

    assigned = client.put(
        f"/api/v1/admin/hr/employees/{seeded['person_id']}/workforce-category",
        headers=headers,
        json={
            "master_run_id": seeded["master_run_id"],
            "category_code": category_code,
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["changed"] is True
    assert assigned.json()["identity_resolution_revision"] == 1

    in_use = client.delete(
        f"/api/v1/admin/hr/workforce-categories/{category_code}",
        headers=headers,
    )
    assert in_use.status_code == 409, in_use.text
    assert in_use.json()["code"] == "admin.hr_workforce_category_in_use"

    reset = client.request(
        "DELETE",
        f"/api/v1/admin/hr/employees/{seeded['person_id']}/workforce-category",
        headers=headers,
        json={"master_run_id": seeded["master_run_id"]},
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["changed"] is True
    assert reset.json()["identity_resolution_revision"] == 2

    archived = client.delete(
        f"/api/v1/admin/hr/workforce-categories/{category_code}",
        headers=headers,
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["is_active"] is False
    replacement = client.post(
        "/api/v1/admin/hr/workforce-categories",
        headers=headers,
        json={"name": "프로젝트 전담"},
    )
    assert replacement.status_code == 201, replacement.text
    duplicate_restore = client.patch(
        f"/api/v1/admin/hr/workforce-categories/{category_code}",
        headers=headers,
        json={"is_active": True},
    )
    assert duplicate_restore.status_code == 409, duplicate_restore.text
    assert duplicate_restore.json()["code"] == "admin.hr_workforce_category_name_exists"

    with get_session_factory()() as db:
        assignments = list(
            db.scalars(
                select(HrWorkforceCategoryAssignment).where(
                    HrWorkforceCategoryAssignment.category_code == category_code
                )
            ).all()
        )
        assert len(assignments) == 1
        assert assignments[0].status == "revoked"
        assert assignments[0].activated_revision == 1
        assert assignments[0].revoked_revision == 2
