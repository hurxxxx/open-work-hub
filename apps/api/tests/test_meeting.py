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
        (item for item in workspaces_response.json() if item["key"] == workspace_key),
        None,
    )
    if workspace is None:
        workspace = next(iter(workspaces_response.json()), None)
    assert workspace is not None

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


def _dev_login(client: TestClient, account_key: str) -> dict:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"account_key": account_key},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_meeting(
    client: TestClient,
    token: str,
    *,
    title: str = "Sprint planning",
    attendees: list[dict] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    task_ids: list[str] | None = None,
    doc_ids: list[str] | None = None,
) -> dict:
    start = start_at or datetime(2026, 5, 1, 10, 0, 0)
    end = end_at or (start + timedelta(hours=1))
    response = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": title,
            "agenda": "Discuss Q2 roadmap.",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "attendees": attendees or [],
            "task_ids": task_ids or [],
            "doc_ids": doc_ids or [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_project(
    client: TestClient,
    token: str,
    *,
    key: str = "MTG",
    name: str = "Meeting Test",
    description: str = "",
    team_id: str | None = None,
) -> dict:
    payload = {
        "key": key,
        "name": name,
        "description": description,
    }
    if team_id is not None:
        payload["team_id"] = team_id
    response = client.post(
        "/api/v1/pms/projects",
        headers=_auth_headers(token),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_issue(
    client: TestClient,
    token: str,
    project_id: str,
    *,
    title: str = "Plan Q2",
    status: str = "backlog",
) -> dict:
    response = client.post(
        f"/api/v1/pms/projects/{project_id}/issues",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "",
            "status": status,
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _first_workspace_slug(client: TestClient, token: str) -> str:
    response = client.get(
        "/api/v1/auth/me",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    workspaces = response.json()["workspaces"]
    assert workspaces
    return workspaces[0]["slug"]


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


def test_meeting_notes_ensure_is_idempotent_and_separate_from_doc_links(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    meeting = _create_meeting(client, admin_token, title="Notes ensure")

    first_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert first_response.status_code == 200, first_response.text
    first_payload = first_response.json()
    assert first_payload["notes_doc_id"] is not None
    assert first_payload["notes_page_id"] is not None
    assert first_payload["doc_links"] == []

    second_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert second_response.status_code == 200, second_response.text
    second_payload = second_response.json()
    assert second_payload["notes_doc_id"] == first_payload["notes_doc_id"]
    assert second_payload["notes_page_id"] == first_payload["notes_page_id"]
    assert second_payload["doc_links"] == []


def test_meeting_notes_support_self_heal_and_wrong_workspace_slug_is_blocked(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    _grant_workspace_access(client, admin_token, admin["user"]["id"], "delivery-hub")
    meeting = _create_meeting(client, admin_token, title="Notes self heal")

    initial_notes = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert initial_notes.status_code == 200, initial_notes.text
    initial_payload = initial_notes.json()

    wrong_workspace_response = client.post(
        f"/api/v1/workspaces/delivery-hub/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert wrong_workspace_response.status_code == 404

    delete_doc_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{initial_payload['notes_doc_id']}",
        headers=_auth_headers(admin_token),
    )
    assert delete_doc_response.status_code == 204

    recreated_notes = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert recreated_notes.status_code == 200, recreated_notes.text
    recreated_payload = recreated_notes.json()
    assert recreated_payload["notes_doc_id"] != initial_payload["notes_doc_id"]
    assert recreated_payload["notes_page_id"] != initial_payload["notes_page_id"]

    delete_page_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/docs/pages/{recreated_payload['notes_page_id']}",
        headers=_auth_headers(admin_token),
    )
    assert delete_page_response.status_code == 204

    rehealed_notes = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert rehealed_notes.status_code == 200, rehealed_notes.text
    rehealed_payload = rehealed_notes.json()
    assert rehealed_payload["notes_doc_id"] == recreated_payload["notes_doc_id"]
    assert rehealed_payload["notes_page_id"] != recreated_payload["notes_page_id"]


def test_meeting_notes_attendee_can_edit_and_loses_access_when_removed(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]
    workspace_slug = _first_workspace_slug(client, admin_token)

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="notes-attendee@aidoo.local",
        full_name="Notes Attendee",
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
        title="Notes attendee edit",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
    )

    ensure_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/notes/ensure",
        headers=_auth_headers(admin_token),
    )
    assert ensure_response.status_code == 200, ensure_response.text
    notes = ensure_response.json()

    pages_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{notes['notes_doc_id']}/pages",
        headers=_auth_headers(attendee_token),
    )
    assert pages_response.status_code == 200, pages_response.text
    attendee_page = pages_response.json()["items"][0]
    assert attendee_page["id"] == notes["notes_page_id"]
    assert attendee_page["can_edit"] is True

    update_page_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/docs/pages/{notes['notes_page_id']}",
        headers=_auth_headers(attendee_token),
        json={
            "content_blocks": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Attendee updated notes"}],
                }
            ]
        },
    )
    assert update_page_response.status_code == 200, update_page_response.text

    remove_attendee_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin_token),
        json={"attendees": []},
    )
    assert remove_attendee_response.status_code == 200, remove_attendee_response.text

    after_removal_response = client.get(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{notes['notes_doc_id']}",
        headers=_auth_headers(attendee_token),
    )
    assert after_removal_response.status_code == 404


