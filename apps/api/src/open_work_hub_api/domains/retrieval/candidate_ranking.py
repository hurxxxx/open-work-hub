from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite, log, sqrt
from typing import Any

from open_work_hub_api.domains.rag.providers.base import EmbeddingClient, RerankClient
from open_work_hub_api.domains.rag.sparse_terms import tokenize_sparse_terms
from open_work_hub_api.domains.retrieval.contracts import RetrievalHit
from open_work_hub_api.domains.retrieval.ranking import (
    dedupe_ranked_hits,
    fuse_ranked_hits,
    rerank_hits,
)

MAX_CANDIDATES = 100
MAX_CANDIDATE_TEXT_CHARS = 8_000
MAX_QUERY_CHARS = 2_000
MAX_TOP_K = 100
EMBEDDING_TIMEOUT_SECONDS = 5.0
_BM25_K1 = 1.5
_BM25_B = 0.75
_RESOURCE_TYPE = "transient_candidate"


@dataclass(frozen=True, slots=True)
class CandidateDocument:
    """Transient, caller-owned content to rank without creating a search index."""

    candidate_id: str
    text: str
    title: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateRankingRequest:
    query: str
    candidates: Sequence[CandidateDocument]
    top_k: int = 10
    enable_semantic: bool = True
    enable_rerank: bool = True


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: CandidateDocument
    rank: int
    score: float
    bm25_score: float
    semantic_score: float | None
    rrf_score: float | None
    rerank_score: float | None
    methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateRankingProfile:
    input_candidate_count: int
    ranked_candidate_count: int
    returned_candidate_count: int
    requested_top_k: int
    applied_top_k: int
    candidate_limit: int
    candidate_limit_applied: bool
    candidate_text_char_limit: int
    truncated_text_count: int
    query_char_limit: int
    query_truncated: bool
    semantic_requested: bool
    semantic_applied: bool
    semantic_provider: str | None
    fusion_applied: bool
    rerank_requested: bool
    rerank_applied: bool
    rerank_provider: str | None
    methods: tuple[str, ...]
    degraded_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CandidateRankingResult:
    candidates: tuple[RankedCandidate, ...]
    profile: CandidateRankingProfile


@dataclass(frozen=True, slots=True)
class _PreparedCandidate:
    candidate: CandidateDocument
    text: str
    input_order: int


