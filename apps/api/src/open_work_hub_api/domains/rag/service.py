from __future__ import annotations

import time
from collections.abc import Callable

from open_work_hub_api.domains.rag.contracts import (
    RagDeleteRequest,
    RagProjection,
    RagScopeKind,
    RagSyncOperation,
    RagSyncResult,
    RagUpsertRequest,
)
from open_work_hub_api.domains.rag.metrics import (
    record_embedding_latency,
    record_ingest_latency,
    record_ocr_latency,
    record_provider_error,
    record_provider_timeout,
)
from open_work_hub_api.domains.rag.projection import projection_to_chunks
from open_work_hub_api.domains.rag.providers import RagProviderConfigurationError
from open_work_hub_api.domains.rag.providers.base import (
    AsrClient,
    EmbeddingClient,
    OcrClient,
    RerankClient,
    VectorIndexClient,
)
from open_work_hub_api.domains.rag.vector_records import (
    build_rag_vector_records,
    projection_dense_dimensions,
)


class RagService:
    def __init__(
        self,
        *,
        vector_index: VectorIndexClient,
        embedding_client: EmbeddingClient,
        ocr_client: OcrClient | None = None,
        asr_client: AsrClient | None = None,
        rerank_client: RerankClient | None = None,
        default_collection: str = "open-work-hub-dev-rag-dev",
    ) -> None:
        self._vector_index = vector_index
        self._embedding_client = embedding_client
        self._ocr_client = ocr_client
        self._asr_client = asr_client
        self._rerank_client = rerank_client
        self._default_collection = default_collection

    @property
    def ocr_provider_name(self) -> str | None:
        if self._ocr_client is None:
            return None
        return _provider_name(self._ocr_client)

    def sync_projection(
        self,
        projection: RagProjection,
        *,
        collection: str | None = None,
    ) -> RagSyncResult:
        return self._sync_projection(
            projection,
            collection=collection,
            before_vector_write=None,
        )

    def sync_projection_with_fence(
        self,
        projection: RagProjection,
        *,
        collection: str | None = None,
        before_vector_write: Callable[[], None],
    ) -> RagSyncResult:
        """Embed first, then acquire the caller's final fence before vector mutation."""

        return self._sync_projection(
            projection,
            collection=collection,
            before_vector_write=before_vector_write,
        )

    def _sync_projection(
        self,
        projection: RagProjection,
        *,
        collection: str | None,
        before_vector_write: Callable[[], None] | None,
    ) -> RagSyncResult:
        started = time.perf_counter()
        resolved_collection = collection or self._default_collection
        chunks = projection_to_chunks(projection)
        index_texts = [chunk.index_text or chunk.text for chunk in chunks]
        embedding_started = time.perf_counter()
        try:
            embeddings = self._embedding_client.embed_texts(index_texts)
        except Exception as error:
            _record_provider_failure(
                provider_name=_provider_name(self._embedding_client),
                operation="embed_texts",
                resource_type=projection.resource_type,
                source_kind=projection.source_kind,
                error=error,
            )
            raise
        record_embedding_latency(
            provider_name=_provider_name(self._embedding_client),
            operation="ingest_embedding",
            latency_ms=_elapsed_ms(embedding_started),
            resource_type=projection.resource_type,
            source_kind=projection.source_kind,
        )
        dense_dimensions = projection_dense_dimensions(embeddings)
        records = build_rag_vector_records(
            projection=projection,
            chunks=chunks,
            index_texts=index_texts,
            embeddings=embeddings,
        )
        if before_vector_write is not None:
            before_vector_write()
        try:
            self._vector_index.ensure_collection(
                collection=resolved_collection,
                dense_dimensions=dense_dimensions,
                sparse_enabled=True,
            )
            request = RagUpsertRequest(
                collection=resolved_collection,
                projection=projection,
                chunks=chunks,
            )
            written = self._vector_index.upsert_chunks(request=request, records=records)
            stale_deleted = self._vector_index.delete_chunks_at_or_after(
                request=RagDeleteRequest(
                    collection=resolved_collection,
                    retrieval_partition_id=projection.retrieval_partition_id,
                    scope_kind=projection.scope_kind,
                    resource_type=projection.resource_type,
                    resource_id=projection.resource_id,
                ),
                chunk_index=len(records),
            )
        except Exception as error:
            _record_provider_failure(
                provider_name=_provider_name(self._vector_index),
                operation="ingest_upsert",
                resource_type=projection.resource_type,
                source_kind=projection.source_kind,
                error=error,
            )
            raise
        record_ingest_latency(
            resource_type=projection.resource_type,
            source_kind=projection.source_kind,
            provider_name=_provider_name(self._vector_index),
            latency_ms=_elapsed_ms(started),
        )
        return RagSyncResult(
            collection=resolved_collection,
            operation=RagSyncOperation.UPSERT,
            chunk_count=written,
            deleted_count=stale_deleted,
        )

    def delete_projection(
        self,
        *,
        scope_kind: RagScopeKind = RagScopeKind.COMPANY,
        resource_type: str,
        resource_id: str,
        collection: str | None = None,
        retrieval_partition_id: str | None = None,
    ) -> RagSyncResult:
        resolved_collection = collection or self._default_collection
        deleted = self._vector_index.delete_resource(
            request=RagDeleteRequest(
                collection=resolved_collection,
                retrieval_partition_id=retrieval_partition_id,
                scope_kind=scope_kind,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
        return RagSyncResult(
            collection=resolved_collection,
            operation=RagSyncOperation.DELETE,
            deleted_count=deleted,
        )

    def delete_collection(self, *, collection: str) -> bool:
        """Delete one explicitly named collection owned by a bounded workflow."""

        return self._vector_index.delete_collection(collection=collection)

    def extract_text(
        self,
        *,
        content: bytes,
        content_type: str | None = None,
        resource_type: str | None = None,
        source_kind: str | None = None,
    ) -> str:
        if self._ocr_client is None:
            raise RagProviderConfigurationError("OCR client is not configured for RagService")
        started = time.perf_counter()
        try:
            text = self._ocr_client.extract_text(content=content, content_type=content_type)
        except Exception as error:
            _record_provider_failure(
                provider_name=_provider_name(self._ocr_client),
                operation="ocr",
                resource_type=resource_type,
                source_kind=source_kind,
                error=error,
            )
            raise
        record_ocr_latency(
            provider_name=_provider_name(self._ocr_client),
            latency_ms=_elapsed_ms(started),
            resource_type=resource_type,
            source_kind=source_kind,
        )
        return text


def _provider_name(provider: object) -> str | None:
    return getattr(provider, "provider_name", provider.__class__.__name__)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _record_provider_failure(
    *,
    provider_name: str | None,
    operation: str,
    resource_type: str | None,
    source_kind: str | None,
    error: Exception,
) -> None:
    error_type = error.__class__.__name__
    if _is_timeout_error(error):
        record_provider_timeout(
            provider_name=provider_name,
            operation=operation,
            resource_type=resource_type,
            source_kind=source_kind,
            error_type=error_type,
        )
        return
    record_provider_error(
        provider_name=provider_name,
        operation=operation,
        resource_type=resource_type,
        source_kind=source_kind,
        error_type=error_type,
    )


def _is_timeout_error(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    return "timeout" in error.__class__.__name__.lower()
