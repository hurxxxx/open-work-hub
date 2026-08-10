from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.auth.models import AuditLog, OrgUnit, User
from open_alm_api.domains.auth.platform_api_keys import PlatformApiPrincipal
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.hr.erp_snapshot import (
    ERP_EMPLOYEE_SCHEMA_VERSION,
    ERP_EMPLOYEE_SCOPE_KEY,
    ERP_SOURCE_SYSTEM,
)
from open_alm_api.domains.hr.groupware_sync import GROUPWARE_SOURCE_SYSTEM
from open_alm_api.domains.hr.history import (
    GROUPWARE_SCOPE_KEY,
    HR_SNAPSHOT_SCHEMA_VERSION,
    canonical_payload_hash,
)
from open_alm_api.domains.hr.integration_router import (
    require_hr_integration_read,
    router as hr_integration_router,
)
from open_alm_api.domains.hr.master import (
    HR_MASTER_SCHEMA_VERSION,
    HrMasterErpEmployee,
)
from open_alm_api.domains.hr.models import (
    HrMasterConflictRow,
    HrMasterExternalPersonRow,
    HrMasterGroupRow,
    HrMasterPersonRow,
    HrMasterRun,
    HrSyncRun,
    HrWorkforceCategory,
)


pytestmark = pytest.mark.fresh_api_app

TEST_API_KEY_ID = "00000000-0000-0000-0000-000000000901"
CAPTURED_AT = datetime(2026, 7, 29, 0, 20)
COMPLETED_AT = datetime(2026, 7, 29, 0, 30)


@pytest.fixture
def hr_client(client: TestClient) -> TestClient:
    employee_path = "/api/v1/integrations/hr/employees"
    if not any(getattr(route, "path", None) == employee_path for route in client.app.routes):
        client.app.include_router(hr_integration_router, prefix="/api/v1")
        client.app.openapi_schema = None
    client.app.dependency_overrides[require_hr_integration_read] = lambda: PlatformApiPrincipal(
        key_id=TEST_API_KEY_ID,
        scopes=frozenset({"hr:read"}),
    )
    return client


def _source_run(
    *,
    run_id: str,
    source_system: str,
    scope_key: str,
    schema_version: str,
    user_count: int,
    org_count: int,
) -> HrSyncRun:
    return HrSyncRun(
        id=run_id,
        source_system=source_system,
        scope_key=scope_key,
        trigger_kind="scheduled",
        idempotency_key=f"integration-{run_id}",
        status="succeeded",
        attempts=1,
        schema_version=schema_version,
        canonicalization_version="test-v1",
        org_row_count=org_count,
        user_row_count=user_count,
        active_user_row_count=user_count,
        org_snapshot_hash="a" * 64,
        user_snapshot_hash="b" * 64,
        started_at=CAPTURED_AT,
        captured_at=CAPTURED_AT,
        applied_at=CAPTURED_AT,
        completed_at=CAPTURED_AT,
        snapshot_purge_after=datetime(2027, 7, 29, 0, 20),
        created_at=CAPTURED_AT,
        updated_at=CAPTURED_AT,
    )


def _groupware_user(
    *,
    user_id: str,
    login_id: str,
    email: str,
    employee_code: str | None,
    name: str,
    org_id: str,
    user_num: int,
    synced_at: datetime = CAPTURED_AT,
) -> User:
    return User(
        id=user_id,
        login_id=login_id,
        email=email,
        full_name=name,
        display_name=name,
        employee_code=employee_code,
        job_title="Groupware Position",
        password_hash="not-used",
        auth_provider="groupware",
        status="active",
        login_blocked=False,
        is_admin=False,
        must_change_password=False,
        theme_preference="system",
        locale="ko-KR",
        time_zone="Asia/Seoul",
        date_format="korean",
        primary_org_unit_id=org_id,
        hr_source_system=GROUPWARE_SOURCE_SYSTEM,
        hr_domain_num=1,
        hr_user_num=user_num,
        hr_com_state=1,
        hr_last_synced_at=synced_at,
        created_at=CAPTURED_AT,
    )


