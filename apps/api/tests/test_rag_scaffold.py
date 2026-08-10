from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.rag import application as rag_application
from open_work_hub_api.domains.rag import access_filter as rag_access_filter
from open_work_hub_api.domains.rag import provider_factory, runtime as rag_runtime
from open_work_hub_api.domains.rag.contracts import (
    RagAnswerMode,
    RagProjection,
    RagQueryRequest,
    RagQueryResponse,
    RagScopeKind,
    RagSyncLane,
    RagVectorSearchHit,
)
from open_work_hub_api.domains.rag.providers.fake import (
    FakeEmbeddingClient,
    FakeRerankClient,
    FakeVectorIndexClient,
)
from open_work_hub_api.domains.rag.filters import RagQueryFilters
from open_work_hub_api.domains.rag.provider_factory import RagProviderFactory
from open_work_hub_api.domains.rag.provider_registry import RagProviderDescriptor
from open_work_hub_api.domains.rag.providers.base import RagProviderConfigurationError
from open_work_hub_api.domains.rag.query_service import RagQueryService
from open_work_hub_api.domains.rag.service import RagService


def _reset_settings() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def test_retrieval_candidate_service_caps_dense_backend_budget(monkeypatch) -> None:
    providers = SimpleNamespace(
        vector_index=FakeVectorIndexClient(),
        embedding=FakeEmbeddingClient(),
        rerank=FakeRerankClient(),
    )
    settings = SimpleNamespace(
        rag_query_timeout_ms=210_000,
        rag_rerank_candidate_k=80,
        rag_qdrant_collection_prefix="rag-test",
    )
    monkeypatch.setattr(rag_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(rag_runtime, "get_provider_bundle", lambda: providers)
    rag_runtime.get_retrieval_candidate_query_service.cache_clear()
    try:
        service = rag_runtime.get_retrieval_candidate_query_service()
    finally:
        rag_runtime.get_retrieval_candidate_query_service.cache_clear()

    assert service._query_timeout_ms == 5_000
    assert service._rerank_client is None


def test_inference_gateway_reranker_declares_normalized_score_semantics() -> None:
    provider_factory.get_rag_provider_registry.cache_clear()
    try:
        settings = Settings(
            _env_file=None,
            postgres_dsn="postgresql+psycopg://test:test@127.0.0.1:5432/test",
            rag_rerank_provider="inference_gateway",
            inference_gateway_base_url="http://inference-gateway.test",
            rag_local_reranker_model="reranker-model",
        )

        client = RagProviderFactory(settings).build_rerank()

        assert client is not None
        assert getattr(client, "score_semantics") == "normalized_relevance"
        close = getattr(client, "close", None)
        if close is not None:
            close()
    finally:
        provider_factory.get_rag_provider_registry.cache_clear()


def test_rag_query_service_forwards_explicit_partition_candidate_scope() -> None:
    class RecordingVectorIndex(FakeVectorIndexClient):
        def __init__(self) -> None:
            super().__init__()
            self.requests = []

        def query(self, *, request, timeout_seconds=None):
            self.requests.append(request)
            return []

    vector_index = RecordingVectorIndex()
    service = RagQueryService(
        vector_index=vector_index,
        embedding_client=FakeEmbeddingClient(),
    )

    service.query(
        RagQueryRequest(
            collection="partition-v3",
            workspace_id="diagnostic-workspace",
            retrieval_partition_ids=["a3b6638a-7547-45f8-81f2-973bfa6080d6"],
            query="heater",
        )
    )

    assert vector_index.requests[0].retrieval_partition_ids == [
        "a3b6638a-7547-45f8-81f2-973bfa6080d6"
    ]


def test_ensure_rag_enabled_raises_domain_error(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        OPEN_WORK_HUB_POSTGRES_DSN="postgresql+psycopg://test:test@127.0.0.1:5432/test",
        OPEN_WORK_HUB_RAG_ENABLED=False,
    )

    with pytest.raises(rag_application.RagUnavailableError) as exc_info:
        rag_application.ensure_rag_enabled(settings=settings)
    assert exc_info.value.code == "rag.disabled"


def test_workspace_rag_sources_require_ai_app_enablement(monkeypatch) -> None:
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"docs"},
    )

    with pytest.raises(rag_application.RagAccessDeniedError) as exc_info:
        rag_application.list_workspace_rag_sources(
            db=object(),
            workspace=SimpleNamespace(id="ws-1"),
            user=SimpleNamespace(id="user-1"),
            settings=SimpleNamespace(rag_enabled=True),
        )
    assert exc_info.value.code == "rag.access_denied_not_enabled"


