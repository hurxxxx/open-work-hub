from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from dev_accounts import dev_login


TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/l5vN2wAAAABJRU5ErkJggg=="
)


@pytest.mark.external_integration("minio")
def test_diagrams_create_update_archive_restore_and_preview(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-admin")
    token = session["token"]

    create_response = client.post(
        "/api/v1/diagrams/items",
        headers=_auth_headers(token),
        json={
            "title": "Launch Flow",
            "xml": '<mxfile><diagram id="page-1" name="Page-1" /></mxfile>',
            "preview_png_data_url": TINY_PNG_DATA_URL,
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["title"] == "Launch Flow"
    assert created["visibility"] == "personal"
    assert created["version"] == 1
    assert created["preview_available"] is True
    assert created["can_edit"] is True
    assert created["can_manage"] is True

    preview_response = client.get(
        f"/api/v1/diagrams/items/{created['id']}/preview.png",
        headers=_auth_headers(token),
    )
    assert preview_response.status_code == 200, preview_response.text
    assert preview_response.headers["content-type"].startswith("image/png")
    assert preview_response.content.startswith(b"\x89PNG")

    stale_update_response = client.patch(
        f"/api/v1/diagrams/items/{created['id']}",
        headers=_auth_headers(token),
        json={"version": created["version"] + 1, "title": "Stale"},
    )
    assert stale_update_response.status_code == 409
    assert stale_update_response.json()["code"] == "diagrams.version_conflict"

    update_response = client.patch(
        f"/api/v1/diagrams/items/{created['id']}",
        headers=_auth_headers(token),
        json={
            "version": created["version"],
            "title": "Launch Flow v2",
            "xml": '<mxfile><diagram id="page-2" name="Updated" /></mxfile>',
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["title"] == "Launch Flow v2"
    assert updated["version"] == 2
    assert "page-2" in updated["xml"]

    visibility_response = client.patch(
        f"/api/v1/diagrams/items/{created['id']}",
        headers=_auth_headers(token),
        json={
            "version": updated["version"],
            "visibility": "company",
            "company_admin_read_acknowledged": True,
        },
    )
    assert visibility_response.status_code == 200, visibility_response.text
    visible_to_company = visibility_response.json()
    assert visible_to_company["visibility"] == "company"
    assert visible_to_company["version"] == 3

    mine_response = client.get(
        "/api/v1/diagrams/hub",
        headers=_auth_headers(token),
        params={"view": "mine"},
    )
    assert mine_response.status_code == 200
    assert [item["id"] for item in mine_response.json()["items"]] == [created["id"]]

    archive_response = client.delete(
        f"/api/v1/diagrams/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert archive_response.status_code == 204

    archived_response = client.get(
        "/api/v1/diagrams/hub",
        headers=_auth_headers(token),
        params={"view": "archived"},
    )
    assert archived_response.status_code == 200
    assert [item["id"] for item in archived_response.json()["items"]] == [created["id"]]

    restore_response = client.post(
        f"/api/v1/diagrams/items/{created['id']}/restore",
        headers=_auth_headers(token),
    )
    assert restore_response.status_code == 200, restore_response.text
    assert restore_response.json()["archived_at"] is None


def test_diagrams_requires_current_app_admission(client: TestClient) -> None:
    session = dev_login(client, "delivery-hub-member")

    from open_work_hub_api.core.db import get_session_factory
    from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

    with get_session_factory()() as db:
        db.get(AppAccessPolicy, "diagrams").audience = "selected"
        db.commit()

    response = client.get(
        "/api/v1/diagrams/hub",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 403


def test_diagrams_visibility_limits_personal_items_to_owner(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    owner = dev_login(client, "delivery-hub-admin")
    member = dev_login(client, "delivery-hub-member")

    personal_response = client.post(
        "/api/v1/diagrams/items",
        headers=_auth_headers(owner["token"]),
        json={"title": "Private Flow"},
    )
    assert personal_response.status_code == 201, personal_response.text
    personal = personal_response.json()
    assert personal["visibility"] == "personal"

    company_response = client.post(
        "/api/v1/diagrams/items",
        headers=_auth_headers(owner["token"]),
        json={
            "title": "Shared Flow",
            "visibility": "company",
            "company_admin_read_acknowledged": True,
        },
    )
    assert company_response.status_code == 201, company_response.text
    company_item = company_response.json()
    assert company_item["visibility"] == "company"

    member_hub_response = client.get(
        "/api/v1/diagrams/hub",
        headers=_auth_headers(member["token"]),
    )
    assert member_hub_response.status_code == 200, member_hub_response.text
    member_ids = [item["id"] for item in member_hub_response.json()["items"]]
    assert company_item["id"] in member_ids
    assert personal["id"] not in member_ids

    member_private_response = client.get(
        f"/api/v1/diagrams/items/{personal['id']}",
        headers=_auth_headers(member["token"]),
    )
    assert member_private_response.status_code == 404

    member_public_update_response = client.patch(
        f"/api/v1/diagrams/items/{company_item['id']}",
        headers=_auth_headers(member["token"]),
        json={"version": company_item["version"], "title": "Shared Flow Updated"},
    )
    assert member_public_update_response.status_code == 403, member_public_update_response.text

    member_visibility_response = client.patch(
        f"/api/v1/diagrams/items/{company_item['id']}",
        headers=_auth_headers(member["token"]),
        json={"version": company_item["version"], "visibility": "personal"},
    )
    assert member_visibility_response.status_code == 403


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