def _seed_hr_integration_projection() -> dict[str, str]:
    erp_run_id = new_id()
    groupware_run_id = new_id()
    master_run_id = new_id()
    groupware_org_id = new_id()
    stale_groupware_org_id = new_id()
    matched_user_id = new_id()
    duplicate_employee_code_user_id = new_id()
    external_user_id = new_id()
    stale_groupware_user_id = new_id()
    erp_snapshot_row_id = new_id()
    groupware_snapshot_row_id = new_id()
    external_snapshot_row_id = new_id()

    erp_employee = HrMasterErpEmployee(
        snapshot_row_id=erp_snapshot_row_id,
        employee_code="E100",
        name="ERP Employee",
        department_code="D001",
        department_name="Research",
        position="Manager",
        occupation="Engineer",
        birth_date=date(1990, 1, 1),
        hire_date=date(2020, 2, 3),
        phone_number="010-1234-5678",
    )
    erp_projection_hash = canonical_payload_hash([erp_employee.projection_payload()])

    erp_run = _source_run(
        run_id=erp_run_id,
        source_system=ERP_SOURCE_SYSTEM,
        scope_key=ERP_EMPLOYEE_SCOPE_KEY,
        schema_version=ERP_EMPLOYEE_SCHEMA_VERSION,
        user_count=1,
        org_count=1,
    )
    groupware_run = _source_run(
        run_id=groupware_run_id,
        source_system=GROUPWARE_SOURCE_SYSTEM,
        scope_key=GROUPWARE_SCOPE_KEY,
        schema_version=HR_SNAPSHOT_SCHEMA_VERSION,
        user_count=3,
        org_count=1,
    )
    groupware_org = OrgUnit(
        id=groupware_org_id,
        name="Groupware Research",
        slug=f"groupware-{groupware_org_id}",
        unit_type="group",
        active=True,
        hr_source_system=GROUPWARE_SOURCE_SYSTEM,
        hr_domain_num=1,
        hr_org_code="GW-D001",
        hr_last_synced_at=CAPTURED_AT,
        created_at=CAPTURED_AT,
        updated_at=CAPTURED_AT,
    )
    stale_groupware_org = OrgUnit(
        id=stale_groupware_org_id,
        name="Historical Groupware Org",
        slug=f"groupware-{stale_groupware_org_id}",
        unit_type="group",
        active=False,
        hr_source_system=GROUPWARE_SOURCE_SYSTEM,
        hr_domain_num=1,
        hr_org_code="GW-HISTORICAL",
        hr_last_synced_at=CAPTURED_AT - timedelta(days=1),
        created_at=CAPTURED_AT - timedelta(days=1),
        updated_at=CAPTURED_AT - timedelta(days=1),
    )
    matched_user = _groupware_user(
        user_id=matched_user_id,
        login_id="matched-user",
        email="matched@example.test",
        employee_code="E100",
        name="Groupware Employee",
        org_id=groupware_org_id,
        user_num=100,
    )
    external_user = _groupware_user(
        user_id=external_user_id,
        login_id="external-user",
        email="external-user@groupware.local",
        employee_code="Z0000",
        name="External User",
        org_id=groupware_org_id,
        user_num=101,
    )
    duplicate_employee_code_user = _groupware_user(
        user_id=duplicate_employee_code_user_id,
        login_id="duplicate-employee-code",
        email="duplicate@example.test",
        employee_code="E100",
        name="Duplicate Employee Code",
        org_id=groupware_org_id,
        user_num=102,
    )
    stale_groupware_user = _groupware_user(
        user_id=stale_groupware_user_id,
        login_id="historical-user",
        email="historical@example.test",
        employee_code="E099",
        name="Historical User",
        org_id=stale_groupware_org_id,
        user_num=99,
        synced_at=CAPTURED_AT - timedelta(days=1),
    )
    master_run = HrMasterRun(
        id=master_run_id,
        status="succeeded",
        idempotency_key="hr-integration-master",
        erp_run_id=erp_run_id,
        groupware_run_id=groupware_run_id,
        schema_version=HR_MASTER_SCHEMA_VERSION,
        identity_resolution_revision=7,
        checksum="c" * 64,
        erp_projection_hash=erp_projection_hash,
        person_row_count=1,
        external_row_count=1,
        group_row_count=2,
        conflict_row_count=1,
        result_payload={"erp_employee_count": 1},
        started_at=COMPLETED_AT,
        completed_at=COMPLETED_AT,
        created_at=COMPLETED_AT,
    )
    person = HrMasterPersonRow(
        id=new_id(),
        master_run_id=master_run_id,
        employee_code="E100",
        name="ERP Employee",
        position="Manager",
        occupation="Engineer",
        birth_date=date(1990, 1, 1),
        hire_date=date(2020, 2, 3),
        phone_number="010-1234-5678",
        email="matched@example.test",
        login_id="matched-user",
        group_source="erp",
        group_code="D001",
        group_name="Research",
        reconciliation_status="matched",
        inferred_workforce_category="internal",
        workforce_category="internal",
        workforce_category_resolution_kind="inferred",
        identity_resolution_kind="employee_code",
        has_identity_conflict=True,
        erp_snapshot_row_id=erp_snapshot_row_id,
        groupware_snapshot_row_id=groupware_snapshot_row_id,
        groupware_source_identity="1:100",
        created_at=COMPLETED_AT,
    )
    external = HrMasterExternalPersonRow(
        id=new_id(),
        master_run_id=master_run_id,
        groupware_source_identity="1:101",
        employee_code="Z0000",
        name="External User",
        position="External",
        email="external-user@groupware.local",
        login_id="external-user",
        group_code="GW-D001",
        group_name="Groupware Research",
        inferred_workforce_category="external",
        workforce_category="external",
        workforce_category_resolution_kind="inferred",
        groupware_snapshot_row_id=external_snapshot_row_id,
        created_at=COMPLETED_AT,
    )
    conflict = HrMasterConflictRow(
        id=new_id(),
        master_run_id=master_run_id,
        source_system="groupware",
        reason_code="private:must-not-leak",
        normalized_employee_code="E999",
        source_snapshot_row_id=new_id(),
        details={"source_row_no": 99, "raw_name": "must-not-leak"},
        workforce_category="unresolved",
        created_at=COMPLETED_AT,
    )
    groups = [
        HrMasterGroupRow(
            id=new_id(),
            master_run_id=master_run_id,
            source_system="erp",
            source_code="D001",
            name="Research",
            source_snapshot_row_id=new_id(),
            created_at=COMPLETED_AT,
        ),
        HrMasterGroupRow(
            id=new_id(),
            master_run_id=master_run_id,
            source_system="groupware",
            source_code="GW-D001",
            name="Groupware Research",
            source_snapshot_row_id=new_id(),
            created_at=COMPLETED_AT,
        ),
    ]

    with get_session_factory()() as db:
        db.add_all([erp_run, groupware_run])
        db.flush()
        db.add_all([groupware_org, stale_groupware_org])
        db.flush()
        db.add_all(
            [
                matched_user,
                external_user,
                duplicate_employee_code_user,
                stale_groupware_user,
                master_run,
            ]
        )
        db.flush()
        db.add_all([person, external, conflict, *groups])
        db.commit()
    return {
        "erp_run_id": erp_run_id,
        "groupware_run_id": groupware_run_id,
        "master_run_id": master_run_id,
        "matched_user_id": matched_user_id,
        "duplicate_employee_code_user_id": duplicate_employee_code_user_id,
        "external_user_id": external_user_id,
        "stale_groupware_user_id": stale_groupware_user_id,
        "erp_snapshot_row_id": erp_snapshot_row_id,
        "groupware_snapshot_row_id": groupware_snapshot_row_id,
    }


