from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data


TEST_USER_PASSWORD = "supersecret123"

_LEGACY_ACCOUNTS = {
    "delivery-hub-admin": {
        "workspace_key": "delivery-hub",
        "workspace_name": "Delivery Hub",
        "role": "admin",
        "login_id": "deliveryhubadmin",
        "email": "delivery-hub-admin@open-work-hub.local",
        "full_name": "Delivery Hub Admin",
    },
    "delivery-hub-member": {
        "workspace_key": "delivery-hub",
        "workspace_name": "Delivery Hub",
        "role": "member",
        "login_id": "deliveryhubmember",
        "email": "delivery-hub-member@open-work-hub.local",
        "full_name": "Delivery Hub Member",
    },
    "knowledge-base-admin": {
        "workspace_key": "knowledge-base",
        "workspace_name": "Knowledge Base",
        "role": "admin",
        "login_id": "knowledgebaseadmin",
        "email": "knowledge-base-admin@open-work-hub.local",
        "full_name": "Knowledge Base Admin",
    },
}


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def content_grant_headers(content_url: str) -> dict[str, str]:
    parsed = urlsplit(content_url)
    fragment = parse_qs(parsed.fragment, keep_blank_values=True)
    grants = fragment.get("grant", [])
    assert not parsed.scheme and not parsed.netloc
    assert parsed.path == "/api/v1/content" and not parsed.query
    assert set(fragment) == {"grant"} and len(grants) == 1 and grants[0]
    return {"X-Open-Work-Hub-Content-Grant": grants[0]}


def content_headers(token: str, content_url: str) -> dict[str, str]:
    return {**auth_headers(token), **content_grant_headers(content_url)}


def dev_login(client: TestClient, account_key: str = "administrator") -> dict:
    if account_key == "administrator":
        return _administrator_session(client)

    definition = _LEGACY_ACCOUNTS.get(account_key)
    if definition is None:
        response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
        assert response.status_code == 200, response.text
        return response.json()

    admin = _administrator_session(client)
    workspace = _ensure_workspace(
        client,
        admin["token"],
        key=definition["workspace_key"],
        name=definition["workspace_name"],
    )
    user = _ensure_user(
        client,
        admin["token"],
        login_id=definition["login_id"],
        email=definition["email"],
        full_name=definition["full_name"],
    )
    _ensure_workspace_member(
        client,
        admin["token"],
        workspace_id=workspace["id"],
        user_id=user["id"],
        role=definition["role"],
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"login_id": definition["login_id"], "password": TEST_USER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_workspace_user_session(
    client: TestClient,
    *,
    workspace_key: str,
    login_id: str,
    email: str,
    full_name: str,
    role: str = "member",
    workspace_name: str | None = None,
) -> dict:
    admin = _administrator_session(client)
    workspace = _ensure_workspace(
        client,
        admin["token"],
        key=workspace_key,
        name=workspace_name or workspace_key.replace("-", " ").title(),
    )
    user = _ensure_user(
        client,
        admin["token"],
        login_id=login_id,
        email=email,
        full_name=full_name,
    )
    _ensure_workspace_member(
        client,
        admin["token"],
        workspace_id=workspace["id"],
        user_id=user["id"],
        role=role,
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"login_id": login_id, "password": TEST_USER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _administrator_session(client: TestClient) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": "administrator"})
    assert response.status_code == 200, response.text
    return response.json()


def _ensure_workspace(client: TestClient, admin_token: str, *, key: str, name: str) -> dict:
    list_response = client.get("/api/v1/admin/workspaces", headers=auth_headers(admin_token))
    assert list_response.status_code == 200, list_response.text
    existing = next((item for item in list_response.json() if item["key"] == key), None)
    if existing is not None:
        return existing

    create_response = client.post(
        "/api/v1/admin/workspaces",
        headers=auth_headers(admin_token),
        json={"key": key, "name": name},
    )
    assert create_response.status_code == 201, create_response.text
    return create_response.json()


def _ensure_user(
    client: TestClient,
    admin_token: str,
    *,
    login_id: str,
    email: str,
    full_name: str,
) -> dict:
    list_response = client.get(
        "/api/v1/admin/users",
        headers=auth_headers(admin_token),
        params={"q": email},
    )
    assert list_response.status_code == 200, list_response.text
    existing = next(
        (item for item in list_response.json()["items"] if item["email"] == email), None
    )
    if existing is not None:
        return existing

    create_response = client.post(
        "/api/v1/admin/users",
        headers=auth_headers(admin_token),
        json={
            "login_id": login_id,
            "email": email,
            "full_name": full_name,
            "temporary_password": TEST_USER_PASSWORD,
        },
    )
    assert create_response.status_code == 201, create_response.text
    return create_response.json()["user"]


def _ensure_workspace_member(
    client: TestClient,
    admin_token: str,
    *,
    workspace_id: str,
    user_id: str,
    role: str,
) -> None:
    response = client.post(
        f"/api/v1/admin/workspaces/{workspace_id}/members",
        headers=auth_headers(admin_token),
        json={"subject_id": user_id, "subject_type": "user", "role": role},
    )
    if response.status_code == 409:
        update_response = client.patch(
            f"/api/v1/admin/workspaces/{workspace_id}/members/user/{user_id}",
            headers=auth_headers(admin_token),
            json={"role": role},
        )
        assert update_response.status_code == 200, update_response.text
        return
    assert response.status_code == 201, response.text
