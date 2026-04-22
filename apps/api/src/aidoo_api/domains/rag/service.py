from __future__ import annotations

from aidoo_api.domains.rag.contracts import (
    RagDeleteRequest,
    RagProjection,
    RagSyncOperation,
    RagSyncResult,
    RagUpsertRequest,
    RagVectorRecord,
)
from aidoo_api.domains.rag.projection import projection_to_chunks
from aidoo_api.domains.rag.providers.base import (
    AsrClient,
    EmbeddingClient,
    OcrClient,
    RerankClient,
    VectorIndexClient,
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
        default_collection: str = "doowon-rag-dev",
    ) -> None:
        self._vector_index = vector_index
        self._embedding_client = embedding_client
        self._ocr_client = ocr_client
        self._asr_client = asr_client
        self._rerank_client = rerank_client
        self._default_collection = default_collection

    def sync_projection(
        self,
        projection: RagProjection,
        *,
        collection: str | None = None,
    ) -> RagSyncResult:
        resolved_collection = collection or self._default_collection
        chunks = projection_to_chunks(projection)
        embeddings = self._embedding_client.embed_texts([chunk.text for chunk in chunks])
        dense_dimensions = len(embeddings[0]) if embeddings else 0
        self._vector_index.ensure_collection(
            collection=resolved_collection,
            dense_dimensions=dense_dimensions,
            sparse_enabled=True,
        )
        records = [
            RagVectorRecord(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                summary=chunk.summary,
                embedding=embedding,
                sparse_terms=_build_sparse_terms(chunk.text),
                projection=projection,
                metadata=dict(chunk.metadata),
            )
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        request = RagUpsertRequest(
            collection=resolved_collection,
            projection=projection,
            chunks=chunks,
        )
        written = self._vector_index.upsert_chunks(request=request, records=records)
        return RagSyncResult(
            collection=resolved_collection,
            operation=RagSyncOperation.UPSERT,
            chunk_count=written,
        )

    def delete_projection(
        self,
        *,
        workspace_id: str,
        resource_type: str,
        resource_id: str,
        collection: str | None = None,
    ) -> RagSyncResult:
        resolved_collection = collection or self._default_collection
        deleted = self._vector_index.delete_resource(
            request=RagDeleteRequest(
                collection=resolved_collection,
                workspace_id=workspace_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
        return RagSyncResult(
            collection=resolved_collection,
            operation=RagSyncOperation.DELETE,
            deleted_count=deleted,
        )


def _build_sparse_terms(text: str) -> dict[str, float]:
    sparse_terms: dict[str, float] = {}
    for token in text.lower().replace("\n", " ").split(" "):
        normalized = token.strip()
        if not normalized:
            continue
        sparse_terms[normalized] = sparse_terms.get(normalized, 0.0) + 1.0
    return sparse_terms
