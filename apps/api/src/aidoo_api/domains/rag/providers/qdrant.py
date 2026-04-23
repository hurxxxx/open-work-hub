from __future__ import annotations

from hashlib import blake2b
import time
from typing import Any
import uuid

from qdrant_client import QdrantClient, models

from aidoo_api.domains.rag.contracts import (
    RagDeleteRequest,
    RagProjection,
    RagProviderHealth,
    RagUpsertRequest,
    RagVectorRecord,
    RagVectorSearchHit,
    RagVectorSearchRequest,
)
from aidoo_api.domains.rag.metrics import (
    record_provider_error,
    record_provider_timeout,
    record_vector_query_latency,
)
from aidoo_api.domains.rag.providers.base import RagProviderConfigurationError

_DENSE_VECTOR_NAME = "dense"
_SPARSE_VECTOR_NAME = "sparse"
_PAYLOAD_INDEX_FIELDS = (
    "workspace_id",
    "resource_type",
    "resource_id",
    "source_kind",
    "visibility_refs",
)
_RESERVED_PAYLOAD_FIELDS = {
    "workspace_id",
    "resource_type",
    "resource_id",
    "source_kind",
    "visibility_refs_contains",
}


class QdrantVectorIndexClient:
    provider_name = "qdrant"

    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        client: QdrantClient | None = None,
        dense_vector_name: str = _DENSE_VECTOR_NAME,
        sparse_vector_name: str = _SPARSE_VECTOR_NAME,
    ) -> None:
        if client is None and not url:
            raise ValueError("QdrantVectorIndexClient requires either client or url")
        self._client = client or QdrantClient(url=url, api_key=api_key or None)
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name
        self._indexed_collections: set[str] = set()

    def healthcheck(self) -> RagProviderHealth:
        try:
            self._client.get_collections()
        except Exception as error:
            return RagProviderHealth(
                provider_name=self.provider_name,
                ready=False,
                detail=str(error),
            )
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def ensure_collection(
        self,
        *,
        collection: str,
        dense_dimensions: int,
        sparse_enabled: bool = True,
    ) -> None:
        if dense_dimensions <= 0:
            raise ValueError("dense_dimensions must be greater than zero for Qdrant collections")

        if not self._client.collection_exists(collection_name=collection):
            sparse_vectors_config = None
            if sparse_enabled:
                sparse_vectors_config = {
                    self._sparse_vector_name: models.SparseVectorParams(
                        index=models.SparseIndexParams()
                    )
                }
            try:
                self._client.create_collection(
                    collection_name=collection,
                    vectors_config={
                        self._dense_vector_name: models.VectorParams(
                            size=dense_dimensions,
                            distance=models.Distance.COSINE,
                        )
                    },
                    sparse_vectors_config=sparse_vectors_config,
                )
            except Exception:
                if not self._client.collection_exists(collection_name=collection):
                    raise
                self._validate_collection_schema(
                    collection=collection,
                    dense_dimensions=dense_dimensions,
                    sparse_enabled=sparse_enabled,
                )
        else:
            self._validate_collection_schema(
                collection=collection,
                dense_dimensions=dense_dimensions,
                sparse_enabled=sparse_enabled,
            )

        if collection not in self._indexed_collections:
            for field_name in _PAYLOAD_INDEX_FIELDS:
                self._client.create_payload_index(
                    collection_name=collection,
                    field_name=field_name,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            self._indexed_collections.add(collection)

    def upsert_chunks(
        self,
        *,
        request: RagUpsertRequest,
        records: list[RagVectorRecord],
    ) -> int:
        if not records:
            return 0

        self._client.upsert(
            collection_name=request.collection,
            points=[self._to_point(request.collection, record) for record in records],
            wait=True,
        )
        return len(records)

    def delete_resource(self, *, request: RagDeleteRequest) -> int:
        if not self._client.collection_exists(collection_name=request.collection):
            return 0
        resource_filter = self._resource_filter(
            workspace_id=request.workspace_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )
        deleted_count = self._client.count(
            collection_name=request.collection,
            count_filter=resource_filter,
            exact=True,
        ).count
        if deleted_count == 0:
            return 0

        self._client.delete(
            collection_name=request.collection,
            points_selector=models.FilterSelector(filter=resource_filter),
            wait=True,
        )
        return deleted_count

    def delete_chunks_at_or_after(
        self,
        *,
        request: RagDeleteRequest,
        chunk_index: int,
    ) -> int:
        if chunk_index <= 0:
            return self.delete_resource(request=request)
        if not self._client.collection_exists(collection_name=request.collection):
            return 0

        resource_filter = self._resource_filter(
            workspace_id=request.workspace_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )
        offset: int | str | uuid.UUID | None = None
        point_ids: list[models.ExtendedPointId] = []
        while True:
            records, offset = self._client.scroll(
                collection_name=request.collection,
                scroll_filter=resource_filter,
                limit=128,
                offset=offset,
                with_payload=["chunk_metadata"],
                with_vectors=False,
            )
            for record in records:
                payload = record.payload or {}
                if _chunk_index_from_payload(payload) < chunk_index:
                    continue
                point_ids.append(record.id)
            if offset is None:
                break

        if not point_ids:
            return 0

        self._client.delete(
            collection_name=request.collection,
            points_selector=point_ids,
            wait=True,
        )
        return len(point_ids)

    def query(self, *, request: RagVectorSearchRequest) -> list[RagVectorSearchHit]:
        if not request.query_embedding:
            return []
        if not self._client.collection_exists(collection_name=request.collection):
            return []

        query_filter = self._build_query_filter(request)
        sparse_query = self._to_sparse_query_vector(request.query)
        started = time.perf_counter()
        try:
            if sparse_query is not None:
                response = self._client.query_points(
                    collection_name=request.collection,
                    prefetch=[
                        models.Prefetch(
                            query=request.query_embedding,
                            using=self._dense_vector_name,
                            limit=max(request.top_k * 4, request.top_k),
                        ),
                        models.Prefetch(
                            query=sparse_query,
                            using=self._sparse_vector_name,
                            limit=max(request.top_k * 4, request.top_k),
                        ),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    query_filter=query_filter,
                    limit=request.top_k,
                    with_payload=True,
                    with_vectors=False,
                )
            else:
                response = self._client.query_points(
                    collection_name=request.collection,
                    query=request.query_embedding,
                    using=self._dense_vector_name,
                    query_filter=query_filter,
                    limit=request.top_k,
                    with_payload=True,
                    with_vectors=False,
                )
        except Exception as error:
            _record_query_failure(
                request=request,
                error=error,
            )
            raise
        record_vector_query_latency(
            workspace_id=request.workspace_id,
            provider_name=self.provider_name,
            latency_ms=int((time.perf_counter() - started) * 1000),
            source_kind=request.source_kinds[0] if len(request.source_kinds) == 1 else None,
        )
        return [self._to_search_hit(point) for point in response.points]

    def _validate_collection_schema(
        self,
        *,
        collection: str,
        dense_dimensions: int,
        sparse_enabled: bool,
    ) -> None:
        info = self._client.get_collection(collection_name=collection)
        vectors = info.config.params.vectors
        dense_config = vectors.get(self._dense_vector_name) if isinstance(vectors, dict) else None
        if dense_config is None:
            raise RagProviderConfigurationError(
                f"Qdrant collection {collection} is missing dense vector '{self._dense_vector_name}'"
            )
        if dense_config.size != dense_dimensions:
            raise RagProviderConfigurationError(
                f"Qdrant collection {collection} dense vector size mismatch: "
                f"expected {dense_dimensions}, got {dense_config.size}"
            )
        sparse_vectors = info.config.params.sparse_vectors or {}
        has_sparse = self._sparse_vector_name in sparse_vectors
        if sparse_enabled and not has_sparse:
            raise RagProviderConfigurationError(
                f"Qdrant collection {collection} is missing sparse vector '{self._sparse_vector_name}'"
            )

    def _to_point(self, collection: str, record: RagVectorRecord) -> models.PointStruct:
        vector: dict[str, list[float] | models.SparseVector] = {
            self._dense_vector_name: list(record.embedding),
        }
        sparse_vector = _sparse_vector_from_terms(record.sparse_terms)
        if sparse_vector is not None:
            vector[self._sparse_vector_name] = sparse_vector
        return models.PointStruct(
            id=_point_uuid(collection, record.projection.workspace_id, record.chunk_id),
            vector=vector,
            payload=_payload_from_record(record),
        )

    def _build_query_filter(self, request: RagVectorSearchRequest) -> models.Filter:
        must: list[models.FieldCondition] = [
            models.FieldCondition(
                key="workspace_id",
                match=models.MatchValue(value=request.workspace_id),
            )
        ]
        if request.source_kinds:
            must.append(
                models.FieldCondition(
                    key="source_kind",
                    match=models.MatchAny(any=list(request.source_kinds)),
                )
            )

        for key, value in request.metadata_filter.items():
            condition = _build_field_condition(key=key, value=value)
            if condition is not None:
                must.append(condition)
        return models.Filter(must=must)

    def _to_search_hit(self, point: models.ScoredPoint) -> RagVectorSearchHit:
        payload = point.payload or {}
        projection = RagProjection(
            workspace_id=str(payload.get("workspace_id") or ""),
            resource_type=str(payload.get("resource_type") or ""),
            resource_id=str(payload.get("resource_id") or ""),
            source_kind=str(payload.get("source_kind") or ""),
            title=_string_or_none(payload.get("title")),
            summary=_string_or_none(payload.get("projection_summary")),
            text_content=_string_or_empty(payload.get("text")),
            owner_label=_string_or_none(payload.get("owner_label")),
            visibility_refs=[str(ref) for ref in payload.get("visibility_refs") or []],
            metadata=dict(payload.get("metadata") or {}),
        )
        return RagVectorSearchHit(
            chunk_id=_string_or_empty(payload.get("chunk_id")) or str(point.id),
            text=_string_or_empty(payload.get("text")),
            summary=_string_or_none(payload.get("summary")),
            score=float(point.score),
            citation=_string_or_empty(payload.get("chunk_id")) or str(point.id),
            metadata=dict(payload.get("chunk_metadata") or {}),
            projection=projection,
        )

    def _resource_filter(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
    ) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=workspace_id),
                ),
                models.FieldCondition(
                    key="resource_type",
                    match=models.MatchValue(value=resource_type),
                ),
                models.FieldCondition(
                    key="resource_id",
                    match=models.MatchValue(value=resource_id),
                ),
            ]
        )

    def _to_sparse_query_vector(self, query: str) -> models.SparseVector | None:
        terms: dict[str, float] = {}
        for token in _tokenize(query):
            terms[token] = terms.get(token, 0.0) + 1.0
        return _sparse_vector_from_terms(terms)



