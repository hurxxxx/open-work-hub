from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from aidoo_api.core.settings import Settings, get_settings
from aidoo_api.domains.rag import application as rag_application
from aidoo_api.domains.rag.contracts import RagAnswerMode, RagProjection, RagQueryRequest, RagQueryResponse
from aidoo_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.runtime import (
    get_rag_query_service,
    reset_rag_runtime_caches,
    resolve_default_collection_name,
)
from aidoo_api.domains.rag.service import RagService


def _reset_settings() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def test_rag_settings_are_disabled_by_default(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        DOOWON_POSTGRES_DSN="postgresql+psycopg://test:test@127.0.0.1:5432/test",
        AIDOO_RAG_ENABLED=False,
        AIDOO_RAG_UI_ENABLED=False,
        AIDOO_VECTOR_INDEX_PROVIDER="fake",
        AIDOO_EMBEDDING_PROVIDER="fake",
        AIDOO_OCR_PROVIDER="fake",
        AIDOO_RERANK_PROVIDER="fake",
    )

    assert settings.rag_enabled is False
    assert settings.rag_ui_enabled is False
    assert settings.rag_vector_index_provider == "fake"
    assert settings.rag_embedding_provider == "fake"
    assert settings.rag_ocr_provider == "fake"
    assert settings.rag_rerank_provider == "fake"


def test_rag_settings_accept_legacy_qdrant_alias(monkeypatch) -> None:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", "postgresql+psycopg://test:test@127.0.0.1:5432/test")
    monkeypatch.setenv("DOOWON_QDRANT_URL", "http://127.0.0.1:6333")

    _reset_settings()
    try:
        settings = get_settings()
        assert settings.rag_qdrant_url == "http://127.0.0.1:6333"
    finally:
        _reset_settings()


def test_rag_settings_ignore_deepinfra_alias_validation_when_provider_not_selected() -> None:
    settings = Settings(
        _env_file=None,
        DOOWON_POSTGRES_DSN="postgresql+psycopg://test:test@127.0.0.1:5432/test",
        AIDOO_RAG_ENABLED=False,
        DEEPINFRA_BASE_URL="http://127.0.0.1:8080/openai",
    )

    assert settings.rag_enabled is False
    assert settings.rag_deepinfra_base_url == "http://127.0.0.1:8080/openai"


def test_ensure_rag_enabled_raises_domain_error(monkeypatch) -> None:
    settings = Settings(
        _env_file=None,
        DOOWON_POSTGRES_DSN="postgresql+psycopg://test:test@127.0.0.1:5432/test",
        AIDOO_RAG_ENABLED=False,
    )

    with pytest.raises(rag_application.RagUnavailableError) as exc_info:
        rag_application.ensure_rag_enabled(settings=settings)
    assert exc_info.value.code == "rag.disabled"


def test_workspace_rag_sources_require_ai_app_enablement(monkeypatch) -> None:
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_enabled_app_ids",
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
        "resolve_workspace_enabled_app_ids",
        lambda db, workspace_id: {"ai"},
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


def test_workspace_rag_reindex_requires_ai_enablement(monkeypatch) -> None:
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_enabled_app_ids",
        lambda db, workspace_id: {"planner"},
    )

    with pytest.raises(rag_application.RagAccessDeniedError) as exc_info:
        rag_application.enqueue_workspace_rag_reindex(
            db=object(),
            workspace=SimpleNamespace(id="ws-1"),
            settings=SimpleNamespace(rag_enabled=True),
        )
    assert exc_info.value.code == "rag.access_denied_not_enabled"


