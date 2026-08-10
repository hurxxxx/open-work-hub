from __future__ import annotations

from collections.abc import Sequence

from open_work_hub_api.domains.rag.chunking import build_korean_sparse_terms as build_sparse_terms
from open_work_hub_api.domains.rag.contracts import RagChunk, RagProjection, RagVectorRecord


def projection_dense_dimensions(embeddings: Sequence[Sequence[float]]) -> int:
    return len(embeddings[0]) if embeddings else 0


def build_rag_vector_records(
    projection: RagProjection,
    chunks: Sequence[RagChunk],
    index_texts: Sequence[str],
    embeddings: Sequence[Sequence[float]],
) -> list[RagVectorRecord]:
    return [
        RagVectorRecord(
            chunk_id=chunk.chunk_id,
            text=chunk.text,
            summary=chunk.summary,
            embedding=list(embedding),
            sparse_terms=build_sparse_terms(index_text),
            projection=projection,
            metadata=dict(chunk.metadata),
        )
        for chunk, index_text, embedding in zip(chunks, index_texts, embeddings, strict=True)
    ]
