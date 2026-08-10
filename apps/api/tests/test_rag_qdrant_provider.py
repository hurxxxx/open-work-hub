from __future__ import annotations

from datetime import UTC, datetime
import warnings
from types import SimpleNamespace
import uuid

import httpx
import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient, models

from open_alm_api.domains.document_processing import EvidenceBlock
from open_alm_api.domains.files.rag_projection import (
    FileExtractionArtifact,
    build_file_rag_projection,
)
from open_alm_api.domains.rag.contracts import (
    RagDeleteRequest,
    RagProjection,
    RagQueryRequest,
    RagScopeKind,
    RagUpsertRequest,
    RagVectorRecord,
    RagVectorSearchMode,
    RagVectorSearchRequest,
)
from open_alm_api.domains.rag.providers import RagProviderConfigurationError
from open_alm_api.domains.rag.providers.fake import FakeEmbeddingClient
from open_alm_api.domains.rag.providers.openai_compatible import (
    InferenceGatewayOcrClient,
    OpenAICompatibleEmbeddingClient,
    OpenAICompatibleRerankClient,
    RagProviderTimeoutError,
    RagProviderTransientError,
    _clear_inference_gateway_health_cache,
)
from open_alm_api.domains.rag.providers.qdrant import QdrantVectorIndexClient
from open_alm_api.domains.rag.query_service import RagQueryService
from open_alm_api.domains.rag.runtime import (
    PARTITIONED_RAG_GENERATION_SCHEMA_VERSION,
    resolve_partitioned_rag_collection_alias,
    resolve_partitioned_rag_collection_name,
)
from open_alm_api.domains.rag.service import RagService
from open_alm_api.domains.retrieval.projection_identity import canonical_vector_point_id

pytestmark = pytest.mark.filterwarnings(
    "ignore:Payload indexes have no effect in the local Qdrant.*"
)


@pytest.fixture(autouse=True)
def clear_inference_gateway_health_cache():
    _clear_inference_gateway_health_cache()
    yield
    _clear_inference_gateway_health_cache()


@pytest.fixture
def qdrant_client(tmp_path):
    with warnings.catch_warnings():
        return QdrantClient(path=str(tmp_path / "qdrant-local"))


@pytest.mark.slow
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
    assert rag_service.delete_collection(collection="rag-qdrant-smoke") is True
    assert qdrant_client.collection_exists("rag-qdrant-smoke") is False


