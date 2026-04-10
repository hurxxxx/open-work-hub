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
    assert response.status_code == 201
    return response.json()


def _create_user_with_workspaces(
    client: TestClient,
    admin_token: str,
    *,
    email: str,
    full_name: str,
    workspace_keys: list[str],
) -> dict:
    create_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(admin_token),
        json={"email": email, "full_name": full_name},
    )
    assert create_response.status_code == 201, create_response.text
    payload = create_response.json()

    for key in workspace_keys:
        _grant_workspace_access(client, admin_token, payload["user"]["id"], key)
    return payload


def _grant_workspace_access(
    client: TestClient,
    admin_token: str,
    user_id: str,
    workspace_key: str,
    role: str = "member",
) -> None:
    workspaces_response = client.get(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(admin_token),
    )
    assert workspaces_response.status_code == 200
    workspace = next(
        item for item in workspaces_response.json() if item["key"] == workspace_key
    )

    bindings_response = client.get(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(admin_token),
    )
    assert bindings_response.status_code == 200
    bindings = bindings_response.json()

    user_bindings = [
        {"subject_id": item["subject_id"], "role": item["role"]}
        for item in bindings
        if item["subject_type"] == "user" and item["subject_id"] != user_id
    ] + [{"subject_id": user_id, "role": role}]
    group_bindings = [
        {"subject_id": item["subject_id"], "role": item["role"]}
        for item in bindings
        if item["subject_type"] == "group"
    ]

    update_response = client.put(
        f"/api/v1/admin/workspaces/{workspace['id']}/bindings",
        headers=_auth_headers(admin_token),
        json={"users": user_bindings, "groups": group_bindings},
    )
    assert update_response.status_code == 200


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["token"]


def _create_meeting(
    client: TestClient,
    token: str,
    *,
    title: str = "Sprint planning",
    attendees: list[dict] | None = None,
) -> dict:
    start = datetime(2026, 5, 1, 10, 0, 0)
    end = start + timedelta(hours=1)
    response = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": title,
            "agenda": "Discuss Q2 roadmap.",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "attendees": attendees or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_meeting_create_get_update_delete_happy_path(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    meeting = _create_meeting(client, token, title="Kickoff")
    assert meeting["title"] == "Kickoff"
    assert meeting["organizer_id"] == admin["user"]["id"]
    assert meeting["status"] == "scheduled"
    # Organizer is auto-added as an attendee.
    assert {att["user_id"] for att in meeting["attendees"]} == {admin["user"]["id"]}
    assert meeting["attendees"][0]["response"] == "accepted"

    detail_response = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(token),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == meeting["id"]

    update_response = client.patch(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(token),
        json={"title": "Kickoff (revised)", "agenda": "Revised agenda."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Kickoff (revised)"
    assert update_response.json()["agenda"] == "Revised agenda."

    list_response = client.get(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(token),
        params={"scope": "mine"},
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Kickoff (revised)"

    delete_response = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(token),
    )
    assert delete_response.status_code == 204

    after_delete = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(token),
    )
    assert after_delete.status_code == 404


def test_non_organizer_attendee_cannot_modify_meeting(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="member@aidoo.local",
        full_name="Meeting Member",
        workspace_keys=["meeting"],
    )
    member_token = _login(
        client, member["user"]["email"], member["temporary_password"]
    )

    # Admin organizes a meeting and invites the member.
    meeting = _create_meeting(
        client,
        admin_token,
        attendees=[{"user_id": member["user"]["id"], "role": "required"}],
    )
    assert {att["user_id"] for att in meeting["attendees"]} == {
        admin["user"]["id"],
        member["user"]["id"],
    }

    # Member can read.
    member_view = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(member_token),
    )
    assert member_view.status_code == 200

    # Member cannot patch.
    forbidden_patch = client.patch(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(member_token),
        json={"title": "Hijacked"},
    )
    assert forbidden_patch.status_code == 403

    # Member cannot delete.
    forbidden_delete = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(member_token),
    )
    assert forbidden_delete.status_code == 403


def test_attach_task_requires_issue_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    # Admin creates a PMS project + issue.
    project_response = client.post(
        "/api/v1/pms/projects",
        headers=_auth_headers(admin_token),
        json={"key": "MTG", "name": "Meeting Test", "description": ""},
    )
    assert project_response.status_code == 201
    project = project_response.json()

    issue_response = client.post(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(admin_token),
        json={
            "title": "Plan Q2",
            "description": "",
            "status": "backlog",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert issue_response.status_code == 201
    issue = issue_response.json()

    # Admin organizes a meeting and attaches the issue.
    meeting = _create_meeting(client, admin_token)

    attach_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/tasks",
        headers=_auth_headers(admin_token),
        json={"issue_id": issue["id"]},
    )
    assert attach_response.status_code == 200, attach_response.text
    body = attach_response.json()
    assert len(body["task_links"]) == 1
    assert body["task_links"][0]["issue_id"] == issue["id"]
    assert body["task_links"][0]["project_key"] == "MTG"

    # Re-attaching is idempotent.
    second_attach = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/tasks",
        headers=_auth_headers(admin_token),
        json={"issue_id": issue["id"]},
    )
    assert second_attach.status_code == 200
    assert len(second_attach.json()["task_links"]) == 1

    # Detach.
    detach_response = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/tasks/{issue['id']}",
        headers=_auth_headers(admin_token),
    )
    assert detach_response.status_code == 200
    assert detach_response.json()["task_links"] == []