def test_workspace_rag_query_requires_searchable_app_enablement(monkeypatch) -> None:
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot"},
    )

    with pytest.raises(rag_application.RagAccessDeniedError) as exc_info:
        rag_application.query_workspace_rag(
            db=object(),
            workspace=SimpleNamespace(id="ws-1"),
            user=SimpleNamespace(id="user-1"),
            query="budget risk",
            answer_mode=RagAnswerMode.SEARCH_ONLY,
            source_kinds=[],
            filters={},
            top_k=5,
            include_binary_hits=False,
            settings=SimpleNamespace(rag_enabled=True),
        )
    assert exc_info.value.code == "rag.access_denied_not_enabled"


def test_workspace_rag_query_propagates_relaxed_app_gate_to_source_listing(
    monkeypatch,
) -> None:
    class StubPolicy:
        def visible_rag_native_doc_source_kinds(self):
            return ["manual"]

        def has_accessible_source(self, resource_type):
            return resource_type == "docs_native_doc"

    class StubQueryService:
        def query(self, request, *, post_filter, grounded_answer_synthesizer=None):
            del post_filter, grounded_answer_synthesizer
            return RagQueryResponse(
                query=request.query,
                answer_mode=request.answer_mode,
                hits=[],
                sources_used=[],
                query_profile={"source_kinds": list(request.source_kinds)},
                latency_ms=0,
            )

    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"docs"},
    )
    monkeypatch.setattr(
        rag_application.SourceAclPolicy,
        "for_workspace",
        lambda db, workspace, user: StubPolicy(),
    )
    monkeypatch.setattr(
        rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test"
    )
    monkeypatch.setattr(
        rag_application, "resolve_default_collection_name", lambda settings: "rag-test"
    )
    monkeypatch.setattr(
        rag_application,
        "build_user_rag_post_filter",
        lambda db, user, **kwargs: lambda hit: True,
    )

    response = rag_application.query_workspace_rag(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        user=SimpleNamespace(id="user-1"),
        query="budget risk",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        source_kinds=[],
        filters={},
        top_k=5,
        include_binary_hits=False,
        settings=SimpleNamespace(rag_enabled=True),
        query_service=StubQueryService(),
        required_app_ids=frozenset(),
    )

    assert response.query_profile == {"source_kinds": ["manual"]}


def test_workspace_rag_query_allows_explicit_rag_app_gate(monkeypatch) -> None:
    class StubPolicy:
        def has_accessible_source(self, resource_type):
            return resource_type == "docs_native_doc"

    class StubQueryService:
        def query(self, request, *, post_filter, grounded_answer_synthesizer=None):
            del post_filter, grounded_answer_synthesizer
            return RagQueryResponse(
                query=request.query,
                answer_mode=request.answer_mode,
                hits=[],
                sources_used=[],
                query_profile={"source_kinds": list(request.source_kinds)},
                latency_ms=0,
            )

    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"docs"},
    )
    monkeypatch.setattr(
        rag_application.SourceAclPolicy,
        "for_workspace",
        lambda db, workspace, user: StubPolicy(),
    )
    monkeypatch.setattr(
        rag_application,
        "list_registered_workspace_rag_sources",
        lambda policy, enabled_app_ids: [],
    )
    monkeypatch.setattr(
        rag_application,
        "resolve_rag_resource_types_for_source_kinds",
        lambda source_kinds: ("docs_native_doc",) if source_kinds == ["docs_native_doc"] else (),
    )
    monkeypatch.setattr(
        rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test"
    )
    monkeypatch.setattr(
        rag_application, "resolve_default_collection_name", lambda settings: "rag-test"
    )
    monkeypatch.setattr(
        rag_application,
        "build_user_rag_post_filter",
        lambda db, user, **kwargs: lambda hit: True,
    )

    response = rag_application.query_workspace_rag(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        user=SimpleNamespace(id="user-1"),
        query="benefit points",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        source_kinds=["docs_native_doc"],
        filters={},
        top_k=5,
        include_binary_hits=False,
        settings=SimpleNamespace(rag_enabled=True),
        query_service=StubQueryService(),
        require_searchable_app=False,
        allowed_unlisted_source_kinds=frozenset({"docs_native_doc"}),
        required_app_ids=frozenset({"docs"}),
    )

    assert response.sources_used == []
    assert response.query_profile == {"source_kinds": ["docs_native_doc"]}


