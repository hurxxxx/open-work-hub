from datetime import date, timedelta

from fastapi.testclient import TestClient


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
    assert "platform-admin" in auth_payload["user"]["group_slugs"]
    assert auth_payload["user"]["theme_preference"] == "system"
    assert auth_payload["user"]["workspace_roles"]
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


def test_auth_login_success_and_invalid_password(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "ADMIN@AIDOO.LOCAL",
            "password": "supersecret123",
        },
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["email"] == "admin@aidoo.local"
    assert "admin.access" in login_response.json()["user"]["permissions"]
    assert login_response.json()["token"]

    invalid_password_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@aidoo.local",
            "password": "wrongpass123",
        },
    )
    assert invalid_password_response.status_code == 401


def test_auth_preferences_password_and_sessions(client: TestClient) -> None:
    token = _bootstrap_admin(client)

    preferences_response = client.patch(
        "/api/v1/auth/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "display_name": "Portal Admin",
            "job_title": "Platform Owner",
            "theme_preference": "light",
        },
    )
    assert preferences_response.status_code == 200
    assert preferences_response.json()["display_name"] == "Portal Admin"
    assert preferences_response.json()["theme_preference"] == "light"

    sessions_response = client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sessions_response.status_code == 200
    session_id = sessions_response.json()["items"][0]["id"]
    assert sessions_response.json()["items"][0]["is_current"] is True

    revoke_response = client.post(
        f"/api/v1/auth/sessions/{session_id}/revoke",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoke_response.status_code == 204

    revoked_me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revoked_me_response.status_code == 401

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert login_response.status_code == 200
    replacement_token = login_response.json()["token"]

    password_response = client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {replacement_token}"},
        json={
            "current_password": "supersecret123",
            "new_password": "newsupersecret123",
        },
    )
    assert password_response.status_code == 204

    old_login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert old_login_response.status_code == 401

    new_login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@aidoo.local",
            "password": "newsupersecret123",
        },
    )
    assert new_login_response.status_code == 200


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
                display_name=full_name,
                password_hash=hash_password(password),
                status="active",
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


def test_admin_identity_management_endpoints(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    org_units_response = client.get("/api/v1/admin/org-units", headers=headers)
    assert org_units_response.status_code == 200
    root_org_unit_id = org_units_response.json()[0]["id"]

    group_response = client.post(
        "/api/v1/admin/groups",
        headers=headers,
        json={
            "name": "Docs Editors",
            "description": "Can manage docs access",
            "permissions": ["group.read", "workspace.read"],
        },
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    create_user_response = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "email": "member@aidoo.local",
            "full_name": "AIDOO Member",
            "display_name": "Member",
            "primary_org_unit_id": root_org_unit_id,
            "group_ids": [group_id],
        },
    )
    assert create_user_response.status_code == 201
    created_user = create_user_response.json()["user"]
    temporary_password = create_user_response.json()["temporary_password"]
    assert created_user["email"] == "member@aidoo.local"
    assert created_user["must_change_password"] is True
    assert temporary_password

    list_users_response = client.get("/api/v1/admin/users", headers=headers)
    assert list_users_response.status_code == 200
    assert len(list_users_response.json()["items"]) == 2

    workspace_response = client.post(
        "/api/v1/admin/workspaces",
        headers=headers,
        json={
            "name": "Supplier Portal",
            "description": "External supplier collaboration surface",
        },
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]

    bindings_response = client.put(
        f"/api/v1/admin/workspaces/{workspace_id}/bindings",
        headers=headers,
        json={
            "users": [{"subject_id": created_user["id"], "role": "member"}],
            "groups": [{"subject_id": group_id, "role": "viewer"}],
        },
    )
    assert bindings_response.status_code == 200
    assert len(bindings_response.json()) == 2

    team_response = client.post(
        f"/api/v1/admin/workspaces/{workspace_id}/teams",
        headers=headers,
        json={
            "name": "Cross Functional Squad",
            "description": "Shared delivery team",
        },
    )
    assert team_response.status_code == 201
    team_id = team_response.json()["id"]

    team_members_response = client.put(
        f"/api/v1/admin/teams/{team_id}/members",
        headers=headers,
        json={"user_ids": [created_user["id"]]},
    )
    assert team_members_response.status_code == 200
    assert team_members_response.json()[0]["email"] == "member@aidoo.local"

    feature_policies_response = client.get("/api/v1/admin/feature-policies", headers=headers)
    assert feature_policies_response.status_code == 200
    first_policy_id = feature_policies_response.json()[0]["id"]

    update_policy_response = client.put(
        "/api/v1/admin/feature-policies",
        headers=headers,
        json={
            "items": [
                {
                    "id": first_policy_id,
                    "enabled": False,
                    "required_permissions": [],
                    "allowed_workspace_keys": [],
                    "allowed_group_slugs": [],
                }
            ]
        },
    )
    assert update_policy_response.status_code == 200
    assert any(policy["enabled"] is False for policy in update_policy_response.json())

    audit_logs_response = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert audit_logs_response.status_code == 200
    assert audit_logs_response.json()


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
