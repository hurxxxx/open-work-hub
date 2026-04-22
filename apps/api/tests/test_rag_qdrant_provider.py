from __future__ import annotations

import warnings

import pytest
from qdrant_client import QdrantClient

from aidoo_api.domains.rag.contracts import RagDeleteRequest, RagProjection, RagQueryRequest
from aidoo_api.domains.rag.providers.fake import FakeEmbeddingClient
from aidoo_api.domains.rag.providers.qdrant import QdrantVectorIndexClient
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.service import RagService

pytestmark = pytest.mark.filterwarnings(
    "ignore:Payload indexes have no effect in the local Qdrant.*"
)


@pytest.fixture
def qdrant_client(tmp_path):
    with warnings.catch_warnings():
        return QdrantClient(path=str(tmp_path / "qdrant-local"))


def test_qdrant_vector_index_smoke_syncs_queries_and_deletes(qdrant_client) -> None:
    vector_index = QdrantVectorIndexClient(client=qdrant_client)
    embedding_client = FakeEmbeddingClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )

    projection = RagProjection(
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        source_kind="docs",
        title="Budget Review",
        summary="Qdrant hybrid retrieval smoke",
        text_content="Budget risk increased after supplier repricing and approval lag.",
        owner_label="Owner A",
        visibility_refs=["workspace:ws-1", "owner:user-1"],
        metadata={"team_id": "team-1", "origin_ref": "docs:doc-1"},
    )

    sync_result = rag_service.sync_projection(projection, collection="rag-qdrant-smoke")
    collection = qdrant_client.get_collection("rag-qdrant-smoke")

    assert sync_result.chunk_count >= 1
    assert "dense" in collection.config.params.vectors
    assert "sparse" in (collection.config.params.sparse_vectors or {})

    response = query_service.query(
        RagQueryRequest(
            collection="rag-qdrant-smoke",
            workspace_id="ws-1",
            query="budget approval risk",
            source_kinds=["docs"],
            filters={
                "visibility_refs_contains": "owner:user-1",
                "team_id": "team-1",
            },
        )
    )

    assert response.hits
    assert response.hits[0].resource_id == "doc-1"
    assert response.hits[0].resource_type == "doc"
    assert response.hits[0].workspace_id == "ws-1"
    assert response.hits[0].metadata["resource_id"] == "doc-1"

    delete_result = rag_service.delete_projection(
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        collection="rag-qdrant-smoke",
    )
    after_delete = query_service.query(
        RagQueryRequest(
            collection="rag-qdrant-smoke",
            workspace_id="ws-1",
            query="budget approval risk",
            source_kinds=["docs"],
        )
    )

    assert delete_result.deleted_count >= 1
    assert after_delete.hits == []


def test_qdrant_vector_index_detects_existing_dense_dimension_mismatch(qdrant_client) -> None:
    vector_index = QdrantVectorIndexClient(client=qdrant_client)

    vector_index.ensure_collection(
        collection="rag-qdrant-mismatch",
        dense_dimensions=8,
        sparse_enabled=True,
    )

    with pytest.raises(RuntimeError, match="dense vector size mismatch"):
        vector_index.ensure_collection(
            collection="rag-qdrant-mismatch",
            dense_dimensions=16,
            sparse_enabled=True,
        )


def test_qdrant_vector_index_handles_missing_collection_for_delete_and_query(qdrant_client) -> None:
    vector_index = QdrantVectorIndexClient(client=qdrant_client)
    embedding_client = FakeEmbeddingClient()
    query_service = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )

    deleted_count = vector_index.delete_resource(
        request=RagDeleteRequest(
            collection="rag-qdrant-missing",
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-missing",
        )
    )
    response = query_service.query(
        RagQueryRequest(
            collection="rag-qdrant-missing",
            workspace_id="ws-1",
            query="missing collection",
            source_kinds=["docs"],
        )
    )

    assert deleted_count == 0
    assert response.hits == []
