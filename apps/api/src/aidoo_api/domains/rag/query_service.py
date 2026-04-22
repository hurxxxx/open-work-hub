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
from aidoo_api.domains.rag.metrics import (
    record_embedding_latency,
    record_grounded_answer_latency,
    record_provider_error,
    record_provider_timeout,
    record_query_latency,
    record_rerank_latency,
)
from aidoo_api.domains.rag.providers.base import (
    EmbeddingClient,
    RerankClient,
    VectorIndexClient,
)

_MAX_VECTOR_TOP_K = 100
_POST_FILTER_OVERSAMPLE_MULTIPLIER = 5
_POST_FILTER_OVERSAMPLE_BUFFER = 10


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
        source_kind = request.source_kinds[0] if len(request.source_kinds) == 1 else None
        embedding_started = time.perf_counter()
        try:
            query_embedding = self._embedding_client.embed_query(request.query)
        except Exception as error:
            _record_provider_failure(
                provider_name=_provider_name(self._embedding_client),
                operation="embed_query",
                workspace_id=request.workspace_id,
                source_kind=source_kind,
                error=error,
            )
            raise
        record_embedding_latency(
            provider_name=_provider_name(self._embedding_client),
            operation="query_embedding",
            latency_ms=_elapsed_ms(embedding_started),
            workspace_id=request.workspace_id,
            source_kind=source_kind,
        )
        vector_top_k = _resolve_vector_top_k(request.top_k, post_filter=post_filter)
        vector_hits = self._vector_index.query(
            request=RagVectorSearchRequest(
                collection=request.collection,
                query=request.query,
                workspace_id=request.workspace_id,
                query_embedding=query_embedding,
                source_kinds=list(request.source_kinds),
                metadata_filter=dict(request.filters),
                top_k=vector_top_k,
                trace_context=request.trace_context,
            )
        )
        vector_hit_count = len(vector_hits)
        if self._rerank_client is not None:
            rerank_started = time.perf_counter()
            try:
                vector_hits = self._rerank_client.rerank(query=request.query, hits=vector_hits)
            except Exception as error:
                _record_provider_failure(
                    provider_name=_provider_name(self._rerank_client),
                    operation="rerank",
                    workspace_id=request.workspace_id,
                    source_kind=source_kind,
                    error=error,
                )
                raise
            record_rerank_latency(
                provider_name=_provider_name(self._rerank_client),
                latency_ms=_elapsed_ms(rerank_started),
                workspace_id=request.workspace_id,
                source_kind=source_kind,
            )
        if post_filter is not None:
            vector_hits = [hit for hit in vector_hits if post_filter(hit)]
        filtered_hit_count = len(vector_hits)
        vector_hits = vector_hits[: request.top_k]

        hits = [_to_query_hit(hit) for hit in vector_hits]
        grounded_answer = None
        if request.answer_mode == RagAnswerMode.GROUNDED_ANSWER:
            grounded_started = time.perf_counter()
            try:
                grounded_answer = self._build_grounded_answer(request.query, hits)
            finally:
                record_grounded_answer_latency(
                    provider_name=_grounded_answer_provider_name(self._grounded_answer_synthesizer),
                    latency_ms=_elapsed_ms(grounded_started),
                    workspace_id=request.workspace_id,
                    source_kind=source_kind,
                )

        latency_ms = int((time.perf_counter() - started) * 1000)
        record_query_latency(
            workspace_id=request.workspace_id,
            answer_mode=request.answer_mode.value,
            latency_ms=latency_ms,
            source_kind=source_kind,
        )
        return RagQueryResponse(
            query=request.query,
            answer_mode=request.answer_mode,
            hits=hits,
            grounded_answer=grounded_answer,
            sources_used=sorted({hit.source_kind for hit in hits}),
            query_profile={
                "vector_requested_top_k": vector_top_k,
                "vector_hit_count": vector_hit_count,
                "post_filtered_hit_count": filtered_hit_count,
                "returned_hit_count": len(hits),
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


def _provider_name(provider: object) -> str | None:
    return getattr(provider, "provider_name", provider.__class__.__name__)


def _grounded_answer_provider_name(provider: object | None) -> str:
    if provider is None:
        return "default-grounded-answer"
    return _provider_name(provider) or "grounded-answer"


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _resolve_vector_top_k(
    top_k: int,
    *,
    post_filter: Callable[[RagVectorSearchHit], bool] | None,
) -> int:
    if post_filter is None:
        return top_k
    return min(
        max(top_k * _POST_FILTER_OVERSAMPLE_MULTIPLIER, top_k + _POST_FILTER_OVERSAMPLE_BUFFER),
        _MAX_VECTOR_TOP_K,
    )


def _record_provider_failure(
    *,
    provider_name: str | None,
    operation: str,
    workspace_id: str | None,
    source_kind: str | None,
    error: Exception,
) -> None:
    error_type = error.__class__.__name__
    if _is_timeout_error(error):
        record_provider_timeout(
            provider_name=provider_name,
            operation=operation,
            workspace_id=workspace_id,
            source_kind=source_kind,
            error_type=error_type,
        )
        return
    record_provider_error(
        provider_name=provider_name,
        operation=operation,
        workspace_id=workspace_id,
        source_kind=source_kind,
        error_type=error_type,
    )


def _is_timeout_error(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    return "timeout" in error.__class__.__name__.lower()