@pytest.mark.slow
def test_file_projection_survives_default_text_modality_filter(qdrant_client) -> None:
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
    file = SimpleNamespace(
        id="file-1",
        workspace_id="ws-1",
        corpus_id=None,
        corpus=None,
        folder_id=None,
        owner_id="user-1",
        owner=None,
        filename="heater-system.pptx",
        content_type=("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        size_bytes=128,
        visibility="private",
    )
    text = "히터 시스템의 정상 작동 전압 범위는 9V에서 16V입니다."
    projection = build_file_rag_projection(
        file=file,
        artifact=FileExtractionArtifact(
            content_checksum="a" * 64,
            text=text,
            blocks=[
                EvidenceBlock(
                    document_id=file.id,
                    block_id=f"{file.id}:slide:1:text:1",
                    locator_kind="slide",
                    locator_label="Slide 1",
                    section_path="Slide 1",
                    block_kind="text",
                    text=text,
                )
            ],
            metadata={"parser_version": "files-retrieval-v1"},
        ),
    )

    sync_result = rag_service.sync_projection(
        projection,
        collection="rag-qdrant-files-text-modality",
    )
    response = query_service.query(
        RagQueryRequest(
            collection="rag-qdrant-files-text-modality",
            workspace_id="ws-1",
            query="정상 작동 전압",
            source_kinds=["files"],
            filters={"content_modality": "text"},
        )
    )

    assert sync_result.chunk_count == 1
    assert response.query_profile["vector_hit_count"] == 1
    assert response.hits[0].resource_type == "file_manager_file"
    assert response.hits[0].resource_id == "file-1"


@pytest.mark.slow
def test_qdrant_point_ids_keep_same_chunk_id_across_resources(qdrant_client) -> None:
    vector_index = QdrantVectorIndexClient(client=qdrant_client)
    embedding_client = FakeEmbeddingClient()
    rag_service = RagService(vector_index=vector_index, embedding_client=embedding_client)
    collection = "rag-qdrant-resource-scoped-points"
    shared_chunk = {
        "chunk_id": "workbook-row:Sheet1:12",
        "text": "same local row id but first document content",
        "index_text": "same local row id but first document content",
    }

    first = RagProjection(
        workspace_id="ws-1",
        resource_type="plugin_document",
        resource_id="doc-1",
        source_kind="plugin_source",
        title="First plugin document",
        chunks=[shared_chunk],
    )
    second = RagProjection(
        workspace_id="ws-1",
        resource_type="plugin_document",
        resource_id="doc-2",
        source_kind="plugin_source",
        title="Second plugin document",
        chunks=[{**shared_chunk, "text": "same local row id but second document content"}],
    )

    rag_service.sync_projection(first, collection=collection)
    rag_service.sync_projection(second, collection=collection)

    points, _ = qdrant_client.scroll(collection_name=collection, limit=10, with_payload=True)
    resource_ids = {point.payload["resource_id"] for point in points}

    assert len(points) == 2
    assert resource_ids == {"doc-1", "doc-2"}


@pytest.mark.slow
def test_legacy_projection_keeps_existing_scope_bound_point_id(qdrant_client) -> None:
    collection = "rag-qdrant-legacy-point-id"
    rag_service = RagService(
        vector_index=QdrantVectorIndexClient(client=qdrant_client),
        embedding_client=FakeEmbeddingClient(),
    )

    rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-legacy",
            resource_type="native_doc",
            resource_id="doc-legacy",
            source_kind="docs",
            chunks=[{"chunk_id": "chunk-0", "text": "legacy identity"}],
        ),
        collection=collection,
    )
    points, _ = qdrant_client.scroll(collection_name=collection, limit=10)
    legacy_identity = ":".join(
        (
            collection,
            "workspace",
            "ws-legacy",
            "docs",
            "native_doc",
            "doc-legacy",
            "chunk-0",
        )
    )

    assert len(points) == 1
    assert str(points[0].id) == str(uuid.uuid5(uuid.NAMESPACE_URL, legacy_identity))


@pytest.mark.slow
def test_default_generation_does_not_mix_partitioned_point_identity(qdrant_client) -> None:
    collection = "rag-qdrant-versioned-legacy-generation"
    rag_service = RagService(
        vector_index=QdrantVectorIndexClient(client=qdrant_client),
        embedding_client=FakeEmbeddingClient(),
    )

    rag_service.sync_projection(
        RagProjection(
            retrieval_partition_id="11111111-1111-1111-1111-111111111111",
            projection_version=3,
            workspace_id="ws-legacy",
            resource_type="native_doc",
            resource_id="doc-versioned",
            source_kind="docs",
            chunks=[{"chunk_id": "chunk-0", "text": "versioned legacy identity"}],
        ),
        collection=collection,
    )
    points, _ = qdrant_client.scroll(
        collection_name=collection,
        limit=10,
        with_payload=True,
    )
    legacy_identity = ":".join(
        (
            collection,
            "workspace",
            "ws-legacy",
            "docs",
            "native_doc",
            "doc-versioned",
            "chunk-0",
        )
    )

    assert len(points) == 1
    assert str(points[0].id) == str(uuid.uuid5(uuid.NAMESPACE_URL, legacy_identity))
    assert "retrieval_partition_id" not in points[0].payload
    assert "projection_version" not in points[0].payload


