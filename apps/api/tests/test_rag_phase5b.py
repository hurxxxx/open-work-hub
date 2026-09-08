from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from dev_accounts import dev_login, create_company_user_session, auth_headers
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import reset_ai_capability_registry
from open_work_hub_api.domains.auth.access import load_user_graph
from open_work_hub_api.domains.docs import service as docs_service
from open_work_hub_api.domains.rag import application as rag_application
from open_work_hub_api.domains.rag.default_source_adapters import registered_searchable_rag_app_ids
from open_work_hub_api.domains.rag.docs_projection import load_native_doc_projection
import open_work_hub_api.domains.rag.outbox as rag_outbox
from open_work_hub_api.domains.rag.providers.fake import (
    FakeEmbeddingClient,
    FakeRerankClient,
    FakeVectorIndexClient,
)
from open_work_hub_api.domains.rag.query_service import RagQueryService
from open_work_hub_api.domains.rag.runtime import (
    reset_rag_runtime_caches,
    resolve_default_collection_name,
)
from open_work_hub_api.domains.rag.service import RagService


@pytest.fixture(autouse=True)
def _stub_rag_job_publish(monkeypatch) -> None:
    class _FakeSignature:
        def apply_async(self, *, queue: str, retry: bool) -> None:
            del queue, retry

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            del task_name, args, immutable
            return _FakeSignature()

    monkeypatch.setattr(rag_outbox, "get_celery_client", lambda: _FakeCeleryClient())


def _create_user_session(client, admin_token, *, login_id, email, full_name, role="member"):
    return create_company_user_session(client, login_id=login_id, email=email, full_name=full_name)


def _auth_headers(token: str) -> dict[str, str]:
    return auth_headers(token)


def _disable_app(client, *, admin_token, app_id):
    response = client.patch(
        "/api/v1/admin/apps/company-controls",
        headers=auth_headers(admin_token),
        json={"items": [{"app_id": app_id, "enabled": False}]},
    )
    assert response.status_code == 200, response.text


def _reset_settings_and_registry() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    reset_rag_runtime_caches()
    reset_ai_capability_registry()


def test_rag_query_hides_other_users_personal_docs_even_from_platform_admin(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    delivery_session = dev_login(client, "administrator")
    other_session = create_company_user_session(
        client, login_id="other-owner", email="other-owner@example.test", full_name="Other Owner"
    )
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rerank_client = FakeRerankClient()

    with get_session_factory()() as db:
        delivery_owner = load_user_graph(db, delivery_session["user"]["id"])
        hq_owner = load_user_graph(db, other_session["user"]["id"])
        assert delivery_owner is not None and hq_owner is not None

        delivery_doc, _ = docs_service.create_native_doc_for_user(
            db,
            owner_id=delivery_owner.id,
            title="Delivery Hub Phase 5 Note",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Phase 5 rollout note for delivery hub."}],
                }
            ],
        )
        hq_doc, _ = docs_service.create_native_doc_for_user(
            db,
            owner_id=hq_owner.id,
            title="HQ Phase 5 Note",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Phase 5 rollout note for HQ only."}],
                }
            ],
        )
        db.commit()

        rag_service = RagService(
            vector_index=vector_index,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            default_collection=resolve_default_collection_name(get_settings()),
        )
        for doc_id in (delivery_doc.id, hq_doc.id):
            projection = load_native_doc_projection(db, doc_id=doc_id)
            assert projection is not None
            rag_service.sync_projection(projection)

    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        rerank_client=rerank_client,
    )
    monkeypatch.setattr(rag_application, "get_rag_query_service", lambda: query_service)

    response = client.post(
        "/api/v1/rag/query",
        headers=_auth_headers(delivery_session["token"]),
        json={"query": "phase 5 rollout", "answer_mode": "search-only"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {hit["title"] for hit in payload["hits"]} == {"Delivery Hub Phase 5 Note"}
    assert all("workspace_id" not in hit for hit in payload["hits"])


@pytest.mark.slow
def test_company_rag_reindex_requires_admin(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    admin_session = dev_login(client, "administrator")
    session = _create_user_session(
        client,
        admin_session["token"],
        login_id="deliverymember",
        email="delivery-member@example.test",
        full_name="Delivery Member",
        role="member",
    )

    response = client.post(
        "/api/v1/rag/reindex",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 403, response.text


def test_company_rag_reindex_enforces_cooldown(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = dev_login(client, "administrator")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        assert owner is not None
        docs_service.create_native_doc_for_user(
            db,
            owner_id=owner.id,
            title="Cooldown source",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "cooldown"}]}
            ],
        )
        db.commit()

    first = client.post(
        "/api/v1/rag/reindex",
        headers=_auth_headers(session["token"]),
    )
    second = client.post(
        "/api/v1/rag/reindex",
        headers=_auth_headers(session["token"]),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "rag.reindex_cooldown_recent"


@pytest.mark.slow
def test_company_rag_query_validates_payload(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = dev_login(client, "administrator")

    blank_query = client.post(
        "/api/v1/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": ""},
    )
    assert blank_query.status_code == 422, blank_query.text

    invalid_top_k = client.post(
        "/api/v1/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5", "top_k": 0},
    )
    assert invalid_top_k.status_code == 422, invalid_top_k.text

    invalid_metadata = client.post(
        "/api/v1/rag/query",
        headers={**_auth_headers(session["token"]), "Accept-Language": "ko-KR"},
        json={
            "query": "phase 5",
            "filters": {"metadata": {"resource_id": "forged-doc"}},
        },
    )
    assert invalid_metadata.status_code == 422, invalid_metadata.text
    body = invalid_metadata.json()
    assert body["code"] == "rag.metadata_filter_key_reserved"
    assert body["params"]["key"] == "resource_id"
    assert body["detail"] == "예약된 메타데이터 필터 key입니다: resource_id"


@pytest.mark.slow
def test_rag_query_rejects_user_without_admitted_sources(client, monkeypatch):
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    dev_login(client, "administrator")
    session = create_company_user_session(
        client,
        login_id="unadmitted-reader",
        email="unadmitted-reader@example.test",
        full_name="Unadmitted Reader",
    )
    with get_session_factory().begin() as db:
        for app_id in registered_searchable_rag_app_ids():
            policy = db.get(AppAccessPolicy, app_id)
            assert policy is not None
            policy.audience = "selected"
    response = client.post(
        "/api/v1/rag/query", headers=auth_headers(session["token"]), json={"query": "phase 5"}
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "rag.access_denied_not_enabled"


@pytest.mark.slow
def test_rag_ai_manifest_hides_tools_when_no_searchable_apps_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = dev_login(client, "administrator")
    for app_id in sorted(registered_searchable_rag_app_ids()):
        _disable_app(
            client,
            admin_token=session["token"],
            app_id=app_id,
        )

    manifest_response = client.get(
        "/api/v1/chatbot/apps/chatbot/manifest",
        headers=_auth_headers(session["token"]),
    )

    assert manifest_response.status_code == 200, manifest_response.text
    manifest_tools = {item["name"] for item in manifest_response.json()["tools"]}
    assert "rag.query" not in manifest_tools

    query_response = client.post(
        "/api/v1/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5"},
    )
    assert query_response.status_code == 403, query_response.text
    assert query_response.json()["code"] == "rag.access_denied_not_enabled"
