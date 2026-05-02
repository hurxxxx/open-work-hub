from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_engine, get_session_factory
from aidoo_api.core.principal import user_principal
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.registry import reset_ai_capability_registry
from aidoo_api.domains.ai.router import _resolve_agent_tool_specs
from aidoo_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from aidoo_api.domains.auth.models import Workspace, WorkspaceAppEntitlement
from aidoo_api.domains.docs import service as docs_service
from aidoo_api.domains.rag import application as rag_application
from aidoo_api.domains.rag.contracts import RagGroundedAnswer, RagGroundedCitation
from aidoo_api.domains.rag.docs_projection import load_native_doc_projection
from aidoo_api.domains.rag.models import RagSyncJob
import aidoo_api.domains.rag.outbox as rag_outbox
from aidoo_api.domains.rag.providers.fake import (
    FakeEmbeddingClient,
    FakeRerankClient,
    FakeVectorIndexClient,
)
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.runtime import (
    reset_rag_runtime_caches,
    resolve_default_collection_name,
)
from aidoo_api.domains.rag.service import RagService


@pytest.fixture(autouse=True)
def _stub_rag_job_publish(monkeypatch) -> None:
    class _FakeSignature:
        def apply_async(self, *, queue: str, retry: bool) -> None:
            del queue, retry

    class _FakeCeleryClient:
        def signature(self, task_name: str, args: list[str], immutable: bool):
            del task_name, args, immutable
            return _FakeSignature()

    monkeypatch.setattr(rag_outbox, "_get_celery_client", lambda: _FakeCeleryClient())


@pytest.fixture(autouse=True)
def _stub_grounded_answer(monkeypatch) -> None:
    def _fake_synthesize(self, *, query: str, hits, timeout_ms: int | None = None):
        del self, query, timeout_ms
        if not hits:
            return None
        lead_hit = hits[0]
        return RagGroundedAnswer(
            text=lead_hit.summary or lead_hit.title or lead_hit.resource_id,
            citations=[
                RagGroundedCitation(
                    resource_id=lead_hit.resource_id,
                    source_kind=lead_hit.source_kind,
                    quote=lead_hit.summary or lead_hit.title or lead_hit.resource_id,
                    locator=lead_hit.citation,
                )
            ],
            unsupported_claims=[],
            sources_used=[lead_hit.source_kind],
        )

    monkeypatch.setattr(
        "aidoo_api.domains.rag.grounded_answer.LlmGroundedAnswerSynthesizer.synthesize",
        _fake_synthesize,
    )


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_ai_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/ai{suffix}"


def _workspace_tool_path(workspace_slug: str, tool_name: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/ai/tools/{tool_name}/invoke"


def _disable_workspace_app(workspace_slug: str, app_id: str) -> None:
    with Session(get_engine()) as session:
        workspace = session.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert workspace is not None
        entitlement = session.scalar(
            select(WorkspaceAppEntitlement).where(
                WorkspaceAppEntitlement.workspace_id == workspace.id,
                WorkspaceAppEntitlement.app_id == app_id,
            )
        )
        assert entitlement is not None
        entitlement.enabled = False
        session.add(entitlement)
        session.commit()


def _reset_settings_and_registry() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    reset_rag_runtime_caches()
    reset_ai_capability_registry()


def _seed_fake_query_service(client: TestClient, account_key: str) -> tuple[dict, RagQueryService]:
    session = _dev_login(client, account_key)
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rerank_client = FakeRerankClient()
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert workspace is not None
        doc, _page = docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner.id,
            title="Phase 5 Search Notes",
            content_blocks=[
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "DeepInfra embedding plus Qdrant collection bootstrap.",
                        }
                    ],
                }
            ],
        )
        db.commit()
        projection = load_native_doc_projection(db, doc_id=doc.id)
        assert projection is not None
        rag_service = RagService(
            vector_index=vector_index,
            embedding_client=embedding_client,
            rerank_client=rerank_client,
            default_collection=resolve_default_collection_name(get_settings()),
        )
        rag_service.sync_projection(projection)
    return session, RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        rerank_client=rerank_client,
    )


