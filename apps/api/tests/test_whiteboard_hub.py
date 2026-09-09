from __future__ import annotations

import asyncio
import base64

from fastapi.testclient import TestClient
import pytest

from dev_accounts import dev_login
import y_py as Y

from open_work_hub_api.domains.collaboration import CollabConnectionLimitExceeded
from open_work_hub_api.domains.whiteboard.collab import WhiteboardCollabContext, WhiteboardCollabHub


def test_whiteboard_create_update_reload_and_archive(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    create_response = client.post(
        "/api/v1/whiteboard/items",
        headers=_auth_headers(token),
        json={
            "title": "Launch Map",
            "company_visible": True,
            "company_admin_read_acknowledged": True,
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["title"] == "Launch Map"
    assert created["scene"] == {"elements": [], "appState": {}, "files": {}}
    assert created["company_visible"] is True
    assert created["can_edit"] is True

    scene = {
        "elements": [{"id": "text-1", "type": "text", "text": "hello"}],
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    update_response = client.patch(
        f"/api/v1/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
        json={"title": "Launch Map v2", "scene": scene},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["title"] == "Launch Map v2"
    assert update_response.json()["scene"] == scene

    reload_response = client.get(
        f"/api/v1/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert reload_response.status_code == 200
    assert reload_response.json()["scene"] == scene
    updated_at = reload_response.json()["updated_at"]

    view_response = client.post(
        f"/api/v1/whiteboard/items/{created['id']}/view",
        headers=_auth_headers(token),
    )
    assert view_response.status_code == 204
    after_view_response = client.get(
        f"/api/v1/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert after_view_response.status_code == 200
    assert after_view_response.json()["updated_at"] == updated_at

    noop_scene_response = client.patch(
        f"/api/v1/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
        json={
            "scene": {
                **scene,
                "type": "excalidraw",
                "version": 2,
                "appState": {
                    **scene["appState"],
                    "name": "Launch Map v2",
                    "selectedElementIds": {"text-1": True},
                    "scrollX": 12,
                    "zoom": {"value": 1},
                },
            }
        },
    )
    assert noop_scene_response.status_code == 200, noop_scene_response.text
    assert noop_scene_response.json()["updated_at"] == updated_at

    recent_response = client.get(
        "/api/v1/whiteboard/hub",
        headers=_auth_headers(token),
        params={"view": "recent"},
    )
    assert recent_response.status_code == 200
    assert [item["id"] for item in recent_response.json()["items"]] == [created["id"]]

    collab_session_response = client.get(
        f"/api/v1/whiteboard/collab/items/{created['id']}/session",
        headers=_auth_headers(token),
    )
    assert collab_session_response.status_code == 200, collab_session_response.text

    favorite_response = client.patch(
        f"/api/v1/whiteboard/items/{created['id']}/favorite",
        headers=_auth_headers(token),
    )
    assert favorite_response.status_code == 200, favorite_response.text

    delete_response = client.delete(
        f"/api/v1/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert delete_response.status_code == 204

    normal_hub_response = client.get(
        "/api/v1/whiteboard/hub",
        headers=_auth_headers(token),
    )
    assert normal_hub_response.status_code == 200
    assert created["id"] not in {item["id"] for item in normal_hub_response.json()["items"]}

    archived_response = client.get(
        "/api/v1/whiteboard/hub",
        headers=_auth_headers(token),
        params={"view": "archived"},
    )
    assert archived_response.status_code == 200
    assert [item["id"] for item in archived_response.json()["items"]] == [created["id"]]

    restore_response = client.post(
        f"/api/v1/whiteboard/items/{created['id']}/restore",
        headers=_auth_headers(token),
    )
    assert restore_response.status_code == 200, restore_response.text
    assert restore_response.json()["trashed_at"] is None

    normal_after_restore_response = client.get(
        "/api/v1/whiteboard/hub",
        headers=_auth_headers(token),
    )
    assert normal_after_restore_response.status_code == 200
    assert created["id"] in {item["id"] for item in normal_after_restore_response.json()["items"]}

    delete_again_response = client.delete(
        f"/api/v1/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert delete_again_response.status_code == 204

    permanent_delete_response = client.delete(
        f"/api/v1/whiteboard/items/{created['id']}/permanent",
        headers=_auth_headers(token),
    )
    assert permanent_delete_response.status_code == 204, permanent_delete_response.text

    deleted_item_response = client.get(
        f"/api/v1/whiteboard/items/{created['id']}",
        headers=_auth_headers(token),
    )
    assert deleted_item_response.status_code == 404
    assert deleted_item_response.json()["code"] == "whiteboard.not_found"

    archived_after_delete_response = client.get(
        "/api/v1/whiteboard/hub",
        headers=_auth_headers(token),
        params={"view": "archived"},
    )
    assert archived_after_delete_response.status_code == 200
    assert created["id"] not in {
        item["id"] for item in archived_after_delete_response.json()["items"]
    }


def test_whiteboard_collab_session_and_snapshot_save(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    create_response = client.post(
        "/api/v1/whiteboard/items",
        headers=_auth_headers(token),
        json={"title": "Collab Board"},
    )
    assert create_response.status_code == 201, create_response.text
    whiteboard = create_response.json()

    session_response = client.get(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/session",
        headers=_auth_headers(token),
    )
    assert session_response.status_code == 200, session_response.text
    collab_session = session_response.json()
    assert collab_session["whiteboard_id"] == whiteboard["id"]
    assert collab_session["room_key"] == f"whiteboard:{whiteboard['id']}"
    assert collab_session["can_edit"] is True
    assert collab_session["snapshot_scene"] == {"elements": [], "appState": {}, "files": {}}

    doc = Y.YDoc()
    yjs_state = base64.b64encode(Y.encode_state_as_update(doc)).decode("ascii")
    scene = {
        "elements": [{"id": "live-1", "type": "rectangle"}],
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    snapshot_response = client.put(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/snapshot",
        headers=_auth_headers(token),
        json={"scene": scene, "yjs_state": yjs_state},
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot_updated_at = snapshot_response.json()["updated_at"]

    reload_response = client.get(
        f"/api/v1/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(token),
    )
    assert reload_response.status_code == 200, reload_response.text
    assert reload_response.json()["scene"] == scene

    next_session_response = client.get(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/session",
        headers=_auth_headers(token),
    )
    assert next_session_response.status_code == 200, next_session_response.text
    assert next_session_response.json()["snapshot_scene"] == scene
    assert next_session_response.json()["yjs_state"] == yjs_state

    noop_snapshot_response = client.put(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/snapshot",
        headers=_auth_headers(token),
        json={
            "scene": {
                **scene,
                "type": "excalidraw",
                "appState": {
                    **scene["appState"],
                    "name": "Collab Board",
                    "selectedElementIds": {"live-1": True},
                },
            },
            "yjs_state": yjs_state,
        },
    )
    assert noop_snapshot_response.status_code == 200, noop_snapshot_response.text
    assert noop_snapshot_response.json()["updated_at"] == snapshot_updated_at

    changed_yjs_state = base64.b64encode(b"changed-yjs-state").decode("ascii")
    yjs_only_snapshot_response = client.put(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/snapshot",
        headers=_auth_headers(token),
        json={"scene": scene, "yjs_state": changed_yjs_state},
    )
    assert yjs_only_snapshot_response.status_code == 200, yjs_only_snapshot_response.text
    assert yjs_only_snapshot_response.json()["updated_at"] == snapshot_updated_at

    yjs_only_session_response = client.get(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/session",
        headers=_auth_headers(token),
    )
    assert yjs_only_session_response.status_code == 200, yjs_only_session_response.text
    assert yjs_only_session_response.json()["yjs_state"] == changed_yjs_state


def test_whiteboard_collab_hub_limits_connection_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> None:
        context = WhiteboardCollabContext(
            whiteboard_id="slot-test-board",
            room_key="whiteboard:slot-test-board",
            can_edit=True,
            scene={"elements": [], "appState": {}, "files": {}},
            default_actor_user_id="slot-user",
        )
        hub = WhiteboardCollabHub()
        monkeypatch.setattr(hub._settings, "collab_max_user_room_connections", 2)
        monkeypatch.setattr(hub._settings, "collab_max_room_clients", 10)
        try:
            runtime = await hub.get_room(context, None)
            await hub.acquire_connection_slot(runtime, "slot-user")
            await hub.acquire_connection_slot(runtime, "slot-user")
            with pytest.raises(CollabConnectionLimitExceeded):
                await hub.acquire_connection_slot(runtime, "slot-user")
            assert runtime.active_connection_count == 2
            assert runtime.active_user_connections == {"slot-user": 2}

            await hub.release_connection_slot(runtime, "slot-user")
            await hub.release_connection_slot(runtime, "slot-user")
            assert runtime.active_connection_count == 0
            assert runtime.active_user_connections == {}

            monkeypatch.setattr(hub._settings, "collab_max_room_clients", 2)
            await hub.acquire_connection_slot(runtime, "slot-user-1")
            await hub.acquire_connection_slot(runtime, "slot-user-2")
            with pytest.raises(CollabConnectionLimitExceeded):
                await hub.acquire_connection_slot(runtime, "slot-user-3")
            assert runtime.active_connection_count == 2
        finally:
            await hub.shutdown()

    asyncio.run(exercise())


def test_whiteboard_rest_scene_patch_invalidates_collab_room(client: TestClient) -> None:
    session = _dev_login(client, "delivery-hub-admin")
    token = session["token"]

    create_response = client.post(
        "/api/v1/whiteboard/items",
        headers=_auth_headers(token),
        json={"title": "Rest Patch Board"},
    )
    assert create_response.status_code == 201, create_response.text
    whiteboard = create_response.json()

    initial_session_response = client.get(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/session",
        headers=_auth_headers(token),
    )
    assert initial_session_response.status_code == 200, initial_session_response.text
    initial_room_key = initial_session_response.json()["room_key"]

    collab_scene = {
        "elements": [{"id": "live-1", "type": "rectangle"}],
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": {},
    }
    yjs_state = base64.b64encode(b"live-yjs-state").decode("ascii")
    snapshot_response = client.put(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/snapshot",
        headers=_auth_headers(token),
        json={"scene": collab_scene, "yjs_state": yjs_state},
    )
    assert snapshot_response.status_code == 200, snapshot_response.text

    rest_scene = {
        "elements": [{"id": "rest-1", "type": "text", "text": "rest"}],
        "appState": {"viewBackgroundColor": "#f8fafc"},
        "files": {},
    }
    update_response = client.patch(
        f"/api/v1/whiteboard/items/{whiteboard['id']}",
        headers=_auth_headers(token),
        json={"scene": rest_scene},
    )
    assert update_response.status_code == 200, update_response.text

    next_session_response = client.get(
        f"/api/v1/whiteboard/collab/items/{whiteboard['id']}/session",
        headers=_auth_headers(token),
    )
    assert next_session_response.status_code == 200, next_session_response.text
    next_session = next_session_response.json()
    assert next_session["room_key"] != initial_room_key
    assert next_session["snapshot_scene"] == rest_scene
    assert next_session["yjs_state"] is None


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