def test_rag_query_filters_accept_storage_width_resource_ids() -> None:
    resource_id = "x" * 255

    assert RagQueryFilters(resource_id=resource_id).to_flat_dict()["resource_id"] == resource_id
    with pytest.raises(ValidationError):
        RagQueryFilters(resource_id=resource_id + "x")


def test_workspace_rag_reindex_requires_ai_enablement(monkeypatch) -> None:
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"planner"},
    )

    with pytest.raises(rag_application.RagAccessDeniedError) as exc_info:
        rag_application.enqueue_workspace_rag_reindex(
            db=object(),
            workspace=SimpleNamespace(id="ws-1"),
            settings=SimpleNamespace(rag_enabled=True),
        )
    assert exc_info.value.code == "rag.access_denied_not_enabled"


def test_company_rag_reindex_enqueues_company_scope_jobs(monkeypatch) -> None:
    captured: list[dict] = []
    adapter = SimpleNamespace(
        resource_type="docs_native_doc",
        company_resource_ids=lambda db: ["doc-1", "doc-2"],
    )

    monkeypatch.setattr(
        rag_application,
        "ensure_default_collection_ready",
        lambda *args, **kwargs: "rag-test",
    )
    monkeypatch.setattr(
        rag_application,
        "company_reindex_resource_adapters",
        lambda app_ids=None: (adapter,),
    )

    def fake_enqueue_rag_sync_job(db, **kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(
        rag_application,
        "enqueue_rag_sync_job",
        fake_enqueue_rag_sync_job,
    )

    result = rag_application.enqueue_company_rag_reindex(
        db=object(),
        settings=SimpleNamespace(rag_enabled=True),
        app_ids={"docs"},
    )

    assert result == {
        "lane": "backfill",
        "scope_kind": "company",
        "queued_count": 2,
        "resource_counts": {"docs_native_doc": 2},
    }
    assert captured == [
        {
            "scope_kind": RagScopeKind.COMPANY,
            "workspace_id": None,
            "resource_type": "docs_native_doc",
            "resource_id": "doc-1",
            "lane": RagSyncLane.BACKFILL,
        },
        {
            "scope_kind": RagScopeKind.COMPANY,
            "workspace_id": None,
            "resource_type": "docs_native_doc",
            "resource_id": "doc-2",
            "lane": RagSyncLane.BACKFILL,
        },
    ]


def test_workspace_rag_sources_expose_official_docs(monkeypatch) -> None:
    class StubPolicy:
        def visible_rag_native_doc_source_kinds(self):
            return ["manual", "custom_report", "minutes"]

        def has_accessible_source(self, resource_type):
            del resource_type
            return False

    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs", "meeting"},
    )
    monkeypatch.setattr(
        rag_application.SourceAclPolicy,
        "for_workspace",
        lambda db, workspace, user: StubPolicy(),
    )

    sources = rag_application.list_workspace_rag_sources(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        user=SimpleNamespace(id="user-1"),
        settings=SimpleNamespace(rag_enabled=True),
    )

    assert sources == [
        {
            "source_kind": "manual",
            "resource_type": "docs_native_doc",
            "label": "Docs / Manual",
            "app_id": "docs",
        },
        {
            "source_kind": "minutes",
            "resource_type": "docs_native_doc",
            "label": "Meeting / Minutes",
            "app_id": "docs",
        },
        {
            "source_kind": "custom_report",
            "resource_type": "docs_native_doc",
            "label": "Docs / Custom Report",
            "app_id": "docs",
        },
    ]


