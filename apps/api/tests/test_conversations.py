from __future__ import annotations

from fastapi.testclient import TestClient

from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_meeting,
    _create_user_with_workspaces,
    _login,
)


def _workspace_slug(client: TestClient, token: str) -> str:
    response = client.get("/api/v1/admin/workspaces", headers=_auth_headers(token))
    assert response.status_code == 200, response.text
    workspace = response.json()[0]
    return workspace.get("slug", workspace["key"])


def _create(client: TestClient, token: str, slug: str, title: str = "") -> dict:
    response = client.post(
        f"/api/v1/workspaces/{slug}/chatbot/conversations",
        headers=_auth_headers(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_then_list_returns_own_conversation(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="스프린트 계획")
    assert created["id"]
    assert created["title"] == "스프린트 계획"
    assert created["turns"] == []

    listing = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations",
        headers=_auth_headers(token),
    )
    assert listing.status_code == 200
    body = listing.json()
    assert [item["id"] for item in body["items"]] == [created["id"]]
    assert body["nextCursor"] is None


def test_patch_renames_conversation(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="initial")
    response = client.patch(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{created['id']}",
        headers=_auth_headers(token),
        json={"title": "updated"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "updated"


def test_patch_empty_title_rejected(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="x")
    response = client.patch(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{created['id']}",
        headers=_auth_headers(token),
        json={"title": "   "},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "conversations.title_empty"


def test_ai_create_rejects_meeting_scope_for_non_participant(client: TestClient) -> None:
    session = _bootstrap_admin_session(client)
    admin_token = session["token"]
    slug = _workspace_slug(client, admin_token)
    meeting = _create_meeting(client, admin_token, workspace_slug=slug, title="Private scope meeting")
    outsider = _create_user_with_workspaces(
        client,
        admin_token,
        email="conversation-outsider@open-alm.local",
        full_name="Conversation Outsider",
        workspace_keys=[slug],
    )
    outsider_token = _login(
        client,
        outsider["user"]["email"],
        outsider["temporary_password"],
    )

    response = client.post(
        f"/api/v1/workspaces/{slug}/chatbot/conversations",
        headers=_auth_headers(outsider_token),
        json={
            "title": "",
            "scopeRef": "meeting",
            "scopeResourceId": meeting["id"],
        },
    )

    assert response.status_code == 403


def test_delete_soft_hides_from_list_but_direct_get_also_404s(
    client: TestClient,
) -> None:
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)

    created = _create(client, token, slug, title="gone")
    response = client.delete(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{created['id']}",
        headers=_auth_headers(token),
    )
    assert response.status_code == 204

    listing = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations",
        headers=_auth_headers(token),
    )
    assert listing.status_code == 200
    assert created["id"] not in [item["id"] for item in listing.json()["items"]]

    # Soft-delete is not the same as hard-delete, but we still refuse to
    # serve a deleted conversation to the user — preserving rows purely so
    # an admin could restore them out-of-band.
    direct = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/{created['id']}",
        headers=_auth_headers(token),
    )
    assert direct.status_code == 404


def test_get_requires_ownership(client: TestClient) -> None:
    # A bogus id should 404, not leak 200 or 403 — enforces the "scoped to
    # owner" contract.
    session = _bootstrap_admin_session(client)
    token = session["token"]
    slug = _workspace_slug(client, token)
    response = client.get(
        f"/api/v1/workspaces/{slug}/chatbot/conversations/does-not-exist",
        headers=_auth_headers(token),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "conversations.not_found"