def test_attach_task_requires_issue_access(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    # Admin creates a PMS project + issue.
    project = _create_project(client, admin_token)
    issue = _create_issue(client, admin_token, project["id"])

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
    assert body["task_links"][0]["list_key"] == "MTG"

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

    project = _create_project(
        client,
        admin_token,
        key="PRIV",
        name="Private",
    )
    issue = _create_issue(
        client,
        admin_token,
        project["id"],
        title="Confidential",
    )

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


def test_meeting_create_rejects_attendees_outside_meeting_workspace(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    # User with no workspace memberships at all — they cannot belong to the
    # meeting workspace either, so attempting to invite them must fail.
    outsider = _create_user_with_workspaces(
        client,
        admin_token,
        email="no-workspace@aidoo.local",
        full_name="No Workspace",
        workspace_keys=[],
    )

    response = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(admin_token),
        json={
            "title": "Cross workspace attendee",
            "agenda": "",
            "start_at": datetime(2026, 5, 1, 10, 0, 0).isoformat(),
            "end_at": datetime(2026, 5, 1, 11, 0, 0).isoformat(),
            "attendees": [{"user_id": outsider["user"]["id"], "role": "required"}],
        },
    )
    assert response.status_code == 422
    assert "meeting workspace" in response.json()["detail"]


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
        workspace_keys=["meeting"],
    )
    _create_user_with_workspaces(
        client,
        admin_token,
        email="bob@aidoo.local",
        full_name="Bob Lee",
        workspace_keys=["meeting"],
    )
    _create_user_with_workspaces(
        client,
        admin_token,
        email="outsider@aidoo.local",
        full_name="Outside Workspace",
        workspace_keys=[],
    )

    # No query — returns only meeting-workspace members.
    response = client.get(
        "/api/v1/meeting/users",
        headers=_auth_headers(admin_token),
    )
    assert response.status_code == 200
    payload = response.json()
    emails = {item["email"] for item in payload}
    assert {"admin@aidoo.local", "alice@aidoo.local", "bob@aidoo.local"} <= emails
    assert "outsider@aidoo.local" not in emails

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