def test_workspace_rag_query_defaults_to_text_hits_when_binary_hits_not_requested(monkeypatch) -> None:
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
        "resolve_workspace_enabled_app_ids",
        lambda db, workspace_id: {"ai", "docs"},
    )
    monkeypatch.setattr(rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test")
    monkeypatch.setattr(rag_application, "resolve_default_collection_name", lambda settings: "rag-test")
    monkeypatch.setattr(rag_application, "build_user_rag_post_filter", lambda db, user: lambda hit: True)

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
        "resolve_workspace_enabled_app_ids",
        lambda db, workspace_id: {"ai", "docs"},
    )
    monkeypatch.setattr(rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test")
    monkeypatch.setattr(rag_application, "resolve_default_collection_name", lambda settings: "rag-test")
    monkeypatch.setattr(rag_application, "build_user_rag_post_filter", lambda db, user: lambda hit: True)

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


def test_resolve_default_collection_name_normalizes_embedding_model() -> None:
    settings = SimpleNamespace(
        rag_embedding_provider="deepinfra",
        rag_deepinfra_embedding_model="Qwen/Qwen3-Embedding-8B",
        rag_qdrant_collection_prefix="doowon-rag",
    )
    assert resolve_default_collection_name(settings) == "doowon-rag-qwen-qwen3-embedding-8b"


def test_get_rag_query_service_is_cached(monkeypatch) -> None:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", "postgresql+psycopg://test:test@127.0.0.1:5432/test")
    monkeypatch.setenv("AIDOO_VECTOR_INDEX_PROVIDER", "fake")
    monkeypatch.setenv("AIDOO_EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("AIDOO_RERANK_PROVIDER", "fake")

    _reset_settings()
    reset_rag_runtime_caches()
    try:
        service_a = get_rag_query_service()
        service_b = get_rag_query_service()
        assert service_a is service_b
    finally:
        reset_rag_runtime_caches()
        _reset_settings()


def test_fake_rag_scaffold_supports_sync_and_query() -> None:
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

    sync_result = rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
            source_kind="docs",
            title="Budget Review",
            summary="Quarterly budget risk and spending review",
            text_content=(
                "Budget review for Q2.\n\n"
                "Risk increased because supplier pricing changed.\n\n"
                "Finance team requested tighter approval tracking."
            ),
            visibility_refs=["owner:user-1", "workspace:ws-1"],
            metadata={"origin_ref": "docs:doc-1"},
        ),
        collection="rag-test",
    )

    response = query_service.query(
        RagQueryRequest(
            collection="rag-test",
            workspace_id="ws-1",
            query="budget risk",
            top_k=5,
        )
    )

    assert sync_result.chunk_count >= 1
    assert response.hits
    assert response.hits[0].resource_id == "doc-1"
    assert response.sources_used == ["docs"]


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

    assert initial.chunk_count >= 3
    assert updated.chunk_count == 1
    assert updated.deleted_count >= 1
    assert vector_index.snapshot_projection(collection="rag-prune", chunk_id="doc-1:0") is not None
    assert vector_index.snapshot_projection(collection="rag-prune", chunk_id="doc-1:1") is None


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


def test_rag_query_reranks_once_after_post_filter_oversample() -> None:
    class CountingRerankClient:
        provider_name = "counting-rerank"

        def __init__(self) -> None:
            self.calls = 0

        def healthcheck(self):
            raise NotImplementedError

        def rerank(self, *, query, hits):
            self.calls += 1
            return list(reversed(hits))

    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rerank_client = CountingRerankClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        rerank_client=rerank_client,
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
        collection="rag-post-filter-rerank",
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
        collection="rag-post-filter-rerank",
    )

    response = query_service.query(
        RagQueryRequest(
            collection="rag-post-filter-rerank",
            workspace_id="ws-1",
            query="budget risk urgent",
            top_k=1,
        ),
        post_filter=lambda hit: "owner:user-1" in hit.projection.visibility_refs,
    )

    assert [hit.resource_id for hit in response.hits] == ["doc-allowed"]
    assert rerank_client.calls == 1