@pytest.mark.parametrize("generation_collection", [None, "", "   "])
def test_partitioned_generation_requires_explicit_collection_binding(
    generation_collection,
) -> None:
    with pytest.raises(RagProviderConfigurationError, match="explicit generation_collection"):
        QdrantVectorIndexClient(
            client=object(),
            partitioned_generation=True,
            generation_collection=generation_collection,
        )


def test_partitioned_generation_rejects_operations_outside_bound_collection() -> None:
    bound_collection = "rag-partitioned-generation-v2"
    wrong_collection = "rag-default-generation"
    partition_id = "11111111-1111-1111-1111-111111111111"
    projection = RagProjection(
        retrieval_partition_id=partition_id,
        projection_version=1,
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        source_kind="docs",
    )
    record = RagVectorRecord(
        chunk_id="chunk-0",
        text="partitioned content",
        embedding=[0.1, 0.2],
        projection=projection,
    )
    upsert_request = RagUpsertRequest(
        collection=wrong_collection,
        projection=projection,
        chunks=[],
    )
    delete_request = RagDeleteRequest(
        collection=wrong_collection,
        retrieval_partition_id=partition_id,
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
    )
    query_request = RagVectorSearchRequest(
        collection=wrong_collection,
        query="partitioned query",
        query_embedding=[0.1, 0.2],
        retrieval_partition_ids=[partition_id],
    )
    vector_index = QdrantVectorIndexClient(
        client=object(),
        partitioned_generation=True,
        generation_collection=bound_collection,
    )

    operations = (
        lambda: vector_index.ensure_collection(
            collection=wrong_collection,
            dense_dimensions=2,
        ),
        lambda: vector_index.upsert_chunks(request=upsert_request, records=[record]),
        lambda: vector_index.query(request=query_request),
        lambda: vector_index.delete_resource(request=delete_request),
        lambda: vector_index.delete_chunks_at_or_after(
            request=delete_request,
            chunk_index=1,
        ),
        lambda: vector_index.delete_collection(collection=wrong_collection),
    )

    for operation in operations:
        with pytest.raises(RagProviderConfigurationError, match="bound to collection"):
            operation()


def test_partitioned_upsert_requires_projection_fence_on_request_and_records() -> None:
    collection = "rag-partitioned-generation-v2"
    unfenced_projection = RagProjection(
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        source_kind="docs",
    )
    fenced_projection = RagProjection(
        retrieval_partition_id="11111111-1111-1111-1111-111111111111",
        projection_version=1,
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
        source_kind="docs",
    )
    vector_index = QdrantVectorIndexClient(
        client=object(),
        partitioned_generation=True,
        generation_collection=collection,
    )

    with pytest.raises(RagProviderConfigurationError, match="upserts require"):
        vector_index.upsert_chunks(
            request=RagUpsertRequest(
                collection=collection,
                projection=unfenced_projection,
                chunks=[],
            ),
            records=[],
        )

    with pytest.raises(RagProviderConfigurationError, match="upserts require"):
        vector_index.upsert_chunks(
            request=RagUpsertRequest(
                collection=collection,
                projection=fenced_projection,
                chunks=[],
            ),
            records=[
                RagVectorRecord(
                    chunk_id="chunk-0",
                    text="unfenced record",
                    embedding=[0.1, 0.2],
                    projection=unfenced_projection,
                )
            ],
        )


def test_partitioned_query_and_deletes_require_partition_ids() -> None:
    collection = "rag-partitioned-generation-v2"
    vector_index = QdrantVectorIndexClient(
        client=object(),
        partitioned_generation=True,
        generation_collection=collection,
    )

    with pytest.raises(RagProviderConfigurationError, match="retrieval_partition_ids"):
        vector_index.query(
            request=RagVectorSearchRequest(
                collection=collection,
                query="missing partition filter",
                query_embedding=[],
            )
        )

    delete_request = RagDeleteRequest(
        collection=collection,
        workspace_id="ws-1",
        resource_type="doc",
        resource_id="doc-1",
    )
    for delete_operation in (
        lambda: vector_index.delete_resource(request=delete_request),
        lambda: vector_index.delete_chunks_at_or_after(
            request=delete_request,
            chunk_index=1,
        ),
    ):
        with pytest.raises(RagProviderConfigurationError, match="retrieval_partition_id"):
            delete_operation()