def test_workspace_scoped_meeting_routes_keep_hq_context(client: TestClient) -> None:
    _bootstrap_admin_session(client)

    hq_admin = _dev_login(client, "hq-admin")
    hq_member = _dev_login(client, "hq-member")
    hq_admin_token = hq_admin["token"]
    hq_member_token = hq_member["token"]
    hq_member_id = hq_member["user"]["id"]

    me_response = client.get("/api/v1/auth/me", headers=_auth_headers(hq_member_token))
    assert me_response.status_code == 200
    hq_workspace_id = next(
        item["id"]
        for item in me_response.json()["workspaces"]
        if item["slug"] == "hq"
    )

    scoped_users_response = client.get(
        "/api/v1/workspaces/hq/meeting/users",
        headers=_auth_headers(hq_member_token),
        params={"q": "Admin"},
    )
    assert scoped_users_response.status_code == 200
    scoped_emails = {item["email"] for item in scoped_users_response.json()}
    assert "hq-admin@aidoo.local" in scoped_emails
    assert "innovation-lab-admin@aidoo.local" not in scoped_emails

    legacy_users_response = client.get(
        "/api/v1/meeting/users",
        headers=_auth_headers(hq_member_token),
        params={"q": "Admin"},
    )
    assert legacy_users_response.status_code == 200
    legacy_emails = {item["email"] for item in legacy_users_response.json()}
    assert "hq-admin@aidoo.local" in legacy_emails
    assert "innovation-lab-admin@aidoo.local" not in legacy_emails

    create_response = client.post(
        "/api/v1/workspaces/hq/meeting/meetings",
        headers=_auth_headers(hq_admin_token),
        json={
            "title": "HQ scoped meeting",
            "agenda": "Workspace-bound meeting regression",
            "start_at": datetime(2026, 5, 1, 10, 0, 0).isoformat(),
            "end_at": datetime(2026, 5, 1, 11, 0, 0).isoformat(),
            "attendees": [{"user_id": hq_member_id, "role": "required"}],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert create_response.status_code == 201, create_response.text
    meeting = create_response.json()
    assert meeting["workspace_id"] == hq_workspace_id

    scoped_list_response = client.get(
        "/api/v1/workspaces/hq/meeting/meetings",
        headers=_auth_headers(hq_member_token),
        params={"scope": "mine"},
    )
    assert scoped_list_response.status_code == 200
    assert meeting["id"] in {item["id"] for item in scoped_list_response.json()["items"]}

    scoped_detail_response = client.get(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(hq_member_token),
    )
    assert scoped_detail_response.status_code == 200
    assert scoped_detail_response.json()["workspace_id"] == hq_workspace_id


def test_meeting_create_rolls_back_when_initial_attachments_fail(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    before = client.get(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(admin_token),
        params={"scope": "mine"},
    )
    assert before.status_code == 200
    assert before.json()["total"] == 0

    missing_issue = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(admin_token),
        json={
            "title": "Broken issue attach",
            "agenda": "",
            "start_at": datetime(2026, 5, 1, 10, 0, 0).isoformat(),
            "end_at": datetime(2026, 5, 1, 11, 0, 0).isoformat(),
            "attendees": [],
            "task_ids": ["missing-issue"],
        },
    )
    assert missing_issue.status_code == 404

    missing_doc = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(admin_token),
        json={
            "title": "Broken doc attach",
            "agenda": "",
            "start_at": datetime(2026, 5, 1, 10, 0, 0).isoformat(),
            "end_at": datetime(2026, 5, 1, 11, 0, 0).isoformat(),
            "attendees": [],
            "doc_ids": ["missing-doc"],
        },
    )
    assert missing_doc.status_code == 404

    after = client.get(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(admin_token),
        params={"scope": "mine"},
    )
    assert after.status_code == 200
    assert after.json()["total"] == 0


class _FakeMinioClient:
    """Minimal stand-in for the minio client used by file attachment tests.
    Captures put_object calls so assertions can verify the storage path
    without needing a running MinIO container."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.removed: list[str] = []

    def put_object(
        self, bucket: str, key: str, body, length: int, content_type: str
    ) -> None:
        del bucket, length, content_type
        self.objects[key] = body.read()

    def remove_object(self, bucket: str, key: str) -> None:
        del bucket
        self.removed.append(key)
        self.objects.pop(key, None)

    def presigned_get_object(self, bucket: str, key: str, expires) -> str:
        del bucket, expires
        return f"https://fake-minio.local/{key}"


def _install_fake_minio(monkeypatch) -> _FakeMinioClient:
    """Patch the meeting service module's storage and URL builder to a
    fake in-memory MinIO so the upload/list/delete paths can be exercised
    without external dependencies."""
    from aidoo_api.domains.meeting import service as meeting_service

    fake = _FakeMinioClient()
    monkeypatch.setattr(meeting_service, "get_minio_client", lambda: fake)
    monkeypatch.setattr(
        meeting_service,
        "_build_file_download_url",
        lambda storage_key: f"https://fake-minio.local/{storage_key}",
    )
    return fake


def _create_native_doc(client: TestClient, token: str, title: str) -> str:
    response = client.post(
        "/api/v1/docs/native-docs",
        headers=_auth_headers(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()["source_id"]


def _native_item_id(doc_id: str) -> str:
    return f"native_doc__{doc_id}"


def test_attendee_can_attach_task_via_space_access(client: TestClient) -> None:
    """An attendee who has access to the issue's PMS space (Team) — but no
    direct ProjectMember row — must be able to attach the issue. This was
    the regression behind '미팅2 에서 태스크가 등록되지 않는다' — meeting
    permission used the ProjectMember table directly while PMS itself reads
    via space membership, so seed accounts (e.g. delivery-hub-member) were silently
    locked out."""

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    # Admin creates a PMS space, project, and an issue.
    space_response = client.post(
        "/api/v1/pms/spaces",
        headers=_auth_headers(admin_token),
        json={"name": "Meeting Attach Space", "description": ""},
    )
    assert space_response.status_code == 201, space_response.text
    space = space_response.json()

    project_response = client.post(
        "/api/v1/pms/projects",
        headers=_auth_headers(admin_token),
        json={
            "key": "MEETIN",
            "name": "Meeting Attach Project",
            "description": "",
            "team_id": space["id"],
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()

    issue_response = client.post(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(admin_token),
        json={
            "title": "Prep task",
            "description": "",
            "status": "backlog",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert issue_response.status_code == 201
    issue = issue_response.json()

    # Attendee user with both meeting and pms workspace access. We then
    # add them as a member of the PMS space — NOT the project — exactly
    # mirroring how the seeded delivery-hub-member account is provisioned.
    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="space-prep@aidoo.local",
        full_name="Space Prep",
        workspace_keys=["meeting", "pms"],
    )
    add_space_member = client.post(
        f"/api/v1/pms/spaces/{space['id']}/members",
        headers=_auth_headers(admin_token),
        json={"user_id": attendee["user"]["id"], "role": "member"},
    )
    assert add_space_member.status_code in (200, 201), add_space_member.text

    attendee_token = _login(
        client, attendee["user"]["email"], attendee["temporary_password"]
    )

    # Admin organizes a meeting and invites the attendee.
    meeting = _create_meeting(
        client,
        admin_token,
        title="Space-only access meeting",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
    )

    # Attendee attaches the task — should succeed via space membership.
    attach_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/tasks",
        headers=_auth_headers(attendee_token),
        json={"issue_id": issue["id"]},
    )
    assert attach_response.status_code == 200, attach_response.text
    body = attach_response.json()
    assert len(body["task_links"]) == 1
    assert body["task_links"][0]["added_by_id"] == attendee["user"]["id"]


def test_attendee_can_attach_doc_and_only_adder_can_remove(
    client: TestClient,
) -> None:
    """Attendees should be able to upload prep material before the meeting.
    Removing an attachment is restricted to the meeting organizer or the
    user who originally added it. We exercise the matrix with native docs
    because ``ensure_doc_readable`` only requires the owner check, sidestepping
    PR2's IssueUserAccess work."""

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    # Attendee user with meeting + docs workspace access so they can both
    # be invited and create their own native doc.
    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="prep@aidoo.local",
        full_name="Prep Attendee",
        workspace_keys=["meeting", "docs"],
    )
    attendee_token = _login(
        client, attendee["user"]["email"], attendee["temporary_password"]
    )

    admin_doc = _create_native_doc(client, admin_token, "Admin prep")
    attendee_doc = _create_native_doc(client, attendee_token, "Attendee prep")

    # Admin organizes a meeting and invites the attendee.
    meeting = _create_meeting(
        client,
        admin_token,
        title="Prep meeting",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
    )

    # Attendee (non-organizer) attaches their own doc → success.
    attendee_attach = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs",
        headers=_auth_headers(attendee_token),
        json={"doc_id": attendee_doc},
    )
    assert attendee_attach.status_code == 200, attendee_attach.text
    body = attendee_attach.json()
    assert len(body["doc_links"]) == 1
    assert body["doc_links"][0]["added_by_id"] == attendee["user"]["id"]

    # Admin (organizer) attaches their own doc.
    organizer_attach = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs",
        headers=_auth_headers(admin_token),
        json={"doc_id": admin_doc},
    )
    assert organizer_attach.status_code == 200
    assert len(organizer_attach.json()["doc_links"]) == 2

    # Attendee tries to detach the organizer's doc → 403.
    forbidden = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs/{admin_doc}",
        headers=_auth_headers(attendee_token),
    )
    assert forbidden.status_code == 403, forbidden.text

    # Attendee detaches their own doc → success.
    own_detach = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs/{attendee_doc}",
        headers=_auth_headers(attendee_token),
    )
    assert own_detach.status_code == 200
    assert {link["doc_id"] for link in own_detach.json()["doc_links"]} == {
        admin_doc
    }

    # Re-attach attendee's doc, then organizer detaches it → success
    # (organizer always wins).
    re_attach = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs",
        headers=_auth_headers(attendee_token),
        json={"doc_id": attendee_doc},
    )
    assert re_attach.status_code == 200

    organizer_removes_others = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs/{attendee_doc}",
        headers=_auth_headers(admin_token),
    )
    assert organizer_removes_others.status_code == 200