def test_rag_query_degrades_when_rerank_fails() -> None:
    class FailingRerankClient:
        provider_name = "failing-rerank"

        def healthcheck(self):
            raise NotImplementedError

        def rerank(self, *, query, hits):
            raise TimeoutError("rerank timeout")

    vector_index = FakeVectorIndexClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=FakeEmbeddingClient(),
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=FakeEmbeddingClient(),
        rerank_client=FailingRerankClient(),
    )
    rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
            source_kind="docs",
            title="Budget Review",
            text_content="budget risk followup",
        ),
        collection="rag-rerank-degrade",
    )

    response = query_service.query(
        RagQueryRequest(
            collection="rag-rerank-degrade",
            workspace_id="ws-1",
            query="budget risk",
        )
    )

    assert [hit.resource_id for hit in response.hits] == ["doc-1"]
    assert response.query_profile["rerank_applied"] is False
    assert response.query_profile["rerank_degraded"] is True


def test_rag_query_reads_legacy_collections_and_redacts_acl_summary() -> None:
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
        legacy_collection_resolver=lambda _request: ("doowon-rag-docs-native-doc",),
    )

    rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-legacy",
            source_kind="docs",
            title="Legacy doc",
            summary="legacy summary",
            text_content="legacy qdrant fallback",
            visibility_refs=[
                "owner:user-1",
                "share_user:user-2",
                "meeting_source:meeting-1",
            ],
        ),
        collection="doowon-rag-docs-native-doc",
    )

    response = query_service.query(
        RagQueryRequest(
            collection="doowon-rag-qwen-qwen3-embedding-8b",
            workspace_id="ws-1",
            query="legacy fallback",
            top_k=1,
        )
    )

    assert [hit.resource_id for hit in response.hits] == ["doc-legacy"]
    assert response.query_profile["legacy_collection_fallback_applied"] is True
    assert all(":" not in value for value in response.hits[0].acl_summary)
    assert response.hits[0].acl_summary == ["owner", "direct share", "meeting source"]


def test_rag_query_degrades_when_grounded_answer_builder_fails() -> None:
    class FailingSynthesizer:
        def synthesize(self, *, query, hits):
            raise RuntimeError("grounded answer failed")

    vector_index = FakeVectorIndexClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=FakeEmbeddingClient(),
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=FakeEmbeddingClient(),
        grounded_answer_synthesizer=FailingSynthesizer(),
    )
    rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
            source_kind="docs",
            title="Budget Review",
            text_content="budget risk followup",
        ),
        collection="rag-grounded-degrade",
    )

    response = query_service.query(
        RagQueryRequest(
            collection="rag-grounded-degrade",
            workspace_id="ws-1",
            query="budget risk",
            answer_mode="grounded-answer",
        )
    )

    assert [hit.resource_id for hit in response.hits] == ["doc-1"]
    assert response.grounded_answer is None
    assert response.query_profile["grounded_answer_degraded"] is True


def test_rag_service_imports_do_not_pull_optional_provider_sdks() -> None:
    api_src = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{api_src}:{existing_pythonpath}" if existing_pythonpath else str(api_src)
    )
    script = """
import sys
import aidoo_api.domains.rag.query_service  # noqa: F401
import aidoo_api.domains.rag.service  # noqa: F401
unexpected = sorted(
    name for name in sys.modules
    if name == "qdrant_client"
    or name.startswith("qdrant_client.")
    or name == "openai"
    or name.startswith("openai.")
)
if unexpected:
    raise SystemExit("\\n".join(unexpected))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_rag_provider_package_import_is_lazy_for_optional_sdks() -> None:
    api_src = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{api_src}:{existing_pythonpath}" if existing_pythonpath else str(api_src)
    )
    script = """
import sys
import aidoo_api.domains.rag.providers  # noqa: F401
unexpected = sorted(
    name for name in sys.modules
    if name == "qdrant_client" or name.startswith("qdrant_client.")
)
if unexpected:
    raise SystemExit("\\n".join(unexpected))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr or result.stdout
