from datetime import date, timedelta

from fastapi.testclient import TestClient


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_bootstrap_and_protected_search(client: TestClient) -> None:
    status_response = client.get("/api/v1/auth/bootstrap-status")
    assert status_response.status_code == 200
    assert status_response.json() == {
        "requires_setup": True,
        "dev_admin_login_available": True,
        "dev_login_accounts": [],
    }

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
    assert "platform_admin" in auth_payload["user"]["system_roles"]
    assert auth_payload["user"]["theme_preference"] == "system"
    assert auth_payload["user"]["workspace_roles"]
    assert any(item["app"] == "admin" for item in auth_payload["user"]["app_access"])
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
    assert "platform_admin" in login_response.json()["user"]["system_roles"]
    assert login_response.json()["token"]

    invalid_password_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@aidoo.local",
            "password": "wrongpass123",
        },
    )
    assert invalid_password_response.status_code == 401


def test_dev_admin_login_shortcut(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201

    dev_login_response = client.post("/api/v1/auth/dev-admin-login")
    assert dev_login_response.status_code == 200
    payload = dev_login_response.json()
    assert payload["user"]["email"] == "admin@aidoo.local"
    assert "platform_admin" in payload["user"]["system_roles"]
    assert payload["token"]


def test_dev_admin_login_shortcut_skips_non_admin_email_match(client: TestClient) -> None:
    _create_direct_user(
        email="admin@aidoo.local",
        full_name="Plain Admin Email",
        is_admin=False,
    )
    _create_direct_user(
        email="platform-owner@aidoo.local",
        full_name="Platform Owner",
        is_admin=True,
    )

    dev_login_response = client.post("/api/v1/auth/dev-admin-login")
    assert dev_login_response.status_code == 200
    payload = dev_login_response.json()
    assert payload["user"]["email"] == "platform-owner@aidoo.local"
    assert "platform_admin" in payload["user"]["system_roles"]


def test_seeded_dev_login_accounts_are_listed_and_can_log_in(client: TestClient) -> None:
    _seed_dev_login_accounts()

    status_response = client.get("/api/v1/auth/bootstrap-status")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["requires_setup"] is False
    assert payload["dev_admin_login_available"] is True
    assert any(item["account_key"] == "platform-admin" for item in payload["dev_login_accounts"])
    assert any(item["account_key"] == "pms-viewer" for item in payload["dev_login_accounts"])

    platform_admin_login_response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "platform-admin"},
    )
    assert platform_admin_login_response.status_code == 200
    platform_admin_payload = platform_admin_login_response.json()
    assert platform_admin_payload["user"]["email"] == "platform-admin@aidoo.local"
    assert "platform_admin" in platform_admin_payload["user"]["system_roles"]
    assert any(item["app"] == "admin" for item in platform_admin_payload["user"]["app_access"])

    dev_login_response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "pms-viewer"},
    )
    assert dev_login_response.status_code == 200
    login_payload = dev_login_response.json()
    assert login_payload["user"]["email"] == "pms-viewer@aidoo.local"
    assert any(item["app"] == "pms" for item in login_payload["user"]["app_access"])


