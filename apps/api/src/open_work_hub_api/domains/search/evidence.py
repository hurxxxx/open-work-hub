from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.rag.access_filter import build_user_rag_post_filter
from open_work_hub_api.domains.rag.contracts import (
    RagAnswerMode,
    RagProjection,
    RagQueryRequest,
    RagVectorSearchHit,
)
from open_work_hub_api.domains.rag.metrics import record_rerank_latency
from open_work_hub_api.domains.rag.runtime import (
    get_provider_bundle,
    get_rag_query_service,
    resolve_default_collection_name,
)
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordSearchBackendError,
    KeywordSearchClient,
    KeywordSearchQuery,
    KeywordSearchSortSpec,
)
from open_work_hub_api.domains.search.backend_factory import build_keyword_search_client
from open_work_hub_api.domains.search.resource_mapping import maybe_resource_type_for_search_entity
from open_work_hub_api.domains.search.schemas import SearchEntityType
from open_work_hub_api.domains.source_access import SourceAclPolicy


EVIDENCE_METHOD_STRUCTURED = "structured"
EVIDENCE_METHOD_KEYWORD = "keyword"
EVIDENCE_METHOD_SEMANTIC = "semantic"

_MAX_RERANK_CANDIDATES = 80
_KEYWORD_SEARCH_RESULT_SIZE = 50
_SEMANTIC_SEARCH_TOP_K = 20
_QUERY_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣#_./+-]{2,}")
_QUERY_STOPWORDS = {
    "관련",
    "결과",
    "개선",
    "대책",
    "알려줘",
    "원인",
    "평가",
}


@dataclass(frozen=True)
class KeywordEvidencePage:
    rows: list[dict[str, Any]]
    next_search_after: list[Any] | None
    raw_hit_count: int


@dataclass
class EvidenceScores:
    structured: float | None = None
    keyword: float | None = None
    semantic: float | None = None
    rerank: float | None = None

    @property
    def best(self) -> float:
        return max(
            self.rerank if self.rerank is not None else float("-inf"),
            self.keyword if self.keyword is not None else float("-inf"),
            self.semantic if self.semantic is not None else float("-inf"),
            self.structured if self.structured is not None else float("-inf"),
            0.0,
        )

    def merge(self, other: EvidenceScores) -> None:
        self.structured = _max_optional(self.structured, other.structured)
        self.keyword = _max_optional(self.keyword, other.keyword)
        self.semantic = _max_optional(self.semantic, other.semantic)
        self.rerank = _max_optional(self.rerank, other.rerank)

    def to_payload(self) -> dict[str, float | None]:
        return {
            "structured": self.structured,
            "keyword": self.keyword,
            "semantic": self.semantic,
            "rerank": self.rerank,
        }


@dataclass
class EvidenceCandidate:
    source_id: str
    source_kind: str
    resource_type: str
    resource_id: str
    title: str
    excerpt: str
    summary: str = ""
    retrieval_methods: set[str] = field(default_factory=set)
    scores: EvidenceScores = field(default_factory=EvidenceScores)
    match_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def combined_score(self) -> float:
        return self.scores.best


