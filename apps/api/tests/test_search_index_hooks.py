from __future__ import annotations

from dataclasses import replace
from typing import Literal

from fastapi.testclient import TestClient
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.files import rag_sync as file_rag_sync
from open_work_hub_api.domains.files import search_projection as file_search_projection
from open_work_hub_api.domains.files import search_hooks as file_search_hooks
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.pms.access_grants import grant_task_access, revoke_task_access
from open_work_hub_api.domains.search import outbox as search_outbox
from open_work_hub_api.domains.search import indexing as search_indexing
from open_work_hub_api.domains.search import projections as search_projections
from open_work_hub_api.domains.search.indexing import process_search_index_job
from open_work_hub_api.domains.search.models import SearchIndexJob

from test_meeting import (
    _auth_headers,
    _bootstrap_admin_session,
    _create_meeting,
    _create_user_with_workspaces,
    _first_workspace_slug,
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

    def upsert_partitioned_document(self, document: dict) -> str:
        self.upserts.append(document)
        return "upserted"

    def delete_partitioned_document(
        self,
        *,
        resource_type: str,
        resource_id: str,
        projection_version: int,
    ) -> str:
        del projection_version
        prior = next(
            (
                document
                for document in reversed(self.upserts)
                if document.get("entity_id") == resource_id
            ),
            None,
        )
        entity_type = (
            str(prior["entity_type"])
            if prior is not None
            else {
                "docs_native_doc": "doc",
                "file_manager_file": "file",
                "meeting": "meeting",
                "pms_task": "task",
            }[resource_type]
        )
        self.deletes.append(
            (
                str(prior["workspace_id"]) if prior is not None else "",
                entity_type,
                resource_id,
            )
        )
        return "deleted"


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

    monkeypatch.setattr(search_outbox, "get_celery_client", lambda: _FakeCeleryClient())
    return published


def _process_pending_entity(
    search_client: _RecordingSearchClient,
    *,
    entity_type: str,
    entity_id: str,
    lifecycle_operation: Literal["create", "update"],
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
    assert job_ids, (
        f"expected pending {lifecycle_operation} search index job for {entity_type}:{entity_id}"
    )

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
    lifecycle_operation: Literal["delete"],
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
    assert job_ids, (
        f"expected pending {lifecycle_operation} search index job for {entity_type}:{entity_id}"
    )

    for job_id in job_ids:
        with get_session_factory()() as db:
            process_search_index_job(db, job_id, client=search_client)

    matches = [
        item for item in search_client.deletes if item[1] == entity_type and item[2] == entity_id
    ]
    assert matches, f"expected search delete for {entity_type}:{entity_id}"
    return matches[-1]


def _create_space(client: TestClient, token: str, *, workspace_slug: str, name: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/spaces",
        headers=_auth_headers(token),
        json={"name": name, "description": ""},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_task_list(
    client: TestClient,
    token: str,
    *,
    workspace_slug: str,
    team_id: str,
    key: str,
    name: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/lists",
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


def _create_issue(
    client: TestClient,
    token: str,
    *,
    workspace_slug: str,
    list_id: str,
    title: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/pms/lists/{list_id}/tasks",
        headers=_auth_headers(token),
        json={
            "title": title,
            "description": "Task body",
            "status": "todo",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_file_extraction_and_delete_drive_search_projection_lifecycle(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    monkeypatch.setattr(file_rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(file_search_hooks, "FILES_RETRIEVAL_ACTIVE", True)
    active_file_adapter = replace(
        file_search_projection.FILES_WORKSPACE_KEYWORD_SEARCH_ADAPTER,
        active=True,
    )
    original_projection_adapter = search_indexing.get_search_projection_adapter

    def resolve_projection_adapter(entity_type):
        return (
            active_file_adapter
            if str(entity_type) == "file"
            else original_projection_adapter(entity_type)
        )

    monkeypatch.setattr(
        search_indexing,
        "get_search_projection_adapter",
        resolve_projection_adapter,
    )
    monkeypatch.setattr(
        search_projections,
        "get_search_projection_adapter",
        resolve_projection_adapter,
    )
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])

    upload_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/files/upload",
        headers=_auth_headers(admin["token"]),
        data={"visibility": "workspace"},
        files={"file": ("search-lifecycle.txt", b"first searchable body", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    file_id = upload_response.json()["id"]

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, file_id)
        assert file is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "a" * 64
        file.extraction_text = "first searchable body"
        file.extraction_blocks = [{"text": "first searchable body"}]
        file_rag_sync.mark_file_projection_prepared(db, file_id=file_id)
        db.commit()

    created_projection = _process_pending_entity(
        search_client,
        entity_type="file",
        entity_id=file_id,
        lifecycle_operation="create",
    )
    assert created_projection["body"] == "first searchable body"

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, file_id)
        assert file is not None
        file.extraction_content_checksum = "b" * 64
        file.extraction_text = "updated searchable body"
        file.extraction_blocks = [{"text": "updated searchable body"}]
        file_rag_sync.mark_file_projection_prepared(db, file_id=file_id)
        db.commit()

    updated_projection = _process_pending_entity(
        search_client,
        entity_type="file",
        entity_id=file_id,
        lifecycle_operation="update",
    )
    assert updated_projection["body"] == "updated searchable body"

    delete_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/files/{file_id}",
        headers=_auth_headers(admin["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text
    _process_pending_delete(
        search_client,
        entity_type="file",
        entity_id=file_id,
        lifecycle_operation="delete",
    )


def test_doc_user_share_grant_and_revoke_refresh_search_acl_projection(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    owner = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-doc-owner@open-work-hub.local",
        full_name="Search Doc Owner",
        workspace_keys=["administrator"],
    )
    recipient = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-doc-recipient@open-work-hub.local",
        full_name="Search Doc Recipient",
        workspace_keys=["administrator"],
    )
    owner_token = _login(client, owner["user"]["email"], owner["temporary_password"])

    create_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/docs/items",
        headers=_auth_headers(owner_token),
        json={"title": "Incremental Search Doc"},
    )
    assert create_response.status_code == 201, create_response.text
    doc = create_response.json()
    created_projection = _process_pending_entity(
        search_client,
        entity_type="doc",
        entity_id=doc["id"],
        lifecycle_operation="create",
    )
    assert created_projection["entity_id"] == doc["id"]

    share_response = client.put(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner_token),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200, share_response.text

    granted_projection = _process_pending_entity(
        search_client,
        entity_type="doc",
        entity_id=doc["id"],
        lifecycle_operation="update",
    )
    assert recipient["user"]["id"] in granted_projection["shared_user_ids"]

    revoke_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}/sharing/users/{recipient['user']['id']}",
        headers=_auth_headers(owner_token),
    )
    assert revoke_response.status_code == 200, revoke_response.text

    revoked_projection = _process_pending_entity(
        search_client,
        entity_type="doc",
        entity_id=doc["id"],
        lifecycle_operation="update",
    )
    assert recipient["user"]["id"] not in revoked_projection["shared_user_ids"]

    delete_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/docs/items/{doc['id']}",
        headers=_auth_headers(owner_token),
    )
    assert delete_response.status_code == 204, delete_response.text
    _process_pending_delete(
        search_client,
        entity_type="doc",
        entity_id=doc["id"],
        lifecycle_operation="delete",
    )


def test_meeting_attendee_add_and_remove_refresh_search_acl_projection(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    attendee = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-meeting-attendee@open-work-hub.local",
        full_name="Search Meeting Attendee",
        workspace_keys=["administrator"],
    )
    meeting = _create_meeting(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        title="Incremental Search Meeting",
        attendees=[],
    )
    created_projection = _process_pending_entity(
        search_client,
        entity_type="meeting",
        entity_id=meeting["id"],
        lifecycle_operation="create",
    )
    assert created_projection["entity_id"] == meeting["id"]

    add_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/attendees",
        headers=_auth_headers(admin["token"]),
        json={"attendees": [{"user_id": attendee["user"]["id"], "role": "required"}]},
    )
    assert add_response.status_code == 200, add_response.text

    added_projection = _process_pending_entity(
        search_client,
        entity_type="meeting",
        entity_id=meeting["id"],
        lifecycle_operation="update",
    )
    assert attendee["user"]["id"] in added_projection["participant_user_ids"]

    remove_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
        json={"attendees": []},
    )
    assert remove_response.status_code == 200, remove_response.text

    removed_projection = _process_pending_entity(
        search_client,
        entity_type="meeting",
        entity_id=meeting["id"],
        lifecycle_operation="update",
    )
    assert attendee["user"]["id"] not in removed_projection["participant_user_ids"]


def test_meeting_delete_detaches_access_grant_foreign_keys_and_deletes_search_document(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    attendee = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-meeting-delete-attendee@open-work-hub.local",
        full_name="Search Meeting Delete Attendee",
        workspace_keys=["administrator"],
    )
    space = _create_space(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        name="Search Meeting Delete Space",
    )
    task_list = _create_task_list(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        team_id=space["id"],
        key="SMDL",
        name="Search Meeting Delete List",
    )
    issue = _create_issue(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        list_id=task_list["id"],
        title="Meeting Delete Task",
    )
    meeting = _create_meeting(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        title="Delete Meeting With Grants",
        attendees=[],
        task_ids=[issue["id"]],
    )

    add_response = client.post(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}/attendees",
        headers=_auth_headers(admin["token"]),
        json={"attendees": [{"user_id": attendee["user"]["id"], "role": "required"}]},
    )
    assert add_response.status_code == 200, add_response.text

    remove_response = client.patch(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
        json={"attendees": []},
    )
    assert remove_response.status_code == 200, remove_response.text

    delete_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/meeting/meetings/{meeting['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text

    _process_pending_delete(
        search_client,
        entity_type="meeting",
        entity_id=meeting["id"],
        lifecycle_operation="delete",
    )


def test_pms_task_user_access_grant_and_revoke_refresh_search_acl_projection(
    client: TestClient,
    monkeypatch,
) -> None:
    _stub_search_publish(monkeypatch)
    search_client = _RecordingSearchClient()
    admin = _bootstrap_admin_session(client)
    workspace_slug = _first_workspace_slug(client, admin["token"])
    recipient = _create_user_with_workspaces(
        client,
        admin["token"],
        email="search-pms-recipient@open-work-hub.local",
        full_name="Search PMS Recipient",
        workspace_keys=["administrator"],
    )
    space = _create_space(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        name="Search PMS Space",
    )
    task_list = _create_task_list(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        team_id=space["id"],
        key="SRCH",
        name="Search PMS List",
    )
    issue = _create_issue(
        client,
        admin["token"],
        workspace_slug=workspace_slug,
        list_id=task_list["id"],
        title="Incremental Search Task",
    )
    created_projection = _process_pending_entity(
        search_client,
        entity_type="pms_task",
        entity_id=issue["id"],
        lifecycle_operation="create",
    )
    assert created_projection["entity_id"] == issue["id"]

    with get_session_factory()() as db:
        grant_task_access(
            db,
            task_id=issue["id"],
            user_id=recipient["user"]["id"],
            granted_by_user_id=admin["user"]["id"],
            granted_by_meeting_id=None,
            reason="manual_share",
        )
        db.commit()

    granted_projection = _process_pending_entity(
        search_client,
        entity_type="pms_task",
        entity_id=issue["id"],
        lifecycle_operation="update",
    )
    assert recipient["user"]["id"] in granted_projection["granted_user_ids"]

    with get_session_factory()() as db:
        assert (
            revoke_task_access(
                db,
                task_id=issue["id"],
                user_id=recipient["user"]["id"],
                revoked_by_user_id=admin["user"]["id"],
                reason="manual_revoke",
            )
            == 1
        )
        db.commit()

    revoked_projection = _process_pending_entity(
        search_client,
        entity_type="pms_task",
        entity_id=issue["id"],
        lifecycle_operation="update",
    )
    assert recipient["user"]["id"] not in revoked_projection["granted_user_ids"]

    delete_response = client.delete(
        f"/api/v1/workspaces/{workspace_slug}/pms/tasks/{issue['id']}",
        headers=_auth_headers(admin["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text
    _process_pending_delete(
        search_client,
        entity_type="pms_task",
        entity_id=issue["id"],
        lifecycle_operation="delete",
    )


def test_personal_planner_events_do_not_enqueue_workspace_search_jobs(
    client: TestClient,
    monkeypatch,
) -> None:
    published = _stub_search_publish(monkeypatch)
    admin = _bootstrap_admin_session(client)

    create_response = client.post(
        "/api/v1/planner/events",
        headers=_auth_headers(admin["token"]),
        json={
            "title": "Incremental Search Planner Event",
            "description": "Planner body",
            "location": "Seoul",
            "allDay": False,
            "start": "2026-05-04T01:00:00+00:00",
            "end": "2026-05-04T02:00:00+00:00",
        },
    )
    assert create_response.status_code == 201, create_response.text
    event = create_response.json()

    with get_session_factory()() as db:
        job = db.scalar(
            select(SearchIndexJob).where(
                SearchIndexJob.entity_type == "planner_event",
                SearchIndexJob.entity_id == event["id"],
            )
        )
    assert job is None
    assert published == []