class CandidateRankingService:
    """Bounded BM25/semantic candidate ranking over an in-memory candidate set."""

    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient | None = None,
        rerank_client: RerankClient | None = None,
    ) -> None:
        self._embedding_client = embedding_client
        self._rerank_client = rerank_client

    def rank(self, request: CandidateRankingRequest) -> CandidateRankingResult:
        query = request.query.strip()
        if not query:
            raise ValueError("query must not be blank")
        if request.top_k <= 0:
            raise ValueError("top_k must be positive")

        bounded_query = query[:MAX_QUERY_CHARS]
        input_candidates = tuple(request.candidates)
        selected = input_candidates[:MAX_CANDIDATES]
        prepared, truncated_text_count = _prepare_candidates(selected)
        applied_top_k = min(request.top_k, MAX_TOP_K, len(prepared))
        degraded_reasons: list[str] = []

        bm25_scores = _bm25_scores(
            bounded_query,
            [candidate.text for candidate in prepared],
        )
        bm25_hits = _ranked_hits(prepared, scores=bm25_scores, backend="bm25")
        backend_hits: dict[str, list[RetrievalHit]] = {}
        if _has_discriminative_signal(bm25_scores):
            # A zero BM25 score is not a lexical match. Keep those candidates
            # as deterministic fallbacks, but do not grant them an RRF rank
            # that could overpower a real semantic signal through input order.
            backend_hits["bm25"] = [hit for hit in bm25_hits if hit.score > 0.0]
        methods = ["bm25"]

        semantic_scores: list[float] | None = None
        semantic_applied = False
        semantic_provider = _provider_name(self._embedding_client)
        if request.enable_semantic and prepared:
            if self._embedding_client is None:
                degraded_reasons.append("semantic:Unavailable")
            else:
                try:
                    semantic_scores = _semantic_scores(
                        self._embedding_client,
                        query=bounded_query,
                        candidate_texts=[candidate.text for candidate in prepared],
                    )
                except Exception as error:  # noqa: BLE001 - BM25 remains a safe fallback.
                    degraded_reasons.append(f"semantic:{type(error).__name__}")
                else:
                    if _has_discriminative_signal(semantic_scores):
                        semantic_applied = True
                        backend_hits["semantic"] = _ranked_hits(
                            prepared,
                            scores=semantic_scores,
                            backend="semantic",
                        )
                        methods.extend(("semantic", "vector"))
                    else:
                        degraded_reasons.append("semantic:NoSignal")

        if len(backend_hits) > 1:
            ranking_result = fuse_ranked_hits(backend_hits)
            fusion_applied = True
            methods.append("rrf")
            final_hits = list(ranking_result.hits)
        elif len(backend_hits) == 1:
            ranking_result = dedupe_ranked_hits(next(iter(backend_hits.values())))
            fusion_applied = False
            final_hits = list(ranking_result.hits)
        else:
            fusion_applied = False
            final_hits = []

        # Preserve the public contract of returning the bounded candidate set.
        # No-signal candidates follow signal-bearing hits without contributing
        # artificial ranks to fusion.
        final_hits = _append_missing_hits(final_hits, bm25_hits)
        rerank_applied = False
        rerank_provider = _provider_name(self._rerank_client)
        if request.enable_rerank and final_hits:
            if self._rerank_client is None:
                degraded_reasons.append("rerank:Unavailable")
            else:
                try:
                    rerank_result = rerank_hits(
                        query=bounded_query,
                        hits=final_hits,
                        rerank_client=self._rerank_client,
                        limit=MAX_CANDIDATES,
                    )
                except Exception as error:  # noqa: BLE001 - fused order remains usable.
                    degraded_reasons.append(f"rerank:{type(error).__name__}")
                else:
                    final_hits = list(rerank_result.hits)
                    rerank_applied = bool(rerank_result.profile.get("applied"))
                    if rerank_applied:
                        methods.append("cross_encoder")
                    if rerank_result.profile.get("degraded"):
                        error_type = str(rerank_result.profile.get("error_type") or "Unavailable")
                        degraded_reasons.append(f"rerank:{error_type}")

        candidate_by_id = {
            candidate.candidate.candidate_id.strip(): candidate.candidate for candidate in prepared
        }
        bm25_by_id = _scores_by_candidate_id(prepared, bm25_scores)
        semantic_by_id = (
            _scores_by_candidate_id(prepared, semantic_scores)
            if semantic_scores is not None
            else {}
        )
        ranked_candidates = tuple(
            _to_ranked_candidate(
                hit,
                rank=rank,
                candidate=candidate_by_id[hit.resource_id],
                bm25_score=bm25_by_id[hit.resource_id],
                semantic_score=semantic_by_id.get(hit.resource_id),
            )
            for rank, hit in enumerate(final_hits[:applied_top_k], start=1)
        )
        return CandidateRankingResult(
            candidates=ranked_candidates,
            profile=CandidateRankingProfile(
                input_candidate_count=len(input_candidates),
                ranked_candidate_count=len(prepared),
                returned_candidate_count=len(ranked_candidates),
                requested_top_k=request.top_k,
                applied_top_k=applied_top_k,
                candidate_limit=MAX_CANDIDATES,
                candidate_limit_applied=len(input_candidates) > MAX_CANDIDATES,
                candidate_text_char_limit=MAX_CANDIDATE_TEXT_CHARS,
                truncated_text_count=truncated_text_count,
                query_char_limit=MAX_QUERY_CHARS,
                query_truncated=len(query) > MAX_QUERY_CHARS,
                semantic_requested=request.enable_semantic,
                semantic_applied=semantic_applied,
                semantic_provider=semantic_provider,
                fusion_applied=fusion_applied,
                rerank_requested=request.enable_rerank,
                rerank_applied=rerank_applied,
                rerank_provider=rerank_provider,
                methods=tuple(dict.fromkeys(methods)),
                degraded_reasons=tuple(degraded_reasons),
            ),
        )


def get_candidate_ranking_service() -> CandidateRankingService:
    """Build the service from the platform-owned provider bundle."""

    from open_work_hub_api.domains.rag.runtime import get_provider_bundle

    providers = get_provider_bundle()
    return CandidateRankingService(
        embedding_client=providers.embedding,
        rerank_client=providers.rerank,
    )


def _prepare_candidates(
    candidates: Sequence[CandidateDocument],
) -> tuple[tuple[_PreparedCandidate, ...], int]:
    prepared: list[_PreparedCandidate] = []
    seen_ids: set[str] = set()
    truncated_text_count = 0
    for input_order, candidate in enumerate(candidates):
        candidate_id = candidate.candidate_id.strip()
        if not candidate_id:
            raise ValueError("candidate_id must not be blank")
        if candidate_id in seen_ids:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        seen_ids.add(candidate_id)

        title = (candidate.title or "").strip()
        body = candidate.text.strip()
        full_text = "\n\n".join(part for part in (title, body) if part)
        if not full_text:
            raise ValueError(f"candidate text must not be blank: {candidate_id}")
        if len(full_text) > MAX_CANDIDATE_TEXT_CHARS:
            full_text = full_text[:MAX_CANDIDATE_TEXT_CHARS].rstrip()
            truncated_text_count += 1
        prepared.append(
            _PreparedCandidate(
                candidate=candidate,
                text=full_text,
                input_order=input_order,
            )
        )
    return tuple(prepared), truncated_text_count


