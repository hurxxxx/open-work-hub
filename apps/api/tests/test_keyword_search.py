from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from conftest import (
    _build_client,
    _teardown_client_state,
)
from dev_accounts import create_workspace_user_session, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data
from open_work_hub_api.domains.auth.models import Workspace
from open_work_hub_api.domains.docs import service as docs_service
from open_work_hub_api.domains.pms.access_grants import grant_task_access, revoke_task_access
from open_work_hub_api.domains.search.indexing import process_search_index_job
from open_work_hub_api.domains.search.models import SearchIndexJob


pytestmark = pytest.mark.external_integration("opensearch")


class _IntegrationInfra(Protocol):
    opensearch_url: str

    def new_opensearch_index_prefix(self) -> str: ...

    def cleanup_opensearch_indices(self, prefix: str) -> None: ...


@pytest.fixture
def search_client(
    monkeypatch: pytest.MonkeyPatch,
    application_postgres_dsn: str,
    integration_infra: _IntegrationInfra,
) -> Iterator[TestClient]:
    index_prefix = integration_infra.new_opensearch_index_prefix()
    monkeypatch.setenv("OPEN_WORK_HUB_OPENSEARCH_URL", integration_infra.opensearch_url)
    monkeypatch.setenv("OPEN_WORK_HUB_OPENSEARCH_INDEX_PREFIX", index_prefix)
    try:
        test_client = _build_client(
            monkeypatch,
            postgres_dsn=application_postgres_dsn,
        )
        with test_client:
            yield test_client
    finally:
        try:
            _teardown_client_state()
        finally:
            integration_infra.cleanup_opensearch_indices(index_prefix)


def _dev_login(client: TestClient, account_key: str = "delivery-hub-member") -> dict:
    return dev_login(client, account_key)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_id(key: str) -> str:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
        workspace = db.scalar(select(Workspace).where(Workspace.key == key))
        assert workspace is not None
        return workspace.id


def _process_pending_search_jobs() -> None:
    while True:
        with get_session_factory()() as db:
            job_ids = list(
                db.scalars(
                    select(SearchIndexJob.id)
                    .where(SearchIndexJob.status == "pending")
                    .order_by(SearchIndexJob.created_at.asc(), SearchIndexJob.id.asc())
                )
            )
        if not job_ids:
            return
        for job_id in job_ids:
            with get_session_factory()() as db:
                process_search_index_job(db, job_id)


