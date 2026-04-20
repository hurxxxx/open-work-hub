from __future__ import annotations

import asyncio
import base64

from fastapi.testclient import TestClient
import pytest
from starlette.websockets import WebSocketDisconnect
import y_py as Y

from aidoo_api.domains.docs.collab import CollabPageContext, DocsCollabHub, make_room_key
from aidoo_api.domains.docs.collab_codec import blocks_to_yjs_state, yjs_state_to_blocks
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.media.models import MediaFile
from aidoo_api.core.db import get_session_factory
from test_docs_hub import (
    _add_task_list_member,
    _auth_headers,
    _create_doc_page,
    _create_space_doc,
    _create_task_list,
)
from test_meeting import (
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


def _create_unlinked_media(uploaded_by_id: str) -> dict[str, str]:
    media_id = new_id()
    db = get_session_factory()()
    try:
        db.add(
            MediaFile(
                id=media_id,
                storage_key=f"media/{uploaded_by_id}/{media_id}/fixture.png",
                filename="fixture.png",
                content_type="image/png",
                size_bytes=128,
                uploaded_by_id=uploaded_by_id,
            )
        )
        db.commit()
    finally:
        db.close()

    return {"id": media_id}


def _create_native_doc_page(client: TestClient, token: str, workspace_slug: str) -> tuple[dict, dict]:
    create_doc_response = client.post(
        "/api/v1/docs/items",
        headers=_auth_headers(token),
        json={"title": "Realtime Notes"},
    )
    assert create_doc_response.status_code == 201, create_doc_response.text
    doc = create_doc_response.json()

    pages_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(token),
    )
    assert pages_response.status_code == 200, pages_response.text
    page = pages_response.json()["items"][0]
    assert page["realtime_collab"] is True
    return doc, page


