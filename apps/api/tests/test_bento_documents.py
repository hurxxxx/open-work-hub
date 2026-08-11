from __future__ import annotations

import json

from fastapi.testclient import TestClient

from dev_accounts import dev_login


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _document_json(*, title: str, slide_id: str = "slide-1") -> str:
    return json.dumps(
        {
            "format": "bento/slides",
            "version": 1,
            "docId": "doc-1",
            "title": title,
            "size": {"width": 1280, "height": 720},
            "theme": {
                "background": "#FFFFFF",
                "color": "#1E2A3A",
                "accent": "#F7A600",
                "fontFamily": "sans-serif",
            },
            "slides": [
                {
                    "id": slide_id,
                    "background": "#FFFFFF",
                    "transition": "fade",
                    "elements": [],
                    "notes": "",
                }
            ],
            "modified": "2026-08-11T00:00:00Z",
        }
    )


def test_bento_create_update_archive_restore_and_delete(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(session["token"])
    base = "/api/v1/workspaces/delivery-hub/bento"

    create_response = client.post(
        f"{base}/items",
        headers=headers,
        json={"title": "Launch deck"},
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["title"] == "Launch deck"
    assert created["visibility"] == "personal"
    assert created["version"] == 1
    assert json.loads(created["document_json"])["format"] == "bento/slides"

    stale_response = client.patch(
        f"{base}/items/{created['id']}",
        headers=headers,
        json={"version": 99, "title": "Stale"},
    )
    assert stale_response.status_code == 409
    assert stale_response.json()["code"] == "bento.version_conflict"

    update_response = client.patch(
        f"{base}/items/{created['id']}",
        headers=headers,
        json={
            "version": created["version"],
            "document_json": _document_json(title="Launch deck v2", slide_id="slide-2"),
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["title"] == "Launch deck v2"
    assert updated["version"] == 2
    assert json.loads(updated["document_json"])["slides"][0]["id"] == "slide-2"

    visibility_response = client.patch(
        f"{base}/items/{created['id']}",
        headers=headers,
        json={"version": updated["version"], "visibility": "workspace"},
    )
    assert visibility_response.status_code == 200, visibility_response.text
    visible = visibility_response.json()
    assert visible["visibility"] == "workspace"
    assert visible["version"] == 3

    archive_response = client.delete(f"{base}/items/{created['id']}", headers=headers)
    assert archive_response.status_code == 204

    archived_response = client.get(
        f"{base}/hub",
        headers=headers,
        params={"view": "archived"},
    )
    assert archived_response.status_code == 200
    assert [item["id"] for item in archived_response.json()["items"]] == [created["id"]]

    restore_response = client.post(
        f"{base}/items/{created['id']}/restore",
        headers=headers,
    )
    assert restore_response.status_code == 200, restore_response.text
    assert restore_response.json()["archived_at"] is None

    assert client.delete(f"{base}/items/{created['id']}", headers=headers).status_code == 204
    permanent_response = client.delete(
        f"{base}/items/{created['id']}/permanent",
        headers=headers,
    )
    assert permanent_response.status_code == 204
    assert client.get(f"{base}/items/{created['id']}", headers=headers).status_code == 404


def test_bento_visibility_and_workspace_access(client: TestClient) -> None:
    owner = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")
    base = "/api/v1/workspaces/delivery-hub/bento"

    personal_response = client.post(
        f"{base}/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Private deck"},
    )
    assert personal_response.status_code == 201, personal_response.text
    personal = personal_response.json()

    workspace_response = client.post(
        f"{base}/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Shared deck", "visibility": "workspace"},
    )
    assert workspace_response.status_code == 201, workspace_response.text
    workspace_document = workspace_response.json()

    member_hub_response = client.get(
        f"{base}/hub",
        headers=_auth_headers(member["token"]),
    )
    assert member_hub_response.status_code == 200
    member_ids = [item["id"] for item in member_hub_response.json()["items"]]
    assert workspace_document["id"] in member_ids
    assert personal["id"] not in member_ids

    assert (
        client.get(
            f"{base}/items/{personal['id']}",
            headers=_auth_headers(member["token"]),
        ).status_code
        == 404
    )

    member_update = client.patch(
        f"{base}/items/{workspace_document['id']}",
        headers=_auth_headers(member["token"]),
        json={
            "version": workspace_document["version"],
            "document_json": _document_json(title="Shared deck edited"),
        },
    )
    assert member_update.status_code == 200, member_update.text

    member_visibility = client.patch(
        f"{base}/items/{workspace_document['id']}",
        headers=_auth_headers(member["token"]),
        json={"version": member_update.json()["version"], "visibility": "personal"},
    )
    assert member_visibility.status_code == 403

    member_owned_response = client.post(
        f"{base}/items",
        headers=_auth_headers(member["token"]),
        json={"title": "Member deck", "visibility": "workspace"},
    )
    assert member_owned_response.status_code == 201, member_owned_response.text
    member_owned = member_owned_response.json()

    admin_visibility = client.patch(
        f"{base}/items/{member_owned['id']}",
        headers=_auth_headers(owner["token"]),
        json={"version": member_owned["version"], "visibility": "personal"},
    )
    assert admin_visibility.status_code == 200, admin_visibility.text
    assert admin_visibility.json()["visibility"] == "personal"
    assert (
        client.get(
            f"{base}/items/{member_owned['id']}",
            headers=_auth_headers(owner["token"]),
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"{base}/items/{member_owned['id']}",
            headers=_auth_headers(member["token"]),
        ).status_code
        == 200
    )

    no_membership = client.get(
        "/api/v1/workspaces/general/bento/hub",
        headers=_auth_headers(member["token"]),
    )
    assert no_membership.status_code == 403


def test_bento_rejects_invalid_document_payload(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    response = client.post(
        "/api/v1/workspaces/delivery-hub/bento/items",
        headers=_auth_headers(session["token"]),
        json={"title": "Bad deck", "document_json": '{"format":"unknown"}'},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bento.invalid_document"

    blank_title_response = client.post(
        "/api/v1/workspaces/delivery-hub/bento/items",
        headers=_auth_headers(session["token"]),
        json={"title": "   ", "document_json": _document_json(title="Imported")},
    )
    assert blank_title_response.status_code == 422
