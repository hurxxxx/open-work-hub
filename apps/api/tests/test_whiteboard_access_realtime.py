from __future__ import annotations

import asyncio

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from dev_accounts import dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import CompanyAppControl, User, AuthSession
from open_work_hub_api.domains.whiteboard.models import Whiteboard, WhiteboardLinkShare
from open_work_hub_api.domains.whiteboard.router import _authorize_whiteboard_collab_access


def _setup(client: TestClient):
    owner = dev_login(client, "delivery-hub-admin")
    viewer = dev_login(client, "delivery-hub-member")
    headers = {"Authorization": f"Bearer {owner['token']}"}
    response = client.post("/api/v1/whiteboard/items", headers=headers, json={"title": "Board"})
    assert response.status_code == 201, response.text
    return owner, viewer, headers, response.json()["id"]


def _capture(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    events: list[tuple[str, dict]] = []
    globals_sent = []
    monkeypatch.setattr(client.app.state.app_realtime, "publish", lambda *args: events.append(args))
    monkeypatch.setattr(
        client.app.state.app_realtime, "publish_user", lambda *args: globals_sent.append(args)
    )
    return events, globals_sent


def _assert_event(events, globals_sent, board_id: str):
    assert events == [
        (
            f"whiteboard.access:{board_id}",
            {"type": "whiteboard.access.changed", "data": {"whiteboard_id": board_id}},
        )
    ]
    assert globals_sent == []
    events.clear()


def test_user_and_link_acl_changes_invalidate_only_the_board_after_commit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _, viewer, headers, board_id = _setup(client)
    events, globals_sent = _capture(client, monkeypatch)
    base = f"/api/v1/whiteboard/items/{board_id}/sharing"
    for level in ("edit", "read"):
        response = client.put(
            f"{base}/users/{viewer['user']['id']}", headers=headers, json={"access_level": level}
        )
        assert response.status_code == 200, response.text
        _assert_event(events, globals_sent, board_id)
    response = client.delete(f"{base}/users/{viewer['user']['id']}", headers=headers)
    assert response.status_code == 200, response.text
    _assert_event(events, globals_sent, board_id)

    old_token = None
    for payload in (
        {"access_level": "edit"},
        {"access_level": "read"},
        {"access_level": "read", "regenerate_token": True},
        {"access_level": "read", "active": False},
        {"access_level": "read"},
    ):
        response = client.put(f"{base}/link", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        _assert_event(events, globals_sent, board_id)
        if payload.get("regenerate_token"):
            assert response.json()["link_share"]["token"] != old_token
            assert (
                client.get(
                    f"/api/v1/whiteboard/shared-links/{old_token}/item", headers=headers
                ).status_code
                == 404
            )
        if response.json()["link_share"] is not None:
            old_token = response.json()["link_share"]["token"]

    # A separate transaction must already observe the revoked grant at publish time.
    def capture_committed(topic, event):
        with get_session_factory()() as db:
            link = db.scalar(
                select(WhiteboardLinkShare).where(WhiteboardLinkShare.whiteboard_id == board_id)
            )
            assert link is not None and link.active is False
        events.append((topic, event))

    monkeypatch.setattr(client.app.state.app_realtime, "publish", capture_committed)
    response = client.delete(f"{base}/link", headers=headers)
    assert response.status_code == 200, response.text
    _assert_event(events, globals_sent, board_id)
    assert (
        client.get(f"/api/v1/whiteboard/shared-links/{old_token}/item", headers=headers).status_code
        == 404
    )


def test_group_and_company_audience_changes_do_not_broadcast_global_auth(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _, _, headers, board_id = _setup(client)
    admin = dev_login(client, "administrator")
    response = client.post(
        "/api/v1/admin/groups",
        headers={"Authorization": f"Bearer {admin['token']}"},
        json={"name": "Board editors"},
    )
    assert response.status_code == 201, response.text
    group_id = response.json()["id"]
    events, globals_sent = _capture(client, monkeypatch)
    base = f"/api/v1/whiteboard/items/{board_id}/sharing"
    for level in ("edit", "read"):
        response = client.put(
            f"{base}/groups/{group_id}", headers=headers, json={"access_level": level}
        )
        assert response.status_code == 200, response.text
        _assert_event(events, globals_sent, board_id)
    response = client.delete(f"{base}/groups/{group_id}", headers=headers)
    assert response.status_code == 204, response.text
    _assert_event(events, globals_sent, board_id)
    for enabled in (True, False):
        response = client.put(
            f"{base}/company",
            headers=headers,
            json={"enabled": enabled, "company_admin_read_acknowledged": True},
        )
        assert response.status_code == 204, response.text
        _assert_event(events, globals_sent, board_id)


def test_trash_restore_permanent_delete_invalidate_the_board_after_commit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _, _, headers, board_id = _setup(client)
    events, globals_sent = _capture(client, monkeypatch)
    base = f"/api/v1/whiteboard/items/{board_id}"
    for method, path, expected in (
        ("delete", base, 204),
        ("post", f"{base}/restore", 200),
        ("delete", base, 204),
        ("delete", f"{base}/permanent", 204),
    ):
        response = getattr(client, method)(path, headers=headers)
        assert response.status_code == expected, response.text
        _assert_event(events, globals_sent, board_id)
    with get_session_factory()() as db:
        assert db.get(Whiteboard, board_id) is None


def test_denied_mutation_emits_no_access_control_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    _, viewer, _, board_id = _setup(client)
    events, globals_sent = _capture(client, monkeypatch)
    response = client.put(
        f"/api/v1/whiteboard/items/{board_id}/sharing/link",
        headers={"Authorization": f"Bearer {viewer['token']}"},
        json={"access_level": "edit"},
    )
    assert response.status_code == 404, response.text
    assert events == [] and globals_sent == []


@pytest.mark.parametrize("revocation", ["source", "app", "user", "session"])
def test_collab_frame_authorizer_rechecks_current_rights_without_waiting_for_monitor(
    client: TestClient, revocation: str
):
    _, viewer, headers, board_id = _setup(client)
    share_path = f"/api/v1/whiteboard/items/{board_id}/sharing/users/{viewer['user']['id']}"
    response = client.put(share_path, headers=headers, json={"access_level": "edit"})
    assert response.status_code == 200, response.text

    def authorize():
        asyncio.run(_authorize_whiteboard_collab_access(item_id=board_id, token=viewer["token"]))

    authorize()
    if revocation == "source":
        response = client.put(share_path, headers=headers, json={"access_level": "read"})
        assert response.status_code == 200, response.text
    else:
        with get_session_factory()() as db:
            if revocation == "app":
                db.get(CompanyAppControl, "whiteboard").enabled = False
            elif revocation == "user":
                db.get(User, viewer["user"]["id"]).login_blocked = True
            else:
                for session in db.scalars(
                    select(AuthSession).where(AuthSession.user_id == viewer["user"]["id"])
                ):
                    db.delete(session)
            db.commit()
    with pytest.raises(HTTPException) as exc:
        authorize()
    assert exc.value.status_code in (401, 403, 404)


def test_target_reassignment_also_invalidates_the_displaced_context_board(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    owner, _, headers, board_id = _setup(client)
    from test_whiteboard_target import _create_task_list, _create_task_list_slot

    task_list = _create_task_list(client, owner["token"], key="WBACCESS", name="Board target")
    existing = _create_task_list_slot(client, owner["token"], task_list["id"], "Previous board")
    events, globals_sent = _capture(client, monkeypatch)
    payload = {
        "app": "pms",
        "type": "task_list",
        "id": task_list["id"],
        "company_admin_read_acknowledged": True,
    }
    response = client.put(
        f"/api/v1/whiteboard/items/{board_id}/target", headers=headers, json=payload
    )
    assert response.status_code == 200, response.text
    assert {topic for topic, _event in events} == {
        f"whiteboard.access:{board_id}",
        f"whiteboard.access:{existing['id']}",
    }
    assert globals_sent == []
    assert (
        client.get(f"/api/v1/whiteboard/items/{existing['id']}", headers=headers).json()["targets"]
        == []
    )
    events.clear()
    response = client.delete(f"/api/v1/whiteboard/items/{board_id}/target", headers=headers)
    assert response.status_code == 200, response.text
    _assert_event(events, globals_sent, board_id)


def test_context_slot_replacement_and_detach_invalidate_only_affected_boards(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    owner, _, headers, board_id = _setup(client)
    from test_whiteboard_target import _create_task_list, _create_task_list_slot

    task_list = _create_task_list(client, owner["token"], key="WBSACCESS", name="Board slot")
    existing = _create_task_list_slot(client, owner["token"], task_list["id"], "Previous board")
    events, globals_sent = _capture(client, monkeypatch)
    replacement = _create_task_list_slot(client, owner["token"], task_list["id"], "Replacement")
    _assert_event(events, globals_sent, existing["id"])
    payload = {
        "app": "pms",
        "type": "task_list",
        "id": task_list["id"],
        "whiteboard_id": board_id,
        "company_admin_read_acknowledged": True,
    }
    response = client.put("/api/v1/whiteboard/contexts/slot", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert {topic for topic, _event in events} == {
        f"whiteboard.access:{board_id}",
        f"whiteboard.access:{replacement['id']}",
    }
    assert globals_sent == []
    events.clear()
    response = client.delete(
        "/api/v1/whiteboard/contexts/slot",
        headers=headers,
        params={"app": "pms", "type": "task_list", "id": task_list["id"]},
    )
    assert response.status_code == 204, response.text
    _assert_event(events, globals_sent, board_id)
