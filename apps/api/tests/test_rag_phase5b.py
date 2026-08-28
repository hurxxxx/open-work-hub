from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import reset_ai_capability_registry
from open_work_hub_api.domains.auth.access import ensure_dev_login_seed_data, load_user_graph
from open_work_hub_api.domains.auth.models import Workspace
from open_work_hub_api.domains.auth.workspace_apps import get_workspace_app_catalog_item
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

DELIVERY_WORKSPACE_KEY = "delivery-hub"
HQ_WORKSPACE_KEY = "hq"
TEST_USER_PASSWORD = "supersecret123"


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


def _dev_login(client: TestClient, account_key: str) -> dict:
    with get_session_factory()() as db:
        ensure_dev_login_seed_data(db)
    response = client.post("/api/v1/auth/dev-login", json={"account_key": account_key})
    assert response.status_code == 200, response.text
    return response.json()


def _create_workspace(client: TestClient, admin_token: str, *, key: str, name: str) -> dict:
    response = client.post(
        "/api/v1/admin/workspaces",
        headers=_auth_headers(admin_token),
        json={"key": key, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _provision_delivery_workspace(client: TestClient) -> tuple[dict, dict]:
    session = _dev_login(client, "administrator")
    workspace = _create_workspace(
        client,
        session["token"],
        key=DELIVERY_WORKSPACE_KEY,
        name="Delivery Hub",
    )
    return session, workspace


def _create_user_session(
    client: TestClient,
    admin_token: str,
    *,
    login_id: str,
    email: str,
    full_name: str,
    workspace_id: str | None = None,
    role: str = "member",
) -> dict:
    create_response = client.post(
        "/api/v1/admin/users",
        headers=_auth_headers(admin_token),
        json={
            "login_id": login_id,
            "email": email,
            "full_name": full_name,
            "temporary_password": TEST_USER_PASSWORD,
        },
    )
    assert create_response.status_code == 201, create_response.text
    user = create_response.json()["user"]

    if workspace_id is not None:
        member_response = client.post(
            f"/api/v1/admin/workspaces/{workspace_id}/members",
            headers=_auth_headers(admin_token),
            json={"subject_id": user["id"], "subject_type": "user", "role": role},
        )
        assert member_response.status_code == 201, member_response.text

    login_response = client.post(
        "/api/v1/auth/login",
        json={"login_id": login_id, "password": TEST_USER_PASSWORD},
    )
    assert login_response.status_code == 200, login_response.text
    return login_response.json()


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_ai_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/chatbot{suffix}"


def _disable_app(
    client: TestClient,
    *,
    admin_token: str,
    workspace_id: str,
    app_id: str,
) -> None:
    catalog_item = get_workspace_app_catalog_item(app_id)
    assert catalog_item is not None
    if catalog_item.availability_scope == "platform":
        path = "/api/v1/admin/apps/company-controls"
        payload = {"items": [{"app_id": app_id, "enabled": False}]}
    else:
        path = f"/api/v1/admin/workspaces/{workspace_id}/app-overrides"
        payload = {"items": [{"app_id": app_id, "enabled": False}]}
    response = client.patch(
        path,
        headers=_auth_headers(admin_token),
        json=payload,
    )
    assert response.status_code == 200, response.text


def _reset_settings_and_registry() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    reset_rag_runtime_caches()
    reset_ai_capability_registry()


def test_workspace_rag_query_route_filters_out_foreign_workspace_hits(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    delivery_session, _delivery_workspace_item = _provision_delivery_workspace(client)
    _create_workspace(client, delivery_session["token"], key=HQ_WORKSPACE_KEY, name="HQ")
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rerank_client = FakeRerankClient()

    with get_session_factory()() as db:
        delivery_owner = load_user_graph(db, delivery_session["user"]["id"])
        hq_owner = delivery_owner
        delivery_workspace = db.scalar(
            select(Workspace).where(Workspace.key == DELIVERY_WORKSPACE_KEY)
        )
        hq_workspace = db.scalar(select(Workspace).where(Workspace.key == HQ_WORKSPACE_KEY))
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
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/query",
        headers=_auth_headers(delivery_session["token"]),
        json={"query": "phase 5 rollout", "answer_mode": "search-only"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {hit["title"] for hit in payload["hits"]} == {"Delivery Hub Phase 5 Note"}
    assert {hit["workspace_id"] for hit in payload["hits"]} == {delivery_workspace_id}


@pytest.mark.slow
def test_workspace_rag_reindex_requires_admin(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    admin_session, workspace_item = _provision_delivery_workspace(client)
    session = _create_user_session(
        client,
        admin_session["token"],
        login_id="deliverymember",
        email="delivery-member@example.test",
        full_name="Delivery Member",
        workspace_id=workspace_item["id"],
        role="member",
    )

    response = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/reindex",
        headers=_auth_headers(session["token"]),
    )

    assert response.status_code == 403, response.text


def test_workspace_rag_reindex_enforces_cooldown(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session, _workspace_item = _provision_delivery_workspace(client)
    with get_session_factory()() as db:
        owner = load_user_graph(db, session["user"]["id"])
        workspace = db.scalar(select(Workspace).where(Workspace.key == DELIVERY_WORKSPACE_KEY))
        assert owner is not None
        assert workspace is not None
        docs_service.create_native_doc_for_user(
            db,
            workspace_id=workspace.id,
            owner_id=owner.id,
            title="Cooldown source",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "cooldown"}]}
            ],
        )
        db.commit()

    first = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/reindex",
        headers=_auth_headers(session["token"]),
    )
    second = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/reindex",
        headers=_auth_headers(session["token"]),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "rag.reindex_cooldown_recent"


