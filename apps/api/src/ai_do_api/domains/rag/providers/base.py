from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ai_do_api.domains.rag.contracts import (
    RagDeleteRequest,
    RagProviderHealth,
    RagUpsertRequest,
    RagVectorRecord,
    RagVectorSearchHit,
    RagVectorSearchRequest,
)


class RagProviderConfigurationError(RuntimeError):
    pass


class VectorIndexClient(Protocol):
    def healthcheck(self) -> RagProviderHealth: ...

    def ensure_collection(
        self,
        *,
        collection: str,
        dense_dimensions: int,
        sparse_enabled: bool = True,
    ) -> None: ...

    def delete_collection(self, *, collection: str) -> bool: ...

    def upsert_chunks(
        self,
        *,
        request: RagUpsertRequest,
        records: list[RagVectorRecord],
    ) -> int: ...

    def delete_resource(self, *, request: RagDeleteRequest) -> int: ...

    def delete_chunks_at_or_after(
        self,
        *,
        request: RagDeleteRequest,
        chunk_index: int,
    ) -> int: ...

    def query(
        self,
        *,
        request: RagVectorSearchRequest,
        timeout_seconds: float | None = None,
    ) -> list[RagVectorSearchHit]: ...


class EmbeddingClient(Protocol):
    def healthcheck(self) -> RagProviderHealth: ...

    def embed_texts(
        self,
        texts: list[str],
        timeout_seconds: float | None = None,
    ) -> list[list[float]]: ...

    def embed_query(
        self,
        text: str,
        timeout_seconds: float | None = None,
    ) -> list[float]: ...


class OcrClient(Protocol):
    def healthcheck(self) -> RagProviderHealth: ...

    def extract_text(self, *, content: bytes, content_type: str | None = None) -> str: ...


class AsrClient(Protocol):
    def healthcheck(self) -> RagProviderHealth: ...

    def transcribe(self, *, content: bytes, content_type: str | None = None) -> str: ...


class RerankClient(Protocol):
    def healthcheck(self) -> RagProviderHealth: ...

    def rerank(
        self,
        *,
        query: str,
        hits: list[RagVectorSearchHit],
        timeout_seconds: float | None = None,
    ) -> list[RagVectorSearchHit]: ...


@dataclass(slots=True)
class RagProviderBundle:
    vector_index: VectorIndexClient
    embedding: EmbeddingClient
    ocr: OcrClient | None = None
    asr: AsrClient | None = None
    rerank: RerankClient | None = None
