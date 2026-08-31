from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from dev_accounts import dev_login

from open_work_hub_api.core.db import get_engine
from open_work_hub_api.domains.ai.registry import (
    WorkspaceEntitlementView,
    get_ai_capability_registry,
    reset_ai_capability_registry,
)
from open_work_hub_api.domains.auth.models import (
    CompanyAppControl,
    Workspace,
    WorkspaceAppOverride,
)
from open_work_hub_api.domains.auth.workspace_apps import get_workspace_app_catalog_item
from open_work_hub_api.domains.rag.contracts import (
    RagAnswerMode,
    RagQueryHit,
    RagQueryResponse,
)
from open_work_hub_api.domains.rag.default_source_adapters import registered_rag_app_ids
from open_work_hub_api.domains.rag.providers.fake import FakeRerankClient
from open_work_hub_api.domains.retrieval import application as retrieval_application
from open_work_hub_api.domains.retrieval import tools as retrieval_tools
from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalCitation,
    RetrievalGroundedAnswer,
    RetrievalHit,
    RetrievalQueryRequest,
    RetrievalStrategy,
)
from open_work_hub_api.domains.retrieval.grounding import RetrievalGroundingResult
from open_work_hub_api.domains.retrieval.source_catalog import (
    default_sources_for_strategy,
    iter_retrieval_source_catalog,
    registered_retrieval_source_app_ids,
    source_catalog_item,
)
from open_work_hub_api.domains.retrieval.tools import retrieval_discoverable_app_ids
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordSearchQuery,
    KeywordSearchResult,
)
from open_work_hub_api.domains.search.schemas import (
    KeywordSearchResponse,
    SearchFacets,
    SearchHit,
    SearchSnippet,
)


def _dev_login(client: TestClient, account_key: str) -> dict:
    return dev_login(client, account_key)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workspace_retrieval_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/retrieval{suffix}"


def _allow_final_retrieval_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        retrieval_application,
        "_filter_current_retrieval_hits",
        lambda _db, *, user, request_workspace_id, hits: list(hits),
    )


def _workspace_ai_path(workspace_slug: str, suffix: str) -> str:
    return f"/api/v1/workspaces/{workspace_slug}/chatbot{suffix}"


def _workspace_tool_path(workspace_slug: str, tool_name: str) -> str:
    return _workspace_ai_path(workspace_slug, f"/tools/{tool_name}/invoke")


def _install_in_process_keyword_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> list[KeywordSearchQuery]:
    captured_queries: list[KeywordSearchQuery] = []

    class _KeywordSearchClient:
        def index_exists(self) -> bool:
            return True

        def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
            captured_queries.append(query)
            return KeywordSearchResult(hits=())

    client = _KeywordSearchClient()
    monkeypatch.setattr(
        retrieval_application.search_service,
        "_search_client",
        lambda: client,
    )
    return captured_queries


def _disable_retrieval_discoverability_apps(workspace_slug: str) -> None:
    with Session(get_engine()) as session:
        workspace = session.scalar(select(Workspace).where(Workspace.key == workspace_slug))
        assert workspace is not None
        workspace_app_ids = {
            app_id
            for app_id in retrieval_discoverable_app_ids()
            if (catalog_item := get_workspace_app_catalog_item(app_id)) is not None
            and catalog_item.availability_scope == "workspace"
        }
        platform_app_ids = {
            app_id
            for app_id in retrieval_discoverable_app_ids()
            if (catalog_item := get_workspace_app_catalog_item(app_id)) is not None
            and catalog_item.availability_scope == "platform"
        }
        existing = {
            row.app_id: row
            for row in session.scalars(
                select(WorkspaceAppOverride).where(
                    WorkspaceAppOverride.workspace_id == workspace.id,
                    WorkspaceAppOverride.app_id.in_(workspace_app_ids),
                )
            )
        }
        for app_id in workspace_app_ids:
            row = existing.get(app_id)
            if row is None:
                row = WorkspaceAppOverride(
                    workspace_id=workspace.id,
                    app_id=app_id,
                    enabled=False,
                )
            row.enabled = False
            session.add(row)
        company_controls_by_app_id = {
            row.app_id: row
            for row in session.scalars(
                select(CompanyAppControl).where(CompanyAppControl.app_id.in_(platform_app_ids))
            )
        }
        for app_id in platform_app_ids:
            row = company_controls_by_app_id.get(app_id)
            if row is None:
                row = CompanyAppControl(app_id=app_id, enabled=False)
            else:
                row.enabled = False
            session.add(row)
        session.commit()


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pnpm-workspace.yaml").exists():
            return parent
    return current.parents[3]