def test_attach_task_returns_403_for_user_without_project_access(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    project_response = client.post(
        "/api/v1/pms/projects",
        headers=_auth_headers(admin_token),
        json={"key": "PRIV", "name": "Private", "description": ""},
    )
    assert project_response.status_code == 201
    project = project_response.json()

    issue_response = client.post(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(admin_token),
        json={
            "title": "Confidential",
            "description": "",
            "status": "backlog",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert issue_response.status_code == 201
    issue = issue_response.json()

    organizer = _create_user_with_workspaces(
        client,
        admin_token,
        email="organizer@aidoo.local",
        full_name="Meeting Organizer",
        workspace_keys=["meeting"],
    )
    organizer_token = _login(
        client, organizer["user"]["email"], organizer["temporary_password"]
    )

    meeting = _create_meeting(client, organizer_token, title="External sync")

    forbidden_attach = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/tasks",
        headers=_auth_headers(organizer_token),
        json={"issue_id": issue["id"]},
    )
    assert forbidden_attach.status_code == 403


def test_attach_doc_links_native_doc_to_meeting(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    create_doc = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(admin_token),
        json={"title": "Meeting reference"},
    )
    assert create_doc.status_code == 201, create_doc.text
    doc = create_doc.json()
    # The Docs hub serializes a synthesized hub id; the NativeDoc PK is `source_id`.
    doc_id = doc["source_id"]

    meeting = _create_meeting(client, admin_token)

    attach_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs",
        headers=_auth_headers(admin_token),
        json={"doc_id": doc_id},
    )
    assert attach_response.status_code == 200, attach_response.text
    body = attach_response.json()
    assert len(body["doc_links"]) == 1
    assert body["doc_links"][0]["doc_id"] == doc_id
    assert body["doc_links"][0]["doc_title"] == "Meeting reference"

    detach_response = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs/{doc_id}",
        headers=_auth_headers(admin_token),
    )
    assert detach_response.status_code == 200
    assert detach_response.json()["doc_links"] == []


def test_meeting_create_rejects_invalid_time_range(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    start = datetime(2026, 5, 1, 10, 0, 0)
    end = start - timedelta(hours=1)
    response = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "Backwards",
            "agenda": "",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "attendees": [],
        },
    )
    assert response.status_code == 400


def test_user_without_meeting_workspace_access_is_blocked(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    outsider = _create_user_with_workspaces(
        client,
        admin_token,
        email="outsider@aidoo.local",
        full_name="Outsider",
        workspace_keys=[],  # No meeting workspace access.
    )
    outsider_token = _login(
        client,
        outsider["user"]["email"],
        outsider["temporary_password"],
    )

    response = client.get(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(outsider_token),
        params={"scope": "mine"},
    )
    assert response.status_code == 403


def test_meeting_user_search_returns_users_without_pms_access(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    _create_user_with_workspaces(
        client,
        admin_token,
        email="alice@aidoo.local",
        full_name="Alice Park",
        workspace_keys=[],
    )
    _create_user_with_workspaces(
        client,
        admin_token,
        email="bob@aidoo.local",
        full_name="Bob Lee",
        workspace_keys=[],
    )

    # No query — returns all active users (admin + alice + bob).
    response = client.get(
        "/api/v1/meeting/users",
        headers=_auth_headers(admin_token),
    )
    assert response.status_code == 200
    payload = response.json()
    emails = {item["email"] for item in payload}
    assert {"admin@aidoo.local", "alice@aidoo.local", "bob@aidoo.local"} <= emails

    # Partial-name query.
    name_response = client.get(
        "/api/v1/meeting/users",
        headers=_auth_headers(admin_token),
        params={"q": "alice"},
    )
    assert name_response.status_code == 200
    assert [item["email"] for item in name_response.json()] == ["alice@aidoo.local"]

    # Partial-email query — confirms that users without PMS workspace access
    # are still searchable from the meeting modal.
    email_response = client.get(
        "/api/v1/meeting/users",
        headers=_auth_headers(admin_token),
        params={"q": "bob@"},
    )
    assert email_response.status_code == 200
    assert [item["email"] for item in email_response.json()] == ["bob@aidoo.local"]


def test_meeting_update_changes_time_and_attendees(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="invitee@aidoo.local",
        full_name="Invitee User",
        workspace_keys=[],
    )

    meeting = _create_meeting(client, admin_token, title="Original")
    assert {att["user_id"] for att in meeting["attendees"]} == {admin["user"]["id"]}

    new_start = datetime(2026, 5, 2, 14, 0, 0).isoformat()
    new_end = datetime(2026, 5, 2, 15, 30, 0).isoformat()

    update_response = client.patch(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin_token),
        json={
            "title": "Updated title",
            "start_at": new_start,
            "end_at": new_end,
            "attendees": [{"user_id": member["user"]["id"], "role": "required"}],
        },
    )
    assert update_response.status_code == 200, update_response.text
    body = update_response.json()
    assert body["title"] == "Updated title"
    assert body["start_at"].startswith("2026-05-02T14:00")
    assert body["end_at"].startswith("2026-05-02T15:30")
    # Organizer is always reinjected as an attendee.
    user_ids = {att["user_id"] for att in body["attendees"]}
    assert user_ids == {admin["user"]["id"], member["user"]["id"]}
