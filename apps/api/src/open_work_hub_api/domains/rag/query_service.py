from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from open_work_hub_api.core.telemetry import current_trace_id
from open_work_hub_api.domains.rag.contracts import (
    RagAnswerMode,
    RagGroundedAnswer,
    RagQueryHit,
    RagQueryRequest,
    RagQueryResponse,
    RagVectorSearchHit,
    RagVectorSearchMode,
    RagVectorSearchRequest,
)
from open_work_hub_api.domains.rag.metrics import (
    record_embedding_latency,
    record_grounded_answer_latency,
    record_provider_error,
    record_provider_timeout,
    record_query_latency,
    record_rerank_latency,
)
from open_work_hub_api.domains.rag.providers.base import (
    EmbeddingClient,
    RerankClient,
    VectorIndexClient,
)
from open_work_hub_api.domains.rag.query_projection import (
    build_default_grounded_answer,
    build_query_profile,
    to_query_hit,
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
        query_timeout_ms: int = 210000,
        rerank_candidate_k: int = 80,
        vector_search_mode: RagVectorSearchMode = RagVectorSearchMode.DENSE_SPARSE_RRF,
        legacy_collection_resolver: Callable[[RagQueryRequest], Sequence[str]] | None = None,
    ) -> None:
        self._vector_index = vector_index
        self._embedding_client = embedding_client
        self._rerank_client = rerank_client
        self._grounded_answer_synthesizer = grounded_answer_synthesizer
        self._query_timeout_ms = query_timeout_ms
        self._rerank_candidate_k = min(max(rerank_candidate_k, 1), _MAX_VECTOR_TOP_K)
        self._vector_search_mode = vector_search_mode
        self._legacy_collection_resolver = legacy_collection_resolver

    def query(
        self,
        request: RagQueryRequest,
        *,
        post_filter: Callable[[RagVectorSearchHit], bool] | None = None,
        hit_hydrator: (
            Callable[[Sequence[RagVectorSearchHit]], Sequence[RagVectorSearchHit]] | None
        ) = None,
        grounded_answer_synthesizer: RagGroundedAnswerSynthesizer | None = None,
    ) -> RagQueryResponse:
        started = time.perf_counter()
        source_kind = request.source_kinds[0] if len(request.source_kinds) == 1 else None
        embedding_started = time.perf_counter()
        try:
            embed_timeout_ms = _remaining_budget_ms(started, self._query_timeout_ms)
            _ensure_budget_remaining(embed_timeout_ms, operation="embed_query")
            query_embedding = _call_with_optional_timeout(
                self._embedding_client.embed_query,
                timeout_seconds=_timeout_seconds_from_ms(embed_timeout_ms),
                text=request.query,
            )
        except Exception as error:
            _record_provider_failure(
                provider_name=_provider_name(self._embedding_client),
                operation="embed_query",
                source_kind=source_kind,
                error=error,
            )
            raise
        record_embedding_latency(
            provider_name=_provider_name(self._embedding_client),
            operation="query_embedding",
            latency_ms=_elapsed_ms(embedding_started),
            source_kind=source_kind,
        )
        vector_hit_count = 0
        filtered_hit_count = 0
        rerank_applied = False
        rerank_degraded = False
        vector_hits: list[RagVectorSearchHit] = []
        rerank_client = self._rerank_client
        retrieval_top_k = request.top_k
        if rerank_client is not None:
            retrieval_top_k = max(request.top_k, self._rerank_candidate_k)
        vector_top_k = _resolve_vector_top_k(retrieval_top_k, post_filter=post_filter)
        query_collections = _resolve_query_collections(
            request=request,
            legacy_collection_resolver=self._legacy_collection_resolver,
        )
        while True:
            raw_hits = self._query_collections(
                collections=query_collections,
                request=request,
                query_embedding=query_embedding,
                top_k=vector_top_k,
                timeout_ms=_remaining_budget_ms(started, self._query_timeout_ms),
            )
            vector_hit_count = len(raw_hits)
            filtered_hits = _apply_post_filter(post_filter, raw_hits)
            filtered_hit_count = len(filtered_hits)
            vector_hits = filtered_hits
            if post_filter is None:
                break
            if len(filtered_hits) >= request.top_k:
                break
            max_possible_hits = vector_top_k * len(query_collections)
            if vector_top_k >= _MAX_VECTOR_TOP_K or vector_hit_count < max_possible_hits:
                break
            if _remaining_budget_ms(started, self._query_timeout_ms) <= 0:
                break
            next_top_k = min(
                max(vector_top_k * 2, vector_top_k + _POST_FILTER_OVERSAMPLE_BUFFER),
                _MAX_VECTOR_TOP_K,
            )
            if next_top_k <= vector_top_k:
                break
            vector_top_k = next_top_k

        if (
            rerank_client is not None
            and vector_hits
            and _remaining_budget_ms(started, self._query_timeout_ms) > 0
        ):
            rerank_started = time.perf_counter()
            try:
                rerank_timeout_ms = _remaining_budget_ms(started, self._query_timeout_ms)
                _ensure_budget_remaining(rerank_timeout_ms, operation="rerank")
                vector_hits = _call_with_optional_timeout(
                    rerank_client.rerank,
                    timeout_seconds=_timeout_seconds_from_ms(rerank_timeout_ms),
                    query=request.query,
                    hits=vector_hits,
                )
            except Exception as error:
                _record_provider_failure(
                    provider_name=_provider_name(rerank_client),
                    operation="rerank",
                    source_kind=source_kind,
                    error=error,
                )
                rerank_degraded = True
            else:
                rerank_applied = True
                record_rerank_latency(
                    provider_name=_provider_name(rerank_client),
                    latency_ms=_elapsed_ms(rerank_started),
                    source_kind=source_kind,
                )
        elif rerank_client is not None and vector_hits:
            rerank_degraded = True

        # Refresh response metadata from source state before the final ACL.
        # Hydration is never an authorization grant and may only narrow or
        # rewrite the candidate set.
        if hit_hydrator is not None:
            vector_hits = _apply_hit_hydrator(hit_hydrator, vector_hits)

        # Re-run the source-owned ACL after rerank/hydration and immediately
        # before any hit can flow to projection, grounding, or citation
        # assembly. This is the final authorization linearization point.
        vector_hits = _apply_post_filter(post_filter, vector_hits)
        filtered_hit_count = len(vector_hits)
        vector_hits = vector_hits[: request.top_k]

        hits = [to_query_hit(hit) for hit in vector_hits]
        grounded_answer = None
        grounded_answer_degraded = False
        if request.answer_mode == RagAnswerMode.GROUNDED_ANSWER:
            grounded_started = time.perf_counter()
            try:
                grounded_answer = self._build_grounded_answer(
                    request.query,
                    hits,
                    grounded_answer_synthesizer=grounded_answer_synthesizer,
                    timeout_ms=None,
                )
            except Exception as error:
                _record_provider_failure(
                    provider_name=_grounded_answer_provider_name(
                        grounded_answer_synthesizer or self._grounded_answer_synthesizer
                    ),
                    operation="grounded_answer",
                    source_kind=source_kind,
                    error=error,
                )
                grounded_answer_degraded = True
            finally:
                record_grounded_answer_latency(
                    provider_name=_grounded_answer_provider_name(
                        grounded_answer_synthesizer or self._grounded_answer_synthesizer
                    ),
                    latency_ms=_elapsed_ms(grounded_started),
                    source_kind=source_kind,
                )
            if grounded_answer is None and hits:
                grounded_answer_degraded = True

        if (
            request.answer_mode == RagAnswerMode.GROUNDED_ANSWER
            and grounded_answer is None
            and hits
        ):
            grounded_answer = build_default_grounded_answer(query=request.query, hits=hits)
            grounded_answer_degraded = True

        latency_ms = int((time.perf_counter() - started) * 1000)
        record_query_latency(
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
            query_profile=build_query_profile(
                vector_requested_top_k=vector_top_k,
                vector_hit_count=vector_hit_count,
                post_filtered_hit_count=filtered_hit_count,
                returned_hit_count=len(hits),
                rerank_applied=rerank_applied,
                rerank_degraded=rerank_degraded,
                post_filter_applied=post_filter is not None,
                grounded_answer_degraded=grounded_answer_degraded,
                collections_consulted=query_collections,
                vector_search_mode=self._vector_search_mode.value,
            ),
            trace_id=current_trace_id(),
            latency_ms=latency_ms,
        )

    def _build_grounded_answer(
        self,
        query: str,
        hits: Sequence[RagQueryHit],
        *,
        grounded_answer_synthesizer: RagGroundedAnswerSynthesizer | None = None,
        timeout_ms: int | None = None,
    ) -> RagGroundedAnswer | None:
        if not hits:
            return None
        synthesizer = grounded_answer_synthesizer or self._grounded_answer_synthesizer
        if synthesizer is not None:
            return _call_with_optional_timeout(
                synthesizer.synthesize,
                timeout_ms=timeout_ms,
                query=query,
                hits=hits,
            )
        return build_default_grounded_answer(query=query, hits=hits)

    def _query_collections(
        self,
        *,
        collections: Sequence[str],
        request: RagQueryRequest,
        query_embedding: list[float],
        top_k: int,
        timeout_ms: int,
    ) -> list[RagVectorSearchHit]:
        hits: list[RagVectorSearchHit] = []
        for collection in collections:
            collection_timeout_ms = timeout_ms
            _ensure_budget_remaining(collection_timeout_ms, operation="vector_query")
            hits.extend(
                _call_with_optional_timeout(
                    self._vector_index.query,
                    timeout_seconds=_timeout_seconds_from_ms(collection_timeout_ms),
                    request=RagVectorSearchRequest(
                        collection=collection,
                        query=request.query,
                        scope_kind=request.scope_kind,
                        query_embedding=query_embedding,
                        retrieval_partition_ids=request.retrieval_partition_ids,
                        source_kinds=list(request.source_kinds),
                        metadata_filter=dict(request.filters),
                        search_mode=self._vector_search_mode,
                        top_k=top_k,
                        trace_context=request.trace_context,
                    ),
                )
            )
        return _dedupe_hits(hits)