def test_legacy_delete_filter_remains_scope_bound_for_versioned_projection() -> None:
    class _CapturingClient:
        def __init__(self) -> None:
            self.count_filter = None

        def collection_exists(self, *, collection_name: str) -> bool:
            del collection_name
            return True

        def count(self, *, count_filter, **kwargs):
            del kwargs
            self.count_filter = count_filter
            return SimpleNamespace(count=0)

    client = _CapturingClient()
    vector_index = QdrantVectorIndexClient(client=client)

    vector_index.delete_resource(
        request=RagDeleteRequest(
            collection="rag-legacy",
            retrieval_partition_id="11111111-1111-1111-1111-111111111111",
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
        )
    )

    assert client.count_filter is not None
    keys = {condition.key for condition in client.count_filter.must}
    assert keys == {"scope_kind", "workspace_id", "resource_type", "resource_id"}
    assert "retrieval_partition_id" not in keys


@pytest.mark.slow
def test_partition_aware_points_keep_canonical_id_across_scope_move(qdrant_client) -> None:
    collection = "rag-qdrant-partition-aware-points"
    vector_index = QdrantVectorIndexClient(client=qdrant_client).for_partitioned_generation(
        collection=collection
    )
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=FakeEmbeddingClient(),
    )
    partition_id = "11111111-1111-1111-1111-111111111111"
    shared_chunk = {
        "chunk_id": "stable-chunk-0",
        "text": "stable content across an access-scope move",
        "metadata": {"chunk_index": 0},
    }

    rag_service.sync_projection(
        RagProjection(
            retrieval_partition_id=partition_id,
            projection_version=1,
            scope_kind=RagScopeKind.WORKSPACE,
            workspace_id="ws-before",
            resource_type="native_doc",
            resource_id="doc-1",
            source_kind="docs",
            chunks=[
                shared_chunk,
                {
                    "chunk_id": "stale-chunk-1",
                    "text": "this tail is removed after the move",
                    "metadata": {"chunk_index": 1},
                },
            ],
        ),
        collection=collection,
    )
    before, _ = qdrant_client.scroll(
        collection_name=collection,
        limit=10,
        with_payload=True,
    )
    before_id = next(point.id for point in before if point.payload["chunk_id"] == "stable-chunk-0")

    updated = rag_service.sync_projection(
        RagProjection(
            retrieval_partition_id=partition_id,
            projection_version=2,
            scope_kind=RagScopeKind.COMPANY,
            workspace_id=None,
            resource_type="native_doc",
            resource_id="doc-1",
            source_kind="docs",
            visibility_refs=["company_public"],
            chunks=[shared_chunk],
        ),
        collection=collection,
    )
    after, _ = qdrant_client.scroll(
        collection_name=collection,
        limit=10,
        with_payload=True,
    )

    assert len(after) == 1
    assert updated.deleted_count == 1
    assert (
        str(before_id)
        == str(after[0].id)
        == canonical_vector_point_id(
            resource_type="native_doc",
            resource_id="doc-1",
            chunk_id="stable-chunk-0",
        )
    )
    assert after[0].payload["retrieval_partition_id"] == partition_id
    assert after[0].payload["projection_version"] == 2
    assert after[0].payload["scope_kind"] == "company"