def test_workspace_rag_sources_include_registered_domain_sources(monkeypatch) -> None:
    class StubPolicy:
        def visible_rag_native_doc_source_kinds(self):
            return []

        def has_accessible_source(self, resource_type):
            return resource_type in {"meeting", "pms_task"}

    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs", "meeting", "pms", "planner"},
    )
    monkeypatch.setattr(
        rag_application.SourceAclPolicy,
        "for_workspace",
        lambda db, workspace, user: StubPolicy(),
    )

    sources = rag_application.list_workspace_rag_sources(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        user=SimpleNamespace(id="user-1"),
        settings=SimpleNamespace(rag_enabled=True),
    )

    assert sources == []


def test_workspace_rag_reindex_enqueues_official_docs(monkeypatch) -> None:
    class StubDb:
        def scalar(self, _statement):
            return None

    enqueued: list[tuple[str, str]] = []

    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs", "meeting"},
    )
    monkeypatch.setattr(
        rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        rag_application,
        "workspace_reindex_resource_adapters",
        lambda enabled_app_ids: (
            SimpleNamespace(
                resource_type="docs_native_doc",
                workspace_resource_ids=lambda db, workspace: ["doc-1", "doc-2"],
            ),
        ),
    )
    monkeypatch.setattr(
        rag_application,
        "_enqueue_ids",
        lambda db, workspace, resource_type, resource_ids: enqueued.extend(
            (resource_type, resource_id) for resource_id in resource_ids
        )
        or len(list(resource_ids)),
    )

    result = rag_application.enqueue_workspace_rag_reindex(
        db=StubDb(),
        workspace=SimpleNamespace(id="ws-1"),
        settings=SimpleNamespace(rag_enabled=True),
    )

    assert enqueued == [
        ("docs_native_doc", "doc-1"),
        ("docs_native_doc", "doc-2"),
    ]
    assert result["resource_counts"] == {
        "docs_native_doc": 2,
    }
    assert result["queued_count"] == 2


def test_workspace_rag_reindex_force_bypasses_cooldown(monkeypatch) -> None:
    class StubDb:
        def scalar(self, _statement):
            return None

    enqueued: list[tuple[str, str]] = []

    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs"},
    )
    monkeypatch.setattr(
        rag_application,
        "_ensure_workspace_reindex_available",
        lambda db, *, workspace: (_ for _ in ()).throw(
            AssertionError("force should bypass cooldown")
        ),
    )
    monkeypatch.setattr(
        rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        rag_application,
        "workspace_reindex_resource_adapters",
        lambda enabled_app_ids: (
            SimpleNamespace(
                resource_type="docs_native_doc",
                workspace_resource_ids=lambda db, workspace: ["doc-1"],
            ),
        ),
    )
    monkeypatch.setattr(
        rag_application,
        "_enqueue_ids",
        lambda db, workspace, resource_type, resource_ids: enqueued.extend(
            (resource_type, resource_id) for resource_id in resource_ids
        )
        or len(list(resource_ids)),
    )

    result = rag_application.enqueue_workspace_rag_reindex(
        db=StubDb(),
        workspace=SimpleNamespace(id="ws-1"),
        settings=SimpleNamespace(rag_enabled=True),
        force=True,
    )

    assert enqueued == [("docs_native_doc", "doc-1")]
    assert result["queued_count"] == 1


