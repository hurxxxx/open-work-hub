import pytest
from starlette.websockets import WebSocketDisconnect

from test_company_content_boundaries import _enable
from test_company_groups import _setup


@pytest.mark.parametrize("app", ["docs", "whiteboard"])
def test_collaboration_authenticates_first_frame_and_rejects_valid_token_in_url(client, app):
    headers, _ = _setup(client)
    _enable(client, headers, app)
    created = client.post(f"/api/v1/{app}/items", headers=headers, json={"title": "Auth frame"})
    assert created.status_code == 201
    item_id = created.json()["id"]
    if app == "docs":
        pages = client.get(f"/api/v1/docs/items/{item_id}/pages", headers=headers)
        assert pages.status_code == 200
        page = pages.json()["items"][0]
        page_ref = f"{page['source_type']}__{page['source_page_id']}"
        path = f"/api/v1/docs/collab/pages/{page_ref}/ws"
    else:
        path = f"/api/v1/whiteboard/collab/items/{item_id}/ws"
    token = headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(path) as websocket:
        websocket.send_json({"type": "auth", "token": token})
        assert websocket.receive_bytes()
        websocket.close()
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(f"{path}?token={token}") as websocket:
            websocket.receive_bytes()
    assert denied.value.code == 4401


@pytest.mark.parametrize(
    "path",
    ["/api/v1/docs/collab/pages/missing/ws", "/api/v1/whiteboard/collab/items/missing/ws"],
)
@pytest.mark.parametrize("payload", [None, [], "auth", 5, {"type": "auth", "token": []}])
def test_collaboration_rejects_malformed_auth_frames_without_server_error(client, path, payload):
    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(path) as websocket:
            websocket.send_json(payload)
            websocket.receive_bytes()
    assert denied.value.code == 4401
