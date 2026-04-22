from __future__ import annotations

from collections import defaultdict
from math import sqrt

from aidoo_api.domains.rag.contracts import (
    RagDeleteRequest,
    RagProjection,
    RagProviderHealth,
    RagUpsertRequest,
    RagVectorRecord,
    RagVectorSearchHit,
    RagVectorSearchRequest,
)


def _tokenize(text: str) -> list[str]:
    return [token for token in text.lower().replace("\n", " ").split(" ") if token]


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

    def healthcheck(self) -> RagProviderHealth:
        return RagProviderHealth(provider_name=self.provider_name, ready=True)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        buckets = [0.0] * 8
        normalized = text.strip().lower()
        if not normalized:
            return buckets
        for index, char in enumerate(normalized):
            buckets[index % 8] += float((ord(char) % 31) + 1)
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
    ) -> list[RagVectorSearchHit]:
        query_tokens = set(_tokenize(query))
        reranked = []
        for hit in hits:
            overlap = len(query_tokens.intersection(_tokenize(hit.text)))
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
            if record.projection.workspace_id == request.workspace_id
            and record.projection.resource_type == request.resource_type
            and record.projection.resource_id == request.resource_id
        ]
        for chunk_id in to_delete:
            del collection[chunk_id]
        return len(to_delete)

    def query(self, *, request: RagVectorSearchRequest) -> list[RagVectorSearchHit]:
        query_tokens = set(_tokenize(request.query))
        hits: list[RagVectorSearchHit] = []
        for record in self._collections[request.collection].values():
            projection = record.projection
            if projection.workspace_id != request.workspace_id:
                continue
            if request.source_kinds and projection.source_kind not in request.source_kinds:
                continue
            if not _matches_metadata_filter(projection, request.metadata_filter):
                continue

            token_overlap = len(query_tokens.intersection(_tokenize(record.text)))
            dense_score = _cosine(request.query_embedding, record.embedding)
            sparse_score = sum(
                weight for token, weight in record.sparse_terms.items() if token in query_tokens
            )
            score = dense_score + sparse_score + (0.1 * token_overlap)
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


def _matches_metadata_filter(projection: RagProjection, metadata_filter: dict[str, object]) -> bool:
    if not metadata_filter:
        return True
    for key, value in metadata_filter.items():
        if key == "workspace_id" and projection.workspace_id != value:
            return False
        if key == "resource_type" and projection.resource_type != value:
            return False
        if key == "source_kind" and projection.source_kind != value:
            return False
        if key == "visibility_refs_contains" and value not in projection.visibility_refs:
            return False
        if key in projection.metadata and projection.metadata[key] != value:
            return False
    return True