def test_bootstrap_status_syncs_missing_dev_login_accounts(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201

    status_response = client.get("/api/v1/auth/bootstrap-status")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["requires_setup"] is False
    assert any(item["account_key"] == "org-admin" for item in payload["dev_login_accounts"])

    org_admin_login_response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": "org-admin"},
    )
    assert org_admin_login_response.status_code == 200
    assert org_admin_login_response.json()["user"]["email"] == "org-admin@aidoo.local"
    assert "org_admin" in org_admin_login_response.json()["user"]["system_roles"]


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


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _create_direct_user(
    *,
    email: str,
    full_name: str,
    password: str = "supersecret123",
    is_admin: bool = False,
    system_roles: tuple[str, ...] = (),
    workspace_keys: tuple[str, ...] = (),
) -> tuple[str, str]:
    from sqlalchemy import select

    from aidoo_api.core.db import get_session_factory
    from aidoo_api.domains.auth.models import AuthSession, User, UserSystemRole, Workspace, WorkspaceUserBinding
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
        for role in {*(system_roles or ()), *(("platform_admin",) if is_admin else ())}:
            db.add(
                UserSystemRole(
                    id=new_id(),
                    user_id=user_id,
                    role=role,
                )
            )
        for workspace_key in workspace_keys:
            workspace = db.scalar(select(Workspace).where(Workspace.key == workspace_key))
            if workspace is None:
                continue
            db.add(
                WorkspaceUserBinding(
                    id=new_id(),
                    workspace_id=workspace.id,
                    user_id=user_id,
                    role="member",
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


def _seed_dev_login_accounts() -> None:
    from aidoo_api.core.db import get_session_factory
    from aidoo_api.domains.auth.access import ensure_dev_login_seed_data

    db = get_session_factory()()
    try:
        ensure_dev_login_seed_data(db)
    finally:
        db.close()


def _create_pms_project(
    client: TestClient,
    token: str,
    *,
    key: str,
    name: str,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/pms/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "key": key,
            "name": name,
            "description": f"{name} description",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_pms_issue(
    client: TestClient,
    token: str,
    project_id: str,
    *,
    title: str,
    parent_id: str | None = None,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/pms/projects/{project_id}/issues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": title,
            "description": f"{title} description",
            "status": "todo",
            "priority": "medium",
            "parent_id": parent_id,
        },
    )
    assert response.status_code == 201
    return response.json()


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
            "system_roles": ["org_admin"],
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
    list_users_payload = list_users_response.json()
    assert len(list_users_payload["items"]) == 2
    assert list_users_payload["total"] == 2
    assert list_users_payload["page"] == 1
    assert list_users_payload["page_size"] == 20

    paged_users_response = client.get(
        "/api/v1/admin/users",
        headers=headers,
        params={"page": 1, "page_size": 1},
    )
    assert paged_users_response.status_code == 200
    paged_users_payload = paged_users_response.json()
    assert len(paged_users_payload["items"]) == 1
    assert paged_users_payload["total"] == 2

    searched_users_response = client.get(
        "/api/v1/admin/users",
        headers=headers,
        params={"q": "member"},
    )
    assert searched_users_response.status_code == 200
    searched_users_payload = searched_users_response.json()
    assert len(searched_users_payload["items"]) == 1
    assert searched_users_payload["total"] == 1

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
                }
            ]
        },
    )
    assert update_policy_response.status_code == 200
    assert any(policy["enabled"] is False for policy in update_policy_response.json())

    audit_logs_response = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert audit_logs_response.status_code == 200
    assert audit_logs_response.json()


def test_workspace_scoped_team_management_requires_workspace_admin_role(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    permission_group_response = client.post(
        "/api/v1/admin/groups",
        headers=admin_headers,
        json={
            "name": "Scoped Team Operators",
            "description": "Can manage teams only within scoped workspaces.",
            "system_roles": [],
        },
    )
    assert permission_group_response.status_code == 201
    permission_group_id = permission_group_response.json()["id"]

    workspace_response = client.post(
        "/api/v1/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "Scoped Workspace",
            "description": "Workspace for scoped team management tests",
        },
    )
    assert workspace_response.status_code == 201
    workspace_id = workspace_response.json()["id"]

    second_workspace_response = client.post(
        "/api/v1/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "Another Workspace",
            "description": "Second workspace for negative coverage",
        },
    )
    assert second_workspace_response.status_code == 201
    second_workspace_id = second_workspace_response.json()["id"]

    scoped_user_response = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "scoped-manager@aidoo.local",
            "full_name": "Scoped Manager",
            "group_ids": [permission_group_id],
        },
    )
    assert scoped_user_response.status_code == 201
    scoped_user = scoped_user_response.json()["user"]
    scoped_user_token = _login(
        client,
        scoped_user["email"],
        scoped_user_response.json()["temporary_password"],
    )
    scoped_headers = {"Authorization": f"Bearer {scoped_user_token}"}

    inaccessible_workspaces_response = client.get("/api/v1/admin/workspaces", headers=scoped_headers)
    assert inaccessible_workspaces_response.status_code == 200
    assert inaccessible_workspaces_response.json() == []

    create_team_without_scope_response = client.post(
        f"/api/v1/admin/workspaces/{workspace_id}/teams",
        headers=scoped_headers,
        json={"name": "Forbidden Team", "description": "Should be blocked"},
    )
    assert create_team_without_scope_response.status_code == 403

    bind_workspace_response = client.put(
        f"/api/v1/admin/workspaces/{workspace_id}/bindings",
        headers=admin_headers,
        json={
            "users": [{"subject_id": scoped_user["id"], "role": "admin"}],
            "groups": [],
        },
    )
    assert bind_workspace_response.status_code == 200

    visible_workspaces_response = client.get("/api/v1/admin/workspaces", headers=scoped_headers)
    assert visible_workspaces_response.status_code == 200
    assert [item["id"] for item in visible_workspaces_response.json()] == [workspace_id]

    create_team_with_scope_response = client.post(
        f"/api/v1/admin/workspaces/{workspace_id}/teams",
        headers=scoped_headers,
        json={"name": "Scoped Team", "description": "Allowed via workspace role"},
    )
    assert create_team_with_scope_response.status_code == 201
    created_team = create_team_with_scope_response.json()

    visible_teams_response = client.get(
        "/api/v1/admin/teams",
        headers=scoped_headers,
        params={"workspace_id": workspace_id},
    )
    assert visible_teams_response.status_code == 200
    assert [item["id"] for item in visible_teams_response.json()] == [created_team["id"]]

    create_team_other_workspace_response = client.post(
        f"/api/v1/admin/workspaces/{second_workspace_id}/teams",
        headers=scoped_headers,
        json={"name": "Forbidden Elsewhere", "description": "No scope here"},
    )
    assert create_team_other_workspace_response.status_code == 403


