from __future__ import annotations

import inspect
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
        query_timeout_ms: int = 2500,
        grounded_answer_timeout_ms: int = 7000,
        legacy_collection_resolver: Callable[[RagQueryRequest], Sequence[str]] | None = None,
    ) -> None:
        self._vector_index = vector_index
        self._embedding_client = embedding_client
        self._rerank_client = rerank_client
        self._grounded_answer_synthesizer = grounded_answer_synthesizer
        self._query_timeout_ms = query_timeout_ms
        self._grounded_answer_timeout_ms = grounded_answer_timeout_ms
        self._legacy_collection_resolver = legacy_collection_resolver

    def query(
        self,
        request: RagQueryRequest,
        *,
        post_filter: Callable[[RagVectorSearchHit], bool] | None = None,
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
        vector_hit_count = 0
        filtered_hit_count = 0
        rerank_applied = False
        rerank_degraded = False
        vector_hits: list[RagVectorSearchHit] = []
        rerank_client = self._rerank_client
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
            filtered_hits = (
                [hit for hit in raw_hits if post_filter(hit)]
                if post_filter is not None
                else list(raw_hits)
            )
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
            next_top_k = min(max(vector_top_k * 2, vector_top_k + _POST_FILTER_OVERSAMPLE_BUFFER), _MAX_VECTOR_TOP_K)
            if next_top_k <= vector_top_k:
                break
            vector_top_k = next_top_k

        if rerank_client is not None and vector_hits and _remaining_budget_ms(started, self._query_timeout_ms) > 0:
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
                    workspace_id=request.workspace_id,
                    source_kind=source_kind,
                    error=error,
                )
                rerank_degraded = True
            else:
                rerank_applied = True
                record_rerank_latency(
                    provider_name=_provider_name(rerank_client),
                    latency_ms=_elapsed_ms(rerank_started),
                    workspace_id=request.workspace_id,
                    source_kind=source_kind,
                )
        elif rerank_client is not None and vector_hits:
            rerank_degraded = True

        vector_hits = vector_hits[: request.top_k]

        hits = [_to_query_hit(hit) for hit in vector_hits]
        grounded_answer = None
        grounded_answer_degraded = False
        if (
            request.answer_mode == RagAnswerMode.GROUNDED_ANSWER
            and _remaining_budget_ms(started, self._query_timeout_ms) > 0
            and self._grounded_answer_timeout_ms > 0
        ):
            grounded_started = time.perf_counter()
            grounded_timeout_ms = min(
                self._grounded_answer_timeout_ms,
                _remaining_budget_ms(started, self._query_timeout_ms),
            )
            try:
                grounded_answer = self._build_grounded_answer(
                    request.query,
                    hits,
                    grounded_answer_synthesizer=grounded_answer_synthesizer,
                    timeout_ms=grounded_timeout_ms,
                )
            except Exception as error:
                _record_provider_failure(
                    provider_name=_grounded_answer_provider_name(
                        grounded_answer_synthesizer or self._grounded_answer_synthesizer
                    ),
                    operation="grounded_answer",
                    workspace_id=request.workspace_id,
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
                    workspace_id=request.workspace_id,
                    source_kind=source_kind,
                )
                if _elapsed_ms(grounded_started) > self._grounded_answer_timeout_ms:
                    grounded_answer = None
                    grounded_answer_degraded = True
            if grounded_answer is None and hits:
                grounded_answer_degraded = True
        elif request.answer_mode == RagAnswerMode.GROUNDED_ANSWER:
            grounded_answer_degraded = True

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
                "rerank_applied": rerank_applied,
                "rerank_degraded": rerank_degraded,
                "post_filter_applied": post_filter is not None,
                "grounded_answer_degraded": grounded_answer_degraded,
                "collections_consulted": list(query_collections),
                "legacy_collection_fallback_applied": len(query_collections) > 1,
            },
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
        lead_hits = list(hits[:3])
        text = " ".join(
            _safe_result_text(hit.summary or hit.title or hit.resource_id, max_chars=280)
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
                    quote=_safe_result_text(hit.summary or hit.title or hit.resource_id, max_chars=280),
                    locator=hit.citation,
                )
                for hit in lead_hits
            ],
            sources_used=sorted({hit.source_kind for hit in hits}),
        )

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
                        workspace_id=request.workspace_id,
                        query_embedding=query_embedding,
                        source_kinds=list(request.source_kinds),
                        metadata_filter=dict(request.filters),
                        top_k=top_k,
                        trace_context=request.trace_context,
                    ),
                )
            )
        return _dedupe_hits(hits)


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
        acl_summary=_summarize_acl_refs(projection.visibility_refs),
        origin_ref=projection.metadata.get("origin_ref") if projection.metadata else None,
        metadata=dict(hit.metadata),
    )


def _resolve_query_collections(
    *,
    request: RagQueryRequest,
    legacy_collection_resolver: Callable[[RagQueryRequest], Sequence[str]] | None,
) -> tuple[str, ...]:
    collections = [request.collection]
    if legacy_collection_resolver is not None:
        collections.extend(legacy_collection_resolver(request))
    return tuple(dict.fromkeys(collections))


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


def _query_hit_identity(hit: RagVectorSearchHit) -> tuple[str, str, str, str]:
    projection = hit.projection
    return (
        projection.workspace_id,
        projection.resource_type,
        projection.resource_id,
        hit.chunk_id,
    )


def _dedupe_hits(hits: Sequence[RagVectorSearchHit]) -> list[RagVectorSearchHit]:
    deduped: dict[tuple[str, str, str, str], RagVectorSearchHit] = {}
    for hit in hits:
        identity = _query_hit_identity(hit)
        existing = deduped.get(identity)
        if existing is None or hit.score > existing.score:
            deduped[identity] = hit
    return sorted(deduped.values(), key=lambda item: item.score, reverse=True)


def _summarize_acl_refs(visibility_refs: Sequence[str]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for raw_ref in visibility_refs:
        prefix = raw_ref.split(":", 1)[0]
        label = _ACL_SUMMARY_LABELS.get(prefix, prefix.replace("_", " "))
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


_ACL_SUMMARY_LABELS = {
    "workspace": "workspace",
    "workspace_public": "workspace public",
    "owner": "owner",
    "container": "container access",
    "share_user": "direct share",
    "link_share_ref": "link share",
    "meeting_grant": "meeting grant",
    "meeting_source": "meeting source",
    "meeting_organizer": "meeting organizer",
    "meeting_attendee": "meeting attendee",
    "team": "team access",
    "list": "list access",
    "issue_grant": "issue grant",
}


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


def _safe_result_text(value: str, *, max_chars: int) -> str:
    normalized = " ".join(value.split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
