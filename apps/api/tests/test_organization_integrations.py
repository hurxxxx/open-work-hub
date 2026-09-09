from __future__ import annotations

from fastapi.testclient import TestClient

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.integrations.models import PlatformApiKey


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Directory Admin",
            "email": "directory-admin@open-work-hub.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_organization_unit(
    client: TestClient,
    token: str,
    *,
    name: str,
    parent_id: str | None = None,
) -> dict:
    response = client.post(
        "/api/v1/admin/organization-units",
        headers=_auth_headers(token),
        json={
            "name": name,
            "unit_type": "department",
            "parent_id": parent_id,
            "active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_organization_hierarchy_user_metadata_and_filters(client: TestClient) -> None:
    admin = _bootstrap_admin(client)
    token = admin["token"]
    root = _create_organization_unit(client, token, name="Product")
    child = _create_organization_unit(
        client,
        token,
        name="Product Research",
        parent_id=root["id"],
    )

    cycle_response = client.patch(
        f"/api/v1/admin/organization-units/{root['id']}",
        headers=_auth_headers(token),
        json={"parent_id": child["id"]},
    )
    assert cycle_response.status_code == 409
    assert cycle_response.json()["code"] == "organization.cycle_detected"

    duplicate_response = client.post(
        "/api/v1/admin/organization-units",
        headers=_auth_headers(token),
        json={
            "name": "Duplicate",
            "slug": root["slug"],
            "unit_type": "department",
            "active": True,
        },
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["code"] == "organization.slug_exists"

    blank_name_response = client.post(
        "/api/v1/admin/organization-units",
        headers=_auth_headers(token),
        json={"name": "  ", "unit_type": "department", "active": True},
    )
    assert blank_name_response.status_code == 422

    create_user_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": "researcher@open-work-hub.local",
            "full_name": "Researcher One",
            "employee_code": "E-1001",
            "job_title": "Staff Researcher",
            "primary_organization_unit_id": child["id"],
        },
    )
    assert create_user_response.status_code == 201, create_user_response.text
    created_user = create_user_response.json()["user"]
    assert created_user["employee_code"] == "E-1001"
    assert created_user["job_title"] == "Staff Researcher"
    assert created_user["primary_organization_unit"] == {
        "head_user_id": None,
        "id": child["id"],
        "name": child["name"],
        "slug": child["slug"],
        "unit_type": "department",
        "active": True,
    }

    descendants_response = client.get(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        params={
            "organization_unit_id": root["id"],
            "include_descendants": "true",
        },
    )
    assert descendants_response.status_code == 200, descendants_response.text
    assert created_user["id"] in {item["id"] for item in descendants_response.json()["items"]}

    exact_response = client.get(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        params={
            "organization_unit_id": root["id"],
            "include_descendants": "false",
        },
    )
    assert exact_response.status_code == 200, exact_response.text
    assert created_user["id"] not in {item["id"] for item in exact_response.json()["items"]}

    unknown_filter_response = client.get(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        params={
            "organization_unit_id": "missing-organization-unit",
            "include_descendants": "false",
        },
    )
    assert unknown_filter_response.status_code == 404
    assert unknown_filter_response.json()["code"] == "organization.unit_not_found"

    deactivate_response = client.patch(
        f"/api/v1/admin/organization-units/{child['id']}",
        headers=_auth_headers(token),
        json={"active": False},
    )
    assert deactivate_response.status_code == 200, deactivate_response.text
    assert deactivate_response.json()["active"] is False

    inactive_assignment_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(token),
        json={
            "email": "inactive-unit@open-work-hub.local",
            "full_name": "Inactive Unit",
            "primary_organization_unit_id": child["id"],
        },
    )
    assert inactive_assignment_response.status_code == 409
    assert inactive_assignment_response.json()["code"] == "organization.unit_inactive"

    active_units_response = client.get(
        "/api/v1/admin/organization-units",
        headers=_auth_headers(token),
    )
    assert active_units_response.status_code == 200
    assert child["id"] not in {item["id"] for item in active_units_response.json()}

    all_units_response = client.get(
        "/api/v1/admin/organization-units?include_inactive=true",
        headers=_auth_headers(token),
    )
    assert all_units_response.status_code == 200
    assert child["id"] in {item["id"] for item in all_units_response.json()}


