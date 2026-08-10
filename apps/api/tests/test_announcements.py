from __future__ import annotations

from fastapi.testclient import TestClient

from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_user_with_workspaces,
    _login,
)

_BASE = "/api/v1/workspaces/administrator/announcements"


def test_announcement_crud_and_pin_ordering(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    first = client.post(
        _BASE,
        headers=_auth_headers(token),
        json={"title": "1차 공지", "body": "본문 내용"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["title"] == "1차 공지"
    assert first.json()["isPinned"] is False
    assert first.json()["authorName"]

    second = client.post(
        _BASE,
        headers=_auth_headers(token),
        json={"title": "고정 공지", "isPinned": True},
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]

    listing = client.get(_BASE, headers=_auth_headers(token))
    assert listing.status_code == 200, listing.text
    items = listing.json()["items"]
    assert {item["id"] for item in items} >= {first.json()["id"], second_id}
    # Pinned announcement is ordered first.
    assert items[0]["id"] == second_id

    detail = client.get(f"{_BASE}/{second_id}", headers=_auth_headers(token))
    assert detail.status_code == 200, detail.text

    patched = client.patch(
        f"{_BASE}/{second_id}",
        headers=_auth_headers(token),
        json={"isPinned": False, "title": "고정 해제 공지"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["isPinned"] is False
    assert patched.json()["title"] == "고정 해제 공지"

    deleted = client.delete(
        f"{_BASE}/{first.json()['id']}",
        headers=_auth_headers(token),
    )
    assert deleted.status_code == 204
    gone = client.get(
        f"{_BASE}/{first.json()['id']}",
        headers=_auth_headers(token),
    )
    assert gone.status_code == 404


def test_announcement_requires_admin_to_write(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="ann-member@open-alm.local",
        full_name="Announcement Member",
        workspace_keys=["administrator"],
    )
    member_token = _login(
        client,
        member["user"]["email"],
        member["temporary_password"],
    )

    forbidden = client.post(
        _BASE,
        headers=_auth_headers(member_token),
        json={"title": "권한 없는 공지"},
    )
    assert forbidden.status_code == 403, forbidden.text

    # Reading announcements is allowed for any workspace member.
    listing = client.get(_BASE, headers=_auth_headers(member_token))
    assert listing.status_code == 200, listing.text


def test_announcement_company_scope_visibility(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]  # bootstrap admin is also a platform admin
    other = _create_user_with_workspaces(
        client,
        token,
        email="ann-other-workspace@open-alm.local",
        full_name="Other Workspace User",
        workspace_keys=["ai-tft"],
    )
    other_token = _login(
        client,
        other["user"]["email"],
        other["temporary_password"],
    )

    company = client.post(
        _BASE,
        headers=_auth_headers(token),
        json={"title": "전사 공지", "scope": "company", "isPinned": True},
    )
    assert company.status_code == 201, company.text
    assert company.json()["scope"] == "company"
    company_id = company.json()["id"]

    workspace_only = client.post(
        _BASE,
        headers=_auth_headers(token),
        json={"title": "팀 공지"},
    )
    assert workspace_only.status_code == 201, workspace_only.text

    company_list = client.get(
        _BASE,
        headers=_auth_headers(token),
        params={"scope": "company"},
    )
    assert company_list.status_code == 200, company_list.text
    company_ids = {item["id"] for item in company_list.json()["items"]}
    assert company_id in company_ids
    assert workspace_only.json()["id"] not in company_ids

    workspace_list = client.get(
        _BASE,
        headers=_auth_headers(token),
        params={"scope": "workspace"},
    )
    assert workspace_list.status_code == 200, workspace_list.text
    assert company_id not in {item["id"] for item in workspace_list.json()["items"]}

    visible_from_other_workspace = client.get(
        "/api/v1/workspaces/ai-tft/announcements",
        headers=_auth_headers(other_token),
        params={"scope": "company"},
    )
    assert visible_from_other_workspace.status_code == 200, (
        visible_from_other_workspace.text
    )
    assert company_id in {
        item["id"] for item in visible_from_other_workspace.json()["items"]
    }

    detail_from_other_workspace = client.get(
        f"/api/v1/workspaces/ai-tft/announcements/{company_id}",
        headers=_auth_headers(other_token),
    )
    assert detail_from_other_workspace.status_code == 200, (
        detail_from_other_workspace.text
    )


def test_company_announcement_requires_platform_admin(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="ann-company-member@open-alm.local",
        full_name="Company Member",
        workspace_keys=["administrator"],
    )
    member_token = _login(
        client,
        member["user"]["email"],
        member["temporary_password"],
    )

    forbidden = client.post(
        _BASE,
        headers=_auth_headers(member_token),
        json={"title": "전사 공지 시도", "scope": "company"},
    )
    assert forbidden.status_code == 403, forbidden.text