def test_docs_collab_session_snapshot_and_rest_patch_stay_in_sync(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    doc, page = _create_native_doc_page(client, admin["token"], workspace_slug)

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
    assert initial_session["realtime_status"] == "enabled"
    assert initial_session["read_only_reason"] is None
    assert initial_session["snapshot_content_blocks"] == []
    assert isinstance(initial_session["yjs_state"], str)
    assert initial_session["yjs_state"]

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
    assert isinstance(rest_session["yjs_state"], str)
    assert rest_session["yjs_state"]


def test_docs_collab_websocket_requires_auth_and_accepts_valid_token(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    _doc, page = _create_native_doc_page(client, admin["token"], workspace_slug)
    page_ref = _page_ref(page["source_type"], page["source_page_id"])
    websocket_path = f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/ws"

    with pytest.raises(WebSocketDisconnect) as invalid_auth:
        with client.websocket_connect(websocket_path) as websocket:
            websocket.send_json({"type": "auth", "token": "not-a-real-token"})
            websocket.receive_json()
    assert invalid_auth.value.code == 4401

    with client.websocket_connect(f"{websocket_path}?token={admin['token']}") as websocket:
        websocket.close()


def test_docs_native_page_linked_media_resolves_for_shared_user(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    doc, page = _create_native_doc_page(client, admin["token"], workspace_slug)

    member = _create_user_with_workspaces(
        client,
        admin["token"],
        email="docs-media-member@aidoo.local",
        full_name="Docs Media Member",
        workspace_keys=["hq"],
    )
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    share_response = client.put(
        f"/api/v1/docs/items/{doc['id']}/sharing/users/{member['user']['id']}",
        headers=_auth_headers(admin["token"]),
        json={"access_level": "edit"},
    )
    assert share_response.status_code == 200, share_response.text

    media = _create_unlinked_media(admin["user"]["id"])
    link_response = client.post(
        "/api/v1/media/link",
        headers=_auth_headers(admin["token"]),
        json={
            "media_ids": [media["id"]],
            "resource_type": "docs_native_page",
            "resource_id": page["id"],
        },
    )
    assert link_response.status_code == 204, link_response.text

    resolve_response = client.post(
        "/api/v1/media/resolve",
        headers=_auth_headers(member_token),
        json={"urls": [f"media:{media['id']}"]},
    )
    assert resolve_response.status_code == 200, resolve_response.text
    assert resolve_response.json()["resolved"][f"media:{media['id']}"]


def test_docs_collab_session_degraded_when_relay_is_unavailable(client_without_collab_relay: TestClient) -> None:
    admin = _bootstrap_admin_session(client_without_collab_relay)
    workspace_slug = _first_workspace_slug(client_without_collab_relay, admin["token"])
    _doc, page = _create_native_doc_page(client_without_collab_relay, admin["token"], workspace_slug)
    page_ref = _page_ref(page["source_type"], page["source_page_id"])

    session_response = client_without_collab_relay.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/session",
        headers=_auth_headers(admin["token"]),
    )
    assert session_response.status_code == 200, session_response.text
    payload = session_response.json()
    assert payload["realtime_status"] == "degraded"
    assert payload["read_only_reason"] == "relay_unavailable"

    with pytest.raises(WebSocketDisconnect) as relay_down:
        with client_without_collab_relay.websocket_connect(
            f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/ws?token={admin['token']}"
        ) as websocket:
            websocket.receive_json()
    assert relay_down.value.code == 1013


def test_docs_collab_hub_relays_updates_and_flushes_server_side(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    doc, page = _create_native_doc_page(client, admin["token"], workspace_slug)
    collab_blocks = _paragraph_blocks("Server-side relay flush")
    collab_update = blocks_to_yjs_state(collab_blocks)
    assert collab_update is not None
    expected_blocks = yjs_state_to_blocks(collab_update)
    assert expected_blocks is not None

    async def exercise_hubs() -> None:
        context = CollabPageContext(
            page_ref=_page_ref(page["source_type"], page["source_page_id"]),
            source_type=page["source_type"],
            source_page_id=page["source_page_id"],
            room_key=make_room_key(page["source_type"], page["source_page_id"]),
            can_edit=True,
            content_blocks=[],
            default_actor_user_id=page["created_by_id"],
        )
        hub1 = DocsCollabHub()
        hub2 = DocsCollabHub()
        hub1._instance_id = "test-hub-1"
        hub1._bus.instance_id = "test-hub-1"
        hub2._instance_id = "test-hub-2"
        hub2._bus.instance_id = "test-hub-2"
        await hub1.startup()
        await hub2.startup()
        try:
            runtime1 = await hub1.get_room(context, None)
            runtime2 = await hub2.get_room(context, None)
            Y.apply_update(runtime1.room.ydoc, collab_update)

            deadline = asyncio.get_running_loop().time() + 5
            while True:
                mirrored_blocks = yjs_state_to_blocks(Y.encode_state_as_update(runtime2.room.ydoc))
                if mirrored_blocks == expected_blocks:
                    break
                if asyncio.get_running_loop().time() >= deadline:
                    raise AssertionError("Timed out waiting for cross-instance relay sync.")
                await asyncio.sleep(0.1)

            await hub1.cleanup_room(context.room_key)
            await hub2.cleanup_room(context.room_key)
        finally:
            await hub1.shutdown()
            await hub2.shutdown()

    asyncio.run(exercise_hubs())

    refreshed_pages_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/pages",
        headers=_auth_headers(admin["token"]),
    )
    assert refreshed_pages_response.status_code == 200, refreshed_pages_response.text
    refreshed_page = next(
        item for item in refreshed_pages_response.json()["items"] if item["id"] == page["id"]
    )
    assert refreshed_page["content_blocks"] == expected_blocks


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


def test_pms_container_doc_collab_session_uses_workspace_acl_and_page_ref(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    task_list = _create_task_list(client, admin_token, key="CLAB", name="Collab List")

    space_doc = _create_space_doc(client, admin_token, task_list["team_id"], title="Space Handbook")
    page = _create_doc_page(client, admin_token, space_doc["id"], title="Overview")
    assert page["realtime_collab"] is True

    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="space-collab-member@aidoo.local",
        full_name="Space Collab Member",
        workspace_keys=[workspace_slug],
    )
    _add_task_list_member(client, admin_token, task_list["id"], member["user"]["id"], "member")
    member_token = _login(
        client,
        member["user"]["email"],
        member["temporary_password"],
    )

    page_ref = _page_ref("native_doc_page", page["id"])
    session_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/collab/pages/{page_ref}/session",
        headers=_auth_headers(member_token),
    )
    assert session_response.status_code == 200, session_response.text
    payload = session_response.json()
    assert payload["page_ref"] == page_ref
    assert payload["source_type"] == "native_doc_page"
    assert payload["source_page_id"] == page["id"]
    assert payload["room_key"] == f"native_doc_page:{page['id']}"
    assert payload["can_edit"] is True
