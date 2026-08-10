from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from ai_do_api.domains.rag.contracts import (
    RagProjection,
    RagScopeKind,
    RagVectorSearchHit,
)
from ai_do_api.domains.rag.providers.base import RerankClient
from ai_do_api.domains.retrieval.contracts import RetrievalHit


RRF_K = 60
MIN_CANDIDATE_K = 80
# Existing OpenSearch and Generic RAG query interfaces cap candidate reads at
# 100. Keep the public contracts narrow rather than widening both backends just
# for orchestration.
MAX_CANDIDATE_K = 100
RERANK_TIMEOUT_SECONDS = 5.0
MAX_MERGED_EXCERPT_CHARS = 1400
MIN_NORMALIZED_RERANK_SCORE = 0.001
MIN_RERANK_SCORE_SPREAD = 0.000001


@dataclass(frozen=True, slots=True)
class RetrievalRankingResult:
    hits: tuple[RetrievalHit, ...]
    profile: dict[str, Any]


def candidate_limit(top_k: int) -> int:
    return min(max(int(top_k) * 4, MIN_CANDIDATE_K), MAX_CANDIDATE_K)


def dedupe_ranked_hits(hits: Sequence[RetrievalHit]) -> RetrievalRankingResult:
    """Collapse duplicate resource hits without changing a backend's score scale."""

    by_identity: dict[tuple[str, str], RetrievalHit] = {}
    for hit in sorted(hits, key=lambda item: item.score, reverse=True):
        identity = canonical_resource_identity(hit)
        existing = by_identity.get(identity)
        if existing is None:
            by_identity[identity] = _with_retrieval_metadata(hit, backend=hit.source, rank=None)
        else:
            by_identity[identity] = _merge_resource_hits(existing, hit)
    ranked = tuple(sorted(by_identity.values(), key=lambda item: item.score, reverse=True))
    return RetrievalRankingResult(
        hits=ranked,
        profile={
            "mode": "single_backend",
            "candidate_count": len(hits),
            "deduped_resource_count": len(ranked),
        },
    )


def fuse_ranked_hits(
    backend_hits: Mapping[str, Sequence[RetrievalHit]],
    *,
    rrf_k: int = RRF_K,
) -> RetrievalRankingResult:
    """Fuse independent ranked lists by canonical resource identity using RRF."""

    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")

    representatives: dict[tuple[str, str], RetrievalHit] = {}
    scores: dict[tuple[str, str], float] = {}
    backend_ranks: dict[tuple[str, str], dict[str, int]] = {}
    backend_depths: dict[str, int] = {}

    for backend, hits in backend_hits.items():
        backend_depths[backend] = len(hits)
        seen: set[tuple[str, str]] = set()
        for rank, hit in enumerate(hits, start=1):
            identity = canonical_resource_identity(hit)
            if identity in seen:
                existing = representatives.get(identity)
                if existing is not None:
                    representatives[identity] = _merge_resource_hits(existing, hit)
                continue
            seen.add(identity)
            scores[identity] = scores.get(identity, 0.0) + (1.0 / (rrf_k + rank))
            backend_ranks.setdefault(identity, {})[backend] = rank
            existing = representatives.get(identity)
            candidate = _with_retrieval_metadata(hit, backend=backend, rank=rank)
            representatives[identity] = (
                candidate if existing is None else _merge_resource_hits(existing, candidate)
            )

    fused: list[RetrievalHit] = []
    for identity, representative in representatives.items():
        fusion_score = scores[identity]
        retrieval_metadata = _retrieval_metadata(representative)
        retrieval_metadata.update(
            {
                "fusion": "rrf",
                "rrf_k": rrf_k,
                "rrf_score": fusion_score,
                "backend_ranks": dict(sorted(backend_ranks[identity].items())),
            }
        )
        fused.append(
            representative.model_copy(
                update={
                    "score": fusion_score,
                    "methods": _unique([*representative.methods, "rrf"]),
                    "metadata": {
                        **dict(representative.metadata),
                        "retrieval": retrieval_metadata,
                    },
                }
            )
        )

    fused.sort(key=lambda item: item.score, reverse=True)
    return RetrievalRankingResult(
        hits=tuple(fused),
        profile={
            "mode": "rrf",
            "rrf_k": rrf_k,
            "backend_depths": dict(sorted(backend_depths.items())),
            "candidate_count": sum(backend_depths.values()),
            "deduped_resource_count": len(fused),
        },
    )


