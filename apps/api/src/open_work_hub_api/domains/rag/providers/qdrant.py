from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import blake2b
import inspect
import time
from typing import Any
import uuid

from qdrant_client import QdrantClient, models

from open_work_hub_api.domains.rag.chunking import tokenize_sparse_terms
from open_work_hub_api.domains.rag.contracts import (
    RagDeleteRequest,
    RagProjection,
    RagProviderHealth,
    RagScopeKind,
    RagUpsertRequest,
    RagVectorRecord,
    RagVectorSearchHit,
    RagVectorSearchMode,
    RagVectorSearchRequest,
)
from open_work_hub_api.domains.rag.metrics import (
    record_provider_error,
    record_provider_timeout,
    record_vector_query_latency,
)
from open_work_hub_api.domains.rag.providers.base import RagProviderConfigurationError
from open_work_hub_api.domains.rag.providers.openai_compatible import (
    RagProviderError,
    RagProviderTimeoutError,
    RagProviderTransientError,
)
from open_work_hub_api.domains.rag.providers.operation import (
    ProviderCircuitBreaker,
    ceil_positive_timeout_seconds as _qdrant_timeout,
)
from open_work_hub_api.domains.retrieval.projection_identity import canonical_vector_point_id

_DENSE_VECTOR_NAME = "dense"
_SPARSE_VECTOR_NAME = "sparse"
_LEGACY_PAYLOAD_INDEX_FIELDS = {
    "scope_kind": models.PayloadSchemaType.KEYWORD,
    "workspace_id": models.PayloadSchemaType.KEYWORD,
    "resource_type": models.PayloadSchemaType.KEYWORD,
    "resource_id": models.PayloadSchemaType.KEYWORD,
    "source_kind": models.PayloadSchemaType.KEYWORD,
    "visibility_refs": models.PayloadSchemaType.KEYWORD,
}
_PARTITIONED_PAYLOAD_INDEX_FIELDS = {
    "retrieval_partition_id": models.PayloadSchemaType.KEYWORD,
    "projection_version": models.PayloadSchemaType.INTEGER,
    **_LEGACY_PAYLOAD_INDEX_FIELDS,
}
_RESERVED_PAYLOAD_FIELDS = {
    "retrieval_partition_id",
    "projection_version",
    "scope_kind",
    "workspace_id",
    "resource_type",
    "resource_id",
    "source_kind",
    "visibility_refs_contains",
}