def _read_source_matrix() -> dict[str, dict[str, object]]:
    matrix_path = _repo_root() / "docs" / "domains" / "rag" / "source-matrix.md"
    rows: dict[str, dict[str, object]] = {}
    for line in matrix_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        source = cells[0].strip("`")
        rows[source] = {
            "scope": cells[1],
            "backend": cells[2],
            "active": cells[3].lower() == "true",
        }
    return rows


def test_retrieval_source_catalog_exposes_active_sources() -> None:
    sources = {item.source: item for item in iter_retrieval_source_catalog()}

    assert default_sources_for_strategy(RetrievalStrategy.HYBRID) == (
        "keyword",
        "generic_rag",
    )
    assert default_sources_for_strategy(RetrievalStrategy.GRAPH_HYBRID) == (
        "keyword",
        "generic_rag",
    )
    assert sources["generic_rag"].active is True
    assert sources["keyword"].active is True
    assert source_catalog_item("missing") is None


def test_retrieval_discoverability_is_derived_from_registered_descriptors() -> None:
    assert retrieval_discoverable_app_ids() == (
        registered_retrieval_source_app_ids() | registered_rag_app_ids()
    )


def test_final_retrieval_filter_rechecks_owner_app_and_source_acl(monkeypatch) -> None:
    user = SimpleNamespace(id="user-1", status="active", login_blocked=False)
    db = SimpleNamespace(scalar=lambda _statement: user)
    enabled = {"value": True}

    class Policy:
        def authorize_many_resources(self, resources):
            return {
                resource for resource in resources if resource == ("docs_native_doc", "allowed")
            }

        def authorize_many_rag_resources(self, resources):
            return self.authorize_many_resources(resources)

    monkeypatch.setattr(
        retrieval_application,
        "get_rag_resource_adapter",
        lambda resource_type: (
            SimpleNamespace(app_id="docs") if resource_type == "docs_native_doc" else None
        ),
    )
    monkeypatch.setattr(
        retrieval_application,
        "is_app_enabled_for_user_context",
        lambda *_args, **_kwargs: enabled["value"],
    )
    monkeypatch.setattr(
        retrieval_application.SourceAclPolicy,
        "for_workspace_id",
        lambda *_args, **_kwargs: Policy(),
    )
    hits = [
        RetrievalHit(
            source="generic_rag",
            resource_type="docs_native_doc",
            resource_id=resource_id,
            workspace_id="workspace-1",
            metadata={"scope_kind": "workspace"},
        )
        for resource_id in ("allowed", "denied")
    ]
    hits.append(
        RetrievalHit(
            source="generic_rag",
            resource_type="unknown",
            resource_id="unknown",
            workspace_id="workspace-1",
            metadata={"scope_kind": "workspace"},
        )
    )

    assert [
        hit.resource_id
        for hit in retrieval_application._filter_current_retrieval_hits(
            db,
            user=user,
            request_workspace_id="workspace-1",
            hits=hits,
        )
    ] == ["allowed"]

    enabled["value"] = False
    assert (
        retrieval_application._filter_current_retrieval_hits(
            db,
            user=user,
            request_workspace_id="workspace-1",
            hits=hits,
        )
        == []
    )