def _search(
    client: TestClient,
    *,
    token: str,
    workspace_key: str,
    workspace_id: str,
    query: str,
    entity_types: list[str],
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_key}/search/query",
        headers=_headers(token),
        json={
            "workspace_id": workspace_id,
            "query": query,
            "entity_types": entity_types,
            "sort": {"field": "relevance", "direction": "desc"},
            "limit": 20,
            "offset": 0,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _hit_ids(payload: dict) -> set[str]:
    return {hit["entity_id"] for hit in payload["hits"]}


def _create_sentinel_doc(client: TestClient, *, token: str, workspace_key: str, title: str) -> None:
    response = client.post(
        f"/api/v1/workspaces/{workspace_key}/docs/items",
        headers=_headers(token),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    _process_pending_search_jobs()


def _create_pms_space(client: TestClient, *, token: str, workspace_key: str, name: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_key}/pms/spaces",
        headers=_headers(token),
        json={"name": name, "description": ""},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_pms_task_list(
    client: TestClient,
    *,
    token: str,
    workspace_key: str,
    team_id: str,
    key: str,
    name: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_key}/pms/lists",
        headers=_headers(token),
        json={"key": key, "name": name, "description": "", "team_id": team_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_pms_task(
    client: TestClient,
    *,
    token: str,
    workspace_key: str,
    list_id: str,
    title: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_key}/pms/lists/{list_id}/tasks",
        headers=_headers(token),
        json={
            "title": title,
            "description": "E2E issue body",
            "status": "todo",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_keyword_search_returns_contract_facets_snippets_and_deep_links(
    search_client: TestClient,
) -> None:
    session = _dev_login(search_client)
    token = session["token"]
    user_id = session["user"]["id"]
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        workspace_id = workspace.id
        doc, page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user_id,
            title="예산 리스크 검토",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "공급사 단가 변경으로 예산 리스크가 증가했습니다."}
                    ],
                }
            ],
        )
        expected_deep_link = f"/w/delivery-hub/docs/{doc.id}?page={page.id}"
        db.commit()
    _process_pending_search_jobs()

    response = search_client.post(
        "/api/v1/workspaces/delivery-hub/search/query",
        headers=_headers(token),
        json={
            "workspace_id": workspace_id,
            "query": "예산 리스크",
            "entity_types": ["doc"],
            "sort": {"field": "relevance", "direction": "desc"},
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["has_more"] is False
    assert payload["facets"]["entity_types"][0]["value"] == "doc"
    hit = payload["hits"][0]
    assert hit["entity_type"] == "doc"
    assert hit["deep_link"] == expected_deep_link
    assert hit["snippet"]["text"]
    assert "highlights" in hit["snippet"]


def test_keyword_search_filters_private_docs_by_acl(search_client: TestClient) -> None:
    owner_session = _dev_login(search_client, "administrator")
    viewer_session = create_workspace_user_session(
        search_client,
        workspace_key="administrator",
        login_id="searchviewer",
        email="search-viewer@open-work-hub.local",
        full_name="Search Viewer",
    )
    owner_token = owner_session["token"]
    viewer_token = viewer_session["token"]
    owner_id = owner_session["user"]["id"]
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "administrator"))
        assert workspace is not None
        workspace_id = workspace.id
        docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner_id,
            title="비공개 강아지 메모",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "우리집 강아지는 복슬강아지"}],
                }
            ],
        )
        db.commit()
    _process_pending_search_jobs()

    payload = {
        "workspace_id": workspace_id,
        "query": "복슬",
        "entity_types": ["doc"],
        "sort": {"field": "relevance", "direction": "desc"},
        "limit": 20,
        "offset": 0,
    }
    owner_response = search_client.post(
        "/api/v1/workspaces/administrator/search/query",
        headers=_headers(owner_token),
        json=payload,
    )
    viewer_response = search_client.post(
        "/api/v1/workspaces/administrator/search/query",
        headers=_headers(viewer_token),
        json=payload,
    )

    assert owner_response.status_code == 200, owner_response.text
    assert viewer_response.status_code == 200, viewer_response.text
    owner_payload = owner_response.json()
    viewer_payload = viewer_response.json()
    assert any(hit["title"] == "비공개 강아지 메모" for hit in owner_payload["hits"])
    assert all(hit["title"] != "비공개 강아지 메모" for hit in viewer_payload["hits"])
    assert viewer_payload["total"] == 0
    assert viewer_payload["facets"] == {"entity_types": [], "status": [], "targets": []}


