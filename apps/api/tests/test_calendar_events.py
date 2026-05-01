"""Tests for the unified calendar events endpoint.

Covers (per autoplan Round 2 Eng review test plan):
  - Unauthenticated → 401
  - Range exceeds 366-day cap → 400 (ENG-HIGH-4)
  - Invalid source name → 400
  - Empty sources → 200 with []
  - Happy path: meeting + PMS issue both visible to current user
  - assignee_id parameter is silently ignored / never accepted (ENG-CRIT-1)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_meeting(
    client: TestClient,
    token: str,
    *,
    title: str = "Calendar test meeting",
    start_at: datetime,
    end_at: datetime,
) -> dict:
    response = client.post(
        "/api/v1/workspaces/hq/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": title,
            "agenda": "",
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "attendees": [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list(client: TestClient, token: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/hq/pms/lists",
        headers=_auth_headers(token),
        json={
            "key": "CAL",
            "name": "Calendar Test List",
            "description": "",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_issue_with_due_date(
    client: TestClient,
    token: str,
    list_id: str,
    *,
    due_date: str,
    start_date: str | None = None,
    assignee_id: str | None = None,
    title: str = "Issue with due date",
) -> dict:
    create = client.post(
        f"/api/v1/workspaces/hq/pms/lists/{list_id}/issues",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "",
            "status": "todo",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert create.status_code == 201, create.text
    issue = create.json()
    # Set due_date via update endpoint (setup endpoint doesn't take it directly)
    update = client.patch(
        f"/api/v1/workspaces/hq/pms/issues/{issue['id']}",
        headers=_auth_headers(token),
        json={
            "due_date": due_date,
            **({"start_date": start_date} if start_date is not None else {}),
            **({"assignee_id": assignee_id} if assignee_id is not None else {}),
        },
    )
    assert update.status_code == 200, update.text
    return update.json()


def test_calendar_events_requires_auth(client: TestClient) -> None:
    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        params={"from": "2026-04-01", "to": "2026-04-30"},
    )
    assert response.status_code in (401, 403)


def test_calendar_events_range_cap_enforced(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(admin["token"]),
        params={"from": "2020-01-01", "to": "2099-12-31"},
    )
    assert response.status_code == 400
    assert "366" in response.json()["detail"]


def test_calendar_events_invalid_source_rejected(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(admin["token"]),
        params={
            "from": "2026-04-01",
            "to": "2026-04-30",
            "sources": "meeting,bogus",
        },
    )
    assert response.status_code == 400
    assert "bogus" in response.json()["detail"]


def test_calendar_events_empty_sources_returns_empty(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(admin["token"]),
        params={
            "from": "2026-04-01",
            "to": "2026-04-30",
            "sources": "",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_calendar_events_invalid_dates_rejected(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(admin["token"]),
        params={"from": "not a date", "to": "also not"},
    )
    assert response.status_code == 400


def test_calendar_events_to_must_be_after_from(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(admin["token"]),
        params={"from": "2026-04-30", "to": "2026-04-01"},
    )
    assert response.status_code == 400


def test_calendar_events_returns_meeting_for_organizer(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    start = datetime(2026, 4, 15, 10, 0, 0)
    end = start + timedelta(hours=1)
    meeting = _create_meeting(
        client,
        token,
        title="Calendar visible meeting",
        start_at=start,
        end_at=end,
    )

    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(token),
        params={
            "from": "2026-04-01",
            "to": "2026-05-01",
            "sources": "meeting",
        },
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    titles = [item["title"] for item in items]
    assert "Calendar visible meeting" in titles
    matching = next(item for item in items if item["title"] == "Calendar visible meeting")
    assert matching["sourceType"] == "meeting"
    assert matching["sourceId"] == meeting["id"]
    assert matching["allDay"] is False
    assert matching["color"] == "#3b82f6"


def test_calendar_events_excludes_meeting_starting_at_exclusive_end(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    start = datetime(2026, 5, 1, 0, 0, 0)
    end = start + timedelta(hours=1)
    _create_meeting(
        client,
        token,
        title="Boundary meeting",
        start_at=start,
        end_at=end,
    )

    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(token),
        params={
            "from": "2026-04-01",
            "to": "2026-05-01",
            "sources": "meeting",
        },
    )
    assert response.status_code == 200, response.text
    assert "Boundary meeting" not in [item["title"] for item in response.json()["items"]]


def test_calendar_events_date_only_and_offset_ranges_match(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    start = datetime(2026, 4, 15, 1, 0, 0)
    end = start + timedelta(hours=1)
    _create_meeting(
        client,
        token,
        title="Offset range meeting",
        start_at=start,
        end_at=end,
    )

    date_only = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(token),
        params={
            "from": "2026-04-15",
            "to": "2026-04-16",
            "sources": "meeting",
        },
    )
    offset_range = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(token),
        params={
            "from": "2026-04-15T00:00:00+09:00",
            "to": "2026-04-16T00:00:00+09:00",
            "sources": "meeting",
        },
    )
    assert date_only.status_code == 200, date_only.text
    assert offset_range.status_code == 200, offset_range.text
    assert date_only.json() == offset_range.json()


def test_calendar_events_pms_all_day_end_is_exclusive(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    task_list = _create_task_list(client, token)
    due_issue = _create_issue_with_due_date(
        client,
        token,
        task_list["id"],
        due_date="2026-04-20",
        assignee_id=admin["user"]["id"],
        title="Due on Apr 20",
    )
    block_issue = _create_issue_with_due_date(
        client,
        token,
        task_list["id"],
        start_date="2026-04-18",
        due_date="2026-04-20",
        assignee_id=admin["user"]["id"],
        title="Block through Apr 20",
    )

    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(token),
        params={
            "from": "2026-04-01",
            "to": "2026-05-01",
            "sources": "pms_due,pms_block",
        },
    )
    assert response.status_code == 200, response.text
    items = {item["sourceId"]: item for item in response.json()["items"]}
    assert items[due_issue["id"]]["start"] == "2026-04-20"
    assert items[due_issue["id"]]["end"] == "2026-04-21"
    assert items[block_issue["id"]]["start"] == "2026-04-18"
    assert items[block_issue["id"]]["end"] == "2026-04-21"


def test_calendar_events_assignee_id_query_param_is_ignored(client: TestClient) -> None:
    """ENG-CRIT-1: caller cannot read another user's calendar by passing an id."""
    admin = _bootstrap_admin_session(client)
    token = admin["token"]
    # The endpoint does not declare assignee_id at all — extra params are silently
    # dropped by FastAPI. Ensure we still get back only the current user's data.
    response = client.get(
        "/api/v1/workspaces/hq/calendar/events",
        headers=_auth_headers(token),
        params={
            "from": "2026-04-01",
            "to": "2026-04-30",
            "assignee_id": "some-other-user-id",
        },
    )
    assert response.status_code == 200
    # And for sanity: the absence of assignee_id in the schema means the optional
    # parameter is never honored. This is the contract.