def test_final_retrieval_filter_preserves_rank_order_across_scopes(monkeypatch) -> None:
    user = SimpleNamespace(id="user-1", status="active", login_blocked=False)
    db = SimpleNamespace(scalar=lambda _statement: user)

    class Policy:
        def __init__(self, allowed_id: str) -> None:
            self.allowed_id = allowed_id

        def authorize_many_resources(self, resources):
            return {
                resource
                for resource in resources
                if resource == ("docs_native_doc", self.allowed_id)
            }

        def authorize_many_rag_resources(self, resources):
            return self.authorize_many_resources(resources)

    monkeypatch.setattr(
        retrieval_application,
        "get_rag_resource_adapter",
        lambda _resource_type: SimpleNamespace(app_id="docs"),
    )
    monkeypatch.setattr(
        retrieval_application,
        "is_app_enabled_for_user_context",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        retrieval_application,
        "is_company_app_enabled_for_user_context",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        retrieval_application.SourceAclPolicy,
        "for_workspace_id",
        lambda *_args, **_kwargs: Policy("workspace-result"),
    )
    monkeypatch.setattr(
        retrieval_application.SourceAclPolicy,
        "for_company",
        lambda *_args, **_kwargs: Policy("company-result"),
    )
    hits = [
        RetrievalHit(
            source="generic_rag",
            resource_type="docs_native_doc",
            resource_id="company-result",
            workspace_id=None,
            metadata={"scope_kind": "company"},
        ),
        RetrievalHit(
            source="generic_rag",
            resource_type="docs_native_doc",
            resource_id="workspace-result",
            workspace_id="workspace-1",
            metadata={"scope_kind": "workspace"},
        ),
    ]

    assert [
        hit.resource_id
        for hit in retrieval_application._filter_current_retrieval_hits(
            db,
            user=user,
            request_workspace_id="workspace-1",
            hits=hits,
        )
    ] == ["company-result", "workspace-result"]


def test_final_retrieval_filter_uses_rag_acl_for_rag_backed_hits(monkeypatch) -> None:
    user = SimpleNamespace(id="user-1", status="active", login_blocked=False)
    db = SimpleNamespace(scalar=lambda _statement: user)

    class Policy:
        def authorize_many_resources(self, resources):
            return set(resources)

        def authorize_many_rag_resources(self, resources):
            return set()

    monkeypatch.setattr(
        retrieval_application,
        "get_rag_resource_adapter",
        lambda _resource_type: SimpleNamespace(app_id="docs"),
    )
    monkeypatch.setattr(
        retrieval_application,
        "is_app_enabled_for_user_context",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        retrieval_application.SourceAclPolicy,
        "for_workspace_id",
        lambda *_args, **_kwargs: Policy(),
    )
    hits = [
        RetrievalHit(
            source="generic_rag",
            resource_type="docs_native_doc",
            resource_id="rag-only",
            workspace_id="workspace-1",
            metadata={"scope_kind": "workspace"},
        ),
        RetrievalHit(
            source="keyword",
            resource_type="docs_native_doc",
            resource_id="keyword-only",
            workspace_id="workspace-1",
            metadata={"scope_kind": "workspace"},
        ),
        RetrievalHit(
            source="keyword",
            resource_type="docs_native_doc",
            resource_id="fused-with-rag",
            workspace_id="workspace-1",
            metadata={
                "scope_kind": "workspace",
                "retrieval": {"backends": ["keyword", "generic_rag"]},
            },
        ),
    ]

    assert [
        hit.resource_id
        for hit in retrieval_application._filter_current_retrieval_hits(
            db,
            user=user,
            request_workspace_id="workspace-1",
            hits=hits,
        )
    ] == ["keyword-only"]


def test_retrieval_source_matrix_doc_matches_catalog() -> None:
    matrix = _read_source_matrix()
    catalog = {
        item.source: {
            "scope": item.scope,
            "backend": item.backend,
            "active": item.active,
        }
        for item in iter_retrieval_source_catalog()
    }

    assert matrix == catalog


def test_retrieval_contract_rejects_unknown_request_fields() -> None:
    with pytest.raises(ValueError):
        RetrievalQueryRequest.model_validate(
            {
                "query": "find docs",
                "strategy": "hybrid",
                "unknown": True,
            }
        )


