from __future__ import annotations

import subprocess
import time
import uuid

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from conftest import _build_client, _ensure_docker_image, _find_free_port, _teardown_client_state
from aidoo_api.core.db import get_session_factory
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data
from aidoo_api.domains.auth.models import Workspace
from aidoo_api.domains.docs import service as docs_service


OPENSEARCH_IMAGE = "opensearchproject/opensearch:3.3.2"


@pytest.fixture(scope="session")
def opensearch_url() -> str:
    _ensure_docker_image(OPENSEARCH_IMAGE)
    port = _find_free_port()
    container_name = f"aidoo-opensearch-test-{uuid.uuid4().hex[:10]}"
    url = f"http://127.0.0.1:{port}"
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            container_name,
            "-e",
            "discovery.type=single-node",
            "-e",
            "DISABLE_SECURITY_PLUGIN=true",
            "-e",
            "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m",
            "-p",
            f"{port}:9200",
            OPENSEARCH_IMAGE,
        ],
        check=True,
    )
    try:
        _wait_for_opensearch(url)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], check=False)


@pytest.fixture
def search_client(
    monkeypatch: pytest.MonkeyPatch,
    postgres_dsn: str,
    redis_url: str,
    opensearch_url: str,
) -> TestClient:
    monkeypatch.setenv("DOOWON_OPENSEARCH_URL", opensearch_url)
    monkeypatch.setenv("DOOWON_OPENSEARCH_INDEX_PREFIX", f"aidoo_test_{uuid.uuid4().hex[:10]}")
    test_client = _build_client(monkeypatch, postgres_dsn=postgres_dsn, collab_redis_url=redis_url)
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