@dataclass
class SemanticEvidenceHit:
    chunk_id: str
    text: str
    summary: str | None
    score: float
    citation: str | None
    source_kind: str
    resource_type: str
    resource_id: str
    workspace_id: str
    title: str | None
    owner_label: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceRankingPolicy:
    max_rerank_candidates: int = _MAX_RERANK_CANDIDATES
    base_rank_weight: float = 0.40
    rerank_rank_weight: float = 0.45
    lexical_overlap_weight: float = 0.15
    rrf_k: int = 60

    def sort_by_base_score(
        self,
        candidates: list[EvidenceCandidate],
        *,
        question: str | None = None,
    ) -> list[EvidenceCandidate]:
        return sorted(
            candidates,
            key=lambda item: (
                self.candidate_query_overlap(question, item),
                item.combined_score,
                len(item.retrieval_methods),
                item.scores.keyword if item.scores.keyword is not None else float("-inf"),
                item.scores.structured if item.scores.structured is not None else float("-inf"),
                item.scores.semantic if item.scores.semantic is not None else float("-inf"),
            ),
            reverse=True,
        )

    def sort_by_hybrid_rerank_score(
        self,
        candidates: list[EvidenceCandidate],
        *,
        question: str,
        rerank_order: dict[str, int],
    ) -> list[EvidenceCandidate]:
        base_order = {
            candidate.source_id: index
            for index, candidate in enumerate(
                self.sort_by_base_score(candidates, question=question)
            )
        }
        missing_rank = len(candidates) + 100

        def hybrid_score(candidate: EvidenceCandidate) -> tuple[float, float]:
            base_rank = base_order.get(candidate.source_id, missing_rank)
            rerank_rank = rerank_order.get(candidate.source_id, missing_rank)
            lexical_overlap = self.candidate_query_overlap(question, candidate)
            score = (
                (self.base_rank_weight * self._rrf(base_rank))
                + (self.rerank_rank_weight * self._rrf(rerank_rank))
                + (self.lexical_overlap_weight * lexical_overlap)
            )
            return score, candidate.combined_score

        return sorted(candidates, key=hybrid_score, reverse=True)

    def select_diverse_sources(
        self,
        candidates: list[EvidenceCandidate],
        *,
        max_sources: int,
    ) -> list[EvidenceCandidate]:
        selected: list[EvidenceCandidate] = []
        overflow: list[EvidenceCandidate] = []
        seen_keys: set[str] = set()
        for candidate in candidates:
            key = self.source_identity_key(candidate)
            if key in seen_keys:
                overflow.append(candidate)
                continue
            seen_keys.add(key)
            selected.append(candidate)
            if len(selected) >= max_sources:
                return selected
        for candidate in overflow:
            selected.append(candidate)
            if len(selected) >= max_sources:
                return selected
        return selected

    def source_identity_key(self, candidate: EvidenceCandidate) -> str:
        metadata = dict(candidate.metadata)
        normalized_title = _normalize_key_part(candidate.title)
        if _is_record_like_candidate(candidate):
            if len(normalized_title) >= 12:
                return f"record-title:{normalized_title}"
            return ":".join(
                [
                    "record",
                    _normalize_key_part(_metadata_str(metadata, "record_id")),
                    _normalize_key_part(candidate.resource_type),
                    normalized_title,
                ]
            )
        artifact_title = _metadata_str(metadata, "artifact_title")
        if _metadata_str(metadata, "artifact_id") or artifact_title:
            return f"artifact:{_normalize_key_part(artifact_title or candidate.title)}"
        document_id = _metadata_str(metadata, "document_id")
        if document_id:
            return f"document:{document_id}:{normalized_title}"
        return f"{candidate.source_kind}:{normalized_title}:{candidate.resource_id}"

    def candidate_query_overlap(
        self,
        question: str | None,
        candidate: EvidenceCandidate,
    ) -> float:
        query_tokens = important_query_tokens(question)
        if not query_tokens:
            return 0.0
        haystack = _candidate_searchable_text(candidate).casefold()
        matches = sum(1 for token in query_tokens if token.casefold() in haystack)
        return matches / len(query_tokens)

    def _rrf(self, rank: int) -> float:
        return 1.0 / (self.rrf_k + rank + 1)


DEFAULT_EVIDENCE_RANKING_POLICY = EvidenceRankingPolicy()


class KeywordEvidenceSearchError(RuntimeError):
    pass


def query_keywords_from_text(value: str | None) -> list[str]:
    return _QUERY_TOKEN_PATTERN.findall(value or "")


