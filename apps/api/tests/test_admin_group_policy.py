from open_work_hub_api.core.settings import get_settings
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from dev_accounts import auth_headers, create_company_user_session, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import AuditLog
from open_work_hub_api.domains.docs.app_catalog import DOCS_APP
from open_work_hub_api.domains.groups.models import GroupMember
from open_work_hub_api.domains.groups.service import current_group_ids


def _auth_headers(token):
    return auth_headers(token)


def _bootstrap_admin_session(client):
    return dev_login(client)


def _group(client, headers, name="Review Group"):
    response = client.post("/api/v1/admin/groups", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _replace(client, headers, group_id, user_ids):
    return client.put(
        f"/api/v1/admin/groups/{group_id}/members", headers=headers, json={"user_ids": user_ids}
    )


def test_manual_group_starts_empty_without_implicit_creator_membership(client):
    admin = dev_login(client)
    headers = auth_headers(admin["token"])
    group = _group(client, headers)
    assert group["kind"] == "manual"
    assert group["active"]
    response = client.get(f"/api/v1/admin/groups/{group['id']}/members", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["user_ids"] == []


def test_invalid_member_replace_is_atomic_and_valid_replace_deduplicates(client):
    member = create_company_user_session(
        client, login_id="atomic-member", email="atomic@example.test", full_name="Atomic Member"
    )
    admin = dev_login(client)
    headers = auth_headers(admin["token"])
    group = _group(client, headers)
    user_id = member["user"]["id"]
    response = _replace(client, headers, group["id"], [user_id, user_id])
    assert response.status_code == 200, response.text
    assert response.json()["user_ids"] == [user_id]
    response = _replace(client, headers, group["id"], ["missing-user"])
    assert response.status_code == 400, response.text
    response = client.get(f"/api/v1/admin/groups/{group['id']}/members", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["user_ids"] == [user_id]
    response = _replace(client, headers, group["id"], [])
    assert response.status_code == 200, response.text
    assert response.json()["user_ids"] == []


def test_group_deactivation_revokes_effective_membership_but_retains_assignments(client):
    member = create_company_user_session(
        client,
        login_id="retained-member",
        email="retained@example.test",
        full_name="Retained Member",
    )
    admin = dev_login(client)
    headers = auth_headers(admin["token"])
    group = _group(client, headers)
    user_id = member["user"]["id"]
    response = _replace(client, headers, group["id"], [user_id])
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        assert group["id"] in current_group_ids(db, user_id)
    response = client.patch(
        f"/api/v1/admin/groups/{group['id']}", headers=headers, json={"active": False}
    )
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        assert group["id"] not in current_group_ids(db, user_id)
        assert (
            db.scalar(
                select(GroupMember).where(
                    GroupMember.group_id == group["id"], GroupMember.user_id == user_id
                )
            )
            is not None
        )
    active = client.get("/api/v1/admin/groups", headers=headers)
    retained = client.get(
        "/api/v1/admin/groups", headers=headers, params={"include_inactive": True}
    )
    assert group["id"] not in {item["id"] for item in active.json()["items"]}
    assert group["id"] in {item["id"] for item in retained.json()["items"]}


@pytest.mark.parametrize(
    "method,suffix,payload",
    [
        ("post", "", {"name": "Denied"}),
        ("patch", "/{id}", {"active": False}),
        ("put", "/{id}/members", {"user_ids": []}),
    ],
)
def test_group_mutation_requires_platform_administration(client, method, suffix, payload):
    member = create_company_user_session(
        client,
        login_id="ordinary-member",
        email="ordinary@example.test",
        full_name="Ordinary Member",
    )
    admin = dev_login(client)
    group = _group(client, auth_headers(admin["token"]))
    response = getattr(client, method)(
        "/api/v1/admin/groups" + suffix.format(id=group["id"]),
        headers=auth_headers(member["token"]),
        json=payload,
    )
    assert response.status_code == 403, response.text


def test_group_membership_audit_captures_before_and_after(client):
    admin = dev_login(client)
    headers = auth_headers(admin["token"])
    group = _group(client, headers)
    response = _replace(client, headers, group["id"], [admin["user"]["id"]])
    assert response.status_code == 200, response.text
    with get_session_factory()() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == group["id"], AuditLog.action == "admin.group.members.replace"
            )
        )
        assert audit is not None
        assert audit.actor_user_id == admin["user"]["id"]
        assert audit.payload["before"] == {"user_ids": []}
        assert audit.payload["after"] == {"user_ids": [admin["user"]["id"]]}


def test_app_bar_categories_are_admin_managed_presentation_groups(
    client: TestClient,
) -> None:
    get_settings.cache_clear()
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    list_response = client.get(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    # Migrations may provision launcher categories. Establish an empty layout
    # through the admin API, which must also allow removing those categories.
    for category in payload["categories"]:
        clear_response = client.delete(
            f"/api/v1/admin/app-bar-categories/{category['id']}",
            headers=_auth_headers(token),
        )
        assert clear_response.status_code == 200, clear_response.text
    list_response = client.get(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    payload = list_response.json()
    assert payload["categories"] == []
    available_app_ids = {item["app_id"] for item in payload["available_apps"]}
    assert {DOCS_APP.app_id, "pms"} <= available_app_ids
    assert {"home", "extensions"}.isdisjoint(available_app_ids)

    create_response = client.post(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
        json={"title": "Field Ops", "icon_key": "microscope"},
    )
    assert create_response.status_code == 200, create_response.text
    created = next(
        item for item in create_response.json()["categories"] if item["title"] == "Field Ops"
    )
    assert created["key"] != "field-ops"
    assert created["icon_key"] == "microscope"

    layout_response = client.put(
        "/api/v1/admin/app-bar-categories/layout",
        headers=_auth_headers(token),
        json={
            "categories": [
                {
                    "id": created["id"],
                    "title": "Field tools",
                    "icon_key": "history",
                    "app_ids": ["docs", "pms"],
                }
            ]
        },
    )
    assert layout_response.status_code == 200, layout_response.text
    updated = next(
        item for item in layout_response.json()["categories"] if item["id"] == created["id"]
    )
    assert updated["title"] == "Field tools"
    assert updated["icon_key"] == "history"
    assert [item["app_id"] for item in updated["items"]] == [
        "docs",
        "pms",
    ]

    bootstrap_response = client.get(
        "/api/v1/apps/bootstrap",
        headers=_auth_headers(token),
    )
    assert bootstrap_response.status_code == 200, bootstrap_response.text
    bootstrap = bootstrap_response.json()
    assert len(bootstrap["app_bar_categories"]) == 1
    bootstrap_category = bootstrap["app_bar_categories"][0]
    assert {
        "id": bootstrap_category["id"],
        "key": bootstrap_category["key"],
        "title": bootstrap_category["title"],
        "icon_key": bootstrap_category["icon_key"],
    } == {
        "id": updated["id"],
        "key": updated["key"],
        "title": "Field tools",
        "icon_key": "history",
    }
    assert [item["app_id"] for item in bootstrap_category["items"]] == [
        "docs",
        "pms",
    ]

    invalid_icon_response = client.post(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
        json={"title": "Invalid Icon", "icon_key": "../bad"},
    )
    assert invalid_icon_response.status_code == 400
    assert invalid_icon_response.json()["code"] == "admin.invalid_app_bar_icon"

    delete_response = client.delete(
        f"/api/v1/admin/app-bar-categories/{created['id']}",
        headers=_auth_headers(token),
    )
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.json()["categories"] == []

    reread_response = client.get(
        "/api/v1/admin/app-bar-categories",
        headers=_auth_headers(token),
    )
    assert reread_response.status_code == 200, reread_response.text
    assert reread_response.json()["categories"] == []
    get_settings.cache_clear()