@pytest.mark.slow
def test_workspace_rag_query_validates_payload(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session, _workspace_item = _provision_delivery_workspace(client)

    blank_query = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": ""},
    )
    assert blank_query.status_code == 422, blank_query.text

    invalid_top_k = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5", "top_k": 0},
    )
    assert invalid_top_k.status_code == 422, invalid_top_k.text

    invalid_metadata = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/query",
        headers={**_auth_headers(session["token"]), "Accept-Language": "ko-KR"},
        json={
            "query": "phase 5",
            "filters": {"metadata": {"workspace_id": "foreign"}},
        },
    )
    assert invalid_metadata.status_code == 422, invalid_metadata.text
    body = invalid_metadata.json()
    assert body["code"] == "rag.metadata_filter_key_reserved"
    assert body["params"]["key"] == "workspace_id"
    assert body["detail"] == "예약된 메타데이터 필터 key입니다: workspace_id"


@pytest.mark.slow
def test_workspace_rag_query_rejects_non_member(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    admin_session, _delivery_workspace_item = _provision_delivery_workspace(client)
    hq_workspace = _create_workspace(
        client,
        admin_session["token"],
        key=HQ_WORKSPACE_KEY,
        name="HQ",
    )
    session = _create_user_session(
        client,
        admin_session["token"],
        login_id="othermember",
        email="other-member@example.test",
        full_name="Other Workspace Member",
        workspace_id=hq_workspace["id"],
        role="member",
    )

    response = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5"},
    )

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "workspace.membership_required"


@pytest.mark.slow
def test_rag_ai_manifest_hides_tools_when_no_searchable_apps_enabled(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "1")
    _reset_settings_and_registry()
    session, workspace_item = _provision_delivery_workspace(client)
    for app_id in sorted(registered_searchable_rag_app_ids()):
        _disable_app(
            client,
            admin_token=session["token"],
            workspace_id=workspace_item["id"],
            app_id=app_id,
        )

    manifest_response = client.get(
        _workspace_ai_path(DELIVERY_WORKSPACE_KEY, "/apps/chatbot/manifest"),
        headers=_auth_headers(session["token"]),
    )

    assert manifest_response.status_code == 200, manifest_response.text
    manifest_tools = {item["name"] for item in manifest_response.json()["tools"]}
    assert "rag.query" not in manifest_tools

    query_response = client.post(
        f"/api/v1/workspaces/{DELIVERY_WORKSPACE_KEY}/rag/query",
        headers=_auth_headers(session["token"]),
        json={"query": "phase 5"},
    )
    assert query_response.status_code == 403, query_response.text
    assert query_response.json()["code"] == "rag.access_denied_not_enabled"