def important_query_tokens(question: str | None) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in _QUERY_TOKEN_PATTERN.findall(question or ""):
        token = raw.strip().strip("?!.~,;:()[]{}")
        key = token.casefold()
        if len(token) < 2 or key in seen or key in _QUERY_STOPWORDS:
            continue
        seen.add(key)
        tokens.append(token)
    return tokens[:8]


def dedupe_query_terms(*values: str | None) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for value in values:
        for token in query_keywords_from_text(value):
            normalized = token.strip()
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            seen.add(key)
            tokens.append(normalized)
    return " ".join(tokens)


def search_keyword_evidence_rows(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    entity_types: list[SearchEntityType | str],
    dataset_id: str | None = None,
    result_size: int = _KEYWORD_SEARCH_RESULT_SIZE,
    search_after: list[Any] | None = None,
) -> list[dict[str, Any]]:
    return search_keyword_evidence_page(
        db,
        workspace=workspace,
        user=user,
        query=query,
        entity_types=entity_types,
        dataset_id=dataset_id,
        result_size=result_size,
        search_after=search_after,
    ).rows


def search_keyword_evidence_page(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    entity_types: list[SearchEntityType | str],
    dataset_id: str | None = None,
    result_size: int = _KEYWORD_SEARCH_RESULT_SIZE,
    search_after: list[Any] | None = None,
) -> KeywordEvidencePage:
    client = _keyword_search_client()
    try:
        if not client.index_exists():
            raise KeywordSearchBackendError(
                "Keyword search index is not initialized. Run keyword search backfill first."
            )
    except KeywordSearchBackendError as error:
        raise KeywordEvidenceSearchError(str(error)) from error
    policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
    keyword_query = KeywordSearchQuery(
        workspace_id=workspace.id,
        text=query,
        entity_types=tuple(str(entity_type) for entity_type in entity_types),
        acl_filter=policy.build_keyword_acl_filter(),
        dataset_id=dataset_id,
        include_missing_dataset=bool(dataset_id),
        size=result_size,
        search_after=tuple(search_after or ()),
        text_operator="or",
        phrase_match_fields=("title^8", "keywords^5", "summary^3"),
        sort=(
            KeywordSearchSortSpec(field="score", direction="desc"),
            KeywordSearchSortSpec(
                field="source_updated_at",
                direction="desc",
                unmapped_type="date",
            ),
            KeywordSearchSortSpec(field="entity_type", direction="asc"),
            KeywordSearchSortSpec(field="entity_id", direction="asc"),
        ),
    )
    try:
        result = client.search(keyword_query)
    except KeywordSearchBackendError as error:
        raise KeywordEvidenceSearchError(str(error)) from error
    rows: list[dict[str, Any]] = []
    next_search_after = None
    for hit in result.hits:
        if hit.sort_values:
            next_search_after = list(hit.sort_values)
        source = dict(hit.document)
        source["_search_score"] = hit.score
        if hit.sort_values:
            source["_search_sort"] = list(hit.sort_values)
        entity_type = str(source.get("entity_type") or "")
        resource_type = maybe_resource_type_for_search_entity(entity_type)
        if resource_type is None:
            continue
        source_dataset_id = source.get("dataset_id") or (source.get("metadata") or {}).get(
            "dataset_id"
        )
        if dataset_id and source_dataset_id not in (None, dataset_id):
            continue
        if policy.can_read_resource(resource_type, str(source.get("entity_id") or "")):
            rows.append(source)
    return KeywordEvidencePage(
        rows=rows,
        next_search_after=next_search_after,
        raw_hit_count=len(result.hits),
    )