def test_keyword_search_doc_acl_grant_revoke_and_crud_updates_index(
    search_client: TestClient,
) -> None:
    workspace_key = "delivery-hub"
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
    workspace_id = _workspace_id(workspace_key)
    suffix = uuid.uuid4().hex[:8]
    original_title = f"ACL 문서 검색 원본 {suffix}"
    updated_title = f"ACL 문서 검색 수정 {suffix}"
    sentinel_title = f"ACL 문서 검색 센티널 {suffix}"

    _create_sentinel_doc(
        search_client,
        token=admin["token"],
        workspace_key=workspace_key,
        title=sentinel_title,
    )

    create_response = search_client.post(
        f"/api/v1/workspaces/{workspace_key}/docs/items",
        headers=_headers(admin["token"]),
        json={"title": original_title, "first_page_title": f"ACL 문서 페이지 {suffix}"},
    )
    assert create_response.status_code == 201, create_response.text
    doc = create_response.json()
    _process_pending_search_jobs()

    assert doc["id"] in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=original_title,
            entity_types=["doc"],
        )
    )
    assert doc["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=original_title,
            entity_types=["doc"],
        )
    )

    share_response = search_client.put(
        f"/api/v1/workspaces/{workspace_key}/docs/items/{doc['id']}/sharing/users/{member['user']['id']}",
        headers=_headers(admin["token"]),
        json={"access_level": "read"},
    )
    assert share_response.status_code == 200, share_response.text
    _process_pending_search_jobs()
    assert doc["id"] in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=original_title,
            entity_types=["doc"],
        )
    )

    revoke_response = search_client.delete(
        f"/api/v1/workspaces/{workspace_key}/docs/items/{doc['id']}/sharing/users/{member['user']['id']}",
        headers=_headers(admin["token"]),
    )
    assert revoke_response.status_code == 200, revoke_response.text
    _process_pending_search_jobs()
    assert doc["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=original_title,
            entity_types=["doc"],
        )
    )

    update_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/docs/items/{doc['id']}",
        headers=_headers(admin["token"]),
        json={"title": updated_title},
    )
    assert update_response.status_code == 200, update_response.text
    _process_pending_search_jobs()
    assert doc["id"] in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=updated_title,
            entity_types=["doc"],
        )
    )
    assert doc["id"] not in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=original_title,
            entity_types=["doc"],
        )
    )

    delete_response = search_client.delete(
        f"/api/v1/workspaces/{workspace_key}/docs/items/{doc['id']}",
        headers=_headers(admin["token"]),
    )
    assert delete_response.status_code == 204, delete_response.text
    _process_pending_search_jobs()
    assert doc["id"] not in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=updated_title,
            entity_types=["doc"],
        )
    )


def test_keyword_search_meeting_attendee_acl_add_remove_updates_index(
    search_client: TestClient,
) -> None:
    workspace_key = "delivery-hub"
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
    workspace_id = _workspace_id(workspace_key)
    title = f"ACL 회의 검색 {uuid.uuid4().hex[:8]}"

    create_response = search_client.post(
        f"/api/v1/workspaces/{workspace_key}/meeting/meetings",
        headers=_headers(admin["token"]),
        json={
            "title": title,
            "agenda": "Meeting ACL search body",
            "start_at": "2026-05-04T01:00:00",
            "end_at": "2026-05-04T02:00:00",
            "attendees": [],
            "task_ids": [],
            "doc_ids": [],
        },
    )
    assert create_response.status_code == 201, create_response.text
    meeting = create_response.json()
    _process_pending_search_jobs()

    assert meeting["id"] in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["meeting"],
        )
    )
    assert meeting["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["meeting"],
        )
    )

    add_response = search_client.post(
        f"/api/v1/workspaces/{workspace_key}/meeting/meetings/{meeting['id']}/attendees",
        headers=_headers(admin["token"]),
        json={"attendees": [{"user_id": member["user"]["id"], "role": "required"}]},
    )
    assert add_response.status_code == 200, add_response.text
    _process_pending_search_jobs()
    assert meeting["id"] in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["meeting"],
        )
    )

    remove_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/meeting/meetings/{meeting['id']}",
        headers=_headers(admin["token"]),
        json={"attendees": []},
    )
    assert remove_response.status_code == 200, remove_response.text
    _process_pending_search_jobs()
    assert meeting["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["meeting"],
        )
    )