def test_retrieval_ai_tools_compile_with_ai_specific_dto() -> None:
    reset_ai_capability_registry()
    try:
        registry = get_ai_capability_registry()

        assert "retrieval.search" in registry.tools
        assert "retrieval.list_sources" in registry.tools
        assert registry.tools["retrieval.search"].descriptor is not None
        assert (
            registry.tools["retrieval.search"].descriptor.discoverability_predicate_id
            == "retrieval.enabled"
        )
        schema = registry.get_compiled_schemas("retrieval.search")
        assert schema is not None
        assert set(schema.mcp_input_schema["properties"]) == {
            "answer_mode",
            "dataset_keys",
            "field_hints",
            "include_binary_hits",
            "keywords",
            "query",
            "source_kinds",
            "sources",
            "strategy",
            "top_k",
        }
    finally:
        reset_ai_capability_registry()


def test_retrieval_tool_is_discoverable_for_platform_docs_only(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_tools,
        "get_settings",
        lambda: SimpleNamespace(retrieval_unified_enabled=True),
    )

    assert retrieval_tools._retrieval_enabled(
        None,
        None,
        WorkspaceEntitlementView(
            enabled_app_ids=frozenset(),
            platform_enabled_app_ids=frozenset({"docs"}),
        ),
    )


def test_retrieval_rest_routes_expose_sources_and_keyword_query(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_queries = _install_in_process_keyword_backend(monkeypatch)
    auth = _dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(auth["token"])

    sources_response = client.get(
        _workspace_retrieval_path("delivery-hub", "/sources"),
        headers=headers,
    )
    assert sources_response.status_code == 200, sources_response.text
    sources = {item["source"]: item for item in sources_response.json()["sources"]}
    assert {"generic_rag", "keyword"} == set(sources)
    assert sources["keyword"]["active"] is True
    assert isinstance(sources["keyword"]["available"], bool)

    query_response = client.post(
        _workspace_retrieval_path("delivery-hub", "/query"),
        headers=headers,
        json={
            "query": "delivery hub",
            "strategy": "keyword",
            "sources": ["keyword"],
            "top_k": 3,
        },
    )
    assert query_response.status_code == 200, query_response.text
    payload = query_response.json()
    assert payload["query"] == "delivery hub"
    assert payload["strategy"] == "keyword"
    assert payload["profile"]["requested_sources"] == ["keyword"]
    assert payload["profile"]["resolved_sources"] == ["keyword"]
    assert isinstance(payload["hits"], list)
    assert len(captured_queries) == 1
    assert captured_queries[0].text == "delivery hub"
    assert captured_queries[0].text_operator == "or"
    assert captured_queries[0].text_minimum_should_match == "30%"


def test_retrieval_ai_manifest_and_tool_invoke_paths(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_queries = _install_in_process_keyword_backend(monkeypatch)
    auth = _dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(auth["token"])

    manifest_response = client.get(
        _workspace_ai_path("delivery-hub", "/capabilities/manifest"),
        headers=headers,
    )
    assert manifest_response.status_code == 200, manifest_response.text
    tool_names = {item["name"] for item in manifest_response.json()["tools"]}
    assert {"retrieval.search", "retrieval.list_sources"} <= tool_names

    sources_response = client.post(
        _workspace_tool_path("delivery-hub", "retrieval.list_sources"),
        headers=headers,
        json={"arguments": {}},
    )
    assert sources_response.status_code == 200, sources_response.text
    sources_payload = sources_response.json()
    assert sources_payload["tool"] == "retrieval.list_sources"
    assert {item["source"] for item in sources_payload["result"]["sources"]} >= {
        "keyword",
        "generic_rag",
    }

    search_response = client.post(
        _workspace_tool_path("delivery-hub", "retrieval.search"),
        headers=headers,
        json={
            "arguments": {
                "query": "delivery hub",
                "strategy": "keyword",
                "sources": ["keyword"],
                "top_k": 2,
            }
        },
    )
    assert search_response.status_code == 200, search_response.text
    search_payload = search_response.json()
    assert search_payload["tool"] == "retrieval.search"
    assert search_payload["result"]["strategy"] == "keyword"
    assert search_payload["result"]["profile"]["resolved_sources"] == ["keyword"]
    assert len(captured_queries) == 1
    assert captured_queries[0].text == "delivery hub"
    assert captured_queries[0].text_operator == "or"
    assert captured_queries[0].text_minimum_should_match == "30%"


def test_retrieval_ai_tools_are_hidden_and_blocked_when_sources_disabled(
    client: TestClient,
) -> None:
    auth = _dev_login(client, "delivery-hub-admin")
    headers = _auth_headers(auth["token"])
    _disable_retrieval_discoverability_apps("delivery-hub")

    manifest_response = client.get(
        _workspace_ai_path("delivery-hub", "/capabilities/manifest"),
        headers=headers,
    )
    assert manifest_response.status_code == 200, manifest_response.text
    tool_names = {item["name"] for item in manifest_response.json()["tools"]}
    assert "retrieval.search" not in tool_names
    assert "retrieval.list_sources" not in tool_names

    invoke_response = client.post(
        _workspace_tool_path("delivery-hub", "retrieval.list_sources"),
        headers=headers,
        json={"arguments": {}},
    )
    assert invoke_response.status_code == 403, invoke_response.text
    body = invoke_response.json()
    assert body["code"] == "ai.tool_unavailable_in_workspace"
    assert body["params"]["tool_name"] == "retrieval.list_sources"


def test_hybrid_retrieval_fuses_actual_keyword_and_rag_resource_shapes(monkeypatch) -> None:
    _allow_final_retrieval_hits(monkeypatch)
    now = datetime.now(UTC)
    keyword_response = KeywordSearchResponse(
        query="hybrid",
        hits=[
            SearchHit(
                entity_type="doc",
                entity_id="doc-1",
                workspace_id="workspace-1",
                title="Hybrid document",
                summary="Keyword summary",
                snippet=SearchSnippet(text="BM25 passage"),
                score=27.5,
                updated_at=now,
                created_at=now,
                deep_link="/apps/docs/workspaces/workspace/documents/doc-1",
                metadata={"source_kind": "manual"},
            )
        ],
        facets=SearchFacets(),
        total=1,
        has_more=False,
    )
    rag_response = RagQueryResponse(
        query="hybrid",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        hits=[
            RagQueryHit(
                source_kind="manual",
                resource_type="docs_native_doc",
                resource_id="doc-1",
                workspace_id="workspace-1",
                title="Hybrid document",
                excerpt="semantic hybrid retrieval passage",
                score=0.82,
                citation="doc-1:0",
            )
        ],
        query_profile={"rerank_applied": False},
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        retrieval_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda *_args, **_kwargs: ["docs"],
    )
    monkeypatch.setattr(retrieval_application, "_source_available", lambda *_args: True)
    monkeypatch.setattr(
        retrieval_application,
        "_query_primary_candidate_backends",
        lambda *_args, **_kwargs: (
            {"keyword": keyword_response, "generic_rag": rag_response},
            {},
        ),
    )
    monkeypatch.setattr(
        retrieval_application,
        "get_provider_bundle",
        lambda: SimpleNamespace(rerank=FakeRerankClient()),
    )

    response = retrieval_application.query_retrieval(
        object(),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        request=RetrievalQueryRequest(query="hybrid", strategy="hybrid", top_k=5),
    )

    assert len(response.hits) == 1
    hit = response.hits[0]
    assert hit.resource_type == "docs_native_doc"
    assert hit.excerpt == "BM25 passage\n\nsemantic hybrid retrieval passage"
    assert hit.citation == "/apps/docs/workspaces/workspace/documents/doc-1"
    assert {"bm25", "dense_vector", "rrf", "cross_encoder"} <= set(hit.methods)
    assert hit.metadata["retrieval"]["backend_ranks"] == {
        "generic_rag": 1,
        "keyword": 1,
    }
    assert response.profile.backend_profiles["fusion"]["deduped_resource_count"] == 1
    assert response.profile.backend_profiles["rerank"]["applied"] is True
    assert captured == {}


def test_grounded_answer_uses_final_fused_hits_once(monkeypatch) -> None:
    _allow_final_retrieval_hits(monkeypatch)
    rag_response = RagQueryResponse(
        query="policy",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        hits=[
            RagQueryHit(
                source_kind="manual",
                resource_type="docs_native_doc",
                resource_id="doc-1",
                workspace_id="workspace-1",
                excerpt="final evidence",
                score=0.8,
                citation="doc-1:0",
            )
        ],
        query_profile={},
    )
    calls: list[list[str]] = []

    monkeypatch.setattr(
        retrieval_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda *_args, **_kwargs: ["docs"],
    )
    monkeypatch.setattr(retrieval_application, "_source_available", lambda *_args: True)
    monkeypatch.setattr(
        retrieval_application,
        "_query_primary_candidate_backends",
        lambda *_args, **_kwargs: ({"generic_rag": rag_response}, {}),
    )
    monkeypatch.setattr(
        retrieval_application,
        "get_provider_bundle",
        lambda: SimpleNamespace(rerank=None),
    )

    def fake_ground(**kwargs):
        calls.append([hit.resource_id for hit in kwargs["hits"]])
        return RetrievalGroundingResult(
            answer=RetrievalGroundedAnswer(
                text="grounded",
                citations=[
                    RetrievalCitation(
                        resource_id="doc-1",
                        source="generic_rag",
                        quote="final evidence",
                        locator="doc-1:0",
                    )
                ],
                sources_used=["generic_rag"],
            ),
            degraded=False,
        )

    monkeypatch.setattr(retrieval_application, "ground_ranked_hits", fake_ground)

    response = retrieval_application.query_retrieval(
        object(),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        request=RetrievalQueryRequest(
            query="policy",
            strategy="semantic",
            answer_mode=RetrievalAnswerMode.GROUNDED_ANSWER,
        ),
    )

    assert calls == [["doc-1"]]
    assert response.grounded_answer is not None
    assert response.grounded_answer.text == "grounded"
    assert response.citations == response.grounded_answer.citations


def test_hybrid_evaluation_routes_keyword_leg_to_injected_staging_client(
    monkeypatch,
) -> None:
    staging_client = SimpleNamespace(index_name="keyword_v2_evaluation")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        retrieval_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda *_args, **_kwargs: ["docs"],
    )
    monkeypatch.setattr(retrieval_application, "_source_available", lambda *_args: True)

    def fake_primary(*_args, **kwargs):
        captured["client"] = kwargs["keyword_search_client"]
        return {}, {}

    monkeypatch.setattr(
        retrieval_application,
        "_query_primary_candidate_backends",
        fake_primary,
    )

    response = retrieval_application.query_retrieval(
        object(),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        request=RetrievalQueryRequest(query="heater", strategy="hybrid"),
        keyword_search_client=staging_client,
    )

    assert response.hits == []
    assert captured["client"] is staging_client


def test_explicit_source_selection_fails_closed() -> None:
    with pytest.raises(HTTPException) as invalid:
        retrieval_application._resolve_request_sources(
            RetrievalQueryRequest(query="x", sources=["missing"]),
            enabled_app_ids=set(),
        )
    assert invalid.value.status_code == 422

    with pytest.raises(HTTPException) as unavailable:
        retrieval_application._resolve_request_sources(
            RetrievalQueryRequest(query="x", sources=["generic_rag"]),
            enabled_app_ids=set(),
        )
    assert unavailable.value.status_code == 403


def test_explicit_source_runtime_failure_is_service_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda *_args, **_kwargs: ["docs"],
    )
    monkeypatch.setattr(retrieval_application, "_source_available", lambda *_args: True)
    monkeypatch.setattr(
        retrieval_application,
        "_query_primary_candidate_backends",
        lambda *_args, **_kwargs: ({}, {"keyword": "OpenSearchError"}),
    )

    with pytest.raises(HTTPException) as failed:
        retrieval_application.query_retrieval(
            object(),
            workspace=SimpleNamespace(id="workspace-1"),
            user=SimpleNamespace(id="user-1"),
            request=RetrievalQueryRequest(
                query="explicit",
                strategy="keyword",
                sources=["keyword"],
            ),
        )

    assert failed.value.status_code == 503