def search_semantic_evidence_hits(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    source_kinds: list[str],
    dataset_id: str | None = None,
    top_k: int = _SEMANTIC_SEARCH_TOP_K,
) -> tuple[list[SemanticEvidenceHit], dict[str, Any]]:
    settings = get_settings()
    if not settings.rag_enabled:
        return [], {"count": 0, "degraded": False, "enabled": False}
    user_post_filter = build_user_rag_post_filter(db, user=user)
    source_kind_set = set(source_kinds)
    request = RagQueryRequest(
        collection=resolve_default_collection_name(settings),
        workspace_id=workspace.id,
        query=query,
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        source_kinds=source_kinds,
        filters={"dataset_id": dataset_id} if dataset_id else {},
        top_k=top_k,
    )

    def post_filter(hit: RagVectorSearchHit) -> bool:
        if not user_post_filter(hit):
            return False
        if hit.projection.workspace_id != workspace.id:
            return False
        metadata = {**dict(hit.projection.metadata or {}), **dict(hit.metadata or {})}
        if dataset_id and metadata.get("dataset_id") != dataset_id:
            return False
        return hit.projection.source_kind in source_kind_set

    response = get_rag_query_service().query(request, post_filter=post_filter)
    hits = [
        SemanticEvidenceHit(
            chunk_id=str(
                hit.metadata.get("chunk_key") or hit.metadata.get("chunk_db_id") or hit.resource_id
            ),
            text=hit.excerpt or hit.summary or "",
            summary=hit.summary,
            score=hit.score,
            citation=hit.citation,
            source_kind=hit.source_kind,
            resource_type=hit.resource_type,
            resource_id=hit.resource_id,
            workspace_id=hit.workspace_id,
            title=hit.title,
            owner_label=hit.owner_label,
            metadata=dict(hit.metadata),
        )
        for hit in response.hits
    ]
    return hits, response.query_profile


def rerank_evidence_candidates(
    *,
    workspace: Workspace,
    question: str,
    candidates: list[EvidenceCandidate],
    max_sources: int,
    ranking_policy: EvidenceRankingPolicy = DEFAULT_EVIDENCE_RANKING_POLICY,
    source_kind: str = "evidence_search",
) -> tuple[list[EvidenceCandidate], dict[str, Any]]:
    if not candidates:
        return [], {"applied": False, "degraded": False, "candidate_count": 0}
    limited_candidates = ranking_policy.sort_by_base_score(candidates, question=question)[
        : ranking_policy.max_rerank_candidates
    ]
    settings = get_settings()
    if settings.rag_rerank_provider in {"", "none", "disabled"}:
        selected = ranking_policy.select_diverse_sources(
            limited_candidates, max_sources=max_sources
        )
        return selected, {
            "applied": False,
            "degraded": False,
            "provider": settings.rag_rerank_provider,
            "candidate_count": len(limited_candidates),
            "returned_count": len(selected),
        }
    try:
        providers = get_provider_bundle()
        if providers.rerank is None:
            selected = ranking_policy.select_diverse_sources(
                limited_candidates, max_sources=max_sources
            )
            return selected, {
                "applied": False,
                "degraded": False,
                "provider": settings.rag_rerank_provider,
                "candidate_count": len(limited_candidates),
                "returned_count": len(selected),
            }
        hit_map = {candidate.source_id: candidate for candidate in limited_candidates}
        rerank_hits = [
            _candidate_to_rag_hit(workspace=workspace, candidate=candidate)
            for candidate in limited_candidates
        ]
        started = time.perf_counter()
        reranked = providers.rerank.rerank(query=question, hits=rerank_hits)
        record_rerank_latency(
            provider_name=getattr(providers.rerank, "provider_name", settings.rag_rerank_provider),
            latency_ms=int((time.perf_counter() - started) * 1000),
            workspace_id=workspace.id,
            source_kind=source_kind,
        )
    except Exception as error:  # noqa: BLE001 - fallback order is still usable.
        selected = ranking_policy.select_diverse_sources(
            limited_candidates, max_sources=max_sources
        )
        return selected, {
            "applied": False,
            "degraded": True,
            "provider": settings.rag_rerank_provider,
            "candidate_count": len(limited_candidates),
            "returned_count": len(selected),
            "error": f"{type(error).__name__}: {error}",
        }

    rerank_order: dict[str, int] = {}
    rerank_scores: list[float] = []
    for hit in reranked:
        candidate = hit_map.get(str(hit.metadata.get("candidate_id") or ""))
        if candidate is None:
            continue
        score = float(hit.metadata.get("rerank_score") or hit.score)
        candidate.scores.rerank = score
        rerank_order[candidate.source_id] = len(rerank_order)
        rerank_scores.append(score)
    if _rerank_scores_are_uninformative(rerank_scores):
        selected = ranking_policy.select_diverse_sources(
            limited_candidates, max_sources=max_sources
        )
        return selected, {
            "applied": False,
            "degraded": True,
            "provider": getattr(providers.rerank, "provider_name", settings.rag_rerank_provider),
            "candidate_count": len(limited_candidates),
            "returned_count": len(selected),
            "reason": "uninformative_rerank_scores",
        }

    ordered = ranking_policy.sort_by_hybrid_rerank_score(
        limited_candidates,
        question=question,
        rerank_order=rerank_order,
    )
    selected = ranking_policy.select_diverse_sources(ordered, max_sources=max_sources)
    return selected, {
        "applied": True,
        "degraded": False,
        "provider": getattr(providers.rerank, "provider_name", settings.rag_rerank_provider),
        "candidate_count": len(limited_candidates),
        "returned_count": len(selected),
    }