def test_workspace_rag_query_route_returns_indexed_hits(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session, query_service = _seed_fake_query_service(client, "delivery-hub-admin")
    monkeypatch.setattr(
        rag_application,
        "get_rag_query_service",
        lambda: query_service,
    )

    response = client.post(
        "/api/v1/workspaces/delivery-hub/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "deepinfra qdrant bootstrap", "answer_mode": "grounded-answer"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["hits"]
    assert payload["hits"][0]["title"] == "Phase 5 Search Notes"
    assert payload["grounded_answer"] is not None


def test_workspace_rag_query_route_filters_out_foreign_workspace_hits(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    delivery_session = _dev_login(client, "delivery-hub-admin")
    hq_session = _dev_login(client, "hq-admin")
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rerank_client = FakeRerankClient()

    with get_session_factory()() as db:
        delivery_owner = load_user_graph(db, delivery_session["user"]["id"])
        hq_owner = load_user_graph(db, hq_session["user"]["id"])
        delivery_workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        hq_workspace = db.scalar(select(Workspace).where(Workspace.key == "hq"))
        assert delivery_owner is not None
        assert hq_owner is not None
        assert delivery_workspace is not None
        assert hq_workspace is not None

        delivery_doc, _ = docs_service.create_native_doc_for_user(
            db,
            workspace_id=delivery_workspace.id,
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
            workspace_id=hq_workspace.id,
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

        delivery_workspace_id = delivery_workspace.id

    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        rerank_client=rerank_client,
    )
    monkeypatch.setattr(rag_application, "get_rag_query_service", lambda: query_service)

    response = client.post(
        "/api/v1/workspaces/delivery-hub/rag/query",
        headers=_auth_headers(delivery_session["token"]),
        json={"query": "phase 5 rollout", "answer_mode": "search-only"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {hit["title"] for hit in payload["hits"]} == {"Delivery Hub Phase 5 Note"}
    assert {hit["workspace_id"] for hit in payload["hits"]} == {delivery_workspace_id}


def test_workspace_rag_sources_and_reindex_routes_work(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert workspace is not None
        docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner.id,
            title="Phase 5 Reindex Source",
            content_blocks=[{"type": "paragraph", "content": [{"type": "text", "text": "source"}]}],
        )
        db.commit()

    sources_response = client.get(
        "/api/v1/workspaces/delivery-hub/rag/sources",
        headers=_auth_headers(session["token"]),
    )
    assert sources_response.status_code == 200, sources_response.text
    assert "manual" in {item["source_kind"] for item in sources_response.json()["sources"]}

    reindex_response = client.post(
        "/api/v1/workspaces/delivery-hub/rag/reindex",
        headers=_auth_headers(session["token"]),
    )
    assert reindex_response.status_code == 200, reindex_response.text
    payload = reindex_response.json()
    assert payload["lane"] == "backfill"
    assert payload["queued_count"] >= 1

    with get_session_factory()() as db:
        jobs = list(
            db.scalars(
                select(RagSyncJob).where(
                    RagSyncJob.workspace_id == db.scalar(
                        select(Workspace.id).where(Workspace.key == "delivery-hub")
                    ),
                    RagSyncJob.lane == "backfill",
                )
            )
        )
    assert jobs


def test_rag_ai_manifest_and_tool_invoke_respect_feature_and_entitlements(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session, query_service = _seed_fake_query_service(client, "delivery-hub-admin")
    monkeypatch.setattr(
        rag_application,
        "get_rag_query_service",
        lambda: query_service,
    )

    manifest_response = client.get(
        _workspace_ai_path("delivery-hub", "/apps/ai/manifest"),
        headers=_auth_headers(session["token"]),
    )
    assert manifest_response.status_code == 200, manifest_response.text
    manifest_tools = {item["name"] for item in manifest_response.json()["tools"]}
    assert {"rag.query", "rag.list_sources"} <= manifest_tools

    invoke_response = client.post(
        _workspace_tool_path("delivery-hub", "rag.query"),
        headers=_auth_headers(session["token"]),
        json={"arguments": {"query": "deepinfra qdrant"}},
    )
    assert invoke_response.status_code == 200, invoke_response.text
    invoke_payload = invoke_response.json()
    assert invoke_payload["tool"] == "rag.query"
    assert invoke_payload["result"]["hits"]

    _disable_workspace_app("delivery-hub", "ai")
    manifest_response = client.get(
        _workspace_ai_path("delivery-hub", "/capabilities/manifest"),
        headers=_auth_headers(session["token"]),
    )
    assert manifest_response.status_code == 200, manifest_response.text
    manifest_tools = {item["name"] for item in manifest_response.json()["tools"]}
    assert "rag.query" not in manifest_tools


def test_workspace_rag_reindex_requires_admin(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = _dev_login(client, "delivery-hub-member")

    response = client.post(
        "/api/v1/workspaces/delivery-hub/rag/reindex",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 403, response.text


def test_agent_tool_specs_hide_rag_tools_without_search_intent(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = _dev_login(client, "delivery-hub-admin")

    with get_session_factory()() as db:
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        user = load_user_graph(db, session["user"]["id"])
        assert workspace is not None
        assert user is not None
        principal = user_principal(
            workspace_id=workspace.id,
            user_id=user.id,
            source="api.stream",
        )

        generic_specs, _ = _resolve_agent_tool_specs(
            db,
            workspace=workspace,
            principal=principal,
            messages=[{"role": "user", "content": "안녕, 오늘 해야 할 일을 짧게 정리해줘"}],
        )
        retrieval_specs, _ = _resolve_agent_tool_specs(
            db,
            workspace=workspace,
            principal=principal,
            messages=[
                {
                    "role": "user",
                    "content": "최근 회의와 PMS 이슈를 기준으로 출시 리스크를 근거와 함께 정리해줘",
                }
            ],
        )

    generic_names = {item["function"]["name"] for item in generic_specs}
    retrieval_names = {item["function"]["name"] for item in retrieval_specs}
    assert "rag.query" not in generic_names
    assert "rag.list_sources" not in generic_names
    assert {"rag.query", "rag.list_sources"} <= retrieval_names


def test_workspace_rag_reindex_enforces_cooldown(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = _dev_login(client, "delivery-hub-admin")
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == "delivery-hub"))
        assert owner is not None
        assert workspace is not None
        docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner.id,
            title="Cooldown source",
            content_blocks=[{"type": "paragraph", "content": [{"type": "text", "text": "cooldown"}]}],
        )
        db.commit()

    first = client.post(
        "/api/v1/workspaces/delivery-hub/rag/reindex",
        headers=_auth_headers(session["token"]),
    )
    second = client.post(
        "/api/v1/workspaces/delivery-hub/rag/reindex",
        headers=_auth_headers(session["token"]),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "rag.reindex_cooldown_recent"


def test_workspace_rag_query_validates_payload(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = _dev_login(client, "delivery-hub-admin")

    blank_query = client.post(
        "/api/v1/workspaces/delivery-hub/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": ""},
    )
    assert blank_query.status_code == 422, blank_query.text

    invalid_top_k = client.post(
        "/api/v1/workspaces/delivery-hub/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5", "top_k": 0},
    )
    assert invalid_top_k.status_code == 422, invalid_top_k.text


def test_workspace_rag_query_rejects_non_member(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = _dev_login(client, "hq-member")

    response = client.post(
        "/api/v1/workspaces/delivery-hub/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5"},
    )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "workspace.membership_required"


def test_rag_ai_manifest_hides_tools_when_no_searchable_apps_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AIDOO_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session = _dev_login(client, "delivery-hub-admin")
    for app_id in ("docs", "meeting", "pms", "planner"):
        _disable_workspace_app("delivery-hub", app_id)

    manifest_response = client.get(
        _workspace_ai_path("delivery-hub", "/apps/ai/manifest"),
        headers=_auth_headers(session["token"]),
    )

    assert manifest_response.status_code == 200, manifest_response.text
    manifest_tools = {item["name"] for item in manifest_response.json()["tools"]}
    assert "rag.query" not in manifest_tools

    query_response = client.post(
        "/api/v1/workspaces/delivery-hub/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5"},
    )
    assert query_response.status_code == 403, query_response.text
    assert query_response.json()["code"] == "rag.access_denied"
