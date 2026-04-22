from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

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
