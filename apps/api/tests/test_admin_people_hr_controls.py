from __future__ import annotations

from fastapi.testclient import TestClient
import pytest


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


def _sync_groupware_user() -> None:
    from open_alm_api.core.db import get_session_factory
    from open_alm_api.domains.hr.groupware_sync import (
        GroupwareOrgRow,
        GroupwareUserRow,
        sync_groupware_hr,
    )

    session_factory = get_session_factory()
    with session_factory() as db:
        sync_groupware_hr(
            db,
            departments=[
                GroupwareOrgRow(
                    domain_num=1,
                    depart_num=10,
                    org_code="RND",
                    org_depart="연구소",
                    org_order=8,
                )
            ],
            users=[
                GroupwareUserRow(
                    domain_num=1,
                    user_num=100,
                    user_id="hruser",
                    kor_name="인사연동",
                    com_num="HR-100",
                    com_state=1,
                    email="hruser@example.test",
                    org_code1="RND",
                    org_level=1,
                )
            ],
        )
        db.commit()


def test_admin_can_block_login_for_local_user(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    headers = _auth_headers(session["token"])
    create_response = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "login_id": "localuser",
            "email": "localuser@example.test",
            "full_name": "Local User",
        },
    )
    assert create_response.status_code == 201, create_response.text
    payload = create_response.json()
    user_id = payload["user"]["id"]
    temporary_password = payload["temporary_password"]

    block_response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=headers,
        json={"login_blocked": True},
    )
    assert block_response.status_code == 200, block_response.text
    assert block_response.json()["login_blocked"] is True

    login_response = client.post(
        "/api/v1/auth/login",
        json={"login_id": "localuser", "password": temporary_password},
    )
    assert login_response.status_code == 403

    unblock_response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=headers,
        json={"login_blocked": False},
    )
    assert unblock_response.status_code == 200, unblock_response.text
    assert unblock_response.json()["login_blocked"] is False

    login_after_unblock_response = client.post(
        "/api/v1/auth/login",
        json={"login_id": "localuser", "password": temporary_password},
    )
    assert login_after_unblock_response.status_code == 200, login_after_unblock_response.text


def test_admin_login_block_revokes_an_existing_user_session(client: TestClient) -> None:
    admin_session = _bootstrap_admin_session(client)
    admin_headers = _auth_headers(admin_session["token"])
    create_response = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "login_id": "activeuser",
            "email": "activeuser@example.test",
            "full_name": "Active User",
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    user_id = created["user"]["id"]

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "activeuser",
            "password": created["temporary_password"],
        },
    )
    assert login_response.status_code == 200, login_response.text
    user_headers = _auth_headers(login_response.json()["token"])
    assert client.get("/api/v1/auth/me", headers=user_headers).status_code == 200

    block_response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=admin_headers,
        json={"login_blocked": True},
    )
    assert block_response.status_code == 200, block_response.text

    blocked_session_response = client.get("/api/v1/auth/me", headers=user_headers)
    assert blocked_session_response.status_code == 401
    assert blocked_session_response.json()["code"] == "auth.session_invalid_or_expired"
    assert client.get("/api/v1/auth/me", headers=admin_headers).status_code == 200

    unblock_response = client.patch(
        f"/api/v1/admin/users/{user_id}",
        headers=admin_headers,
        json={"login_blocked": False},
    )
    assert unblock_response.status_code == 200, unblock_response.text
    assert client.get("/api/v1/auth/me", headers=user_headers).status_code == 401

    login_after_unblock_response = client.post(
        "/api/v1/auth/login",
        json={
            "login_id": "activeuser",
            "password": created["temporary_password"],
        },
    )
    assert login_after_unblock_response.status_code == 200, login_after_unblock_response.text


