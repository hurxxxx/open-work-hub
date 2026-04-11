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


def test_attendee_can_attach_task_via_space_access(client: TestClient) -> None:
    """An attendee who has access to the issue's PMS space (Team) — but no
    direct ProjectMember row — must be able to attach the issue. This was
    the regression behind '미팅2 에서 태스크가 등록되지 않는다' — meeting
    permission used the ProjectMember table directly while PMS itself reads
    via space membership, so seed accounts (e.g. pms-member) were silently
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
    # mirroring how the seed pms-member account is provisioned.
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