def _resolve_query_collections(
    *,
    request: RagQueryRequest,
    legacy_collection_resolver: Callable[[RagQueryRequest], Sequence[str]] | None,
) -> tuple[str, ...]:
    collections = [request.collection]
    if legacy_collection_resolver is not None:
        collections.extend(legacy_collection_resolver(request))
    return tuple(dict.fromkeys(collections))


def _apply_post_filter(
    post_filter: Callable[[RagVectorSearchHit], bool] | None,
    hits: Sequence[RagVectorSearchHit],
) -> list[RagVectorSearchHit]:
    if post_filter is None:
        return list(hits)
    filter_many = getattr(post_filter, "filter_many", None)
    if callable(filter_many):
        return list(filter_many(hits))
    return [hit for hit in hits if post_filter(hit)]


def _apply_hit_hydrator(
    hit_hydrator: Callable[
        [Sequence[RagVectorSearchHit]],
        Sequence[RagVectorSearchHit],
    ],
    hits: Sequence[RagVectorSearchHit],
) -> list[RagVectorSearchHit]:
    candidate_keys = {
        (hit.projection.resource_type, hit.projection.resource_id, hit.chunk_id) for hit in hits
    }
    hydrated = list(hit_hydrator(hits))
    if any(
        (hit.projection.resource_type, hit.projection.resource_id, hit.chunk_id)
        not in candidate_keys
        for hit in hydrated
    ):
        raise ValueError("RAG hit hydrator may not add retrieval candidates")
    return hydrated


