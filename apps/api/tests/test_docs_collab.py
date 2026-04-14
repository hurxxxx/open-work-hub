from __future__ import annotations

import base64

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect
import y_py as Y

from tests.test_docs_hub import _add_project_member, _auth_headers, _create_project
from tests.test_meeting import (
    _bootstrap_admin_session,
    _create_meeting,
    _create_user_with_workspaces,
    _first_workspace_slug,
    _login,
)


def _paragraph_blocks(text: str) -> list[dict]:
    return [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }
    ]


def _encode_test_yjs_state(text: str) -> str:
    doc = Y.YDoc()
    with doc.begin_transaction() as txn:
        doc.get_text("prosemirror").extend(txn, text)
    return base64.b64encode(Y.encode_state_as_update(doc)).decode("ascii")


def _page_ref(source_type: str, source_page_id: str) -> str:
    return f"{source_type}__{source_page_id}"


def test_docs_collab_session_snapshot_and_rest_patch_stay_in_sync(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])

    create_doc_response = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Realtime Notes"},
    )
    assert create_doc_response.status_code == 201, create_doc_response.text
    doc = create_doc_response.json()

    pages_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(admin["token"]),
    )
    assert pages_response.status_code == 200, pages_response.text
    page = pages_response.json()["items"][0]
    assert page["realtime_collab"] is True

    page_ref = _page_ref(page["source_type"], page["source_page_id"])
    session_path = f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/session"
    snapshot_path = f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/snapshot"

    initial_session_response = client.get(
        session_path,
        headers=_auth_headers(admin["token"]),
    )
    assert initial_session_response.status_code == 200, initial_session_response.text
    initial_session = initial_session_response.json()
    assert initial_session["page_ref"] == page_ref
    assert initial_session["room_key"] == f"native_doc_page:{page['id']}"
    assert initial_session["can_edit"] is True
    assert initial_session["snapshot_content_blocks"] == []
    assert initial_session["yjs_state"] is None

    collab_blocks = _paragraph_blocks("Synced from collab")
    yjs_state = _encode_test_yjs_state("Synced from collab")

    snapshot_response = client.put(
        snapshot_path,
        headers=_auth_headers(admin["token"]),
        json={
            "content_blocks": collab_blocks,
            "yjs_state": yjs_state,
        },
    )
    assert snapshot_response.status_code == 200, snapshot_response.text

    refreshed_session_response = client.get(
        session_path,
        headers=_auth_headers(admin["token"]),
    )
    assert refreshed_session_response.status_code == 200, refreshed_session_response.text
    refreshed_session = refreshed_session_response.json()
    assert refreshed_session["snapshot_content_blocks"] == collab_blocks
    assert refreshed_session["yjs_state"] == yjs_state

    page_refresh_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(admin["token"]),
    )
    assert page_refresh_response.status_code == 200, page_refresh_response.text
    refreshed_page = next(
        item for item in page_refresh_response.json()["items"] if item["id"] == page["id"]
    )
    assert refreshed_page["content_blocks"] == collab_blocks

    rest_blocks = _paragraph_blocks("Updated through REST")
    rest_patch_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/docs/pages/{page['id']}",
        headers=_auth_headers(admin["token"]),
        json={"content_blocks": rest_blocks},
    )
    assert rest_patch_response.status_code == 200, rest_patch_response.text

    rest_session_response = client.get(
        session_path,
        headers=_auth_headers(admin["token"]),
    )
    assert rest_session_response.status_code == 200, rest_session_response.text
    rest_session = rest_session_response.json()
    assert rest_session["snapshot_content_blocks"] == rest_blocks
    assert rest_session["yjs_state"] is None


def test_docs_collab_websocket_requires_auth_and_accepts_valid_token(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])

    create_doc_response = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(admin["token"]),
        json={"title": "Realtime Socket"},
    )
    assert create_doc_response.status_code == 201, create_doc_response.text
    doc = create_doc_response.json()

    pages_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(admin["token"]),
    )
    assert pages_response.status_code == 200, pages_response.text
    page = pages_response.json()["items"][0]
    page_ref = _page_ref(page["source_type"], page["source_page_id"])
    websocket_path = f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/ws"

    with pytest.raises(WebSocketDisconnect) as invalid_auth:
        with client.websocket_connect(websocket_path) as websocket:
            websocket.send_json({"type": "auth", "token": "not-a-real-token"})
            websocket.receive_json()
    assert invalid_auth.value.code == 4401

    with client.websocket_connect(f"{websocket_path}?token={admin['token']}") as websocket:
        assert websocket.receive_json() == {"type": "auth_ok"}
        websocket.close()


def test_meeting_notes_collab_session_is_revoked_when_attendee_is_removed(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="notes-collab-attendee@aidoo.local",
        full_name="Notes Collab Attendee",
        workspace_keys=[workspace_slug],
    )
    attendee_token = _login(
        client,
        attendee["user"]["email"],
        attendee["temporary_password"],
    )

    meeting = _create_meeting(
        client,
        admin_token,
        title="Realtime notes ACL",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
    )

    ensure_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert ensure_response.status_code == 200, ensure_response.text
    notes = ensure_response.json()
    page_ref = _page_ref("native_doc_page", notes["notes_page_id"])
    session_path = f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/session"

    attendee_session_response = client.get(
        session_path,
        headers=_auth_headers(attendee_token),
    )
    assert attendee_session_response.status_code == 200, attendee_session_response.text
    assert attendee_session_response.json()["can_edit"] is True

    remove_attendee_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin_token),
        json={"attendees": []},
    )
    assert remove_attendee_response.status_code == 200, remove_attendee_response.text

    revoked_session_response = client.get(
        session_path,
        headers=_auth_headers(attendee_token),
    )
    assert revoked_session_response.status_code == 404, revoked_session_response.text


def test_pms_space_doc_collab_session_uses_workspace_acl_and_page_ref(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    project = _create_project(client, admin_token, key="CLAB", name="Collab Project")

    create_space_doc_response = client.post(
        f"/api/v1/pms/spaces/{project['team_id']}/docs",
        headers=_auth_headers(admin_token),
        json={"title": "Space Handbook"},
    )
    assert create_space_doc_response.status_code == 201, create_space_doc_response.text
    space_doc = create_space_doc_response.json()

    create_page_response = client.post(
        f"/api/v1/pms/spaces/{project['team_id']}/docs/pages",
        headers=_auth_headers(admin_token),
        json={"title": "Overview", "space_doc_id": space_doc["id"]},
    )
    assert create_page_response.status_code == 201, create_page_response.text
    page = create_page_response.json()
    assert page["realtime_collab"] is True

    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="space-collab-member@aidoo.local",
        full_name="Space Collab Member",
        workspace_keys=[workspace_slug],
    )
    _add_project_member(client, admin_token, project["id"], member["user"]["id"], "member")
    member_token = _login(
        client,
        member["user"]["email"],
        member["temporary_password"],
    )

    page_ref = _page_ref("pms_space_doc_page", page["id"])
    session_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/session",
        headers=_auth_headers(member_token),
    )
    assert session_response.status_code == 200, session_response.text
    payload = session_response.json()
    assert payload["page_ref"] == page_ref
    assert payload["source_type"] == "pms_space_doc_page"
    assert payload["source_page_id"] == page["id"]
    assert payload["room_key"] == f"pms_space_doc_page:{page['id']}"
    assert payload["can_edit"] is True