class QdrantVectorIndexClient:
    provider_name = "qdrant"
    _circuit_breaker_failure_threshold = 3
    _circuit_breaker_cooldown_seconds = 15

    def __init__(
        self,
        *,
        url: str | None = None,
        api_key: str | None = None,
        client: QdrantClient | None = None,
        dense_vector_name: str = _DENSE_VECTOR_NAME,
        sparse_vector_name: str = _SPARSE_VECTOR_NAME,
        partitioned_generation: bool = False,
        generation_collection: str | None = None,
    ) -> None:
        normalized_generation_collection = (
            generation_collection.strip() if generation_collection is not None else None
        )
        if partitioned_generation and not normalized_generation_collection:
            raise RagProviderConfigurationError(
                "partition-aware Qdrant generation requires an explicit "
                "generation_collection binding"
            )
        if not partitioned_generation and normalized_generation_collection is not None:
            raise RagProviderConfigurationError(
                "generation_collection requires partitioned_generation=True"
            )
        if client is None and not url:
            raise ValueError("QdrantVectorIndexClient requires either client or url")
        self._client = client or QdrantClient(url=url, api_key=api_key or None)
        self._dense_vector_name = dense_vector_name
        self._sparse_vector_name = sparse_vector_name
        self._partitioned_generation = partitioned_generation
        self._generation_collection = normalized_generation_collection
        self._indexed_collections: set[str] = set()
        self._query_circuit = ProviderCircuitBreaker(
            failure_threshold=self._circuit_breaker_failure_threshold,
            cooldown_seconds=self._circuit_breaker_cooldown_seconds,
            open_message="Provider temporarily unavailable after repeated query failures.",
        )

    def for_partitioned_generation(
        self,
        *,
        collection: str,
    ) -> QdrantVectorIndexClient:
        """Reuse transport credentials while isolating the new ID/payload contract."""

        return QdrantVectorIndexClient(
            client=self._client,
            dense_vector_name=self._dense_vector_name,
            sparse_vector_name=self._sparse_vector_name,
            partitioned_generation=True,
            generation_collection=collection,
        )

    def healthcheck(self) -> RagProviderHealth:
        if self._query_circuit.retry_after_seconds() is not None:
            return RagProviderHealth(
                provider_name=self.provider_name,
                ready=False,
                detail=self._query_circuit.open_message,
            )
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
        self._require_bound_collection(collection)
        if dense_dimensions <= 0:
            raise ValueError("dense_dimensions must be greater than zero for Qdrant collections")

        collection_created = False
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
                collection_created = True
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

        if self._partitioned_generation and not collection_created:
            if collection not in self._indexed_collections:
                self._validate_partitioned_payload_indexes(collection=collection)
                self._indexed_collections.add(collection)
            return

        if collection not in self._indexed_collections:
            payload_indexes = (
                _PARTITIONED_PAYLOAD_INDEX_FIELDS
                if self._partitioned_generation
                else _LEGACY_PAYLOAD_INDEX_FIELDS
            )
            for field_name, field_schema in payload_indexes.items():
                self._client.create_payload_index(
                    collection_name=collection,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            self._indexed_collections.add(collection)

    def delete_collection(self, *, collection: str) -> bool:
        self._require_bound_collection(collection)
        if not self._client.collection_exists(collection_name=collection):
            return False
        self._client.delete_collection(collection_name=collection)
        self._indexed_collections.discard(collection)
        return True

    def upsert_chunks(
        self,
        *,
        request: RagUpsertRequest,
        records: list[RagVectorRecord],
    ) -> int:
        self._require_bound_collection(request.collection)
        if self._partitioned_generation:
            _require_projection_fence(request.projection)
            for record in records:
                _require_projection_fence(record.projection)
        if not records:
            return 0

        self._client.upsert(
            collection_name=request.collection,
            points=[self._to_point(request.collection, record) for record in records],
            wait=True,
        )
        return len(records)

    def delete_resource(self, *, request: RagDeleteRequest) -> int:
        self._require_bound_collection(request.collection)
        resource_filter = self._resource_filter(
            retrieval_partition_id=request.retrieval_partition_id,
            scope_kind=request.scope_kind,
            workspace_id=request.workspace_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )
        if not self._client.collection_exists(collection_name=request.collection):
            return 0
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
        self._require_bound_collection(request.collection)
        if chunk_index <= 0:
            return self.delete_resource(request=request)
        resource_filter = self._resource_filter(
            retrieval_partition_id=request.retrieval_partition_id,
            scope_kind=request.scope_kind,
            workspace_id=request.workspace_id,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
        )
        if not self._client.collection_exists(collection_name=request.collection):
            return 0
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

    def query(
        self,
        *,
        request: RagVectorSearchRequest,
        timeout_seconds: float | None = None,
    ) -> list[RagVectorSearchHit]:
        self._require_bound_collection(request.collection)
        query_filter = self._build_query_filter(request)
        if not request.query_embedding:
            return []
        self._raise_if_circuit_open()
        timeout = _qdrant_timeout(timeout_seconds)
        if not _call_client_with_optional_timeout(
            self._client.collection_exists,
            timeout=timeout,
            collection_name=request.collection,
        ):
            return []

        sparse_query = (
            self._to_sparse_query_vector(request.query)
            if request.search_mode == RagVectorSearchMode.DENSE_SPARSE_RRF
            else None
        )
        started = time.perf_counter()
        try:
            if sparse_query is not None:
                response = _call_client_with_optional_timeout(
                    self._client.query_points,
                    timeout=timeout,
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
                response = _call_client_with_optional_timeout(
                    self._client.query_points,
                    timeout=timeout,
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
            normalized = _normalize_query_error(error)
            self._record_query_failure(normalized)
            raise normalized from error
        self._reset_query_failures()
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

    def _validate_partitioned_payload_indexes(self, *, collection: str) -> None:
        info = self._client.get_collection(collection_name=collection)
        payload_schema = getattr(info, "payload_schema", None)
        if not isinstance(payload_schema, dict):
            raise RagProviderConfigurationError(
                f"Qdrant collection {collection} is missing partitioned payload indexes"
            )
        for field_name, expected_schema in _PARTITIONED_PAYLOAD_INDEX_FIELDS.items():
            raw_schema = payload_schema.get(field_name)
            if isinstance(raw_schema, dict):
                actual_schema = raw_schema.get("data_type")
            else:
                actual_schema = getattr(raw_schema, "data_type", raw_schema)
            actual_value = getattr(actual_schema, "value", actual_schema)
            if actual_value != expected_schema.value:
                raise RagProviderConfigurationError(
                    f"Qdrant collection {collection} payload index mismatch for {field_name}: "
                    f"expected {expected_schema.value}"
                )

    def _to_point(self, collection: str, record: RagVectorRecord) -> models.PointStruct:
        self._require_bound_collection(collection)
        if self._partitioned_generation:
            _require_projection_fence(record.projection)
        vector: dict[str, list[float] | models.SparseVector] = {
            self._dense_vector_name: list(record.embedding),
        }
        sparse_vector = _sparse_vector_from_terms(record.sparse_terms)
        if sparse_vector is not None:
            vector[self._sparse_vector_name] = sparse_vector
        return models.PointStruct(
            id=_point_id(
                collection=collection,
                record=record,
                partitioned_generation=self._partitioned_generation,
            ),
            vector=vector,
            payload=qdrant_payload_from_record(
                record,
                partitioned_generation=self._partitioned_generation,
            ),
        )

    def _build_query_filter(self, request: RagVectorSearchRequest) -> models.Filter:
        if self._partitioned_generation:
            if request.retrieval_partition_ids is None:
                raise RagProviderConfigurationError(
                    "partition-aware Qdrant queries require retrieval_partition_ids"
                )
            must: list[models.FieldCondition] = [
                models.FieldCondition(
                    key="retrieval_partition_id",
                    match=models.MatchAny(any=list(request.retrieval_partition_ids)),
                )
            ]
        else:
            if request.retrieval_partition_ids is not None:
                raise RagProviderConfigurationError(
                    "retrieval partition filters require a partition-aware Qdrant generation"
                )
            must = [
                models.FieldCondition(
                    key="scope_kind",
                    match=models.MatchValue(value=request.scope_kind.value),
                )
            ]
            if request.scope_kind == RagScopeKind.WORKSPACE:
                must.append(
                    models.FieldCondition(
                        key="workspace_id",
                        match=models.MatchValue(value=request.workspace_id),
                    )
                )
            else:
                must.append(
                    models.FieldCondition(
                        key="visibility_refs",
                        match=models.MatchValue(value="company_public"),
                    )
                )
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
            retrieval_partition_id=_string_or_none(payload.get("retrieval_partition_id")),
            projection_version=_int_or_none(payload.get("projection_version")),
            scope_kind=RagScopeKind(str(payload.get("scope_kind") or RagScopeKind.WORKSPACE)),
            workspace_id=_string_or_none(payload.get("workspace_id")),
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
        retrieval_partition_id: str | None = None,
        workspace_id: str | None,
        resource_type: str,
        resource_id: str,
        scope_kind: RagScopeKind = RagScopeKind.WORKSPACE,
    ) -> models.Filter:
        must: list[models.FieldCondition] = [
            models.FieldCondition(
                key="resource_type",
                match=models.MatchValue(value=resource_type),
            ),
            models.FieldCondition(
                key="resource_id",
                match=models.MatchValue(value=resource_id),
            ),
        ]
        if self._partitioned_generation:
            if retrieval_partition_id is None:
                raise RagProviderConfigurationError(
                    "partition-aware Qdrant deletes require retrieval_partition_id"
                )
            must.insert(
                0,
                models.FieldCondition(
                    key="retrieval_partition_id",
                    match=models.MatchValue(value=retrieval_partition_id),
                ),
            )
        else:
            must.insert(
                0,
                models.FieldCondition(
                    key="scope_kind",
                    match=models.MatchValue(value=scope_kind.value),
                ),
            )
        if not self._partitioned_generation and scope_kind == RagScopeKind.WORKSPACE:
            must.append(
                models.FieldCondition(
                    key="workspace_id",
                    match=models.MatchValue(value=workspace_id),
                )
            )
        return models.Filter(must=must)

    def _require_bound_collection(self, collection: str) -> None:
        if not self._partitioned_generation:
            return
        if collection != self._generation_collection:
            raise RagProviderConfigurationError(
                "partition-aware Qdrant generation is bound to collection "
                f"{self._generation_collection!r}, not {collection!r}"
            )

    def _to_sparse_query_vector(self, query: str) -> models.SparseVector | None:
        terms: dict[str, float] = {}
        for token in _tokenize(query):
            terms[token] = terms.get(token, 0.0) + 1.0
        return _sparse_vector_from_terms(terms)

    def _record_query_failure(self, error: Exception) -> None:
        del error
        self._query_circuit.record_failure()

    def _reset_query_failures(self) -> None:
        self._query_circuit.record_success()

    def _raise_if_circuit_open(self) -> None:
        self._query_circuit.raise_if_open(
            lambda message, retry_after_seconds: RagProviderTransientError(
                message,
                retry_after_seconds=retry_after_seconds,
            )
        )


def qdrant_payload_from_record(
    record: RagVectorRecord,
    *,
    partitioned_generation: bool,
) -> dict[str, Any]:
    """Build the canonical Qdrant payload shared by writers and verifiers."""

    projection = record.projection
    if partitioned_generation:
        _require_projection_fence(projection)
    payload = {
        "chunk_id": record.chunk_id,
        "text": record.text,
        "summary": record.summary,
        "scope_kind": projection.scope_kind.value,
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
    if partitioned_generation:
        payload["retrieval_partition_id"] = projection.retrieval_partition_id
        payload["projection_version"] = projection.projection_version
    return payload


def _require_projection_fence(projection: RagProjection) -> None:
    if projection.retrieval_partition_id is None or projection.projection_version is None:
        raise RagProviderConfigurationError(
            "partition-aware Qdrant upserts require retrieval_partition_id and projection_version"
        )


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


def _normalize_query_error(error: Exception) -> Exception:
    if isinstance(error, RagProviderError):
        return error
    if isinstance(error, TimeoutError):
        return RagProviderTimeoutError(str(error))
    return RagProviderError(str(error))


def _call_client_with_optional_timeout(
    method: Any,
    *,
    timeout: int | None,
    **kwargs: Any,
) -> Any:
    if timeout is None or not _method_accepts_timeout(method):
        return method(**kwargs)
    try:
        return method(**kwargs, timeout=timeout)
    except (AssertionError, TypeError) as error:
        if not _is_timeout_keyword_rejection(error):
            raise
        return method(**kwargs)


def _method_accepts_timeout(method: Any) -> bool:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return True
    if "timeout" in signature.parameters:
        return True
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _is_timeout_keyword_rejection(error: Exception) -> bool:
    message = str(error)
    return "timeout" in message and (
        "Unknown arguments" in message or "unexpected keyword argument" in message
    )


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
    if isinstance(value, dict) and value:
        range_keys = frozenset({"lt", "gt", "gte", "lte"})
        if not set(value).issubset(range_keys):
            return None
        numeric = {
            key: float(item)
            for key, item in value.items()
            if isinstance(item, int | float) and not isinstance(item, bool)
        }
        if len(numeric) == len(value):
            return models.FieldCondition(key=field_key, range=models.Range(**numeric))
        temporal = {
            key: normalized
            for key, item in value.items()
            if (normalized := _filter_datetime(item)) is not None
        }
        if len(temporal) == len(value):
            return models.FieldCondition(
                key=field_key,
                range=models.DatetimeRange(**temporal),
            )
    return None


def _filter_datetime(value: object) -> datetime | date | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _payload_key_for_filter(key: str) -> str:
    if key in _RESERVED_PAYLOAD_FIELDS:
        return "visibility_refs" if key == "visibility_refs_contains" else key
    if key.startswith("metadata."):
        return key
    return f"metadata.{key}"


def _sparse_vector_from_terms(terms: dict[str, float]) -> models.SparseVector | None:
    if not terms:
        return None

    weights_by_index: dict[int, float] = {}
    for token, weight in terms.items():
        if weight <= 0:
            continue
        index = _stable_sparse_index(token)
        weights_by_index[index] = weights_by_index.get(index, 0.0) + float(weight)
    if not weights_by_index:
        return None
    indexed = sorted(weights_by_index.items(), key=lambda item: item[0])
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


def _point_uuid(
    collection: str,
    scope_kind: RagScopeKind,
    workspace_id: str | None,
    source_kind: str,
    resource_type: str,
    resource_id: str,
    chunk_id: str,
) -> uuid.UUID:
    identity = ":".join(
        (
            collection,
            scope_kind.value,
            workspace_id or "",
            source_kind,
            resource_type,
            resource_id,
            chunk_id,
        )
    )
    return uuid.uuid5(uuid.NAMESPACE_URL, identity)


def _point_id(
    *,
    collection: str,
    record: RagVectorRecord,
    partitioned_generation: bool,
) -> uuid.UUID:
    projection = record.projection
    if partitioned_generation:
        _require_projection_fence(projection)
        return uuid.UUID(
            canonical_vector_point_id(
                resource_type=projection.resource_type,
                resource_id=projection.resource_id,
                chunk_id=record.chunk_id,
            )
        )
    return _point_uuid(
        collection,
        projection.scope_kind,
        projection.workspace_id,
        projection.source_kind,
        projection.resource_type,
        projection.resource_id,
        record.chunk_id,
    )


def _tokenize(text: str) -> list[str]:
    return tokenize_sparse_terms(text)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_or_empty(value: object) -> str:
    return "" if value is None else str(value)


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


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