def test_hr_integration_employee_bases_are_typed_pinned_and_safe(
    hr_client: TestClient,
) -> None:
    seeded = _seed_hr_integration_projection()

    erp = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "erp", "page_size": 1},
    )
    groupware = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "groupware"},
    )
    integrated = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "integrated", "snapshot_id": seeded["master_run_id"]},
    )

    assert erp.status_code == 200, erp.text
    assert erp.headers["cache-control"] == "private, no-store"
    assert erp.headers["pragma"] == "no-cache"
    assert erp.json()["snapshot_id"] == seeded["master_run_id"]
    assert erp.json()["source_erp_run_id"] == seeded["erp_run_id"]
    assert erp.json()["source_groupware_run_id"] is None
    assert erp.json()["items"][0]["subject_id"] == "employee:E100"
    assert erp.json()["items"][0]["has_erp"] is True
    assert erp.json()["items"][0]["has_groupware"] is False
    assert erp.json()["items"][0]["phone_number"] == "010-1234-5678"

    assert groupware.status_code == 200, groupware.text
    assert groupware.headers["cache-control"] == "private, no-store"
    assert groupware.headers["pragma"] == "no-cache"
    groupware_payload = groupware.json()
    assert len(groupware_payload["snapshot_id"]) == 64
    assert groupware_payload["projection_hash"] == groupware_payload["snapshot_id"]
    assert groupware_payload["source_groupware_run_id"] == seeded["groupware_run_id"]
    assert groupware_payload["total"] == 3
    assert all(item["phone_number"] is None for item in groupware_payload["items"])
    subject_ids = [item["subject_id"] for item in groupware_payload["items"]]
    assert len(subject_ids) == len(set(subject_ids))
    assert all(subject_id.startswith("groupware:") for subject_id in subject_ids)
    external_groupware = next(
        item for item in groupware_payload["items"] if item["record_kind"] == "external"
    )
    assert external_groupware["email"] is None
    assert external_groupware["account_status"] == "active"
    for user_id in (
        seeded["matched_user_id"],
        seeded["duplicate_employee_code_user_id"],
        seeded["external_user_id"],
        seeded["stale_groupware_user_id"],
    ):
        assert user_id not in groupware.text
    assert "Historical User" not in groupware.text

    assert integrated.status_code == 200, integrated.text
    assert integrated.headers["cache-control"] == "private, no-store"
    assert integrated.headers["pragma"] == "no-cache"
    integrated_payload = integrated.json()
    assert integrated_payload["projection_hash"] == "c" * 64
    assert integrated_payload["source_erp_run_id"] == seeded["erp_run_id"]
    assert integrated_payload["source_groupware_run_id"] == seeded["groupware_run_id"]
    assert integrated_payload["identity_resolution_revision"] == 7
    assert integrated_payload["total"] == 3
    matched = next(item for item in integrated_payload["items"] if item["employee_code"] == "E100")
    assert matched["reconciliation_status"] == "identity_conflict"
    assert matched["inferred_workforce_category"] == "internal"
    assert matched["account_status"] is None
    assert matched["phone_number"] == "010-1234-5678"
    external_integrated = next(
        item for item in integrated_payload["items"] if item["record_kind"] == "external"
    )
    assert external_integrated["email"] is None
    assert external_integrated["phone_number"] is None
    conflict_integrated = next(
        item for item in integrated_payload["items"] if item["record_kind"] == "conflict"
    )
    assert conflict_integrated["reconciliation_detail"] == "unclassified_conflict"
    assert conflict_integrated["phone_number"] is None

    serialized = integrated.text
    assert "login_blocked" not in serialized
    assert seeded["erp_snapshot_row_id"] not in serialized
    assert seeded["groupware_snapshot_row_id"] not in serialized
    assert "1:100" not in serialized
    assert "source_row_no" not in serialized
    assert "must-not-leak" not in serialized

    stale = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "integrated", "snapshot_id": "x" * 80},
    )
    oversized = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "erp", "page_size": 201},
    )
    assert stale.status_code == 409
    assert stale.headers["cache-control"] == "private, no-store"
    assert stale.headers["pragma"] == "no-cache"
    assert stale.json()["code"] == "hr.integration_snapshot_changed"
    assert oversized.status_code == 422

    with get_session_factory()() as db:
        failed_audit = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "hr.integration.employees.read")
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        )
        assert failed_audit is not None
        assert failed_audit.entity_id is None
        assert failed_audit.payload["snapshot_id"] is None
        assert failed_audit.payload["outcome"] == "failed"
        assert failed_audit.payload["error_code"] == "hr.integration_snapshot_changed"
        assert failed_audit.payload["requested_snapshot_id_provided"] is True
        assert "x" * 80 not in str(failed_audit.payload)


