from __future__ import annotations

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.rag.contracts import RagProjection, RagQueryRequest
from aidoo_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.service import RagService


def _reset_settings() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def test_rag_settings_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setenv("DOOWON_POSTGRES_DSN", "postgresql+psycopg://test:test@127.0.0.1:5432/test")
    for env_name in (
        "AIDOO_RAG_ENABLED",
        "DOOWON_AIDOO_RAG_ENABLED",
        "DOOWON_API_AIDOO_RAG_ENABLED",
        "AIDOO_RAG_UI_ENABLED",
        "DOOWON_AIDOO_RAG_UI_ENABLED",
        "DOOWON_API_AIDOO_RAG_UI_ENABLED",
    ):
        monkeypatch.delenv(env_name, raising=False)

    _reset_settings()
    try:
        settings = get_settings()
        assert settings.rag_enabled is False
        assert settings.rag_ui_enabled is False
        assert settings.rag_vector_index_provider == "fake"
        assert settings.rag_embedding_provider == "fake"
        assert settings.rag_ocr_provider == "fake"
        assert settings.rag_rerank_provider == "fake"
    finally:
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
