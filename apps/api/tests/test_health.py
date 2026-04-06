from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    database_path = tmp_path / "aidoo-test.sqlite3"
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("DOOWON_API_SESSION_TTL_HOURS", "1")

    from aidoo_api.core.db import get_engine, get_session_factory
    from aidoo_api.core.settings import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from aidoo_api.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    get_engine().dispose()
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_bootstrap_and_protected_search(client: TestClient) -> None:
    status_response = client.get("/api/v1/auth/bootstrap-status")
    assert status_response.status_code == 200
    assert status_response.json() == {"requires_setup": True}

    unauthenticated = client.post(
        "/api/v1/search/documents",
        json={"query": "compressor specification"},
    )
    assert unauthenticated.status_code == 401

    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201
    auth_payload = setup_response.json()
    assert auth_payload["user"]["is_admin"] is True
    token = auth_payload["token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "admin@aidoo.local"

    search_response = client.post(
        "/api/v1/search/documents",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "compressor specification"},
    )
    assert search_response.status_code == 200
    payload = search_response.json()
    assert payload["scenario_id"] == "documents-rag"
    assert payload["hits"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 204

    expired_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert expired_response.status_code == 401


def test_documents_search_filters_and_grounded_answer(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    token = setup_response.json()["token"]

    response = client.post(
        "/api/v1/search/documents",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "query": "seal material change notice",
            "filters": {
                "doc_type": ["revision-note"],
                "project": ["Project A"],
                "department": ["Engineering"],
            },
            "answer_mode": "grounded-answer",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters_applied"]["doc_type"] == ["revision-note"]
    assert payload["hits"][0]["document_id"] == "doc-revision-002"
    assert payload["grounded_answer"]["citations"]
    assert payload["grounded_answer"]["citations"][0]["page_reference"] == "pp. 2-3"


def _bootstrap_admin(client: TestClient) -> str:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201
    return setup_response.json()["token"]


def _create_direct_user(
    *,
    email: str,
    full_name: str,
    password: str = "supersecret123",
    is_admin: bool = False,
) -> tuple[str, str]:
    from aidoo_api.core.db import get_session_factory
    from aidoo_api.domains.auth.models import AuthSession, User
    from aidoo_api.domains.auth.security import (
        hash_password,
        issue_session_token,
        new_id,
        normalize_email,
    )

    session_token = issue_session_token(ttl_hours=1)
    user_id = new_id()
    db = get_session_factory()()
    try:
        db.add(
            User(
                id=user_id,
                email=normalize_email(email),
                full_name=full_name,
                password_hash=hash_password(password),
                is_admin=is_admin,
            )
        )
        db.add(
            AuthSession(
                id=new_id(),
                user_id=user_id,
                token_hash=session_token.token_hash,
                expires_at=session_token.expires_at,
            )
        )
        db.commit()
    finally:
        db.close()

    return user_id, session_token.plain_text


def test_pms_project_workflow_and_dashboard(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    overdue_date = (date.today() - timedelta(days=1)).isoformat()

    project_response = client.post(
        "/api/v1/pms/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": "AID",
            "name": "AIDOO PMS",
            "description": "Execution management",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()
    assert project["role"] == "owner"
    project_id = project["id"]

    members_response = client.get(
        f"/api/v1/pms/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert members_response.status_code == 200
    assert members_response.json()["items"][0]["role"] == "owner"

    milestone_response = client.post(
        f"/api/v1/pms/projects/{project_id}/milestones",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Phase 1",
            "description": "Ship the first management surface",
            "status": "active",
            "due_date": overdue_date,
        },
    )
    assert milestone_response.status_code == 201
    milestone_id = milestone_response.json()["id"]

    first_issue_response = client.post(
        f"/api/v1/pms/projects/{project_id}/issues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build dashboard",
            "description": "Project-level rollup",
            "status": "backlog",
            "priority": "high",
            "milestone_id": milestone_id,
            "due_date": overdue_date,
        },
    )
    assert first_issue_response.status_code == 201
    first_issue = first_issue_response.json()

    second_issue_response = client.post(
        f"/api/v1/pms/projects/{project_id}/issues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Build board",
            "description": "Issue board lane UI",
            "status": "done",
            "priority": "medium",
            "milestone_id": milestone_id,
        },
    )
    assert second_issue_response.status_code == 201
    second_issue = second_issue_response.json()

    dependency_response = client.post(
        "/api/v1/pms/dependencies",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "predecessor_id": first_issue["id"],
            "successor_id": second_issue["id"],
            "relation_type": "blocks",
        },
    )
    assert dependency_response.status_code == 201
    dependency_id = dependency_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/pms/issues/{first_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "in_progress", "board_position": 1},
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "in_progress"

    comment_response = client.post(
        f"/api/v1/pms/issues/{first_issue['id']}/comments",
        headers={"Authorization": f"Bearer {token}"},
        json={"body": "Need summary and overdue metrics."},
    )
    assert comment_response.status_code == 201

    detail_response = client.get(
        f"/api/v1/pms/issues/{first_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["issue"]["reference"] == "AID-1"
    assert detail["comments"][0]["body"] == "Need summary and overdue metrics."
    assert detail["dependencies"][0]["id"] == dependency_id

    logs_response = client.get(
        f"/api/v1/pms/issues/{first_issue['id']}/activity-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logs_response.status_code == 200
    log_actions = [item["action"] for item in logs_response.json()["items"]]
    assert "created" in log_actions
    assert "updated" in log_actions
    assert "commented" in log_actions

    issues_response = client.get(
        f"/api/v1/pms/projects/{project_id}/issues?status=in_progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issues_response.status_code == 200
    assert issues_response.json()["total"] == 1

    project_detail_response = client.get(
        f"/api/v1/pms/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert project_detail_response.status_code == 200
    assert project_detail_response.json()["progress"] == 0.75
    assert project_detail_response.json()["overdue_issue_count"] == 1

    dashboard_response = client.get(
        "/api/v1/pms/dashboard/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dashboard_response.status_code == 200
    dashboard = dashboard_response.json()
    assert dashboard["project_count"] == 1
    assert dashboard["active_issue_count"] == 1
    assert dashboard["overdue_issue_count"] == 1
    assert dashboard["projects"][0]["progress"] == 0.75

    dependency_delete = client.delete(
        f"/api/v1/pms/dependencies/{dependency_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dependency_delete.status_code == 204


def test_pms_membership_permissions(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    outsider_id, outsider_token = _create_direct_user(
        email="member@aidoo.local",
        full_name="PMS Member",
    )

    project_response = client.post(
        "/api/v1/pms/projects",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "key": "PERM",
            "name": "Permissions project",
            "description": "Membership checks",
        },
    )
    project_id = project_response.json()["id"]

    forbidden_response = client.get(
        f"/api/v1/pms/projects/{project_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert forbidden_response.status_code == 403

    add_member_response = client.post(
        f"/api/v1/pms/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_id": outsider_id, "role": "member"},
    )
    assert add_member_response.status_code == 201
    assert add_member_response.json()["role"] == "member"

    member_project_response = client.get(
        f"/api/v1/pms/projects/{project_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert member_project_response.status_code == 200
    assert member_project_response.json()["role"] == "member"