def test_workspace_rag_reindex_resource_count_uses_registry(monkeypatch) -> None:
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs"},
    )
    monkeypatch.setattr(
        rag_application,
        "workspace_reindex_resource_adapters",
        lambda enabled_app_ids: (
            SimpleNamespace(
                resource_type="docs_native_doc",
                workspace_resource_ids=lambda db, workspace: ["doc-1", "doc-2"],
            ),
        ),
    )

    result = rag_application.count_workspace_rag_reindex_resources(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        settings=SimpleNamespace(rag_enabled=True),
    )

    assert result == {
        "docs_native_doc": 2,
    }


def test_workspace_rag_query_defaults_to_text_hits_when_binary_hits_not_requested(
    monkeypatch,
) -> None:
    captured_filters: dict[str, object] = {}

    class StubQueryService:
        def query(self, request, *, post_filter, grounded_answer_synthesizer=None):
            del post_filter, grounded_answer_synthesizer
            captured_filters.update(request.filters)
            return RagQueryResponse(
                query=request.query,
                answer_mode=request.answer_mode,
                hits=[],
                sources_used=[],
                query_profile={},
                latency_ms=0,
            )

    monkeypatch.setattr(
        rag_application,
        "list_workspace_rag_sources",
        lambda *args, **kwargs: [
            {
                "source_kind": "manual",
                "resource_type": "docs_native_doc",
                "label": "Docs / Manual",
                "app_id": "docs",
            }
        ],
    )
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs"},
    )
    monkeypatch.setattr(
        rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test"
    )
    monkeypatch.setattr(
        rag_application, "resolve_default_collection_name", lambda settings: "rag-test"
    )
    monkeypatch.setattr(
        rag_application,
        "build_user_rag_post_filter",
        lambda db, user, **kwargs: lambda hit: True,
    )

    response = rag_application.query_workspace_rag(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        user=SimpleNamespace(id="user-1"),
        query="budget risk",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        source_kinds=[],
        filters={},
        top_k=5,
        include_binary_hits=False,
        settings=SimpleNamespace(rag_enabled=True),
        query_service=StubQueryService(),
    )

    assert response.hits == []
    assert captured_filters == {"content_modality": "text"}


def test_workspace_rag_query_respects_explicit_content_modality_filter(monkeypatch) -> None:
    captured_filters: dict[str, object] = {}

    class StubQueryService:
        def query(self, request, *, post_filter, grounded_answer_synthesizer=None):
            del post_filter, grounded_answer_synthesizer
            captured_filters.update(request.filters)
            return RagQueryResponse(
                query=request.query,
                answer_mode=request.answer_mode,
                hits=[],
                sources_used=[],
                query_profile={},
                latency_ms=0,
            )

    monkeypatch.setattr(
        rag_application,
        "list_workspace_rag_sources",
        lambda *args, **kwargs: [
            {
                "source_kind": "manual",
                "resource_type": "docs_native_doc",
                "label": "Docs / Manual",
                "app_id": "docs",
            }
        ],
    )
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs"},
    )
    monkeypatch.setattr(
        rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test"
    )
    monkeypatch.setattr(
        rag_application, "resolve_default_collection_name", lambda settings: "rag-test"
    )
    monkeypatch.setattr(
        rag_application,
        "build_user_rag_post_filter",
        lambda db, user, **kwargs: lambda hit: True,
    )

    rag_application.query_workspace_rag(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        user=SimpleNamespace(id="user-1"),
        query="budget risk",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        source_kinds=[],
        filters={"content_modality": "binary"},
        top_k=5,
        include_binary_hits=False,
        settings=SimpleNamespace(rag_enabled=True),
        query_service=StubQueryService(),
    )

    assert captured_filters == {"content_modality": "binary"}


def test_provider_factory_rejects_qdrant_without_url() -> None:
    factory = RagProviderFactory(
        SimpleNamespace(
            rag_vector_index_provider="qdrant",
            rag_qdrant_url="",
            rag_qdrant_api_key="",
        )
    )

    with pytest.raises(RagProviderConfigurationError, match="OPEN_WORK_HUB_RAG_QDRANT_URL"):
        factory.build_vector_index()