def test_qdrant_partition_filter_is_match_any_and_replaces_legacy_scope_filter() -> None:
    class _CapturingClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def collection_exists(self, collection_name: str) -> bool:
            del collection_name
            return True

        def query_points(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(points=[])

    client = _CapturingClient()
    vector_index = QdrantVectorIndexClient(
        client=client,
        partitioned_generation=True,
        generation_collection="rag-partition-aware",
    )
    partition_ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]

    vector_index.query(
        request=RagVectorSearchRequest(
            collection="rag-partition-aware",
            query="partition query",
            query_embedding=[0.1, 0.2],
            retrieval_partition_ids=partition_ids,
            source_kinds=["docs"],
            search_mode=RagVectorSearchMode.DENSE,
        )
    )

    conditions = client.calls[0]["query_filter"].must
    partition_condition = next(
        condition for condition in conditions if condition.key == "retrieval_partition_id"
    )
    assert isinstance(partition_condition.match, models.MatchAny)
    assert partition_condition.match.any == partition_ids
    assert {condition.key for condition in conditions}.isdisjoint({"scope_kind", "workspace_id"})


def test_legacy_qdrant_generation_rejects_partition_filter() -> None:
    class _ExistingCollectionClient:
        def collection_exists(self, collection_name: str) -> bool:
            del collection_name
            return True

    vector_index = QdrantVectorIndexClient(client=_ExistingCollectionClient())

    with pytest.raises(RagProviderConfigurationError, match="partition-aware"):
        vector_index.query(
            request=RagVectorSearchRequest(
                collection="rag-legacy",
                query="partition query",
                query_embedding=[0.1, 0.2],
                retrieval_partition_ids=["11111111-1111-1111-1111-111111111111"],
                search_mode=RagVectorSearchMode.DENSE,
            )
        )


@pytest.mark.parametrize("partition_ids", [[], [""], ["   "]])
def test_partition_filter_rejects_empty_or_blank_partition_ids(partition_ids) -> None:
    with pytest.raises(ValidationError, match="retrieval_partition_ids"):
        RagVectorSearchRequest(
            collection="rag-partition-aware",
            query="partition query",
            query_embedding=[0.1, 0.2],
            retrieval_partition_ids=partition_ids,
        )


def test_qdrant_filter_pushes_down_metadata_datetime_range() -> None:
    vector_index = QdrantVectorIndexClient(
        client=SimpleNamespace(),
        partitioned_generation=True,
        generation_collection="rag-filter-test",
    )
    lower = datetime(2026, 8, 1, tzinfo=UTC)
    upper = datetime(2026, 8, 3, tzinfo=UTC)

    query_filter = vector_index._build_query_filter(
        RagVectorSearchRequest(
            collection="rag-filter-test",
            query="냉각",
            query_embedding=[0.1],
            retrieval_partition_ids=["11111111-1111-1111-1111-111111111111"],
            metadata_filter={
                "metadata.authored_at": {"gte": lower, "lte": upper},
            },
        )
    )

    authored_condition = next(
        condition
        for condition in query_filter.must or []
        if isinstance(condition, models.FieldCondition) and condition.key == "metadata.authored_at"
    )
    assert authored_condition.range == models.DatetimeRange(gte=lower, lte=upper)


def test_qdrant_vector_index_detects_existing_dense_dimension_mismatch(qdrant_client) -> None:
    vector_index = QdrantVectorIndexClient(client=qdrant_client)

    vector_index.ensure_collection(
        collection="rag-qdrant-mismatch",
        dense_dimensions=8,
        sparse_enabled=True,
    )

    with pytest.raises(RagProviderConfigurationError, match="dense vector size mismatch"):
        vector_index.ensure_collection(
            collection="rag-qdrant-mismatch",
            dense_dimensions=16,
            sparse_enabled=True,
        )