def test_meeting_attachment_grants_allow_read_but_not_metadata_or_sharing(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    project = _create_project(client, admin_token, key="ACL", name="ACL Project")
    issue = _create_issue(client, admin_token, project["id"], title="Meeting-shared issue")
    doc_id = _create_native_doc(client, admin_token, "Meeting-shared doc")

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="meeting-reader@aidoo.local",
        full_name="Meeting Reader",
        workspace_keys=["meeting", "pms", "docs"],
    )
    attendee_token = _login(
        client,
        attendee["user"]["email"],
        attendee["temporary_password"],
    )

    _create_meeting(
        client,
        admin_token,
        title="ACL grant meeting",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
        task_ids=[issue["id"]],
        doc_ids=[doc_id],
    )

    issue_detail = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert issue_detail.status_code == 200, issue_detail.text
    issue_payload = issue_detail.json()
    assert issue_payload["issue"]["list_id"] == project["id"]
    assert "project_id" not in issue_payload["issue"]

    issue_list = client.get(
        f"/api/v1/pms/projects/{project['id']}/issues",
        headers=_auth_headers(attendee_token),
    )
    assert issue_list.status_code == 403

    doc_item = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}",
        headers=_auth_headers(attendee_token),
    )
    assert doc_item.status_code == 200, doc_item.text
    doc_payload = doc_item.json()
    assert doc_payload["source_id"] == doc_id
    assert doc_payload["can_view"] is True
    assert doc_payload["can_edit"] is False
    assert doc_payload["can_share"] is False
    assert doc_payload["can_manage"] is False

    doc_pages = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}/pages",
        headers=_auth_headers(attendee_token),
    )
    assert doc_pages.status_code == 200, doc_pages.text
    assert len(doc_pages.json()["items"]) == 1

    doc_sharing = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}/sharing",
        headers=_auth_headers(attendee_token),
    )
    assert doc_sharing.status_code == 403