def _bm25_scores(query: str, documents: Sequence[str]) -> list[float]:
    tokenized_documents = [tokenize_sparse_terms(document) for document in documents]
    if not tokenized_documents:
        return []
    query_terms = tuple(dict.fromkeys(tokenize_sparse_terms(query)))
    if not query_terms:
        return [0.0] * len(tokenized_documents)

    document_count = len(tokenized_documents)
    average_length = sum(len(document) for document in tokenized_documents) / document_count
    average_length = average_length or 1.0
    document_frequency = Counter(term for document in tokenized_documents for term in set(document))
    scores: list[float] = []
    for document in tokenized_documents:
        term_frequency = Counter(document)
        document_length = len(document)
        score = 0.0
        for term in query_terms:
            frequency = term_frequency.get(term, 0)
            if frequency == 0:
                continue
            frequency_in_documents = document_frequency[term]
            inverse_document_frequency = log(
                1.0
                + ((document_count - frequency_in_documents + 0.5) / (frequency_in_documents + 0.5))
            )
            length_normalization = _BM25_K1 * (
                1.0 - _BM25_B + (_BM25_B * document_length / average_length)
            )
            score += inverse_document_frequency * (
                (frequency * (_BM25_K1 + 1.0)) / (frequency + length_normalization)
            )
        scores.append(score)
    return scores


def _semantic_scores(
    embedding_client: EmbeddingClient,
    *,
    query: str,
    candidate_texts: list[str],
) -> list[float]:
    query_vector = _validated_vector(
        embedding_client.embed_query(query, timeout_seconds=EMBEDDING_TIMEOUT_SECONDS)
    )
    candidate_vectors = embedding_client.embed_texts(
        candidate_texts,
        timeout_seconds=EMBEDDING_TIMEOUT_SECONDS,
    )
    if len(candidate_vectors) != len(candidate_texts):
        raise ValueError("embedding provider returned an unexpected candidate count")

    scores: list[float] = []
    for vector in candidate_vectors:
        validated = _validated_vector(vector)
        if len(validated) != len(query_vector):
            raise ValueError("embedding provider returned inconsistent dimensions")
        scores.append(_cosine_similarity(query_vector, validated))
    return scores


def _validated_vector(values: Sequence[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if not vector:
        raise ValueError("embedding provider returned an empty vector")
    if not all(isfinite(value) for value in vector):
        raise ValueError("embedding provider returned a non-finite vector")
    return vector


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _has_discriminative_signal(scores: Sequence[float]) -> bool:
    """Return whether a backend distinguishes at least two candidates."""

    if len(scores) < 2:
        return False
    return max(scores) - min(scores) > 1e-12


def _append_missing_hits(
    ranked_hits: Sequence[RetrievalHit],
    fallback_hits: Sequence[RetrievalHit],
) -> list[RetrievalHit]:
    combined = list(ranked_hits)
    seen = {hit.resource_id for hit in combined}
    combined.extend(hit for hit in fallback_hits if hit.resource_id not in seen)
    return combined


def _ranked_hits(
    candidates: Sequence[_PreparedCandidate],
    *,
    scores: Sequence[float],
    backend: str,
) -> list[RetrievalHit]:
    if len(candidates) != len(scores):
        raise ValueError("candidate and score counts must match")
    methods = ["bm25"] if backend == "bm25" else ["semantic", "vector"]
    ranked = sorted(
        zip(candidates, scores, strict=True),
        key=lambda pair: (-pair[1], pair[0].input_order),
    )
    return [
        RetrievalHit(
            source=f"candidate_{backend}",
            source_kind=_RESOURCE_TYPE,
            resource_type=_RESOURCE_TYPE,
            resource_id=prepared.candidate.candidate_id.strip(),
            title=prepared.candidate.title,
            excerpt=prepared.text,
            score=float(score),
            methods=methods,
            metadata={"scope_kind": "company"},
        )
        for prepared, score in ranked
    ]


def _scores_by_candidate_id(
    candidates: Sequence[_PreparedCandidate],
    scores: Sequence[float] | None,
) -> dict[str, float]:
    if scores is None:
        return {}
    return {
        candidate.candidate.candidate_id.strip(): float(score)
        for candidate, score in zip(candidates, scores, strict=True)
    }


def _to_ranked_candidate(
    hit: RetrievalHit,
    *,
    rank: int,
    candidate: CandidateDocument,
    bm25_score: float,
    semantic_score: float | None,
) -> RankedCandidate:
    retrieval = hit.metadata.get("retrieval")
    retrieval_metadata = retrieval if isinstance(retrieval, dict) else {}
    rrf_score = retrieval_metadata.get("rrf_score")
    rerank_score = retrieval_metadata.get("rerank_score")
    return RankedCandidate(
        candidate=candidate,
        rank=rank,
        score=float(hit.score),
        bm25_score=bm25_score,
        semantic_score=semantic_score,
        rrf_score=float(rrf_score) if rrf_score is not None else None,
        rerank_score=float(rerank_score) if rerank_score is not None else None,
        methods=tuple(hit.methods),
    )


def _provider_name(provider: object | None) -> str | None:
    if provider is None:
        return None
    return str(getattr(provider, "provider_name", provider.__class__.__name__))