def test_qdrant_collection_indexes_projection_fence_payload_fields() -> None:
    class _CapturingClient:
        def __init__(self) -> None:
            self.indexes: list[tuple[str, models.PayloadSchemaType]] = []

        def collection_exists(self, *, collection_name: str) -> bool:
            del collection_name
            return False

        def create_collection(self, **kwargs) -> None:
            del kwargs

        def create_payload_index(
            self,
            *,
            collection_name: str,
            field_name: str,
            field_schema: models.PayloadSchemaType,
        ) -> None:
            del collection_name
            self.indexes.append((field_name, field_schema))

    client = _CapturingClient()
    legacy_client = _CapturingClient()

    QdrantVectorIndexClient(
        client=client,
        partitioned_generation=True,
        generation_collection="rag-projection-fence-indexes",
    ).ensure_collection(
        collection="rag-projection-fence-indexes",
        dense_dimensions=8,
    )
    QdrantVectorIndexClient(client=legacy_client).ensure_collection(
        collection="rag-legacy-indexes",
        dense_dimensions=8,
    )

    assert ("retrieval_partition_id", models.PayloadSchemaType.KEYWORD) in client.indexes
    assert ("projection_version", models.PayloadSchemaType.INTEGER) in client.indexes
    optional_metadata_indexes = {
        "metadata.origin_source_kind_filter",
        "metadata.author_filter",
        "metadata.department_filter",
        "metadata.document_type_filter",
        "metadata.authored_at",
    }
    assert optional_metadata_indexes.isdisjoint(field_name for field_name, _ in client.indexes)
    assert all(
        field_name
        not in {
            "retrieval_partition_id",
            "projection_version",
            "metadata.origin_source_kind_filter",
            "metadata.author_filter",
            "metadata.department_filter",
            "metadata.document_type_filter",
            "metadata.authored_at",
        }
        for field_name, _ in legacy_client.indexes
    )


def _partitioned_v1_payload_schema() -> dict[str, dict[str, str]]:
    return {
        "retrieval_partition_id": {"data_type": "keyword"},
        "projection_version": {"data_type": "integer"},
        "scope_kind": {"data_type": "keyword"},
        "workspace_id": {"data_type": "keyword"},
        "resource_type": {"data_type": "keyword"},
        "resource_id": {"data_type": "keyword"},
        "source_kind": {"data_type": "keyword"},
        "visibility_refs": {"data_type": "keyword"},
    }


class _ExistingPartitionedCollectionClient:
    def __init__(self, payload_schema: dict[str, dict[str, str]]) -> None:
        self.payload_schema = payload_schema
        self.index_calls: list[str] = []

    def collection_exists(self, *, collection_name: str) -> bool:
        del collection_name
        return True

    def get_collection(self, *, collection_name: str) -> object:
        del collection_name
        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={"dense": SimpleNamespace(size=8)},
                    sparse_vectors={"sparse": object()},
                )
            ),
            payload_schema=self.payload_schema,
        )

    def create_payload_index(self, *, field_name: str, **_kwargs: object) -> None:
        self.index_calls.append(field_name)


def test_partitioned_existing_collection_is_never_mutated_in_place() -> None:
    client = _ExistingPartitionedCollectionClient(_partitioned_v1_payload_schema())
    collection = "rag-partitioned-v1-existing"

    QdrantVectorIndexClient(
        client=client,  # type: ignore[arg-type]
        partitioned_generation=True,
        generation_collection=collection,
    ).ensure_collection(collection=collection, dense_dimensions=8)

    assert client.index_calls == []


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("resource_id", None),
        ("projection_version", {"data_type": "keyword"}),
    ],
)
def test_partitioned_existing_collection_fails_closed_on_payload_schema_drift(
    field_name: str,
    replacement: dict[str, str] | None,
) -> None:
    payload_schema = _partitioned_v1_payload_schema()
    if replacement is None:
        payload_schema.pop(field_name)
    else:
        payload_schema[field_name] = replacement

    client = _ExistingPartitionedCollectionClient(payload_schema)
    collection = "rag-partitioned-v1-drifted"

    with pytest.raises(RagProviderConfigurationError, match=field_name):
        QdrantVectorIndexClient(
            client=client,  # type: ignore[arg-type]
            partitioned_generation=True,
            generation_collection=collection,
        ).ensure_collection(collection=collection, dense_dimensions=8)

    assert client.index_calls == []


