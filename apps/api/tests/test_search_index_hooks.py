from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from ai_do_api.core.db import get_session_factory
from ai_do_api.domains.pms.access_grants import grant_issue_access, revoke_issue_access
from ai_do_api.domains.search import outbox as search_outbox
from ai_do_api.domains.search.indexing import process_search_index_job
from ai_do_api.domains.search.models import SearchIndexJob

from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_meeting,
    _create_user_with_workspaces,
    _login,
)


class _RecordingSearchClient:
    def __init__(self) -> None:
        self.upserts: list[dict] = []
        self.deletes: list[tuple[str, str, str]] = []

    def upsert_document(self, document: dict) -> None:
        self.upserts.append(document)

    def delete_document(self, *, workspace_id: str, entity_type: str, entity_id: str) -> None:
        self.deletes.append((workspace_id, entity_type, entity_id))


def _stub_search_publish(monkeypatch) -> list[tuple[str, list[str], str]]:
    published: list[tuple[str, list[str], str]] = []

    class _FakeSignature:
        def __init__(self, task_name: str, args: list[str]) -> None:
            self.task_name = task_name
            self.args = args

        def apply_async(self, *, queue: str, retry: bool) -> None:
            published.append((self.task_name, self.args, queue))

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            assert immutable is True
            return _FakeSignature(task_name, args)

    monkeypatch.setattr(search_outbox, "_get_celery_client", lambda: _FakeCeleryClient())
    return published


def _process_pending_entity(
    search_client: _RecordingSearchClient,
    *,
    entity_type: str,
    entity_id: str,
) -> dict:
    with get_session_factory()() as db:
        job_ids = list(
            db.scalars(
                select(SearchIndexJob.id)
                .where(
                    SearchIndexJob.status == "pending",
                    SearchIndexJob.entity_type == entity_type,
                    SearchIndexJob.entity_id == entity_id,
                )
                .order_by(SearchIndexJob.created_at.asc(), SearchIndexJob.id.asc())
            )
        )
    assert job_ids, f"expected pending search index job for {entity_type}:{entity_id}"

    for job_id in job_ids:
        with get_session_factory()() as db:
            process_search_index_job(db, job_id, client=search_client)

    matches = [
        document
        for document in search_client.upserts
        if document.get("entity_type") == entity_type and document.get("entity_id") == entity_id
    ]
    assert matches, f"expected search upsert for {entity_type}:{entity_id}"
    return matches[-1]


def _process_pending_delete(
    search_client: _RecordingSearchClient,
    *,
    entity_type: str,
    entity_id: str,
) -> tuple[str, str, str]:
    with get_session_factory()() as db:
        job_ids = list(
            db.scalars(
                select(SearchIndexJob.id)
                .where(
                    SearchIndexJob.status == "pending",
                    SearchIndexJob.entity_type == entity_type,
                    SearchIndexJob.entity_id == entity_id,
                )
                .order_by(SearchIndexJob.created_at.asc(), SearchIndexJob.id.asc())
            )
        )
    assert job_ids, f"expected pending search index job for {entity_type}:{entity_id}"

    for job_id in job_ids:
        with get_session_factory()() as db:
            process_search_index_job(db, job_id, client=search_client)

    matches = [
        item
        for item in search_client.deletes
        if item[1] == entity_type and item[2] == entity_id
    ]
    assert matches, f"expected search delete for {entity_type}:{entity_id}"
    return matches[-1]