def test_groupware_snapshot_pin_changes_when_current_projection_is_mutated(
    hr_client: TestClient,
) -> None:
    seeded = _seed_hr_integration_projection()
    initial = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "groupware"},
    )
    assert initial.status_code == 200, initial.text
    initial_snapshot_id = initial.json()["snapshot_id"]

    with get_session_factory()() as db:
        user = db.get(User, seeded["matched_user_id"])
        assert user is not None
        user.status = "suspended"
        db.add(user)
        db.commit()

    stale_pin = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={
            "basis": "groupware",
            "snapshot_id": initial_snapshot_id,
        },
    )
    assert stale_pin.status_code == 409
    assert stale_pin.headers["cache-control"] == "private, no-store"
    assert stale_pin.headers["pragma"] == "no-cache"
    assert stale_pin.json()["code"] == "hr.integration_snapshot_changed"

    current = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "groupware"},
    )
    assert current.status_code == 200, current.text
    assert current.json()["snapshot_id"] != initial_snapshot_id
    changed = next(item for item in current.json()["items"] if item["name"] == "Groupware Employee")
    assert changed["account_status"] == "suspended"


def test_hr_integration_groups_status_categories_and_audit_are_bounded(
    hr_client: TestClient,
) -> None:
    seeded = _seed_hr_integration_projection()
    with get_session_factory()() as db:
        db.add(
            HrWorkforceCategory(
                code="custom-inactive",
                name="Inactive category",
                description="Archived",
                is_system=False,
                is_active=False,
                sort_order=999,
                created_at=CAPTURED_AT,
                updated_at=CAPTURED_AT,
            )
        )
        db.commit()

    groups = hr_client.get(
        "/api/v1/integrations/hr/groups",
        params={"basis": "integrated", "page": 1, "page_size": 1},
    )
    status = hr_client.get(
        "/api/v1/integrations/hr/status",
        params={"basis": "groupware"},
    )
    active_categories = hr_client.get(
        "/api/v1/integrations/hr/workforce-categories",
    )
    all_categories = hr_client.get(
        "/api/v1/integrations/hr/workforce-categories",
        params={"include_inactive": True},
    )

    assert groups.status_code == 200, groups.text
    assert groups.headers["cache-control"] == "private, no-store"
    assert groups.headers["pragma"] == "no-cache"
    assert groups.json()["total"] == 2
    assert groups.json()["items"] == [
        {
            "subject_id": "group:erp:D001",
            "code": "D001",
            "name": "Research",
            "source": "erp",
            "parent_code": None,
            "is_active": True,
        }
    ]
    assert status.status_code == 200, status.text
    assert status.headers["cache-control"] == "private, no-store"
    assert status.headers["pragma"] == "no-cache"
    assert status.json()["available"] is True
    assert len(status.json()["snapshot_id"]) == 64
    assert status.json()["projection_hash"] == status.json()["snapshot_id"]
    assert status.json()["source_groupware_run_id"] == seeded["groupware_run_id"]
    assert active_categories.headers["cache-control"] == "private, no-store"
    assert active_categories.headers["pragma"] == "no-cache"
    assert all_categories.headers["cache-control"] == "private, no-store"
    assert all_categories.headers["pragma"] == "no-cache"
    assert "custom-inactive" not in {item["code"] for item in active_categories.json()["items"]}
    assert "custom-inactive" in {item["code"] for item in all_categories.json()["items"]}

    with get_session_factory()() as db:
        audits = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.action.like("hr.integration.%"))
                .order_by(AuditLog.created_at, AuditLog.id)
            ).all()
        )
    assert len(audits) == 4
    for audit in audits:
        assert set(audit.payload) == {
            "api_key_id",
            "basis",
            "snapshot_id",
            "page",
            "page_size",
            "result_count",
            "outcome",
            "error_code",
            "requested_snapshot_id_provided",
        }
        assert audit.payload["api_key_id"] == TEST_API_KEY_ID
        assert audit.payload["outcome"] == "succeeded"
        assert audit.payload["error_code"] is None
        serialized_payload = str(audit.payload)
        assert "ERP Employee" not in serialized_payload
        assert "E100" not in serialized_payload