def test_multiple_backends_always_use_rrf_even_for_semantic_strategy(monkeypatch) -> None:
    _allow_final_retrieval_hits(monkeypatch)
    keyword_response = KeywordSearchResponse(
        query="multi",
        hits=[],
        facets=SearchFacets(),
        total=0,
        has_more=False,
    )
    rag_response = RagQueryResponse(
        query="multi",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        hits=[],
        query_profile={},
    )
    keyword_hit = RetrievalHit(
        source="keyword",
        source_kind="manual",
        resource_type="docs_native_doc",
        resource_id="keyword-doc",
        workspace_id="workspace-1",
        score=900,
        methods=["bm25"],
        metadata={"scope_kind": "workspace"},
    )
    dense_hit = keyword_hit.model_copy(
        update={
            "source": "generic_rag",
            "resource_id": "dense-doc",
            "score": 0.9,
            "methods": ["vector"],
        }
    )
    monkeypatch.setattr(
        retrieval_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda *_args, **_kwargs: ["docs"],
    )
    monkeypatch.setattr(retrieval_application, "_source_available", lambda *_args: True)
    monkeypatch.setattr(
        retrieval_application,
        "_query_primary_candidate_backends",
        lambda *_args, **_kwargs: (
            {"keyword": keyword_response, "generic_rag": rag_response},
            {},
        ),
    )
    monkeypatch.setattr(
        retrieval_application,
        "_keyword_response_to_hits",
        lambda _response: [keyword_hit],
    )
    monkeypatch.setattr(
        retrieval_application,
        "_rag_response_to_hits",
        lambda _response, *, source: [dense_hit],
    )
    monkeypatch.setattr(
        retrieval_application,
        "get_provider_bundle",
        lambda: SimpleNamespace(rerank=None),
    )

    response = retrieval_application.query_retrieval(
        object(),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        request=RetrievalQueryRequest(
            query="multi",
            strategy="semantic",
            sources=["keyword", "generic_rag"],
        ),
    )

    assert response.profile.backend_profiles["fusion"]["mode"] == "rrf"
    assert all(hit.score == pytest.approx(1 / 61) for hit in response.hits)