def test_provider_factory_normalizes_registered_provider_names() -> None:
    provider_factory.get_rag_provider_registry.cache_clear()
    try:
        vector_factory = RagProviderFactory(
            SimpleNamespace(
                rag_vector_index_provider=" FAKE ",
                rag_qdrant_url="",
                rag_qdrant_api_key="",
            )
        )

        assert isinstance(vector_factory.build_vector_index(), FakeVectorIndexClient)

        settings = Settings(
            _env_file=None,
            postgres_dsn="postgresql+psycopg://test:test@127.0.0.1:5432/test",
            rag_embedding_provider=" Inference_Gateway ",
            rag_local_embedding_model="BAAI/bge-m3",
            rag_qdrant_collection_prefix="rag-test",
        )

        assert rag_runtime.resolve_default_collection_name(settings) == "rag-test-baai-bge-m3"
    finally:
        provider_factory.get_rag_provider_registry.cache_clear()


def test_custom_embedding_provider_uses_provider_scoped_collection_token() -> None:
    provider_factory.get_rag_provider_registry.cache_clear()
    try:
        registry = provider_factory.get_rag_provider_registry()
        registry.register_embedding(
            RagProviderDescriptor(
                names=("plugin_embedding",),
                builder=lambda settings: FakeEmbeddingClient(),
            )
        )
        settings = Settings(
            _env_file=None,
            postgres_dsn="postgresql+psycopg://test:test@127.0.0.1:5432/test",
            rag_embedding_provider="plugin_embedding",
            rag_qdrant_collection_prefix="rag-test",
        )

        assert rag_runtime.resolve_default_collection_name(settings) == "rag-test-plugin-embedding"
    finally:
        provider_factory.get_rag_provider_registry.cache_clear()


def test_configured_embedding_provider_collection_token_uses_embedding_model() -> None:
    provider_factory.get_rag_provider_registry.cache_clear()
    try:
        settings = Settings(
            _env_file=None,
            postgres_dsn="postgresql+psycopg://test:test@127.0.0.1:5432/test",
            rag_embedding_provider="inference_gateway",
            rag_local_embedding_model="BAAI/bge-m3",
            rag_qdrant_collection_prefix="rag-test",
        )

        assert rag_runtime.resolve_default_collection_name(settings) == "rag-test-baai-bge-m3"
    finally:
        provider_factory.get_rag_provider_registry.cache_clear()


def test_rag_service_prunes_stale_tail_chunks_for_same_resource() -> None:
    vector_index = FakeVectorIndexClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=FakeEmbeddingClient(),
    )

    initial = rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
            source_kind="docs",
            text_content=("A" * 900) + ("B" * 900),
        ),
        collection="rag-prune",
    )
    updated = rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
            source_kind="docs",
            text_content="Short replacement body",
        ),
        collection="rag-prune",
    )

    assert initial.chunk_count >= 2
    assert updated.chunk_count == 1
    assert updated.deleted_count >= 1
    assert vector_index.snapshot_projection(collection="rag-prune", chunk_id="doc-1:0") is not None
    assert vector_index.snapshot_projection(collection="rag-prune", chunk_id="doc-1:1") is None


def test_rag_service_acquires_final_fence_after_embedding_before_vector_write() -> None:
    calls: list[str] = []

    class OrderedEmbeddingClient(FakeEmbeddingClient):
        def embed_texts(self, texts, timeout_seconds=None):
            calls.append("embed")
            return super().embed_texts(texts, timeout_seconds=timeout_seconds)

    class OrderedVectorIndexClient(FakeVectorIndexClient):
        def ensure_collection(self, **kwargs):
            calls.append("ensure_collection")
            return super().ensure_collection(**kwargs)

        def upsert_chunks(self, **kwargs):
            calls.append("upsert")
            return super().upsert_chunks(**kwargs)

    rag_service = RagService(
        vector_index=OrderedVectorIndexClient(),
        embedding_client=OrderedEmbeddingClient(),
    )

    rag_service.sync_projection_with_fence(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-fenced",
            source_kind="docs",
            text_content="fenced vector mutation",
        ),
        collection="rag-fenced",
        before_vector_write=lambda: calls.append("final_fence"),
    )

    assert calls == ["embed", "final_fence", "ensure_collection", "upsert"]