def test_hr_integration_erp_never_falls_back_to_raw_succeeded_snapshot(
    hr_client: TestClient,
) -> None:
    seeded = _seed_hr_integration_projection()
    with get_session_factory()() as db:
        db.execute(delete(HrMasterRun).where(HrMasterRun.id == seeded["master_run_id"]))
        db.commit()

    response = hr_client.get(
        "/api/v1/integrations/hr/employees",
        params={"basis": "erp"},
    )

    assert response.status_code == 503
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["code"] == "hr.integration_snapshot_unavailable"


def test_hr_integration_openapi_declares_scoped_error_contracts(
    hr_client: TestClient,
) -> None:
    hr_client.app.openapi_schema = None
    schema = hr_client.app.openapi()
    operations = [
        schema["paths"][path]["get"]
        for path in (
            "/api/v1/integrations/hr/employees",
            "/api/v1/integrations/hr/groups",
            "/api/v1/integrations/hr/status",
            "/api/v1/integrations/hr/workforce-categories",
        )
    ]

    assert all(operation["tags"] == ["hr-integrations"] for operation in operations)
    assert all(operation["security"] == [{"PlatformApiKey": []}] for operation in operations)
    assert schema["components"]["securitySchemes"]["PlatformApiKey"] == {
        "type": "http",
        "description": "Platform API key using the aido_pk_ token format.",
        "scheme": "bearer",
    }
    employee_operation = operations[0]
    assert {"401", "403", "409", "503"} <= set(employee_operation["responses"])
    assert employee_operation["operationId"] == "hr_integrations_list_employees_get"
    phone_number_schema = schema["components"]["schemas"]["HrIntegrationEmployeeResponse"][
        "properties"
    ]["phone_number"]
    assert phone_number_schema == {
        "anyOf": [{"type": "string"}, {"type": "null"}],
        "title": "Phone Number",
    }