def _remaining_budget_ms(started: float, timeout_ms: int) -> int:
    return timeout_ms - _elapsed_ms(started)


def _timeout_seconds_from_ms(timeout_ms: int | None) -> float | None:
    if timeout_ms is None or timeout_ms <= 0:
        return None
    return max(timeout_ms / 1000, 0.001)


def _ensure_budget_remaining(timeout_ms: int, *, operation: str) -> None:
    if timeout_ms > 0:
        return
    raise TimeoutError(f"RAG query budget exhausted before {operation}.")


def _call_with_optional_timeout(
    method,
    *,
    timeout_seconds: float | None = None,
    timeout_ms: int | None = None,
    **kwargs,
):
    if timeout_seconds is not None and _accepts_keyword(method, "timeout_seconds"):
        kwargs["timeout_seconds"] = timeout_seconds
    if timeout_ms is not None and _accepts_keyword(method, "timeout_ms"):
        kwargs["timeout_ms"] = timeout_ms
    return method(**kwargs)


def _accepts_keyword(method, keyword: str) -> bool:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        return False
    return keyword in signature.parameters


def _query_hit_identity(hit: RagVectorSearchHit) -> tuple[str, str | None, str, str, str]:
    projection = hit.projection
    return (
        projection.scope_kind.value,
        projection.resource_type,
        projection.resource_id,
        hit.chunk_id,
    )


def _dedupe_hits(hits: Sequence[RagVectorSearchHit]) -> list[RagVectorSearchHit]:
    deduped: dict[tuple[str, str | None, str, str, str], RagVectorSearchHit] = {}
    for hit in hits:
        identity = _query_hit_identity(hit)
        existing = deduped.get(identity)
        if existing is None or hit.score > existing.score:
            deduped[identity] = hit
    return sorted(deduped.values(), key=lambda item: item.score, reverse=True)


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
    source_kind: str | None,
    error: Exception,
) -> None:
    error_type = error.__class__.__name__
    if _is_timeout_error(error):
        record_provider_timeout(
            provider_name=provider_name,
            operation=operation,
            source_kind=source_kind,
            error_type=error_type,
        )
        return
    record_provider_error(
        provider_name=provider_name,
        operation=operation,
        source_kind=source_kind,
        error_type=error_type,
    )


def _is_timeout_error(error: Exception) -> bool:
    if isinstance(error, TimeoutError):
        return True
    return "timeout" in error.__class__.__name__.lower()
