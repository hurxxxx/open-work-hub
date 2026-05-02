from __future__ import annotations

import subprocess
import time
import uuid

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from conftest import (
    _build_client,
    _docker_command,
    _docker_network_args,
    _docker_publish_args,
    _docker_rm,
    _docker_uses_host_network,
    _ensure_docker_image,
    _find_free_port,
    _teardown_client_state,
)
from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.docs import service as docs_service
from aidoo_api.domains.pms.access_grants import grant_issue_access, revoke_issue_access
from aidoo_api.domains.search.indexing import process_search_index_job
from aidoo_api.domains.search.models import SearchIndexJob


OPENSEARCH_IMAGE = "opensearchproject/opensearch:3.3.2"


@pytest.fixture(scope="session")
def opensearch_url() -> str:
    _ensure_docker_image(OPENSEARCH_IMAGE)
    port = _find_free_port()
    transport_port = _find_free_port()
    container_name = f"aidoo-opensearch-test-{uuid.uuid4().hex[:10]}"
    url = f"http://127.0.0.1:{port}"
    subprocess.run(
        [
            *_docker_command(),
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            *_docker_network_args(),
            "-e",
            "discovery.type=single-node",
            "-e",
            "DISABLE_SECURITY_PLUGIN=true",
            "-e",
            "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m",
            *_docker_publish_args(port, 9200),
            OPENSEARCH_IMAGE,
            *(
                []
                if not _docker_uses_host_network()
                else ["opensearch", f"-Ehttp.port={port}", f"-Etransport.port={transport_port}"]
            ),
        ],
        check=True,
    )
    try:
        _wait_for_opensearch(url)
        yield url
    finally:
        _docker_rm(container_name)


@pytest.fixture
def search_client(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
    redis_url: str,
    minio_endpoint: str,
    opensearch_url: str,
) -> TestClient:
    monkeypatch.setenv("DOOWON_OPENSEARCH_URL", opensearch_url)
    monkeypatch.setenv("DOOWON_OPENSEARCH_INDEX_PREFIX", f"aidoo_test_{uuid.uuid4().hex[:10]}")
    test_client = _build_client(
        monkeypatch,
        postgres_dsn=postgres_dsn,
        collab_redis_url=redis_url,
        minio_endpoint=minio_endpoint,
    )
    with test_client:
        yield test_client
    _teardown_client_state()