def rerank_hits(
    *,
    query: str,
    hits: Sequence[RetrievalHit],
    rerank_client: RerankClient | None,
    limit: int = MAX_CANDIDATE_K,
) -> RetrievalRankingResult:
    candidates = list(hits[: max(1, min(limit, MAX_CANDIDATE_K))])
    if rerank_client is None or not candidates:
        return RetrievalRankingResult(
            hits=tuple(candidates),
            profile={
                "applied": False,
                "degraded": False,
                "candidate_count": len(candidates),
            },
        )

    rag_hits = [_to_rag_hit(hit, index=index) for index, hit in enumerate(candidates)]
    provider_name = getattr(
        rerank_client,
        "provider_name",
        rerank_client.__class__.__name__,
    )
    score_semantics = str(getattr(rerank_client, "score_semantics", "unknown"))
    try:
        reranked = rerank_client.rerank(
            query=query,
            hits=rag_hits,
            timeout_seconds=RERANK_TIMEOUT_SECONDS,
        )
    except Exception as error:  # noqa: BLE001 - RRF order is the safe fallback.
        return RetrievalRankingResult(
            hits=tuple(candidates),
            profile={
                "applied": False,
                "degraded": True,
                "provider": provider_name,
                "error_type": type(error).__name__,
                "candidate_count": len(candidates),
            },
        )
    if not reranked:
        return RetrievalRankingResult(
            hits=tuple(candidates),
            profile={
                "applied": False,
                "degraded": True,
                "provider": provider_name,
                "error_type": "EmptyRerankResult",
                "candidate_count": len(candidates),
            },
        )
    score_error_type = _rerank_score_error_type(
        reranked,
        score_semantics=score_semantics,
    )
    if score_error_type is not None:
        return RetrievalRankingResult(
            hits=tuple(candidates),
            profile={
                "applied": False,
                "degraded": True,
                "provider": provider_name,
                "score_semantics": score_semantics,
                "error_type": score_error_type,
                "candidate_count": len(candidates),
            },
        )
    original_by_chunk = {
        rag_hit.chunk_id: original for rag_hit, original in zip(rag_hits, candidates, strict=True)
    }
    ranked: list[RetrievalHit] = []
    seen: set[str] = set()
    for reranked_hit in reranked:
        original = original_by_chunk.get(reranked_hit.chunk_id)
        if original is None or reranked_hit.chunk_id in seen:
            continue
        seen.add(reranked_hit.chunk_id)
        retrieval_metadata = _retrieval_metadata(original)
        retrieval_metadata.update(
            {
                "pre_rerank_score": original.score,
                "rerank_score": float(reranked_hit.score),
            }
        )
        ranked.append(
            original.model_copy(
                update={
                    "score": float(reranked_hit.score),
                    "methods": _unique([*original.methods, "cross_encoder"]),
                    "metadata": {
                        **dict(original.metadata),
                        "retrieval": retrieval_metadata,
                    },
                }
            )
        )
    for rag_hit, original in zip(rag_hits, candidates, strict=True):
        if rag_hit.chunk_id not in seen:
            ranked.append(original)
    return RetrievalRankingResult(
        hits=tuple(ranked),
        profile={
            "applied": True,
            "degraded": False,
            "provider": provider_name,
            "score_semantics": score_semantics,
            "candidate_count": len(candidates),
        },
    )


def _rerank_score_error_type(
    hits: Sequence[RagVectorSearchHit],
    *,
    score_semantics: str,
) -> str | None:
    scores = [float(hit.score) for hit in hits]
    if any(not math.isfinite(score) for score in scores):
        return "InvalidRerankScores"
    if score_semantics == "normalized_relevance":
        if any(score < 0.0 or score > 1.0 for score in scores):
            return "InvalidRerankScores"
        if max(scores) < MIN_NORMALIZED_RERANK_SCORE:
            return "LowConfidenceRerankScores"
    if len(scores) > 1 and max(scores) - min(scores) < MIN_RERANK_SCORE_SPREAD:
        return "UninformativeRerankScores"
    return None