def merge_evidence_candidate(
    candidates: dict[str, EvidenceCandidate],
    incoming: EvidenceCandidate,
) -> None:
    existing = candidates.get(incoming.source_id)
    if existing is None:
        candidates[incoming.source_id] = incoming
        return
    existing.retrieval_methods.update(incoming.retrieval_methods)
    existing.scores.merge(incoming.scores)
    if len(incoming.excerpt) > len(existing.excerpt):
        existing.excerpt = incoming.excerpt
    existing.metadata = {**incoming.metadata, **existing.metadata}
    if incoming.match_reason and incoming.match_reason not in existing.match_reason:
        existing.match_reason = "; ".join(
            part for part in [existing.match_reason, incoming.match_reason] if part
        )


def _keyword_search_client() -> KeywordSearchClient:
    return build_keyword_search_client(get_settings())


def _candidate_to_rag_hit(
    *,
    workspace: Workspace,
    candidate: EvidenceCandidate,
) -> RagVectorSearchHit:
    return RagVectorSearchHit(
        chunk_id=candidate.source_id,
        text=candidate.excerpt,
        summary=candidate.summary,
        score=candidate.combined_score,
        citation=None,
        metadata={
            **candidate.metadata,
            "candidate_id": candidate.source_id,
            "structured_score": candidate.scores.structured,
            "keyword_score": candidate.scores.keyword,
            "semantic_score": candidate.scores.semantic,
        },
        projection=RagProjection(
            workspace_id=workspace.id,
            resource_type=candidate.resource_type,
            resource_id=candidate.resource_id,
            source_kind=candidate.source_kind,
            title=candidate.title,
            summary=candidate.summary,
            text_content="",
            owner_label="Evidence Search",
            visibility_refs=[],
            metadata=candidate.metadata,
        ),
    )


def _candidate_searchable_text(candidate: EvidenceCandidate) -> str:
    metadata_text = " ".join(
        str(value) for value in candidate.metadata.values() if value is not None
    )
    return " ".join([candidate.title, candidate.summary, candidate.excerpt, metadata_text])


def _is_record_like_candidate(candidate: EvidenceCandidate) -> bool:
    return bool(_metadata_str(candidate.metadata, "record_id")) or candidate.resource_type.endswith(
        "_record"
    )


def _rerank_scores_are_uninformative(scores: list[float]) -> bool:
    if len(scores) < 2:
        return True
    return max(scores) - min(scores) < 1e-6


def _normalize_key_part(value: str | None) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z가-힣]+", "", value or "").casefold()
    return normalized or "-"


def _metadata_str(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _max_optional(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)