def _payload_from_record(record: RagVectorRecord) -> dict[str, Any]:
    projection = record.projection
    return {
        "chunk_id": record.chunk_id,
        "text": record.text,
        "summary": record.summary,
        "workspace_id": projection.workspace_id,
        "resource_type": projection.resource_type,
        "resource_id": projection.resource_id,
        "source_kind": projection.source_kind,
        "title": projection.title,
        "projection_summary": projection.summary,
        "owner_label": projection.owner_label,
        "visibility_refs": list(projection.visibility_refs),
        "metadata": dict(projection.metadata),
        "chunk_metadata": dict(record.metadata),
    }


def _chunk_index_from_payload(payload: dict[str, Any]) -> int:
    chunk_metadata = payload.get("chunk_metadata") or {}
    raw_value = chunk_metadata.get("chunk_index")
    if isinstance(raw_value, bool):
        return 0
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str) and raw_value.isdigit():
        return int(raw_value)
    return 0



def _build_field_condition(
    *,
    key: str,
    value: object,
) -> models.FieldCondition | None:
    if value is None:
        return None

    field_key = _payload_key_for_filter(key)
    if key == "visibility_refs_contains":
        return models.FieldCondition(
            key=field_key,
            match=models.MatchValue(value=str(value)),
        )

    if isinstance(value, bool | int | str):
        return models.FieldCondition(
            key=field_key,
            match=models.MatchValue(value=value),
        )

    if isinstance(value, list) and value:
        normalized = [item for item in value if isinstance(item, bool | int | str)]
        if not normalized:
            return None
        if all(isinstance(item, bool) for item in normalized):
            return None
        if all(isinstance(item, int) and not isinstance(item, bool) for item in normalized):
            return models.FieldCondition(
                key=field_key,
                match=models.MatchAny(any=[int(item) for item in normalized]),
            )
        return models.FieldCondition(
            key=field_key,
            match=models.MatchAny(any=[str(item) for item in normalized]),
        )
    return None