def test_retrieval_filter_namespaces_do_not_leak_between_backends() -> None:
    filters = {
        "keywords": ["legacy only"],
        "keyword": {"entity_types": ["doc"]},
        "rag": {"metadata.department": "quality"},
        "content_modality": "text",
    }

    assert retrieval_application._rag_filters_from_retrieval(filters) == {
        "metadata.department": "quality",
        "content_modality": "text",
    }


def test_retrieval_keyword_backend_uses_recall_oriented_text_matching(monkeypatch) -> None:
    captured: dict[str, object] = {}
    expected = object()

    def _query_workspace_keyword_search(*_args, **kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        retrieval_application.search_service,
        "query_workspace_keyword_search",
        _query_workspace_keyword_search,
    )

    response = retrieval_application._query_keyword_search(
        object(),
        workspace=SimpleNamespace(id="workspace-1"),
        user=SimpleNamespace(id="user-1"),
        request=RetrievalQueryRequest(
            query="국제 특허 출원 조사 절차",
            filters={"keyword": {"entity_types": ["file"]}},
        ),
    )

    assert response is expected
    assert captured["text_operator"] == "or"
    assert captured["text_minimum_should_match"] == "30%"
    assert captured["backend_candidate_size"] == 8
    assert captured["request"].query == "국제 특허 출원 조사 절차"