def canonical_resource_identity(hit: RetrievalHit) -> tuple[str, str]:
    """Identify source resources independently from their mutable ACL envelope."""

    return (hit.resource_type, hit.resource_id)


def _merge_resource_hits(existing: RetrievalHit, candidate: RetrievalHit) -> RetrievalHit:
    excerpt = _merge_resource_excerpts(existing, candidate)

    citation = existing.citation
    if candidate.citation and (not citation or str(candidate.citation).startswith("/")):
        citation = candidate.citation

    retrieval_metadata = _retrieval_metadata(existing)
    candidate_retrieval = _retrieval_metadata(candidate)
    backends = _unique(
        [
            *retrieval_metadata.get("backends", []),
            *candidate_retrieval.get("backends", []),
            existing.source,
            candidate.source,
        ]
    )
    retrieval_metadata["backends"] = backends
    return existing.model_copy(
        update={
            "title": existing.title or candidate.title,
            "summary": existing.summary or candidate.summary,
            "excerpt": excerpt,
            "citation": citation,
            "methods": _unique([*existing.methods, *candidate.methods]),
            "metadata": {
                **dict(candidate.metadata),
                **dict(existing.metadata),
                "retrieval": retrieval_metadata,
            },
        }
    )


def _merge_resource_excerpts(existing: RetrievalHit, candidate: RetrievalHit) -> str | None:
    """Keep bounded lexical and semantic evidence for the resource-level reranker."""

    existing_excerpt = (existing.excerpt or "").strip()
    candidate_excerpt = (candidate.excerpt or "").strip()
    if not existing_excerpt:
        return candidate_excerpt or None
    if not candidate_excerpt:
        return existing_excerpt
    if candidate_excerpt in existing_excerpt:
        return existing_excerpt
    if existing_excerpt in candidate_excerpt:
        return candidate_excerpt

    existing_is_keyword = "bm25" in existing.methods
    existing_has_vector = "vector" in existing.methods
    candidate_is_keyword = "bm25" in candidate.methods
    candidate_is_vector = "vector" in candidate.methods
    if (candidate_is_keyword and existing_is_keyword) or (
        candidate_is_vector and existing_has_vector
    ):
        return existing_excerpt
    if candidate_is_keyword and not existing_is_keyword:
        excerpts = (candidate_excerpt, existing_excerpt)
    else:
        excerpts = (existing_excerpt, candidate_excerpt)
    return "\n\n".join(excerpts)[:MAX_MERGED_EXCERPT_CHARS].rstrip()


def _with_retrieval_metadata(
    hit: RetrievalHit,
    *,
    backend: str,
    rank: int | None,
) -> RetrievalHit:
    retrieval_metadata = _retrieval_metadata(hit)
    retrieval_metadata["backends"] = _unique([*retrieval_metadata.get("backends", []), backend])
    if rank is not None:
        retrieval_metadata.setdefault("backend_ranks", {})[backend] = rank
    return hit.model_copy(
        update={
            "metadata": {**dict(hit.metadata), "retrieval": retrieval_metadata},
        }
    )


def _retrieval_metadata(hit: RetrievalHit) -> dict[str, Any]:
    value = hit.metadata.get("retrieval") if hit.metadata else None
    return dict(value) if isinstance(value, dict) else {}


def _to_rag_hit(hit: RetrievalHit, *, index: int) -> RagVectorSearchHit:
    scope_value = str(hit.metadata.get("scope_kind") or RagScopeKind.WORKSPACE.value)
    try:
        scope_kind = RagScopeKind(scope_value)
    except ValueError:
        scope_kind = RagScopeKind.WORKSPACE
    return RagVectorSearchHit(
        chunk_id=f"retrieval:{index}",
        text=hit.excerpt or hit.summary or hit.title or hit.resource_id,
        summary=hit.summary,
        score=hit.score,
        citation=hit.citation,
        metadata=dict(hit.metadata),
        projection=RagProjection(
            scope_kind=scope_kind,
            workspace_id=hit.workspace_id,
            resource_type=hit.resource_type,
            resource_id=hit.resource_id,
            source_kind=hit.source_kind or hit.source,
            title=hit.title,
            summary=hit.summary,
            metadata=dict(hit.metadata),
        ),
    )


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