def test_optional_metadata_filters_do_not_change_the_v1_generation_schema() -> None:
    settings = SimpleNamespace(
        rag_qdrant_collection_prefix="open-alm-test-rag",
        rag_embedding_provider="fake",
        rag_local_embedding_model="unused-for-fake",
    )

    assert PARTITIONED_RAG_GENERATION_SCHEMA_VERSION == 1
    assert resolve_partitioned_rag_collection_alias(settings).endswith("-v1")
    assert resolve_partitioned_rag_collection_name(
        settings,
        generation="payload-indexes",
    ).endswith("-v1-payload-indexes")


@pytest.mark.parametrize(
    "projection_fields",
    [
        {"retrieval_partition_id": "11111111-1111-1111-1111-111111111111"},
        {"projection_version": 1},
    ],
)
def test_rag_projection_requires_complete_partition_version_fence(projection_fields) -> None:
    with pytest.raises(ValidationError, match="must be provided together"):
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
            source_kind="docs",
            **projection_fields,
        )


def test_openai_compatible_embedding_client_batches_large_inputs() -> None:
    class _EmbeddingClient(OpenAICompatibleEmbeddingClient):
        def __init__(self) -> None:
            super().__init__(
                base_url="http://inference-gateway.test/v1",
                api_key="test",
                model="embedding-model",
                max_batch_size=2,
            )
            self.calls: list[list[str]] = []

        def _post_json(self, path, payload, timeout_seconds=None):  # noqa: ANN001
            del timeout_seconds
            assert path == "/embeddings"
            batch = list(payload["input"])
            self.calls.append(batch)
            return {
                "data": [
                    {"index": index, "embedding": [float(len(text)), float(index)]}
                    for index, text in enumerate(batch)
                ]
            }

    client = _EmbeddingClient()
    embeddings = client.embed_texts(["a", "bb", "ccc", "dddd", "eeeee"])

    assert client.calls == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert embeddings == [[1.0, 0.0], [2.0, 1.0], [3.0, 0.0], [4.0, 1.0], [5.0, 0.0]]


@pytest.mark.parametrize(
    ("client", "task", "model"),
    [
        (
            OpenAICompatibleEmbeddingClient(
                base_url="http://inference-gateway.test/v1",
                api_key="test",
                model="embedding-model",
            ),
            "embedding",
            "embedding-model",
        ),
        (
            OpenAICompatibleRerankClient(
                base_url="http://inference-gateway.test/v1",
                api_key="test",
                model="reranker-model",
            ),
            "reranker",
            "reranker-model",
        ),
    ],
)
def test_inference_gateway_healthcheck_probes_loaded_task(client, task, model) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "ready": True,
                "models": {task: {"model": model, "loaded": True}},
            },
        )

    client._http.close()
    client._http = httpx.Client(transport=httpx.MockTransport(handler))

    health = client.healthcheck()

    assert health.ready is True
    assert requested_urls == ["http://inference-gateway.test/health"]
    client.close()


def test_inference_gateway_healthcheck_reuses_one_gateway_probe_across_tasks() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "ready": True,
                "models": {
                    "embedding": {"model": "embedding-model", "loaded": True},
                    "reranker": {"model": "reranker-model", "loaded": True},
                    "docling": {"model": "docling", "loaded": True},
                },
            },
        )

    transport = httpx.MockTransport(handler)
    clients = [
        OpenAICompatibleEmbeddingClient(
            base_url="http://shared-gateway.test/v1",
            api_key="test",
            model="embedding-model",
        ),
        OpenAICompatibleRerankClient(
            base_url="http://shared-gateway.test/v1",
            api_key="test",
            model="reranker-model",
        ),
        InferenceGatewayOcrClient(
            base_url="http://shared-gateway.test/v1",
            api_key="test",
        ),
    ]
    for client in clients:
        client._http.close()
        client._http = httpx.Client(transport=transport)

    assert all(client.healthcheck().ready for client in clients)
    assert request_count == 1

    for client in clients:
        client.close()