def test_meeting_detach_preserves_other_meeting_grants_until_last_source_is_removed(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    project = _create_project(client, admin_token, key="SAFE", name="Safety Project")
    issue = _create_issue(client, admin_token, project["id"], title="Multi-meeting issue")
    doc_id = _create_native_doc(client, admin_token, "Multi-meeting doc")

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="multi-reader@aidoo.local",
        full_name="Multi Reader",
        workspace_keys=["meeting", "pms", "docs"],
    )
    attendee_token = _login(
        client,
        attendee["user"]["email"],
        attendee["temporary_password"],
    )

    meeting_a = _create_meeting(
        client,
        admin_token,
        title="Meeting A",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
        task_ids=[issue["id"]],
        doc_ids=[doc_id],
    )
    meeting_b = _create_meeting(
        client,
        admin_token,
        title="Meeting B",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
        task_ids=[issue["id"]],
        doc_ids=[doc_id],
    )

    first_issue_detach = client.delete(
        f"/api/v1/meeting/meetings/{meeting_a['id']}/tasks/{issue['id']}",
        headers=_auth_headers(admin_token),
    )
    assert first_issue_detach.status_code == 200
    first_doc_detach = client.delete(
        f"/api/v1/meeting/meetings/{meeting_a['id']}/docs/{doc_id}",
        headers=_auth_headers(admin_token),
    )
    assert first_doc_detach.status_code == 200

    still_can_read_issue = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert still_can_read_issue.status_code == 200
    still_can_read_doc = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}",
        headers=_auth_headers(attendee_token),
    )
    assert still_can_read_doc.status_code == 200

    second_issue_detach = client.delete(
        f"/api/v1/meeting/meetings/{meeting_b['id']}/tasks/{issue['id']}",
        headers=_auth_headers(admin_token),
    )
    assert second_issue_detach.status_code == 200
    second_doc_detach = client.delete(
        f"/api/v1/meeting/meetings/{meeting_b['id']}/docs/{doc_id}",
        headers=_auth_headers(admin_token),
    )
    assert second_doc_detach.status_code == 200

    blocked_issue = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert blocked_issue.status_code == 403
    blocked_doc = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}",
        headers=_auth_headers(attendee_token),
    )
    assert blocked_doc.status_code == 404