def _payload_key_for_filter(key: str) -> str:
    if key in _RESERVED_PAYLOAD_FIELDS:
        return "visibility_refs" if key == "visibility_refs_contains" else key
    if key.startswith("metadata."):
        return key
    return f"metadata.{key}"



def _sparse_vector_from_terms(terms: dict[str, float]) -> models.SparseVector | None:
    if not terms:
        return None

    indexed = [(_stable_sparse_index(token), float(weight)) for token, weight in terms.items() if weight > 0]
    if not indexed:
        return None
    indexed.sort(key=lambda item: item[0])
    return models.SparseVector(
        indices=[index for index, _ in indexed],
        values=[value for _, value in indexed],
    )



def _stable_sparse_index(token: str) -> int:
    # Qdrant server accepts sparse indices that fit in 32-bit integer space.
    # Local mode is more permissive, so keep the hash bounded to avoid
    # HTTP upsert failures against real Qdrant instances.
    digest = blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, byteorder="big", signed=False)



def _point_uuid(collection: str, workspace_id: str, chunk_id: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{collection}:{workspace_id}:{chunk_id}")



def _tokenize(text: str) -> list[str]:
    return [token for token in text.lower().replace("\n", " ").split(" ") if token]



def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)



def _string_or_empty(value: object) -> str:
    return "" if value is None else str(value)


def _record_query_failure(
    *,
    request: RagVectorSearchRequest,
    error: Exception,
) -> None:
    payload = {
        "provider_name": QdrantVectorIndexClient.provider_name,
        "operation": "vector_query",
        "workspace_id": request.workspace_id,
        "source_kind": request.source_kinds[0] if len(request.source_kinds) == 1 else None,
        "error_type": error.__class__.__name__,
    }
    if isinstance(error, TimeoutError) or "timeout" in error.__class__.__name__.lower():
        record_provider_timeout(**payload)
        return
    record_provider_error(**payload)
