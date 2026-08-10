from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.auth.models import AuditLog, PlatformAppVisibility
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.hr.erp_snapshot import (
    ERP_EMPLOYEE_SCHEMA_VERSION,
    ERP_EMPLOYEE_SCOPE_KEY,
    ERP_SOURCE_SYSTEM,
)
from open_alm_api.domains.hr.models import HrSyncRun
from tests.dev_accounts import auth_headers, dev_login


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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


def _set_platform_visibility(app_id: str, visible: bool) -> None:
    with get_session_factory()() as db:
        row = db.scalar(select(PlatformAppVisibility).where(PlatformAppVisibility.app_id == app_id))
        assert row is not None
        row.visible = visible
        db.add(row)
        db.commit()


def test_admin_lists_operational_batches(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)

    response = client.get(
        "/api/v1/admin/batches",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    items = {item["id"]: item for item in payload["items"]}
    assert set(items) == {
        "erp-hr",
        "groupware-hr",
        "integrated-hr",
        "news",
        "industry-report",
        "qna-board",
    }
    assert items["erp-hr"]["task_name"] == "hr.capture_erp_snapshot"
    assert items["erp-hr"]["queue"] == "celery"
    assert items["erp-hr"]["schedule"]["kind"] == "daily"
    assert items["erp-hr"]["schedule"]["time_zone"] == "Asia/Seoul"
    assert items["erp-hr"]["last_run"] is None
    assert items["groupware-hr"]["task_name"] == "hr.sync_groupware"
    assert items["groupware-hr"]["queue"] == "celery"
    assert items["groupware-hr"]["schedule"]["kind"] == "daily"
    assert items["groupware-hr"]["schedule"]["time_zone"] == "Asia/Seoul"
    assert items["groupware-hr"]["last_run"] is None
    assert items["integrated-hr"]["task_name"] == "hr.build_master"
    assert items["integrated-hr"]["queue"] == "celery"
    assert items["integrated-hr"]["schedule"] == {
        "enabled": False,
        "kind": "daily",
        "hour": 3,
        "minute": 30,
        "every_hours": None,
        "time_zone": "Asia/Seoul",
    }
    assert items["integrated-hr"]["last_run"] is None
    assert items["news"]["task_name"] == "news.collect_all"
    assert items["news"]["queue"] == "news"
    assert items["news"]["schedule"]["kind"] == "interval"
    assert items["news"]["schedule"]["every_hours"] == 2
    assert items["industry-report"]["task_name"] == "industry_report.collect_all"
    assert items["industry-report"]["queue"] == "news"
    assert items["industry-report"]["schedule"]["kind"] == "daily"
    assert items["industry-report"]["schedule"]["hour"] == 7
    assert items["industry-report"]["schedule"]["minute"] == 0


def test_admin_can_queue_groupware_hr_batch(client: TestClient, monkeypatch) -> None:
    session = _bootstrap_admin_session(client)

    monkeypatch.setattr(
        "open_alm_api.domains.admin.router.dispatch_groupware_hr_sync",
        lambda *, force: "task-123" if force else None,
    )

    response = client.post(
        "/api/v1/admin/batches/groupware-hr/run",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batch"]["id"] == "groupware-hr"
    assert payload["task_id"] == "task-123"
    assert payload["queued_at"]


def test_admin_can_queue_erp_hr_snapshot_without_exposing_source_rows(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _bootstrap_admin_session(client)

    monkeypatch.setattr(
        "open_alm_api.domains.admin.router.dispatch_erp_hr_snapshot",
        lambda *, force: "erp-task-123" if force else None,
    )

    response = client.post(
        "/api/v1/admin/batches/erp-hr/run",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batch"]["id"] == "erp-hr"
    assert payload["batch"]["last_run"] is None
    assert payload["task_id"] == "erp-task-123"
    assert payload["queued_at"]

    with get_session_factory()() as db:
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.action == "admin.batch.run",
                AuditLog.entity_kind == "batch",
                AuditLog.entity_id == "erp-hr",
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        )
        assert audit is not None
        assert audit.actor_user_id == session["user"]["id"]
        assert audit.payload == {
            "task_name": "hr.capture_erp_snapshot",
            "task_id": "erp-task-123",
            "mode": "snapshot_only",
        }


def test_admin_erp_hr_batch_reports_snapshot_metadata_without_pii(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    captured_at = datetime(2026, 7, 21, 15, 30)
    run_id = new_id()
    run = HrSyncRun(
        id=run_id,
        source_system=ERP_SOURCE_SYSTEM,
        scope_key=ERP_EMPLOYEE_SCOPE_KEY,
        trigger_kind="manual",
        celery_task_id="erp-task-sensitive",
        idempotency_key="erp-task-sensitive",
        status="succeeded",
        attempts=1,
        schema_version=ERP_EMPLOYEE_SCHEMA_VERSION,
        canonicalization_version="json-sort-keys-v1",
        user_row_count=698,
        result_payload={
            "mode": "snapshot_only",
            "rows_seen": 698,
            "employee_code": "must-not-leak",
            "employee_name": "must-not-leak",
            "email": "must-not-leak@example.com",
        },
        started_at=captured_at,
        captured_at=captured_at,
        applied_at=captured_at,
        completed_at=captured_at,
        snapshot_purge_after=datetime(2027, 7, 21, 15, 30),
        created_at=captured_at,
        updated_at=captured_at,
    )
    with get_session_factory()() as db:
        db.add(run)
        db.commit()

    response = client.get(
        "/api/v1/admin/batches",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 200, response.text
    erp_batch = next(item for item in response.json()["items"] if item["id"] == "erp-hr")
    assert erp_batch["last_run"] == {
        "completed_at": "2026-07-21T15:30:00",
        "summary": "ERP HR snapshot succeeded",
        "payload": {
            "run_id": run_id,
            "status": "succeeded",
            "mode": "snapshot_only",
            "rows_seen": 698,
        },
    }
    serialized = str(erp_batch)
    assert "must-not-leak" not in serialized
    assert "must-not-leak@example.com" not in serialized


def test_admin_can_queue_integrated_hr_master_batch(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _bootstrap_admin_session(client)
    monkeypatch.setattr(
        "open_alm_api.domains.admin.router.dispatch_hr_master_build",
        lambda *, force: "master-task-123" if force else None,
    )

    response = client.post(
        "/api/v1/admin/batches/integrated-hr/run",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batch"]["id"] == "integrated-hr"
    assert payload["task_id"] == "master-task-123"
    with get_session_factory()() as db:
        audit = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.action == "admin.batch.run",
                AuditLog.entity_id == "integrated-hr",
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        )
        assert audit is not None
        assert audit.payload == {
            "task_name": "hr.build_master",
            "task_id": "master-task-123",
        }


def test_erp_hr_batch_requires_admin_permission(client: TestClient, monkeypatch) -> None:
    def fail_dispatch(*, force: bool) -> None:
        raise AssertionError(f"unauthorized ERP batch must not dispatch (force={force})")

    monkeypatch.setattr(
        "open_alm_api.domains.admin.router.dispatch_erp_hr_snapshot",
        fail_dispatch,
    )
    headers = auth_headers(dev_login(client, "delivery-hub-member")["token"])

    response = client.post("/api/v1/admin/batches/erp-hr/run", headers=headers)

    assert response.status_code == 403, response.text


def test_admin_can_queue_news_batch(client: TestClient, monkeypatch) -> None:
    session = _bootstrap_admin_session(client)

    monkeypatch.setattr(
        "open_alm_api.domains.news.dispatch.dispatch_collect_all",
        lambda *, force: "news-task-123" if force else None,
    )

    response = client.post(
        "/api/v1/admin/batches/news/run",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batch"]["id"] == "news"
    assert payload["task_id"] == "news-task-123"


def test_admin_can_queue_industry_report_batch(client: TestClient, monkeypatch) -> None:
    session = _bootstrap_admin_session(client)

    monkeypatch.setattr(
        "open_alm_api.domains.industry_report.dispatch.dispatch_collect_all",
        lambda *, force: "report-task-123" if force else None,
    )

    response = client.post(
        "/api/v1/admin/batches/industry-report/run",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batch"]["id"] == "industry-report"
    assert payload["task_id"] == "report-task-123"


def test_admin_cannot_queue_news_batches_while_app_is_disabled(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _bootstrap_admin_session(client)
    _set_platform_visibility("news", False)

    def fail_dispatch(*, force: bool) -> None:
        raise AssertionError(f"disabled News batch must not dispatch (force={force})")

    monkeypatch.setattr(
        "open_alm_api.domains.news.dispatch.dispatch_collect_all",
        fail_dispatch,
    )
    monkeypatch.setattr(
        "open_alm_api.domains.industry_report.dispatch.dispatch_collect_all",
        fail_dispatch,
    )

    for batch_id in ("news", "industry-report"):
        response = client.post(
            f"/api/v1/admin/batches/{batch_id}/run",
            headers=_auth_headers(session["token"]),
        )
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "platform.app_disabled"


def test_admin_cannot_queue_qna_batch_while_app_is_disabled(
    client: TestClient,
    monkeypatch,
) -> None:
    session = _bootstrap_admin_session(client)
    _set_platform_visibility("qa-assistant", False)

    def fail_dispatch() -> None:
        raise AssertionError("disabled Q&A batch must not dispatch")

    monkeypatch.setattr(
        "open_alm_api.domains.admin.router.dispatch_board_sync",
        fail_dispatch,
    )

    response = client.post(
        "/api/v1/admin/batches/qna-board/run",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "platform.app_disabled"