def test_non_pms_routes_require_workspace_feature_access(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    user_response = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "email": "docs-member@aidoo.local",
            "full_name": "Docs Member",
        },
    )
    assert user_response.status_code == 201
    user = user_response.json()["user"]
    user_token = _login(client, user["email"], user_response.json()["temporary_password"])
    user_headers = {"Authorization": f"Bearer {user_token}"}

    documents_forbidden_response = client.post(
        "/api/v1/search/documents",
        headers=user_headers,
        json={"query": "compressor specification"},
    )
    assert documents_forbidden_response.status_code == 403

    drafts_forbidden_response = client.get("/api/v1/drafts", headers=user_headers)
    assert drafts_forbidden_response.status_code == 403

    wiki_forbidden_response = client.get("/api/v1/wiki/pages", headers=user_headers)
    assert wiki_forbidden_response.status_code == 403

    plm_forbidden_response = client.post(
        "/api/v1/search/plm",
        headers=user_headers,
        json={"query": "release delay"},
    )
    assert plm_forbidden_response.status_code == 403

    ocr_forbidden_response = client.post(
        "/api/v1/connectors/ocr/route",
        headers=user_headers,
        json={"asset_uri": "file://scan.pdf"},
    )
    assert ocr_forbidden_response.status_code == 403

    workspaces_response = client.get("/api/v1/admin/workspaces", headers=admin_headers)
    assert workspaces_response.status_code == 200
    docs_workspace_id = next(item["id"] for item in workspaces_response.json() if item["key"] == "docs")

    bind_docs_workspace_response = client.put(
        f"/api/v1/admin/workspaces/{docs_workspace_id}/bindings",
        headers=admin_headers,
        json={
            "users": [{"subject_id": user["id"], "role": "member"}],
            "groups": [],
        },
    )
    assert bind_docs_workspace_response.status_code == 200

    documents_allowed_response = client.post(
        "/api/v1/search/documents",
        headers=user_headers,
        json={"query": "compressor specification"},
    )
    assert documents_allowed_response.status_code == 200

    drafts_allowed_response = client.get("/api/v1/drafts", headers=user_headers)
    assert drafts_allowed_response.status_code == 200

    wiki_allowed_response = client.get("/api/v1/wiki/pages", headers=user_headers)
    assert wiki_allowed_response.status_code == 200

    plm_still_forbidden_response = client.post(
        "/api/v1/search/plm",
        headers=user_headers,
        json={"query": "release delay"},
    )
    assert plm_still_forbidden_response.status_code == 403


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
        workspace_keys=("pms",),
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