def test_meeting_reschedule_resyncs_issue_and_doc_grant_expiry(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    project = _create_project(client, admin_token, key="TIME", name="Timing Project")
    issue = _create_issue(client, admin_token, project["id"], title="Expiry issue")
    doc_id = _create_native_doc(client, admin_token, "Expiry doc")

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="expiry-reader@aidoo.local",
        full_name="Expiry Reader",
        workspace_keys=["meeting", "pms", "docs"],
    )
    attendee_token = _login(
        client,
        attendee["user"]["email"],
        attendee["temporary_password"],
    )

    meeting = _create_meeting(
        client,
        admin_token,
        title="Expiry meeting",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
        task_ids=[issue["id"]],
        doc_ids=[doc_id],
    )

    initial_issue = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert initial_issue.status_code == 200
    initial_doc = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}",
        headers=_auth_headers(attendee_token),
    )
    assert initial_doc.status_code == 200

    expired_update = client.patch(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin_token),
        json={
            "start_at": "2000-01-01T09:00:00",
            "end_at": "2000-01-01T10:00:00",
        },
    )
    assert expired_update.status_code == 200, expired_update.text

    expired_issue = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert expired_issue.status_code == 403
    expired_doc = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}",
        headers=_auth_headers(attendee_token),
    )
    assert expired_doc.status_code == 404

    restored_update = client.patch(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin_token),
        json={
            "start_at": "2100-01-01T09:00:00",
            "end_at": "2100-01-01T10:00:00",
        },
    )
    assert restored_update.status_code == 200, restored_update.text

    restored_issue = client.get(
        f"/api/v1/pms/issues/{issue['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert restored_issue.status_code == 200
    restored_doc = client.get(
        f"/api/v1/docs/items/{_native_item_id(doc_id)}",
        headers=_auth_headers(attendee_token),
    )
    assert restored_doc.status_code == 200


def test_meeting_file_attachment_upload_and_permission_matrix(
    client: TestClient, monkeypatch
) -> None:
    """End-to-end exercise of the new POST/DELETE /meetings/{id}/files
    routes. Uses an in-memory fake MinIO so no external services are
    required."""
    fake = _install_fake_minio(monkeypatch)

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    attendee = _create_user_with_workspaces(
        client,
        admin_token,
        email="filer@aidoo.local",
        full_name="File Attendee",
        workspace_keys=["meeting"],
    )
    attendee_token = _login(
        client, attendee["user"]["email"], attendee["temporary_password"]
    )

    meeting = _create_meeting(
        client,
        admin_token,
        title="Files meeting",
        attendees=[{"user_id": attendee["user"]["id"], "role": "required"}],
    )

    # Attendee uploads a prep file → success.
    upload_response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/files",
        headers=_auth_headers(attendee_token),
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert upload_response.status_code == 200, upload_response.text
    body = upload_response.json()
    assert len(body["file_attachments"]) == 1
    file_meta = body["file_attachments"][0]
    assert file_meta["filename"] == "notes.txt"
    assert file_meta["content_type"] == "text/plain"
    assert file_meta["size_bytes"] == len(b"hello world")
    assert file_meta["added_by_id"] == attendee["user"]["id"]
    assert file_meta["download_url"].startswith("https://fake-minio.local/")
    assert any("notes.txt" in key for key in fake.objects)

    file_id = file_meta["id"]

    # GET via meeting detail surfaces the same data.
    detail_response = client.get(
        f"/api/v1/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(attendee_token),
    )
    assert detail_response.status_code == 200
    fetched_files = detail_response.json()["file_attachments"]
    assert len(fetched_files) == 1
    assert fetched_files[0]["id"] == file_id

    # Admin uploads their own file as the organizer.
    admin_upload = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/files",
        headers=_auth_headers(admin_token),
        files={"file": ("agenda.md", b"# agenda", "text/markdown")},
    )
    assert admin_upload.status_code == 200
    admin_file_id = next(
        item["id"]
        for item in admin_upload.json()["file_attachments"]
        if item["filename"] == "agenda.md"
    )

    # Attendee tries to delete the organizer's file → 403.
    forbidden = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/files/{admin_file_id}",
        headers=_auth_headers(attendee_token),
    )
    assert forbidden.status_code == 403

    # Attendee deletes their own file → success.
    own_delete = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/files/{file_id}",
        headers=_auth_headers(attendee_token),
    )
    assert own_delete.status_code == 200
    remaining = own_delete.json()["file_attachments"]
    assert {item["id"] for item in remaining} == {admin_file_id}
    assert any("notes.txt" in key for key in fake.removed)

    # Organizer deletes the remaining file (their own) → success.
    organizer_delete = client.delete(
        f"/api/v1/meeting/meetings/{meeting['id']}/files/{admin_file_id}",
        headers=_auth_headers(admin_token),
    )
    assert organizer_delete.status_code == 200
    assert organizer_delete.json()["file_attachments"] == []