def test_openai_compatible_reranker_score_semantics_default_is_unknown() -> None:
    client = OpenAICompatibleRerankClient(
        base_url="http://inference-gateway.test/v1",
        api_key="test",
        model="reranker-model",
    )

    assert client.score_semantics == "unknown"

    client.close()


def test_inference_gateway_healthcheck_reports_provider_outage() -> None:
    client = OpenAICompatibleEmbeddingClient(
        base_url="http://inference-gateway.test/v1",
        api_key="test",
        model="embedding-model",
    )
    client._http.close()
    client._http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, text="No server is available")
        )
    )

    health = client.healthcheck()

    assert health.ready is False
    assert health.detail is not None
    assert "status 503" in health.detail
    client.close()


@pytest.mark.parametrize(
    "models",
    [
        {},
        {"embedding": {"model": "embedding-model", "loaded": False}},
        {"embedding": {"model": "unexpected-model", "loaded": True}},
    ],
)
def test_inference_gateway_healthcheck_rejects_unavailable_task(models) -> None:
    client = OpenAICompatibleEmbeddingClient(
        base_url="http://inference-gateway.test/v1",
        api_key="test",
        model="embedding-model",
    )
    client._http.close()
    client._http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ready": True, "models": models})
        )
    )

    health = client.healthcheck()

    assert health.ready is False
    client.close()


def test_inference_gateway_ocr_healthcheck_requires_docling() -> None:
    client = InferenceGatewayOcrClient(
        base_url="http://inference-gateway.test/v1",
        api_key="test",
    )
    client._http.close()
    client._http = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "ready": True,
                    "models": {
                        "docling": {
                            "model": "docling.document_converter.DocumentConverter",
                            "loaded": True,
                        }
                    },
                },
            )
        )
    )

    health = client.healthcheck()

    assert health.ready is True
    client.close()


def test_qdrant_query_opens_circuit_breaker_after_repeated_failures() -> None:
    class _FailingClient:
        def __init__(self) -> None:
            self.query_calls = 0

        def collection_exists(self, collection_name: str) -> bool:
            del collection_name
            return True

        def query_points(self, **kwargs):
            del kwargs
            self.query_calls += 1
            raise TimeoutError("qdrant timed out")

    failing_client = _FailingClient()
    vector_index = QdrantVectorIndexClient(client=failing_client)
    request = RagVectorSearchRequest(
        collection="rag-qdrant-breaker",
        workspace_id="ws-1",
        query="budget risk",
        query_embedding=[0.1, 0.2, 0.3],
        source_kinds=["docs"],
        top_k=5,
    )

    for _ in range(3):
        with pytest.raises(RagProviderTimeoutError):
            vector_index.query(request=request)

    with pytest.raises(RagProviderTransientError, match="temporarily unavailable"):
        vector_index.query(request=request)

    assert failing_client.query_calls == 3
    health = vector_index.healthcheck()
    assert health.ready is False
    assert health.detail is not None
    assert "temporarily unavailable" in health.detail


def test_qdrant_dense_mode_skips_legacy_sparse_prefetch() -> None:
    class _CapturingClient:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def collection_exists(self, collection_name: str) -> bool:
            del collection_name
            return True

        def query_points(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(points=[])

    client = _CapturingClient()
    vector_index = QdrantVectorIndexClient(client=client)

    vector_index.query(
        request=RagVectorSearchRequest(
            collection="rag-dense",
            workspace_id="ws-1",
            query="hybrid",
            query_embedding=[0.1, 0.2],
            search_mode=RagVectorSearchMode.DENSE,
        )
    )
    vector_index.query(
        request=RagVectorSearchRequest(
            collection="rag-hybrid",
            workspace_id="ws-1",
            query="hybrid",
            query_embedding=[0.1, 0.2],
        )
    )

    assert "prefetch" not in client.calls[0]
    assert client.calls[0]["using"] == "dense"
    assert len(client.calls[1]["prefetch"]) == 2