def test_keyword_search_pms_task_grant_revoke_and_archive_restore_updates_index(
    search_client: TestClient,
) -> None:
    workspace_key = "delivery-hub"
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
    workspace_id = _workspace_id(workspace_key)
    suffix = uuid.uuid4().hex[:8]
    title = f"ACL PMS 검색 원본 {suffix}"
    updated_title = f"ACL PMS 검색 수정 {suffix}"

    _create_sentinel_doc(
        search_client,
        token=admin["token"],
        workspace_key=workspace_key,
        title=f"ACL PMS 센티널 {suffix}",
    )
    space = _create_pms_space(
        search_client,
        token=admin["token"],
        workspace_key=workspace_key,
        name=f"Search ACL Space {suffix}",
    )
    task_list = _create_pms_task_list(
        search_client,
        token=admin["token"],
        workspace_key=workspace_key,
        team_id=space["id"],
        key=f"S{suffix[:5]}",
        name=f"Search ACL List {suffix}",
    )
    issue = _create_pms_task(
        search_client,
        token=admin["token"],
        workspace_key=workspace_key,
        list_id=task_list["id"],
        title=title,
    )
    _process_pending_search_jobs()

    assert issue["id"] in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["pms_task"],
        )
    )
    assert issue["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["pms_task"],
        )
    )

    with get_session_factory()() as db:
        grant_task_access(
            db,
            task_id=issue["id"],
            user_id=member["user"]["id"],
            granted_by_user_id=admin["user"]["id"],
            granted_by_meeting_id=None,
            reason="manual_share",
        )
        db.commit()
    _process_pending_search_jobs()
    assert issue["id"] in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["pms_task"],
        )
    )

    with get_session_factory()() as db:
        assert (
            revoke_task_access(
                db,
                task_id=issue["id"],
                user_id=member["user"]["id"],
                revoked_by_user_id=admin["user"]["id"],
                reason="manual_revoke",
            )
            == 1
        )
        db.commit()
    _process_pending_search_jobs()
    assert issue["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["pms_task"],
        )
    )

    update_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/tasks/{issue['id']}",
        headers=_headers(admin["token"]),
        json={"title": updated_title},
    )
    assert update_response.status_code == 200, update_response.text
    _process_pending_search_jobs()
    assert issue["id"] in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=updated_title,
            entity_types=["pms_task"],
        )
    )
    assert issue["id"] not in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["pms_task"],
        )
    )

    archive_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/tasks/{issue['id']}",
        headers=_headers(admin["token"]),
        json={"archived": True},
    )
    assert archive_response.status_code == 200, archive_response.text
    _process_pending_search_jobs()
    assert issue["id"] not in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=updated_title,
            entity_types=["pms_task"],
        )
    )

    restore_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/lists/{task_list['id']}/tasks/bulk",
        headers=_headers(admin["token"]),
        json={"task_ids": [issue["id"]], "archived": False},
    )
    assert restore_response.status_code == 200, restore_response.text
    _process_pending_search_jobs()
    assert issue["id"] in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=updated_title,
            entity_types=["pms_task"],
        )
    )

    archive_list_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/lists/{task_list['id']}",
        headers=_headers(admin["token"]),
        json={"archived": True},
    )
    assert archive_list_response.status_code == 200, archive_list_response.text
    _process_pending_search_jobs()
    assert issue["id"] not in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=updated_title,
            entity_types=["pms_task"],
        )
    )

    restore_list_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/lists/{task_list['id']}",
        headers=_headers(admin["token"]),
        json={"archived": False},
    )
    assert restore_list_response.status_code == 200, restore_list_response.text
    _process_pending_search_jobs()
    assert issue["id"] in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=updated_title,
            entity_types=["pms_task"],
        )
    )


def test_keyword_search_excludes_personal_planner_events(search_client: TestClient) -> None:
    workspace_key = "delivery-hub"
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
    workspace_id = _workspace_id(workspace_key)
    title = f"ACL 플래너 검색 {uuid.uuid4().hex[:8]}"
    _create_sentinel_doc(
        search_client,
        token=admin["token"],
        workspace_key=workspace_key,
        title=f"Planner search index sentinel {uuid.uuid4().hex[:8]}",
    )

    create_response = search_client.post(
        "/api/v1/planner/events",
        headers=_headers(admin["token"]),
        json={
            "title": title,
            "description": "Planner ACL search body",
            "location": "Seoul",
            "allDay": False,
            "start": "2026-05-04T01:00:00+00:00",
            "end": "2026-05-04T02:00:00+00:00",
        },
    )
    assert create_response.status_code == 201, create_response.text
    event = create_response.json()
    _process_pending_search_jobs()

    assert event["id"] not in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["planner_event"],
        )
    )
    assert event["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["planner_event"],
        )
    )
