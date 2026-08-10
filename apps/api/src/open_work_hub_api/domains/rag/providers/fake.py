from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time
from math import sqrt

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
from open_work_hub_api.domains.rag.providers.rerank_text import build_rerank_document_text


def _tokenize(text: str) -> list[str]:
    return tokenize_sparse_terms(text)


def _dot(left: list[float], right: list[float]) -> float:
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    return sum(left[index] * right[index] for index in range(size))


def _norm(values: list[float]) -> float:
    return sqrt(sum(value * value for value in values)) or 1.0


def _cosine(left: list[float], right: list[float]) -> float:
    return _dot(left, right) / (_norm(left) * _norm(right))


class FakeEmbeddingClient:
    provider_name = "fake-embedding"

    def __init__(self, *, dimensions: int = 1024) -> None:
        self._dimensions = max(1, min(int(dimensions), 4096))

    def healthcheck(self) -> RagProviderHealth:
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def embed_texts(
        self,
        texts: list[str],
        timeout_seconds: float | None = None,
    ) -> list[list[float]]:
        del timeout_seconds
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str, timeout_seconds: float | None = None) -> list[float]:
        del timeout_seconds
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        buckets = [0.0] * self._dimensions
        normalized = text.strip().lower()
        if not normalized:
            return buckets
        for index, char in enumerate(normalized):
            buckets[index % self._dimensions] += float((ord(char) % 31) + 1)
        scale = float(len(normalized))
        return [round(value / scale, 6) for value in buckets]


class FakeOcrClient:
    provider_name = "fake-ocr"

    def healthcheck(self) -> RagProviderHealth:
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def extract_text(self, *, content: bytes, content_type: str | None = None) -> str:
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return f"[binary:{content_type or 'application/octet-stream'}:{len(content)}]"


class FakeAsrClient:
    provider_name = "fake-asr"

    def healthcheck(self) -> RagProviderHealth:
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def transcribe(self, *, content: bytes, content_type: str | None = None) -> str:
        return FakeOcrClient().extract_text(content=content, content_type=content_type)


class FakeRerankClient:
    provider_name = "fake-rerank"

    def healthcheck(self) -> RagProviderHealth:
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def rerank(
        self,
        *,
        query: str,
        hits: list[RagVectorSearchHit],
        timeout_seconds: float | None = None,
    ) -> list[RagVectorSearchHit]:
        del timeout_seconds
        query_tokens = set(_tokenize(query))
        reranked = []
        for hit in hits:
            overlap = len(query_tokens.intersection(_tokenize(build_rerank_document_text(hit))))
            reranked.append(hit.model_copy(update={"score": hit.score + (0.05 * overlap)}))
        return sorted(reranked, key=lambda item: item.score, reverse=True)


class FakeVectorIndexClient:
    provider_name = "fake-vector-index"

    def __init__(self) -> None:
        self._collections: dict[str, dict[str, RagVectorRecord]] = defaultdict(dict)
        self._schemas: dict[str, dict[str, int | bool]] = {}

    def healthcheck(self) -> RagProviderHealth:
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def ensure_collection(
        self,
        *,
        collection: str,
        dense_dimensions: int,
        sparse_enabled: bool = True,
    ) -> None:
        self._schemas[collection] = {
            "dense_dimensions": dense_dimensions,
            "sparse_enabled": sparse_enabled,
        }

    def delete_collection(self, *, collection: str) -> bool:
        existed = collection in self._collections or collection in self._schemas
        self._collections.pop(collection, None)
        self._schemas.pop(collection, None)
        return existed

    def upsert_chunks(
        self,
        *,
        request: RagUpsertRequest,
        records: list[RagVectorRecord],
    ) -> int:
        collection = self._collections[request.collection]
        for record in records:
            collection[record.chunk_id] = record
        return len(records)

    def delete_resource(self, *, request: RagDeleteRequest) -> int:
        collection = self._collections[request.collection]
        to_delete = [
            chunk_id
            for chunk_id, record in collection.items()
            if _matches_delete_envelope(record.projection, request)
            and record.projection.resource_type == request.resource_type
            and record.projection.resource_id == request.resource_id
        ]
        for chunk_id in to_delete:
            del collection[chunk_id]
        return len(to_delete)

    def delete_chunks_at_or_after(
        self,
        *,
        request: RagDeleteRequest,
        chunk_index: int,
    ) -> int:
        if chunk_index <= 0:
            return self.delete_resource(request=request)
        collection = self._collections[request.collection]
        to_delete = [
            chunk_id
            for chunk_id, record in collection.items()
            if _matches_delete_envelope(record.projection, request)
            and record.projection.resource_type == request.resource_type
            and record.projection.resource_id == request.resource_id
            and _chunk_index(record) >= chunk_index
        ]
        for chunk_id in to_delete:
            del collection[chunk_id]
        return len(to_delete)

    def query(
        self,
        *,
        request: RagVectorSearchRequest,
        timeout_seconds: float | None = None,
    ) -> list[RagVectorSearchHit]:
        del timeout_seconds
        query_tokens = set(_tokenize(request.query))
        hits: list[RagVectorSearchHit] = []
        for record in self._collections[request.collection].values():
            projection = record.projection
            if request.retrieval_partition_ids is not None:
                if projection.retrieval_partition_id not in request.retrieval_partition_ids:
                    continue
            else:
                if projection.scope_kind != request.scope_kind:
                    continue
                if (
                    request.scope_kind == RagScopeKind.WORKSPACE
                    and projection.workspace_id != request.workspace_id
                ):
                    continue
                if (
                    request.scope_kind == RagScopeKind.COMPANY
                    and "company_public" not in projection.visibility_refs
                ):
                    continue
            if request.source_kinds and projection.source_kind not in request.source_kinds:
                continue
            if not _matches_metadata_filter(projection, request.metadata_filter):
                continue

            dense_score = _cosine(request.query_embedding, record.embedding)
            score = dense_score
            if request.search_mode == RagVectorSearchMode.DENSE_SPARSE_RRF:
                token_overlap = len(query_tokens.intersection(_tokenize(record.text)))
                sparse_score = sum(
                    weight for token, weight in record.sparse_terms.items() if token in query_tokens
                )
                score += sparse_score + (0.1 * token_overlap)
            if score <= 0:
                continue
            hits.append(
                RagVectorSearchHit(
                    chunk_id=record.chunk_id,
                    text=record.text,
                    summary=record.summary,
                    score=round(score, 6),
                    citation=record.chunk_id,
                    metadata=dict(record.metadata),
                    projection=projection,
                )
            )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[: request.top_k]

    def snapshot_projection(self, *, collection: str, chunk_id: str) -> RagProjection | None:
        record = self._collections.get(collection, {}).get(chunk_id)
        return None if record is None else record.projection