def test_admin_hr_user_actions_allow_block_but_not_delete_or_password_reset(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.auth import router as auth_router

    session = _bootstrap_admin_session(client)
    headers = _auth_headers(session["token"])
    _sync_groupware_user()
    monkeypatch.setattr(
        auth_router,
        "verify_groupware_password",
        lambda **_kwargs: True,
    )

    users_response = client.get("/api/v1/admin/users?q=hruser", headers=headers)
    assert users_response.status_code == 200, users_response.text
    user = users_response.json()["items"][0]
    assert user["auth_provider"] == "groupware"
    assert user["employee_code"] == "HR-100"
    assert user["login_blocked"] is False

    users_by_employee_code_response = client.get(
        "/api/v1/admin/users?q=HR-100", headers=headers
    )
    assert users_by_employee_code_response.status_code == 200
    assert users_by_employee_code_response.json()["items"][0]["id"] == user["id"]

    login_response = client.post(
        "/api/v1/auth/login",
        json={"login_id": "hruser", "password": "external-password"},
    )
    assert login_response.status_code == 200, login_response.text
    change_response = client.post(
        "/api/v1/auth/change-password",
        headers=_auth_headers(login_response.json()["token"]),
        json={
            "current_password": "external-password",
            "new_password": "new-password123",
        },
    )
    assert change_response.status_code == 403
    assert change_response.json()["code"] == "auth.password_managed_externally"

    block_response = client.patch(
        f"/api/v1/admin/users/{user['id']}",
        headers=headers,
        json={"login_blocked": True},
    )
    assert block_response.status_code == 200, block_response.text
    assert block_response.json()["login_blocked"] is True

    reset_response = client.post(
        f"/api/v1/admin/users/{user['id']}/reset-password",
        headers=headers,
        json={},
    )
    assert reset_response.status_code == 403

    delete_response = client.delete(
        f"/api/v1/admin/users/{user['id']}",
        headers=headers,
    )
    assert delete_response.status_code == 403
    assert delete_response.json()["code"] == "admin.hr_user_delete_denied"


def test_admin_user_list_filters_by_org_descendants_and_marks_org_source(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    headers = _auth_headers(session["token"])
    _sync_groupware_user()

    org_units_response = client.get("/api/v1/admin/org-units", headers=headers)
    assert org_units_response.status_code == 200, org_units_response.text
    org_units = org_units_response.json()
    root = next(item for item in org_units if item["slug"] == "hq")
    child = next(item for item in org_units if item["slug"] == "ai-tft")
    assert root["source_type"] == "manual"
    assert child["source_type"] == "manual"
    assert child["parent_id"] == root["id"]
    hr_org = next(item for item in org_units if item["source_type"] == "groupware")
    assert hr_org["hr_org_order"] == 8
    assert any(item["name"] == "AI TFT" and item["source_type"] == "manual" for item in org_units)

    root_member_id = ""
    for login_id, email, org_unit_id in (
        ("rootmember", "rootmember@example.test", root["id"]),
        ("childmember", "childmember@example.test", child["id"]),
        ("unassignedmember", "unassignedmember@example.test", None),
    ):
        payload = {
            "login_id": login_id,
            "email": email,
            "full_name": login_id,
        }
        if org_unit_id is not None:
            payload["primary_org_unit_id"] = org_unit_id
        create_response = client.post("/api/v1/admin/users", headers=headers, json=payload)
        assert create_response.status_code == 201, create_response.text
        if login_id == "rootmember":
            root_member_id = create_response.json()["user"]["id"]
    assert root_member_id

    direct_response = client.get(
        f"/api/v1/admin/users?org_unit_id={root['id']}&include_descendants=false",
        headers=headers,
    )
    assert direct_response.status_code == 200, direct_response.text
    direct_login_ids = {item["login_id"] for item in direct_response.json()["items"]}
    assert "rootmember" in direct_login_ids
    assert "childmember" not in direct_login_ids

    descendants_response = client.get(
        f"/api/v1/admin/users?org_unit_id={root['id']}&include_descendants=true",
        headers=headers,
    )
    assert descendants_response.status_code == 200, descendants_response.text
    descendant_login_ids = {item["login_id"] for item in descendants_response.json()["items"]}
    assert {"rootmember", "childmember"}.issubset(descendant_login_ids)

    unassigned_response = client.get(
        "/api/v1/admin/users?org_unit_id=__unassigned__",
        headers=headers,
    )
    assert unassigned_response.status_code == 200, unassigned_response.text
    unassigned_login_ids = {item["login_id"] for item in unassigned_response.json()["items"]}
    assert "unassignedmember" in unassigned_login_ids
    assert "rootmember" not in unassigned_login_ids

    clear_org_response = client.patch(
        f"/api/v1/admin/users/{root_member_id}",
        headers=headers,
        json={"primary_org_unit_id": None},
    )
    assert clear_org_response.status_code == 200, clear_org_response.text
    assert clear_org_response.json()["primary_org_unit"] is None

    unassigned_after_clear_response = client.get(
        "/api/v1/admin/users?org_unit_id=__unassigned__",
        headers=headers,
    )
    assert unassigned_after_clear_response.status_code == 200
    unassigned_after_clear_login_ids = {
        item["login_id"] for item in unassigned_after_clear_response.json()["items"]
    }
    assert "rootmember" in unassigned_after_clear_login_ids


def test_admin_org_units_hide_inactive_by_default_and_preserve_inactive_view(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    headers = _auth_headers(session["token"])

    inactive_parent_response = client.post(
        "/api/v1/admin/org-units",
        headers=headers,
        json={
            "name": "폐쇄 부서",
            "slug": "inactive-parent",
            "active": False,
        },
    )
    assert inactive_parent_response.status_code == 201, inactive_parent_response.text
    inactive_parent = inactive_parent_response.json()
    child_response = client.post(
        "/api/v1/admin/org-units",
        headers=headers,
        json={
            "name": "활성 하위 부서",
            "slug": "active-child",
            "parent_id": inactive_parent["id"],
            "active": True,
        },
    )
    assert child_response.status_code == 201, child_response.text

    active_response = client.get("/api/v1/admin/org-units", headers=headers)
    assert active_response.status_code == 200, active_response.text
    active_items = active_response.json()
    assert all(item["active"] for item in active_items)
    assert {item["slug"] for item in active_items}.isdisjoint({"inactive-parent"})
    active_child = next(item for item in active_items if item["slug"] == "active-child")
    assert active_child["parent_id"] is None

    include_inactive_response = client.get(
        "/api/v1/admin/org-units?include_inactive=true",
        headers=headers,
    )
    assert include_inactive_response.status_code == 200, include_inactive_response.text
    all_items = include_inactive_response.json()
    inactive_parent_item = next(item for item in all_items if item["slug"] == "inactive-parent")
    inactive_child_item = next(item for item in all_items if item["slug"] == "active-child")
    assert inactive_parent_item["active"] is False
    assert inactive_child_item["parent_id"] == inactive_parent["id"]