def test_meeting_file_upload_rejects_non_participant(
    client: TestClient, monkeypatch
) -> None:
    _install_fake_minio(monkeypatch)

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    stranger = _create_user_with_workspaces(
        client,
        admin_token,
        email="lurker3@aidoo.local",
        full_name="Stranger",
        workspace_keys=["meeting"],
    )
    stranger_token = _login(
        client, stranger["user"]["email"], stranger["temporary_password"]
    )

    meeting = _create_meeting(client, admin_token, title="Closed for files")

    response = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/files",
        headers=_auth_headers(stranger_token),
        files={"file": ("intruder.txt", b"hi", "text/plain")},
    )
    assert response.status_code == 403


def test_non_participant_cannot_attach_doc(client: TestClient) -> None:
    """A user with meeting workspace access who is neither organizer nor
    attendee must not be able to attach to someone else's meeting."""

    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    stranger = _create_user_with_workspaces(
        client,
        admin_token,
        email="lurker2@aidoo.local",
        full_name="Lurker",
        workspace_keys=["meeting", "docs"],
    )
    stranger_token = _login(
        client, stranger["user"]["email"], stranger["temporary_password"]
    )
    stranger_doc = _create_native_doc(client, stranger_token, "Lurker prep")

    # Admin organizes a meeting and does NOT invite the stranger.
    meeting = _create_meeting(client, admin_token, title="Closed meeting")

    forbidden = client.post(
        f"/api/v1/meeting/meetings/{meeting['id']}/docs",
        headers=_auth_headers(stranger_token),
        json={"doc_id": stranger_doc},
    )
    assert forbidden.status_code == 403