def _matches_delete_envelope(
    projection: RagProjection,
    request: RagDeleteRequest,
) -> bool:
    if request.retrieval_partition_id is not None:
        return projection.retrieval_partition_id == request.retrieval_partition_id
    return projection.scope_kind == request.scope_kind and (
        request.scope_kind == RagScopeKind.COMPANY
        or projection.workspace_id == request.workspace_id
    )


def _matches_metadata_filter(projection: RagProjection, metadata_filter: dict[str, object]) -> bool:
    if not metadata_filter:
        return True
    for key, value in metadata_filter.items():
        if key == "workspace_id" and projection.workspace_id != value:
            return False
        if key == "scope_kind" and projection.scope_kind != value:
            return False
        if key == "resource_type" and projection.resource_type != value:
            return False
        if key == "resource_id" and projection.resource_id != value:
            return False
        if key == "source_kind" and projection.source_kind != value:
            return False
        if key == "visibility_refs_contains" and value not in projection.visibility_refs:
            return False
        if key in {
            "workspace_id",
            "scope_kind",
            "resource_type",
            "resource_id",
            "source_kind",
            "visibility_refs_contains",
        }:
            continue
        metadata_key = key.removeprefix("metadata.")
        if metadata_key not in projection.metadata or not _matches_filter_value(
            projection.metadata[metadata_key],
            value,
        ):
            return False
    return True


def _matches_filter_value(projection_value: object, filter_value: object) -> bool:
    if isinstance(filter_value, list):
        return projection_value in filter_value
    if isinstance(filter_value, dict):
        return _matches_range_filter(projection_value, filter_value)
    return projection_value == filter_value


def _matches_range_filter(projection_value: object, bounds: dict[object, object]) -> bool:
    if not bounds or not set(bounds).issubset({"lt", "gt", "gte", "lte"}):
        return False

    numeric_value = _filter_number(projection_value)
    numeric_bounds = {key: _filter_number(value) for key, value in bounds.items()}
    if numeric_value is not None and all(value is not None for value in numeric_bounds.values()):
        return _value_within_bounds(numeric_value, numeric_bounds)

    temporal_value = _filter_datetime(projection_value)
    temporal_bounds = {key: _filter_datetime(value) for key, value in bounds.items()}
    if temporal_value is not None and all(value is not None for value in temporal_bounds.values()):
        return _value_within_bounds(temporal_value, temporal_bounds)
    return False


def _value_within_bounds(value: object, bounds: dict[object, object | None]) -> bool:
    return not (
        (bounds.get("lt") is not None and value >= bounds["lt"])
        or (bounds.get("gt") is not None and value <= bounds["gt"])
        or (bounds.get("lte") is not None and value > bounds["lte"])
        or (bounds.get("gte") is not None and value < bounds["gte"])
    )


def _filter_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _filter_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min, tzinfo=UTC)
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _chunk_index(record: RagVectorRecord) -> int:
    raw_value = record.metadata.get("chunk_index")
    if isinstance(raw_value, bool):
        return 0
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, str) and raw_value.isdigit():
        return int(raw_value)
    return 0