def _wait_for_opensearch(url: str, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                return
        except Exception as error:  # pragma: no cover - exercised in retry loop
            last_error = error
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for OpenSearch: {last_error}")


def _dev_login(client: TestClient, account_key: str = "delivery-hub-member") -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


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


def _create_pms_issue(
    client: TestClient,
    *,
    token: str,
    workspace_key: str,
    list_id: str,
    title: str,
) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_key}/pms/lists/{list_id}/issues",
        headers=_headers(token),
        json={
            "title": title,
            "description": "E2E issue body",
            "status": "backlog",
            "priority": "medium",
            "label_ids": [],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_keyword_search_does_not_refresh_workspace_index_on_query(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from aidoo_api.domains.search import service as search_service

    session = _dev_login(client)
    token = session["token"]
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        workspace_id = workspace.id

    class _FakeSearchClient:
        def index_exists(self) -> bool:
            return True

        def count_workspace_documents(self, *, workspace_id: str) -> int:
            return 1

        def search(self, body: dict) -> dict:
            return {"hits": {"hits": []}}

    def _fail_refresh(*args, **kwargs) -> None:
        raise AssertionError("refresh_workspace_keyword_index must not be called from search query")

    monkeypatch.setattr(search_service, "_search_client", lambda: _FakeSearchClient())
    monkeypatch.setattr(search_service, "refresh_workspace_keyword_index", _fail_refresh)

    response = client.post(
        "/api/v1/workspaces/delivery-hub/search/query",
        headers=_headers(token),
        json={
            "workspace_id": workspace_id,
            "query": "anything",
            "entity_types": ["doc"],
            "sort": {"field": "relevance", "direction": "desc"},
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0


@pytest.mark.parametrize(
    ("index_exists", "workspace_count", "expected_reason"),
    [
        (False, 0, "Keyword search index is not initialized. Run keyword search backfill first."),
        (True, 0, "Keyword search index is empty for this workspace. Run keyword search backfill first."),
    ],
)
def test_keyword_search_returns_503_when_index_requires_backfill(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    index_exists: bool,
    workspace_count: int,
    expected_reason: str,
) -> None:
    from aidoo_api.domains.search import service as search_service

    session = _dev_login(client)
    token = session["token"]
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        workspace_id = workspace.id

    class _FakeSearchClient:
        def index_exists(self) -> bool:
            return index_exists

        def count_workspace_documents(self, *, workspace_id: str) -> int:
            return workspace_count

        def search(self, body: dict) -> dict:
            raise AssertionError("search must not run when keyword index is not ready")

    monkeypatch.setattr(search_service, "_search_client", lambda: _FakeSearchClient())

    response = client.post(
        "/api/v1/workspaces/delivery-hub/search/query",
        headers=_headers(token),
        json={
            "workspace_id": workspace_id,
            "query": "anything",
            "entity_types": ["doc"],
            "sort": {"field": "relevance", "direction": "desc"},
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "search.keyword_backend_unavailable"
    assert body["params"]["reason"] == expected_reason
    assert expected_reason in body["detail"]


def test_keyword_search_returns_contract_facets_snippets_and_deep_links(search_client: TestClient) -> None:
    session = _dev_login(search_client)
    token = session["token"]
    user_id = session["user"]["id"]
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        workspace_id = workspace.id
        docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user_id,
            title="예산 리스크 검토",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "공급사 단가 변경으로 예산 리스크가 증가했습니다."}],
                }
            ],
        )
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
    assert hit["deep_link"].startswith("/w/delivery-hub/docs/")
    assert hit["snippet"]["text"]
    assert "highlights" in hit["snippet"]


def test_keyword_search_matches_korean_substring_in_doc_body(search_client: TestClient) -> None:
    session = _dev_login(search_client)
    token = session["token"]
    user_id = session["user"]["id"]
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert workspace is not None
        workspace_id = workspace.id
        docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=user_id,
            title="강아지 기록",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "우리집 강아지는 복슬강아지"}],
                }
            ],
        )
        db.commit()
    _process_pending_search_jobs()

    response = search_client.post(
        "/api/v1/workspaces/delivery-hub/search/query",
        headers=_headers(token),
        json={
            "workspace_id": workspace_id,
            "query": "복슬",
            "entity_types": ["doc"],
            "sort": {"field": "relevance", "direction": "desc"},
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 1
    assert any(hit["title"] == "강아지 기록" for hit in payload["hits"])
    target = next(hit for hit in payload["hits"] if hit["title"] == "강아지 기록")
    assert "복슬강아지" in target["snippet"]["text"]
    assert target["snippet"]["highlights"]


def test_keyword_search_filters_private_docs_by_acl(search_client: TestClient) -> None:
    owner_session = _dev_login(search_client, "hq-admin")
    viewer_session = _dev_login(search_client, "hq-member")
    owner_token = owner_session["token"]
    viewer_token = viewer_session["token"]
    owner_id = owner_session["user"]["id"]
    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "hq"))
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
        "/api/v1/workspaces/hq/search/query",
        headers=_headers(owner_token),
        json=payload,
    )
    viewer_response = search_client.post(
        "/api/v1/workspaces/hq/search/query",
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
    assert viewer_payload["facets"] == {"entity_types": [], "status": [], "containers": []}


def test_keyword_search_doc_acl_grant_revoke_and_crud_updates_index(search_client: TestClient) -> None:
    workspace_key = "delivery-hub"
    workspace_id = _workspace_id(workspace_key)
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
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


def test_keyword_search_meeting_attendee_acl_add_remove_updates_index(search_client: TestClient) -> None:
    workspace_key = "delivery-hub"
    workspace_id = _workspace_id(workspace_key)
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
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


def test_keyword_search_pms_issue_grant_revoke_and_archive_restore_updates_index(search_client: TestClient) -> None:
    workspace_key = "delivery-hub"
    workspace_id = _workspace_id(workspace_key)
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
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
    issue = _create_pms_issue(
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
            entity_types=["pms_issue"],
        )
    )
    assert issue["id"] not in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["pms_issue"],
        )
    )

    with get_session_factory()() as db:
        grant_issue_access(
            db,
            issue_id=issue["id"],
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
            entity_types=["pms_issue"],
        )
    )

    with get_session_factory()() as db:
        assert (
            revoke_issue_access(
                db,
                issue_id=issue["id"],
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
            entity_types=["pms_issue"],
        )
    )

    update_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/issues/{issue['id']}",
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
            entity_types=["pms_issue"],
        )
    )
    assert issue["id"] not in _hit_ids(
        _search(
            search_client,
            token=admin["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["pms_issue"],
        )
    )

    archive_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/issues/{issue['id']}",
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
            entity_types=["pms_issue"],
        )
    )

    restore_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/pms/lists/{task_list['id']}/issues/bulk",
        headers=_headers(admin["token"]),
        json={"issue_ids": [issue["id"]], "archived": False},
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
            entity_types=["pms_issue"],
        )
    )


def test_keyword_search_planner_visibility_public_private_updates_index(search_client: TestClient) -> None:
    workspace_key = "delivery-hub"
    workspace_id = _workspace_id(workspace_key)
    admin = _dev_login(search_client, "delivery-hub-admin")
    member = _dev_login(search_client, "delivery-hub-member")
    title = f"ACL 플래너 검색 {uuid.uuid4().hex[:8]}"

    create_response = search_client.post(
        f"/api/v1/workspaces/{workspace_key}/planner/events",
        headers=_headers(admin["token"]),
        json={
            "title": title,
            "description": "Planner ACL search body",
            "location": "Seoul",
            "visibility": "private",
            "allDay": False,
            "start": "2026-05-04T01:00:00+00:00",
            "end": "2026-05-04T02:00:00+00:00",
        },
    )
    assert create_response.status_code == 201, create_response.text
    event = create_response.json()
    _process_pending_search_jobs()

    assert event["id"] in _hit_ids(
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

    public_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/planner/events/{event['id']}",
        headers=_headers(admin["token"]),
        json={"visibility": "public"},
    )
    assert public_response.status_code == 200, public_response.text
    _process_pending_search_jobs()
    assert event["id"] in _hit_ids(
        _search(
            search_client,
            token=member["token"],
            workspace_key=workspace_key,
            workspace_id=workspace_id,
            query=title,
            entity_types=["planner_event"],
        )
    )

    private_response = search_client.patch(
        f"/api/v1/workspaces/{workspace_key}/planner/events/{event['id']}",
        headers=_headers(admin["token"]),
        json={"visibility": "private"},
    )
    assert private_response.status_code == 200, private_response.text
    _process_pending_search_jobs()
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