def test_meeting_time_roundtrip_with_utc_iso_input(client: TestClient) -> None:
    """The frontend serializes datetime-local picker values with
    ``Date.toISOString()`` which always emits a ``Z`` suffix. The backend
    must accept that, store it, and return the same wall-clock value back
    so the frontend can render it without drift."""

    admin = _bootstrap_admin_session(client)
    token = admin["token"]

    # Simulate the frontend pipeline. KST 21:00 → UTC 12:00 with the Z suffix.
    request_start = "2026-05-10T12:00:00.000Z"
    request_end = "2026-05-10T13:30:00.000Z"

    response = client.post(
        "/api/v1/meeting/meetings",
        headers=_auth_headers(token),
        json={
            "title": "TZ roundtrip",
            "agenda": "",
            "start_at": request_start,
            "end_at": request_end,
            "attendees": [],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    # The server emits naive ISO strings (no Z, no offset). They represent
    # the same UTC instant the client sent.
    assert body["start_at"] == "2026-05-10T12:00:00"
    assert body["end_at"] == "2026-05-10T13:30:00"

    # Re-fetch via GET to confirm the value persisted, not just echoed.
    fetched = client.get(
        f"/api/v1/meeting/meetings/{body['id']}",
        headers=_auth_headers(token),
    )
    assert fetched.status_code == 200
    fetched_body = fetched.json()
    assert fetched_body["start_at"] == "2026-05-10T12:00:00"
    assert fetched_body["end_at"] == "2026-05-10T13:30:00"

    # PATCH with another Z-suffixed UTC ISO and verify the same contract.
    patch_response = client.patch(
        f"/api/v1/meeting/meetings/{body['id']}",
        headers=_auth_headers(token),
        json={
            "start_at": "2026-05-10T14:00:00.000Z",
            "end_at": "2026-05-10T15:00:00.000Z",
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert patched["start_at"] == "2026-05-10T14:00:00"
    assert patched["end_at"] == "2026-05-10T15:00:00"


def test_upcoming_scope_does_not_leak_other_users_meetings(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    outsider = _create_user_with_workspaces(
        client,
        admin_token,
        email="lurker@aidoo.local",
        full_name="Lurker",
        workspace_keys=["meeting"],
    )
    outsider_token = _login(
        client,
        outsider["user"]["email"],
        outsider["temporary_password"],
    )

    # Admin organizes a private meeting and does NOT invite the outsider.
    private = _create_meeting(client, admin_token, title="Admin only")

    # Outsider sees nothing in any scope, even though they have meeting
    # workspace access.
    for scope in ("mine", "upcoming", "all"):
        response = client.get(
            "/api/v1/meeting/meetings",
            headers=_auth_headers(outsider_token),
            params={"scope": scope},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 0, (
            f"scope={scope} leaked meeting: {body}"
        )

    # Trying to GET the meeting directly is also blocked.
    direct = client.get(
        f"/api/v1/meeting/meetings/{private['id']}",
        headers=_auth_headers(outsider_token),
    )
    assert direct.status_code == 403

    # Now invite the outsider as an attendee. They should immediately see
    # the meeting in all scopes that include them.
    update_response = client.patch(
        f"/api/v1/meeting/meetings/{private['id']}",
        headers=_auth_headers(admin_token),
        json={
            "attendees": [
                {"user_id": outsider["user"]["id"], "role": "required"}
            ],
        },
    )
    assert update_response.status_code == 200

    for scope in ("mine", "upcoming", "all"):
        response = client.get(
            "/api/v1/meeting/meetings",
            headers=_auth_headers(outsider_token),
            params={"scope": scope},
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1, f"scope={scope}"


def test_meeting_update_changes_time_and_attendees(client: TestClient) -> None:
    admin = _bootstrap_admin_session(client)
    admin_token = admin["token"]

    member = _create_user_with_workspaces(
        client,
        admin_token,
        email="invitee@aidoo.local",
        full_name="Invitee User",
        workspace_keys=["meeting"],
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
