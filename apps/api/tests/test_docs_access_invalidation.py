import pytest
from fastapi import HTTPException

from open_work_hub_api.domains.docs.collab import make_page_ref
from open_work_hub_api.domains.docs.router import _require_collab_edit_access
from test_company_content_boundaries import _enable, _group, _user
from test_company_groups import _setup


def test_doc_sharing_invalidates_only_that_resource_without_content_or_unrelated_users(
    client, monkeypatch
):
    admin, _ = _setup(client)
    for app in ("docs", "pms"):
        _enable(client, admin, app)
    owner, _ = _user(client, admin, "invalidationowner")
    reader, reader_id = _user(client, admin, "invalidationreader")
    group_id = _group(client, admin, [reader_id])
    space = client.post("/api/v1/pms/spaces", headers=owner, json={"name": "Project"})
    assert space.status_code == 201
    created = client.post("/api/v1/docs/items", headers=owner, json={"title": "Private title"})
    assert created.status_code == 201
    item_id = created.json()["id"]
    doc_id = item_id.split("__")[-1]
    url = f"/api/v1/docs/items/{item_id}"
    events = []
    monkeypatch.setattr(
        client.app.state.app_realtime,
        "publish",
        lambda topic, event: events.append((topic, event)),
    )

    def changed(method, suffix, body=None):
        events.clear()
        response = client.request(method, f"{url}{suffix}", headers=owner, json=body)
        assert response.status_code in (200, 204), response.text
        assert events == [
            (f"docs.pages:{doc_id}", {"type": "docs.access.changed", "data": {"doc_id": doc_id}})
        ]
        return response

    changed("PUT", f"/sharing/users/{reader_id}", {"access_level": "edit"})
    assert client.get(url, headers=reader).json()["can_edit"]
    changed("PUT", f"/sharing/users/{reader_id}", {"access_level": "read"})
    assert not client.get(url, headers=reader).json()["can_edit"]
    changed("DELETE", f"/sharing/users/{reader_id}")
    assert client.get(url, headers=reader).status_code == 404

    changed("PUT", "/sharing/link", {"active": True, "access_level": "edit"})
    changed(
        "PUT", "/sharing/link", {"active": True, "access_level": "read", "regenerate_token": True}
    )
    changed("DELETE", "/sharing/link")
    changed("PUT", f"/sharing/groups/{group_id}", {"access_level": "read"})
    assert client.get(url, headers=reader).status_code == 200
    changed("DELETE", f"/sharing/groups/{group_id}")
    assert client.get(url, headers=reader).status_code == 404
    changed("PUT", "/sharing/company", {"enabled": True, "company_admin_read_acknowledged": True})
    assert client.get(url, headers=reader).status_code == 200
    changed("PUT", "/sharing/company", {"enabled": False})
    assert client.get(url, headers=reader).status_code == 404
    changed(
        "PUT",
        "/target",
        {
            "app": "pms",
            "type": "space",
            "id": space.json()["id"],
            "company_admin_read_acknowledged": True,
        },
    )
    changed("DELETE", "/target")
    changed("PUT", f"/sharing/users/{reader_id}", {"access_level": "read"})
    assert client.get(url, headers=reader).status_code == 200
    changed("DELETE", "")
    assert client.get(url, headers=reader).status_code == 404
    assert client.get(url, headers=owner).json()["trashed_at"] is not None


def test_docs_collab_frame_authorization_rechecks_source_and_session(client):
    admin, _ = _setup(client)
    _enable(client, admin, "docs")
    owner, _ = _user(client, admin, "frameowner")
    editor, editor_id = _user(client, admin, "frameeditor")
    created = client.post("/api/v1/docs/items", headers=owner, json={"title": "Frame permissions"})
    assert created.status_code == 201
    url = f"/api/v1/docs/items/{created.json()['id']}"
    pages = client.get(f"{url}/pages", headers=owner)
    assert pages.status_code == 200, pages.text
    page = pages.json()["items"][0]
    page_ref = make_page_ref(page["source_type"], page["source_page_id"])
    token = editor["Authorization"].removeprefix("Bearer ")
    share_url = f"{url}/sharing/users/{editor_id}"
    assert client.put(share_url, headers=owner, json={"access_level": "edit"}).status_code == 200
    _require_collab_edit_access(page_ref=page_ref, token=token)
    assert client.put(share_url, headers=owner, json={"access_level": "read"}).status_code == 200
    with pytest.raises(HTTPException) as denied:
        _require_collab_edit_access(page_ref=page_ref, token=token)
    assert denied.value.status_code == 403
    assert client.put(share_url, headers=owner, json={"access_level": "edit"}).status_code == 200
    _require_collab_edit_access(page_ref=page_ref, token=token)
    assert client.post("/api/v1/auth/logout", headers=editor).status_code == 204
    with pytest.raises(HTTPException) as denied:
        _require_collab_edit_access(page_ref=page_ref, token=token)
    assert denied.value.status_code == 401