def test_scoped_platform_api_keys_are_revealable_audited_and_revocable(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin(client)
    admin_token = admin["token"]
    organization = _create_organization_unit(client, admin_token, name="Operations")

    issue_response = client.post(
        "/api/v1/admin/platform-api-keys",
        headers=_auth_headers(admin_token),
        json={"name": "HR directory sync", "scopes": ["organization:read"]},
    )
    assert issue_response.status_code == 201, issue_response.text
    assert issue_response.headers["cache-control"] == "private, no-store"
    issued = issue_response.json()
    key_id = issued["item"]["id"]
    api_key = issued["api_key"]
    assert api_key.startswith("owh_pk_")
    assert issued["item"]["key_prefix"] == api_key[:18]

    with get_session_factory()() as db:
        stored = db.get(PlatformApiKey, key_id)
        assert stored is not None
        assert stored.token_hash != api_key
        assert api_key not in stored.secret_ciphertext
        assert stored.secret_ciphertext

    list_response = client.get(
        "/api/v1/admin/platform-api-keys",
        headers=_auth_headers(admin_token),
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.headers["cache-control"] == "private, no-store"
    list_payload = list_response.json()
    assert set(list_payload["available_scopes"]) == {
        "organization:read",
        "people:read",
    }
    assert "api_key" not in list_response.text
    assert any(
        operation["path"] == "/api/v1/integrations/directory/organization-units"
        for spec in list_payload["scope_specs"]
        if spec["scope"] == "organization:read"
        for operation in spec["operations"]
    )

    external_response = client.get(
        "/api/v1/integrations/directory/organization-units",
        headers=_auth_headers(api_key),
    )
    assert external_response.status_code == 200, external_response.text
    assert external_response.headers["cache-control"] == "private, no-store"
    assert organization["id"] in {item["id"] for item in external_response.json()["items"]}

    wrong_scope_response = client.get(
        "/api/v1/integrations/directory/people",
        headers=_auth_headers(api_key),
    )
    assert wrong_scope_response.status_code == 403
    assert wrong_scope_response.json()["code"] == "platform_api_key.scope_required"
    assert wrong_scope_response.headers["cache-control"] == "private, no-store"

    user_token_response = client.get(
        "/api/v1/integrations/directory/organization-units",
        headers=_auth_headers(admin_token),
    )
    assert user_token_response.status_code == 401
    assert user_token_response.json()["code"] == "platform_api_key.invalid"

    reveal_response = client.post(
        f"/api/v1/admin/platform-api-keys/{key_id}/reveal",
        headers=_auth_headers(admin_token),
    )
    assert reveal_response.status_code == 200, reveal_response.text
    assert reveal_response.headers["cache-control"] == "private, no-store"
    assert reveal_response.json()["api_key"] == api_key

    audit_response = client.get(
        "/api/v1/admin/audit-logs?limit=100",
        headers=_auth_headers(admin_token),
    )
    assert audit_response.status_code == 200, audit_response.text
    assert api_key not in audit_response.text
    actions = {item["action"] for item in audit_response.json()["items"]}
    assert {
        "admin.platform_api_key.issue",
        "admin.platform_api_key.reveal",
        "integration.directory.organization_units.read",
    }.issubset(actions)

    revoke_response = client.post(
        f"/api/v1/admin/platform-api-keys/{key_id}/revoke",
        headers=_auth_headers(admin_token),
    )
    assert revoke_response.status_code == 200, revoke_response.text
    assert revoke_response.json()["status"] == "revoked"

    with get_session_factory()() as db:
        revoked = db.get(PlatformApiKey, key_id)
        assert revoked is not None
        assert revoked.secret_ciphertext == ""
        assert revoked.revoked_at is not None

    rejected_response = client.get(
        "/api/v1/integrations/directory/organization-units",
        headers=_auth_headers(api_key),
    )
    assert rejected_response.status_code == 401
    assert rejected_response.json()["code"] == "platform_api_key.invalid"

    reveal_revoked_response = client.post(
        f"/api/v1/admin/platform-api-keys/{key_id}/reveal",
        headers=_auth_headers(admin_token),
    )
    assert reveal_revoked_response.status_code == 409
    assert reveal_revoked_response.json()["code"] == "platform_api_key.inactive"


def test_people_scope_returns_only_the_external_directory_projection(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin(client)
    admin_token = admin["token"]
    organization = _create_organization_unit(client, admin_token, name="Finance")
    user_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(admin_token),
        json={
            "email": "finance@open-work-hub.local",
            "full_name": "Finance Person",
            "employee_code": "F-2001",
            "job_title": "Controller",
            "primary_organization_unit_id": organization["id"],
        },
    )
    assert user_response.status_code == 201, user_response.text
    user_id = user_response.json()["user"]["id"]

    issue_response = client.post(
        "/api/v1/admin/platform-api-keys",
        headers=_auth_headers(admin_token),
        json={"name": "People sync", "scopes": ["people:read"]},
    )
    assert issue_response.status_code == 201, issue_response.text
    api_key = issue_response.json()["api_key"]

    people_response = client.get(
        "/api/v1/integrations/directory/people",
        headers=_auth_headers(api_key),
    )
    assert people_response.status_code == 200, people_response.text
    person = next(item for item in people_response.json()["items"] if item["id"] == user_id)
    assert set(person) == {
        "id",
        "login_id",
        "email",
        "full_name",
        "display_name",
        "employee_code",
        "job_title",
        "status",
        "primary_organization_unit_id",
        "created_at",
        "updated_at",
    }
    assert person["employee_code"] == "F-2001"
    assert person["job_title"] == "Controller"
    assert person["primary_organization_unit_id"] == organization["id"]

    wrong_scope_response = client.get(
        "/api/v1/integrations/directory/organization-units",
        headers=_auth_headers(api_key),
    )
    assert wrong_scope_response.status_code == 403
