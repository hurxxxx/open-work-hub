from pathlib import Path

from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    database_path = tmp_path / "aidoo-test.sqlite3"
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", f"sqlite+pysqlite:///{database_path}")
    monkeypatch.setenv("DOOWON_API_SESSION_TTL_HOURS", "1")

    from aidoo_api.core.db import get_engine, get_session_factory
    from aidoo_api.core.settings import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    from aidoo_api.app import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    get_engine().dispose()
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_auth_bootstrap_and_protected_search(client: TestClient) -> None:
    status_response = client.get("/api/v1/auth/bootstrap-status")
    assert status_response.status_code == 200
    assert status_response.json() == {"requires_setup": True}

    unauthenticated = client.post(
        "/api/v1/search/documents",
        json={"query": "compressor specification"},
    )
    assert unauthenticated.status_code == 401

    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    assert setup_response.status_code == 201
    auth_payload = setup_response.json()
    assert auth_payload["user"]["is_admin"] is True
    token = auth_payload["token"]

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "admin@aidoo.local"

    search_response = client.post(
        "/api/v1/search/documents",
        headers={"Authorization": f"Bearer {token}"},
        json={"query": "compressor specification"},
    )
    assert search_response.status_code == 200
    payload = search_response.json()
    assert payload["scenario_id"] == "documents-rag"
    assert payload["hits"]

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 204

    expired_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert expired_response.status_code == 401


def test_documents_search_filters_and_grounded_answer(client: TestClient) -> None:
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "AIDOO Admin",
            "email": "admin@aidoo.local",
            "password": "supersecret123",
        },
    )
    token = setup_response.json()["token"]

    response = client.post(
        "/api/v1/search/documents",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "query": "seal material change notice",
            "filters": {
                "doc_type": ["revision-note"],
                "project": ["Project A"],
                "department": ["Engineering"],
            },
            "answer_mode": "grounded-answer",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filters_applied"]["doc_type"] == ["revision-note"]
    assert payload["hits"][0]["document_id"] == "doc-revision-002"
    assert payload["grounded_answer"]["citations"]
    assert payload["grounded_answer"]["citations"][0]["page_reference"] == "pp. 2-3"