def _create_space(client: TestClient, token: str, *, name: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/hq/pms/spaces",
        headers=_auth_headers(token),
        json={"name": name, "description": ""},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list(client: TestClient, token: str, *, team_id: str, key: str, name: str) -> dict:
    response = client.post(
        "/api/v1/workspaces/hq/pms/lists",
        headers=_auth_headers(token),
        json={
            "key": key,
            "name": name,
            "description": "",
            "team_id": team_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_issue(client: TestClient, token: str, *, list_id: str, title: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/hq/pms/lists/{list_id}/issues",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "Issue body",
            "status": "backlog",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_doc_user_share_grant_and_revoke_refresh_search_acl_projection(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    owner = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-doc-owner@ai-do.local",
        full_name="Search Doc Owner",
        workspace_keys=["docs"],
    )
    recipient = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-doc-recipient@ai-do.local",
        full_name="Search Doc Recipient",
        workspace_keys=["docs"],
    )
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    create_response = client.post(
        "/api/v1/workspaces/hq/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Incremental Search Doc"},
    )
    assert create_response.status_code == 201, create_response.text
    doc = create_response.json()

    share_response = client.put(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200, share_response.text

    granted_projection = _process_pending_entity(search_client, entity_type="doc", entity_id=doc["id"])
    assert recipient["user"]["id"] in granted_projection["shared_user_ids"]

    revoke_response = client.delete(
        f"/api/v1/workspaces/hq/docs/items/{doc['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner_token),
    )
    assert revoke_response.status_code == 200, revoke_response.text

    revoked_projection = _process_pending_entity(search_client, entity_type="doc", entity_id=doc["id"])
    assert recipient["user"]["id"] not in revoked_projection["shared_user_ids"]


def test_meeting_attendee_add_and_remove_refresh_search_acl_projection(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    attendee = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-meeting-attendee@ai-do.local",
        full_name="Search Meeting Attendee",
        workspace_keys=["meeting"],
    )
    meeting = _create_meeting(
        client,
        admin["token"],
        title="Incremental Search Meeting",
        attendees=[],
    )

    add_response = client.post(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}/attendees",
        headers=_auth_headers(admin["token"]),
        json={"attendees": [{"user_id": attendee["user"]["id"], "role": "required"}]},
    )
    assert add_response.status_code == 200, add_response.text

    added_projection = _process_pending_entity(search_client, entity_type="meeting", entity_id=meeting["id"])
    assert attendee["user"]["id"] in added_projection["participant_user_ids"]

    remove_response = client.patch(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
        json={"attendees": []},
    )
    assert remove_response.status_code == 200, remove_response.text

    removed_projection = _process_pending_entity(search_client, entity_type="meeting", entity_id=meeting["id"])
    assert attendee["user"]["id"] not in removed_projection["participant_user_ids"]


def test_meeting_delete_detaches_access_grant_foreign_keys_and_deletes_search_document(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    attendee = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-meeting-delete-attendee@ai-do.local",
        full_name="Search Meeting Delete Attendee",
        workspace_keys=["meeting", "pms"],
    )
    space = _create_space(client, admin["token"], name="Search Meeting Delete Space")
    task_list = _create_task_list(
        client,
        admin["token"],
        team_id=space["id"],
        key="SMDL",
        name="Search Meeting Delete List",
    )
    issue = _create_issue(client, admin["token"], list_id=task_list["id"], title="Meeting Delete Issue")
    meeting = _create_meeting(
        client,
        admin["token"],
        title="Delete Meeting With Grants",
        attendees=[],
        task_ids=[issue["id"]],
    )

    add_response = client.post(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}/attendees",
        headers=_auth_headers(admin["token"]),
        json={"attendees": [{"user_id": attendee["user"]["id"], "role": "required"}]},
    )
    assert add_response.status_code == 200, add_response.text

    remove_response = client.patch(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
        json={"attendees": []},
    )
    assert remove_response.status_code == 200, remove_response.text

    delete_response = client.delete(
        f"/api/v1/workspaces/hq/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text

    _process_pending_delete(search_client, entity_type="meeting", entity_id=meeting["id"])


def test_pms_issue_user_access_grant_and_revoke_refresh_search_acl_projection(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    recipient = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-pms-recipient@ai-do.local",
        full_name="Search PMS Recipient",
        workspace_keys=["pms"],
    )
    space = _create_space(client, admin["token"], name="Search PMS Space")
    task_list = _create_task_list(
        client,
        admin["token"],
        team_id=space["id"],
        key="SRCH",
        name="Search PMS List",
    )
    issue = _create_issue(client, admin["token"], list_id=task_list["id"], title="Incremental Search Issue")

    with get_session_factory()() as db:
        grant_issue_access(
            db,
            issue_id=issue["id"],
            user_id=recipient["user"]["id"],
            granted_by_user_id=admin["user"]["id"],
            granted_by_meeting_id=None,
            reason="manual_share",
        )
        db.commit()

    granted_projection = _process_pending_entity(search_client, entity_type="pms_issue", entity_id=issue["id"])
    assert recipient["user"]["id"] in granted_projection["granted_user_ids"]

    with get_session_factory()() as db:
        assert (
            revoke_issue_access(
                db,
                issue_id=issue["id"],
                user_id=recipient["user"]["id"],
                revoked_by_user_id=admin["user"]["id"],
                reason="manual_revoke",
            )
            == 1
        )
        db.commit()

    revoked_projection = _process_pending_entity(search_client, entity_type="pms_issue", entity_id=issue["id"])
    assert recipient["user"]["id"] not in revoked_projection["granted_user_ids"]


def test_planner_visibility_changes_refresh_search_acl_projection(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)

    create_response = client.post(
        "/api/v1/workspaces/hq/planner/events",
        headers=_auth_headers(admin["token"]),
        json={
            "title": "Incremental Search Planner Event",
            "description": "Planner body",
            "location": "Seoul",
            "visibility": "private",
            "allDay": False,
            "start": "2026-05-04T01:00:00+00:00",
            "end": "2026-05-04T02:00:00+00:00",
        },
    )
    assert create_response.status_code == 201, create_response.text
    event = create_response.json()

    private_projection = _process_pending_entity(
        search_client,
        entity_type="planner_event",
        entity_id=event["id"],
    )
    assert private_projection["visibility"] == "private"

    public_response = client.patch(
        f"/api/v1/workspaces/hq/planner/events/{event['id']}",
        headers=_auth_headers(admin["token"]),
        json={"visibility": "public"},
    )
    assert public_response.status_code == 200, public_response.text

    public_projection = _process_pending_entity(
        search_client,
        entity_type="planner_event",
        entity_id=event["id"],
    )
    assert public_projection["visibility"] == "public"

    private_response = client.patch(
        f"/api/v1/workspaces/hq/planner/events/{event['id']}",
        headers=_auth_headers(admin["token"]),
        json={"visibility": "private"},
    )
    assert private_response.status_code == 200, private_response.text

    final_projection = _process_pending_entity(
        search_client,
        entity_type="planner_event",
        entity_id=event["id"],
    )
    assert final_projection["visibility"] == "private"
