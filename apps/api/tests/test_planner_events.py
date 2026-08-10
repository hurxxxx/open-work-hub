from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.auth.models import PlatformAppVisibility

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


def _set_platform_app_visibility(app_id: str, visible: bool) -> None:
    with get_session_factory()() as db:
        row = db.scalar(
            select(PlatformAppVisibility).where(PlatformAppVisibility.app_id == app_id)
        )
        assert row is not None
        row.visible = visible
        db.add(row)
        db.commit()


def _create_planner_event(
    client: TestClient,
    token: str,
    *,
    title: str = "출장",
    start: str,
    end: str,
    all_day: bool = False,
    location: str = "",
    description: str = "",
) -> dict:
    response = client.post(
        "/api/v1/planner/events",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": description,
            "location": location,
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
    assert created["timeZone"] == "Asia/Seoul"
    assert created["allDay"] is False
    assert created["startHasTime"] is True
    assert created["endHasTime"] is True
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
            "location": "부산",
        },
    )
    assert updated.status_code == 200, updated.text
    updated_body = updated.json()
    assert updated_body["allDay"] is True
    assert updated_body["startHasTime"] is False
    assert updated_body["endHasTime"] is False
    assert updated_body["start"] == "2026-05-06"
    assert updated_body["end"] == "2026-05-08"
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
        email="planner-member@ai-do.local",
        full_name="Planner Member",
        workspace_keys=["administrator"],
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
    assert forbidden_get.status_code == 404

    forbidden_patch = client.patch(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(member_token),
        json={"title": "가로채기"},
    )
    assert forbidden_patch.status_code == 404

    forbidden_delete = client.delete(
        f"/api/v1/planner/events/{created['id']}",
        headers=_auth_headers(member_token),
    )
    assert forbidden_delete.status_code == 404


def test_calendar_events_include_only_current_user_planner_events(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="planner-public@ai-do.local",
        full_name="Planner Public",
        workspace_keys=["administrator"],
    )
    member_token = _login(client, member["user"]["email"], member["temporary_password"])

    own_event = _create_planner_event(
        client,
        admin_token,
        title="나의 일정",
        start="2026-05-11T00:00:00+00:00",
        end="2026-05-11T02:00:00+00:00",
        location="판교",
    )
    _create_planner_event(
        client,
        member_token,
        title="다른 사람 공개 일정",
        start="2026-05-11T03:00:00+00:00",
        end="2026-05-11T04:00:00+00:00",
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
    assert item["workspace"] is None
    assert item["metadata"]["location"] == "판교"
    assert item["metadata"]["plannerAllDay"] is False
    assert item["metadata"]["plannerStartHasTime"] is True
    assert item["metadata"]["plannerEndHasTime"] is True


def test_planner_event_accepts_partial_or_unspecified_times(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    start_only = _create_planner_event(
        client,
        token,
        title="시작만 있는 일정",
        start="2026-05-12T09:00:00+09:00",
        end="2026-05-12",
    )
    assert start_only["allDay"] is False
    assert start_only["startHasTime"] is True
    assert start_only["endHasTime"] is False
    assert start_only["start"] == "2026-05-12T00:00:00+00:00"
    assert start_only["end"] == "2026-05-12"

    end_only = _create_planner_event(
        client,
        token,
        title="종료만 있는 일정",
        start="2026-05-13",
        end="2026-05-13T18:00:00+09:00",
    )
    assert end_only["startHasTime"] is False
    assert end_only["endHasTime"] is True
    assert end_only["start"] == "2026-05-13"
    assert end_only["end"] == "2026-05-13T09:00:00+00:00"

    no_time = _create_planner_event(
        client,
        token,
        title="시간 미정 일정",
        start="2026-05-14",
        end="2026-05-14",
    )
    assert no_time["startHasTime"] is False
    assert no_time["endHasTime"] is False
    assert no_time["start"] == "2026-05-14"
    assert no_time["end"] == "2026-05-14"

    calendar = client.get(
        "/api/v1/calendar/events",
        headers=_auth_headers(token),
        params={
            "from": "2026-05-12",
            "to": "2026-05-15",
            "sources": "planner_event",
        },
    )
    assert calendar.status_code == 200, calendar.text
    by_title = {item["title"]: item for item in calendar.json()["items"]}
    assert by_title["시작만 있는 일정"]["allDay"] is False
    assert by_title["시작만 있는 일정"]["metadata"]["plannerEndHasTime"] is False
    assert by_title["종료만 있는 일정"]["allDay"] is False
    assert by_title["종료만 있는 일정"]["metadata"]["plannerStartHasTime"] is False
    assert by_title["시간 미정 일정"]["allDay"] is True
    assert by_title["시간 미정 일정"]["metadata"]["plannerAllDay"] is False


def test_meeting_availability_masks_other_users_personal_events(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    meeting_workspace_slug = _workspace_slug_for_key(client, admin_token, "administrator")
    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="availability-user@ai-do.local",
        full_name="Availability User",
        workspace_keys=["administrator"],
    )
    attendee_token = _login(client, attendee["user"]["email"], attendee["temporary_password"])

    _create_planner_event(
        client,
        attendee_token,
        title="개인 외근",
        start="2026-05-18T02:00:00+00:00",
        end="2026-05-18T04:00:00+00:00",
        location="비공개",
    )
    _create_planner_event(
        client,
        attendee_token,
        title="출장",
        start="2026-05-19",
        end="2026-05-21",
        all_day=True,
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
    _create_planner_event(
        client,
        attendee_token,
        title="시작만 있는 느슨한 일정",
        start="2026-05-20T09:00:00+09:00",
        end="2026-05-20",
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
    assert "시작만 있는 느슨한 일정" not in {block["title"] for block in blocks if block["title"]}

    planner_blocks = [block for block in blocks if block["sourceType"] == "planner_event"]
    assert len(planner_blocks) == 2
    assert all(block["masked"] is True for block in planner_blocks)
    assert all(block["title"] is None for block in planner_blocks)
    assert all(block["location"] is None for block in planner_blocks)

    meeting_block = next(block for block in blocks if block["sourceType"] == "meeting")
    assert meeting_block["masked"] is True
    assert meeting_block["title"] is None

    _set_platform_app_visibility("planner", False)
    planner_disabled = client.get(
        f"/api/v1/workspaces/{meeting_workspace_slug}/meeting/availability",
        headers=_auth_headers(admin_token),
        params=[
            ("user_ids", attendee["user"]["id"]),
            ("from", "2026-05-18T00:00:00+09:00"),
            ("to", "2026-05-25T00:00:00+09:00"),
        ],
    )
    assert planner_disabled.status_code == 200, planner_disabled.text
    disabled_blocks = planner_disabled.json()["items"][0]["blocks"]
    assert [block["sourceType"] for block in disabled_blocks] == ["meeting"]


def test_meeting_availability_rejects_users_outside_workspace(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    meeting_workspace_slug = _workspace_slug_for_key(client, admin_token, "administrator")
    outsider = _create_user_with_workspaces(
        client,
        admin_token,
        email="availability-outsider@ai-do.local",
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
    assert response.json()["code"] == "meeting.requested_users_workspace_required"
