from __future__ import annotations

from fastapi.testclient import TestClient

from test_meeting import _auth_headers, _bootstrap_admin_session, _create_company_user, _login

_BASE = "/api/v1/announcements"


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
    member = _create_company_user(
        client,
        admin_token,
        email="ann-member@open-work-hub.local",
        full_name="Announcement Member",
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

    # Reading announcements is allowed for any admitted company user.
    listing = client.get(_BASE, headers=_auth_headers(member_token))
    assert listing.status_code == 200, listing.text


def test_announcement_default_and_explicit_company_audience_require_active_company_user(
    client: TestClient,
) -> None:
    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.models import User

    admin = _bootstrap_admin_session(client)
    other = _create_company_user(
        client,
        admin["token"],
        email="ann-colleague@open-work-hub.local",
        full_name="Company Colleague",
    )
    other_token = _login(client, other["user"]["email"], other["temporary_password"])
    ids = set()
    for payload in (
        {"title": "Default audience"},
        {"title": "Explicit audience", "scope": "company"},
    ):
        created = client.post(_BASE, headers=_auth_headers(admin["token"]), json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["scope"] == "company"
        ids.add(created.json()["id"])
    listing = client.get(_BASE, headers=_auth_headers(other_token))
    assert listing.status_code == 200, listing.text
    assert ids <= {item["id"] for item in listing.json()["items"]}
    for resource_id in ids:
        assert (
            client.get(f"{_BASE}/{resource_id}", headers=_auth_headers(other_token)).status_code
            == 200
        )
    with get_session_factory()() as db:
        db.get(User, other["user"]["id"]).login_blocked = True
        db.commit()
    assert client.get(_BASE, headers=_auth_headers(other_token)).status_code == 403
    for resource_id in ids:
        assert (
            client.get(f"{_BASE}/{resource_id}", headers=_auth_headers(other_token)).status_code
            == 403
        )


def test_company_announcement_requires_platform_admin(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    member = _create_company_user(
        client,
        admin_token,
        email="ann-company-member@open-work-hub.local",
        full_name="Company Member",
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