def test_rag_query_oversamples_when_post_filter_removes_top_hit() -> None:
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )

    rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-denied",
            source_kind="docs",
            text_content="budget risk urgent budget risk urgent",
            visibility_refs=["owner:blocked"],
        ),
        collection="rag-post-filter",
    )
    rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-allowed",
            source_kind="docs",
            text_content="budget risk review followup",
            visibility_refs=["owner:user-1"],
        ),
        collection="rag-post-filter",
    )

    response = query_service.query(
        RagQueryRequest(
            collection="rag-post-filter",
            workspace_id="ws-1",
            query="budget risk urgent",
            top_k=1,
        ),
        post_filter=lambda hit: "owner:user-1" in hit.projection.visibility_refs,
    )

    assert [hit.resource_id for hit in response.hits] == ["doc-allowed"]
    assert response.query_profile["vector_requested_top_k"] > 1


def test_rag_query_reauthorizes_after_retrieval_before_response_projection() -> None:
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    ).sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-revoked",
            source_kind="docs",
            text_content="authorization can be revoked during query",
        ),
        collection="rag-final-acl",
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )

    class RevokedBeforeResponse:
        def __init__(self) -> None:
            self.batch_calls = 0

        def __call__(self, hit) -> bool:
            raise AssertionError("batch ACL path should be used")

        def filter_many(self, hits):
            self.batch_calls += 1
            return list(hits) if self.batch_calls == 1 else []

    post_filter = RevokedBeforeResponse()
    response = query_service.query(
        RagQueryRequest(
            collection="rag-final-acl",
            workspace_id="ws-1",
            query="authorization revoked",
            top_k=1,
        ),
        post_filter=post_filter,
    )

    assert response.hits == []
    assert post_filter.batch_calls == 2


def test_rag_hydrates_source_metadata_before_final_acl_and_grounding() -> None:
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    ).sync_projection(
        RagProjection(
            scope_kind=RagScopeKind.WORKSPACE,
            workspace_id="workspace-before-publication",
            resource_type="file_manager_file",
            resource_id="file-1",
            source_kind="files",
            text_content="company handbook",
            visibility_refs=["workspace:workspace-before-publication"],
            metadata={"origin_ref": "/w/workspace-before/files?file=file-1"},
        ),
        collection="rag-source-hydration",
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )

    class RecordingSourceAcl:
        def __init__(self) -> None:
            self.observed_scopes: list[RagScopeKind] = []

        def filter_many(self, hits):
            self.observed_scopes.extend(hit.projection.scope_kind for hit in hits)
            return list(hits)

    source_acl = RecordingSourceAcl()

    def hydrate(hits):
        return [
            hit.model_copy(
                update={
                    "projection": hit.projection.model_copy(
                        update={
                            "scope_kind": RagScopeKind.COMPANY,
                            "workspace_id": None,
                            "visibility_refs": ["company_public"],
                            "metadata": {"origin_ref": "/files?file=file-1"},
                        }
                    )
                }
            )
            for hit in hits
        ]

    response = query_service.query(
        RagQueryRequest(
            collection="rag-source-hydration",
            workspace_id="workspace-before-publication",
            query="company handbook",
            answer_mode=RagAnswerMode.GROUNDED_ANSWER,
            top_k=1,
        ),
        post_filter=source_acl,
        hit_hydrator=hydrate,
    )

    assert source_acl.observed_scopes == [RagScopeKind.WORKSPACE, RagScopeKind.COMPANY]
    assert response.hits[0].scope_kind == RagScopeKind.COMPANY
    assert response.hits[0].workspace_id is None
    assert response.hits[0].acl_summary == ["company public"]
    assert response.hits[0].origin_ref == "/files?file=file-1"
    assert response.grounded_answer is not None
    assert response.grounded_answer.citations[0].resource_id == "file-1"


