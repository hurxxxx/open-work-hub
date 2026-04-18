from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_user_with_workspaces,
    _login,
)


def _workspace_slug_for_key(client: TestClient, token: str, key: str) -> str:
    response = client.get(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    workspace = next(item for item in response.json() if item["key"] == key)
    return workspace.get("slug", key)


def _create_planner_event(
    client: TestClient,
    token: str,
    *,
    workspace_slug: str | None = None,
    title: str = "출장",
    start: str,
    end: str,
    all_day: bool = False,
    visibility: str = "private",
    location: str = "",
    description: str = "",
) -> dict:
    path = (
        f"/api/v1/workspaces/{workspace_slug}/planner/events"
        if workspace_slug
        else "/api/v1/planner/events"
    )
    response = client.post(
        path,
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": description,
            "location": location,
            "visibility": visibility,
            "allDay": all_day,
            "start": start,
            "end": end,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_workspace_meeting(
    client: TestClient,
    token: str,
    *,
    workspace_slug: str,
    title: str = "Sync",
    attendees: list[dict] | None = None,
    start_at: datetime,
    end_at: datetime,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": title,
            "agenda": "Discuss schedule.",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "attendees": attendees or [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_planner_event_crud_happy_path(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    created = _create_planner_event(
        client,
        token,
        title="고객사 방문",
        start="2026-05-04T01:00:00+00:00",
        end="2026-05-04T03:30:00+00:00",
        location="성수동",
        description="오프라인 미팅",
    )
    assert created["title"] == "고객사 방문"
    assert created["location"] == "성수동"
    assert created["visibility"] == "private"
    assert created["allDay"] is False
    assert created["start"] == "2026-05-04T01:00:00+00:00"
    assert created["end"] == "2026-05-04T03:30:00+00:00"

    detail = client.get(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(token),
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["id"] == created["id"]

    updated = client.patch(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(token),
        json={
            "allDay": True,
            "start": "2026-05-06",
            "end": "2026-05-08",
            "visibility": "public",
            "location": "부산",
        },
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["allDay"] is True
    assert updated_body["start"] == "2026-05-06"
    assert updated_body["end"] == "2026-05-08"
    assert updated_body["visibility"] == "public"
    assert updated_body["location"] == "부산"

    listing = client.get(
        "/api/v1/planner/events",
        headers=_auth_headers(token),
        params={"from": "2026-05-01", "to": "2026-05-31"},
    )
    assert listing.status_code == 200, listing.text
    assert created["id"] in {item["id"] for item in listing.json()["items"]}

    deleted = client.delete(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(token),
    )
    assert deleted.status_code == 204

    after_delete = client.get(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(token),
    )
    assert after_delete.status_code == 404


def test_planner_event_owner_only_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="planner-member@aidoo.local",
        full_name="Planner Member",
        workspace_keys=["planner"],
    )
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    created = _create_planner_event(
        client,
        admin_token,
        start="2026-05-04T01:00:00+00:00",
        end="2026-05-04T02:00:00+00:00",
    )

    forbidden_get = client.get(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(member_token),
    )
    assert forbidden_get.status_code == 403

    forbidden_patch = client.patch(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(member_token),
        json={"title": "가로채기"},
    )
    assert forbidden_patch.status_code == 403

    forbidden_delete = client.delete(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(member_token),
    )
    assert forbidden_delete.status_code == 403


def test_calendar_events_include_only_current_user_planner_events(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="planner-public@aidoo.local",
        full_name="Planner Public",
        workspace_keys=["planner"],
    )
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    own_event = _create_planner_event(
        client,
        admin_token,
        title="나의 일정",
        start="2026-05-11T00:00:00+00:00",
        end="2026-05-11T02:00:00+00:00",
        visibility="public",
        location="판교",
    )
    _create_planner_event(
        client,
        member_token,
        title="다른 사람 공개 일정",
        start="2026-05-11T03:00:00+00:00",
        end="2026-05-11T04:00:00+00:00",
        visibility="public",
        location="강남",
    )

    response = client.get(
        "/api/v1/calendar/events",
        headers=_auth_headers(admin_token),
        params={
            "from": "2026-05-01",
            "to": "2026-06-01",
            "sources": "planner_event",
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    item = items[0]
    assert item["sourceType"] == "planner_event"
    assert item["sourceId"] == own_event["id"]
    assert item["metadata"]["plannerEventId"] == own_event["id"]
    assert item["metadata"]["visibility"] == "public"
    assert item["metadata"]["location"] == "판교"


def test_meeting_availability_masks_private_events_and_shows_public_events(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    meeting_workspace_slug = _workspace_slug_for_key(client, admin_token, "hq")
    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="availability-user@aidoo.local",
        full_name="Availability User",
        workspace_keys=["hq"],
    )
    attendee_token = _login(client, attendee["user"]["email"], attendee["temporary_password"])

    _create_planner_event(
        client,
        attendee_token,
        workspace_slug=meeting_workspace_slug,
        title="개인 외근",
        start="2026-05-18T02:00:00+00:00",
        end="2026-05-18T04:00:00+00:00",
        visibility="private",
        location="비공개",
    )
    _create_planner_event(
        client,
        attendee_token,
        workspace_slug=meeting_workspace_slug,
        title="출장",
        start="2026-05-19",
        end="2026-05-21",
        all_day=True,
        visibility="public",
        location="부산",
    )
    _create_workspace_meeting(
        client,
        admin_token,
        workspace_slug=meeting_workspace_slug,
        title="Sync",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
        start_at=datetime(2026, 5, 18, 8, 0, tzinfo=UTC).replace(tzinfo=None),
        end_at=datetime(2026, 5, 18, 9, 0, tzinfo=UTC).replace(tzinfo=None),
    )

    response = client.get(
        f"/api/v1/workspaces/{meeting_workspace_slug}/meeting/availability",
        headers=_auth_headers(admin_token),
        params=[
            ("user_ids", attendee["user"]["id"]),
            ("from", "2026-05-18T00:00:00+09:00"),
            ("to", "2026-05-25T00:00:00+09:00"),
        ],
    )
    assert response.status_code == 200, response.text
    blocks = response.json()["items"][0]["blocks"]
    assert len(blocks) == 3

    private_block = next(block for block in blocks if block["sourceType"] == "planner_event" and block["masked"] is True)
    assert private_block["title"] is None
    assert private_block["location"] is None

    public_block = next(block for block in blocks if block["sourceType"] == "planner_event" and block["masked"] is False)
    assert public_block["title"] == "출장"
    assert public_block["location"] == "부산"
    assert public_block["allDay"] is True
    assert public_block["start"] == "2026-05-19"
    assert public_block["end"] == "2026-05-21"

    meeting_block = next(block for block in blocks if block["sourceType"] == "meeting")
    assert meeting_block["masked"] is True
    assert meeting_block["title"] is None


def test_meeting_availability_rejects_users_outside_workspace(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    meeting_workspace_slug = _workspace_slug_for_key(client, admin_token, "hq")
    outsider = _create_user_with_workspaces(
        client,
        admin_token,
        email="availability-outsider@aidoo.local",
        full_name="Availability Outsider",
        workspace_keys=[],
    )

    response = client.get(
        f"/api/v1/workspaces/{meeting_workspace_slug}/meeting/availability",
        headers=_auth_headers(admin_token),
        params=[
            ("user_ids", outsider["user"]["id"]),
            ("from", "2026-05-18T00:00:00+09:00"),
            ("to", "2026-05-25T00:00:00+09:00"),
        ],
    )
    assert response.status_code == 422
    assert "meeting workspace" in response.json()["detail"]
