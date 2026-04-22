from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Protocol

from aidoo_api.core.telemetry import current_trace_id
from aidoo_api.domains.rag.contracts import (
    RagAnswerMode,
    RagGroundedAnswer,
    RagGroundedCitation,
    RagQueryHit,
    RagQueryRequest,
    RagQueryResponse,
    RagVectorSearchHit,
    RagVectorSearchRequest,
)
from aidoo_api.domains.rag.metrics import record_query_latency
from aidoo_api.domains.rag.providers.base import (
    EmbeddingClient,
    RerankClient,
    VectorIndexClient,
)


class RagGroundedAnswerSynthesizer(Protocol):
    def synthesize(
        self,
        *,
        query: str,
        hits: Sequence[RagQueryHit],
    ) -> RagGroundedAnswer | None: ...


class RagQueryService:
    def __init__(
        self,
        *,
        vector_index: VectorIndexClient,
        embedding_client: EmbeddingClient,
        rerank_client: RerankClient | None = None,
        grounded_answer_synthesizer: RagGroundedAnswerSynthesizer | None = None,
    ) -> None:
        self._vector_index = vector_index
        self._embedding_client = embedding_client
        self._rerank_client = rerank_client
        self._grounded_answer_synthesizer = grounded_answer_synthesizer

    def query(
        self,
        request: RagQueryRequest,
        *,
        post_filter: Callable[[RagVectorSearchHit], bool] | None = None,
    ) -> RagQueryResponse:
        started = time.perf_counter()
        query_embedding = self._embedding_client.embed_query(request.query)
        vector_hits = self._vector_index.query(
            request=RagVectorSearchRequest(
                collection=request.collection,
                query=request.query,
                workspace_id=request.workspace_id,
                query_embedding=query_embedding,
                source_kinds=list(request.source_kinds),
                metadata_filter=dict(request.filters),
                top_k=request.top_k,
                trace_context=request.trace_context,
            )
        )
        if self._rerank_client is not None:
            vector_hits = self._rerank_client.rerank(query=request.query, hits=vector_hits)
        if post_filter is not None:
            vector_hits = [hit for hit in vector_hits if post_filter(hit)]

        hits = [_to_query_hit(hit) for hit in vector_hits]
        grounded_answer = None
        if request.answer_mode == RagAnswerMode.GROUNDED_ANSWER:
            grounded_answer = self._build_grounded_answer(request.query, hits)

        latency_ms = int((time.perf_counter() - started) * 1000)
        record_query_latency(
            workspace_id=request.workspace_id,
            answer_mode=request.answer_mode.value,
            latency_ms=latency_ms,
            source_kind=request.source_kinds[0] if len(request.source_kinds) == 1 else None,
        )
        return RagQueryResponse(
            query=request.query,
            answer_mode=request.answer_mode,
            hits=hits,
            grounded_answer=grounded_answer,
            sources_used=sorted({hit.source_kind for hit in hits}),
            query_profile={
                "vector_hit_count": len(vector_hits),
                "rerank_applied": self._rerank_client is not None,
                "post_filter_applied": post_filter is not None,
            },
            trace_id=current_trace_id(),
            latency_ms=latency_ms,
        )

    def _build_grounded_answer(
        self,
        query: str,
        hits: Sequence[RagQueryHit],
    ) -> RagGroundedAnswer | None:
        if not hits:
            return None
        if self._grounded_answer_synthesizer is not None:
            return self._grounded_answer_synthesizer.synthesize(query=query, hits=hits)
        lead_hits = list(hits[:3])
        text = " ".join(
            hit.summary or hit.title or hit.resource_id
            for hit in lead_hits
            if hit.summary or hit.title
        )
        if not text:
            text = f"'{query}'와 관련된 검색 결과 {len(hits)}건을 찾았습니다."
        return RagGroundedAnswer(
            text=text,
            citations=[
                RagGroundedCitation(
                    resource_id=hit.resource_id,
                    source_kind=hit.source_kind,
                    quote=hit.summary or hit.title or hit.resource_id,
                    locator=hit.citation,
                )
                for hit in lead_hits
            ],
            sources_used=sorted({hit.source_kind for hit in hits}),
        )


def _to_query_hit(hit: RagVectorSearchHit) -> RagQueryHit:
    projection = hit.projection
    return RagQueryHit(
        source_kind=projection.source_kind,
        resource_type=projection.resource_type,
        resource_id=projection.resource_id,
        workspace_id=projection.workspace_id,
        title=projection.title,
        summary=hit.summary or projection.summary,
        score=hit.score,
        citation=hit.citation,
        owner_label=projection.owner_label,
        acl_summary=list(projection.visibility_refs),
        origin_ref=projection.metadata.get("origin_ref") if projection.metadata else None,
        metadata=dict(hit.metadata),
    )