def test_company_rag_filter_requires_source_owned_acl(monkeypatch) -> None:
    calls: list[set[tuple[str, str]]] = []

    class FakeCompanyPolicy:
        def authorize_many_rag_resources(self, resources):
            requested = set(resources)
            calls.append(requested)
            return {("docs_native_doc", "allowed")}

    monkeypatch.setattr(
        rag_access_filter.SourceAclPolicy,
        "for_company",
        lambda db, *, user: FakeCompanyPolicy(),
    )
    post_filter = rag_access_filter.build_company_rag_post_filter(
        SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        source_kinds=["docs_native_doc"],
    )

    def hit(resource_id: str) -> RagVectorSearchHit:
        return RagVectorSearchHit(
            chunk_id=f"{resource_id}:0",
            text=resource_id,
            score=1.0,
            projection=RagProjection(
                scope_kind=RagScopeKind.COMPANY,
                workspace_id=None,
                resource_type="docs_native_doc",
                resource_id=resource_id,
                source_kind="docs_native_doc",
                visibility_refs=["company_public"],
            ),
        )

    assert [
        item.projection.resource_id
        for item in post_filter.filter_many([hit("allowed"), hit("denied")])
    ] == ["allowed"]
    assert calls == [{("docs_native_doc", "allowed"), ("docs_native_doc", "denied")}]


def test_partition_authorized_rag_filters_ignore_stale_scope_payload(monkeypatch) -> None:
    partition_id = "11111111-1111-1111-1111-111111111111"

    class FakePolicy:
        def authorize_many_rag_resources(self, resources):
            return set(resources)

    monkeypatch.setattr(
        rag_access_filter.SourceAclPolicy,
        "for_company",
        lambda db, *, user: FakePolicy(),
    )
    monkeypatch.setattr(
        rag_access_filter.SourceAclPolicy,
        "for_workspace_id",
        lambda db, *, workspace_id, user: FakePolicy(),
    )

    stale_hit = RagVectorSearchHit(
        chunk_id="file-1:0",
        text="scope moved without vector rewrite",
        score=1.0,
        projection=RagProjection(
            retrieval_partition_id=partition_id,
            projection_version=7,
            scope_kind=RagScopeKind.WORKSPACE,
            workspace_id="stale-workspace",
            resource_type="file_manager_file",
            resource_id="file-1",
            source_kind="files",
            visibility_refs=["workspace:stale-workspace"],
        ),
    )
    wrong_partition = stale_hit.model_copy(
        update={
            "projection": stale_hit.projection.model_copy(
                update={"retrieval_partition_id": "22222222-2222-2222-2222-222222222222"}
            )
        }
    )

    workspace_filter = rag_access_filter.build_user_rag_post_filter(
        SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        workspace_id="current-workspace",
        authorized_partition_ids=[partition_id],
    )
    company_filter = rag_access_filter.build_company_rag_post_filter(
        SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
        source_kinds=["files"],
        authorized_partition_ids=[partition_id],
    )

    assert workspace_filter.filter_many([stale_hit, wrong_partition]) == [stale_hit]
    assert company_filter.filter_many([stale_hit, wrong_partition]) == [stale_hit]


def test_rag_query_uses_wider_default_candidate_pool_for_rerank() -> None:
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        rerank_client=FakeRerankClient(),
    )

    for index in range(30):
        rag_service.sync_projection(
            RagProjection(
                workspace_id="ws-1",
                resource_type="doc",
                resource_id=f"doc-{index}",
                source_kind="docs",
                text_content=f"budget risk review candidate {index}",
                visibility_refs=["workspace:ws-1"],
            ),
            collection="rag-rerank-candidate-pool",
        )

    response = query_service.query(
        RagQueryRequest(
            collection="rag-rerank-candidate-pool",
            workspace_id="ws-1",
            query="budget risk",
            top_k=20,
        )
    )

    assert len(response.hits) == 20
    assert response.query_profile["vector_requested_top_k"] == 80
    assert response.query_profile["rerank_applied"] is True