def test_pms_app_access_is_required_even_for_space_members(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    member_id, member_token = _create_direct_user(
        email="space-only@aidoo.local",
        full_name="Space Only Member",
    )

    project_response = client.post(
        "/api/v1/pms/projects",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "key": "SPACEONLY",
            "name": "Space-only project",
            "description": "App access guard",
        },
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    add_member_response = client.post(
        f"/api/v1/pms/projects/{project_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"user_id": member_id, "role": "member"},
    )
    assert add_member_response.status_code == 201

    project_detail_response = client.get(
        f"/api/v1/pms/projects/{project_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert project_detail_response.status_code == 403


def test_pms_space_creator_becomes_owner_and_last_manager_is_protected(client: TestClient) -> None:
    _bootstrap_admin(client)
    creator_id, creator_token = _create_direct_user(
        email="space-creator@aidoo.local",
        full_name="Space Creator",
        workspace_keys=("pms",),
    )

    create_space_response = client.post(
        "/api/v1/pms/spaces",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"name": "Operations", "description": "Owner bootstrap"},
    )
    assert create_space_response.status_code == 201
    space = create_space_response.json()

    members_response = client.get(
        f"/api/v1/pms/spaces/{space['id']}/members",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert members_response.status_code == 200
    assert members_response.json()["items"][0]["user_id"] == creator_id
    assert members_response.json()["items"][0]["role"] == "owner"

    demote_response = client.patch(
        f"/api/v1/pms/spaces/{space['id']}/members/{creator_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"role": "member"},
    )
    assert demote_response.status_code == 409

    remove_response = client.delete(
        f"/api/v1/pms/spaces/{space['id']}/members/{creator_id}",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert remove_response.status_code == 409


def test_org_admin_gets_pms_app_access_and_can_view_all_spaces(client: TestClient) -> None:
    admin_token = _bootstrap_admin(client)
    project_response = client.post(
        "/api/v1/pms/projects",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"key": "ORGADM", "name": "Org Admin Project", "description": "Visibility"},
    )
    assert project_response.status_code == 201
    expected_space_id = project_response.json()["team_id"]

    _, org_admin_token = _create_direct_user(
        email="org-admin@aidoo.local",
        full_name="Org Admin",
        system_roles=("org_admin",),
    )

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {org_admin_token}"},
    )
    assert me_response.status_code == 200
    assert any(item["app"] == "pms" for item in me_response.json()["app_access"])

    spaces_response = client.get(
        "/api/v1/pms/spaces",
        headers={"Authorization": f"Bearer {org_admin_token}"},
    )
    assert spaces_response.status_code == 200
    assert any(item["id"] == expected_space_id for item in spaces_response.json())


def test_pms_parent_issue_validation_and_label_conflicts(client: TestClient) -> None:
    token = _bootstrap_admin(client)
    primary_project = _create_pms_project(client, token, key="PARENT", name="Parent Project")
    secondary_project = _create_pms_project(client, token, key="OTHER", name="Other Project")

    parent_issue = _create_pms_issue(client, token, str(primary_project["id"]), title="Parent issue")
    child_issue = _create_pms_issue(
        client,
        token,
        str(primary_project["id"]),
        title="Child issue",
        parent_id=str(parent_issue["id"]),
    )
    assert child_issue["parent_id"] == parent_issue["id"]

    detail_response = client.get(
        f"/api/v1/pms/issues/{parent_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail_response.status_code == 200
    assert len(detail_response.json()["subtasks"]) == 1

    self_parent_response = client.patch(
        f"/api/v1/pms/issues/{child_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"parent_id": child_issue["id"]},
    )
    assert self_parent_response.status_code == 409

    cycle_response = client.patch(
        f"/api/v1/pms/issues/{parent_issue['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"parent_id": child_issue["id"]},
    )
    assert cycle_response.status_code == 409

    cross_project_response = client.post(
        f"/api/v1/pms/projects/{secondary_project['id']}/issues",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Cross project child",
            "description": "Should fail",
            "status": "todo",
            "priority": "medium",
            "parent_id": parent_issue["id"],
        },
    )
    assert cross_project_response.status_code == 400

    labels_response = client.get(
        f"/api/v1/pms/projects/{primary_project['id']}/labels",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert labels_response.status_code == 200
    labels = labels_response.json()["items"]
    rename_conflict_response = client.patch(
        f"/api/v1/pms/labels/{labels[0]['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": labels[1]["name"]},
    )
    assert rename_conflict_response.status_code == 409
