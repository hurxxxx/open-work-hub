from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.files.external_projection import (
    EXTERNAL_SOURCE_TARGET_APP,
    EXTERNAL_SOURCE_TARGET_TYPES,
    external_source_filter_value,
    external_source_kind,
    external_source_target_id,
    external_source_title,
)
from open_alm_api.domains.files.models import FileManagerFile
from open_alm_api.domains.files.retrieval_contract import FILES_RETRIEVAL_ACTIVE
from open_alm_api.domains.rag.query_service import RagQueryService
from open_alm_api.domains.retrieval.application import query_retrieval
from open_alm_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalQueryRequest,
    RetrievalStrategy,
)
from open_alm_api.domains.retrieval.ranking import MIN_NORMALIZED_RERANK_SCORE
from open_alm_api.domains.search.backend_contracts import KeywordSearchClient
from open_alm_api.domains.retrieval.runtime_binding import (
    PartitionedRetrievalRuntimeUnavailable,
    resolve_partitioned_files_query_runtime,
)
from open_alm_api.domains.source_access import SourceAclPolicy
from open_alm_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


MAX_FILE_SEARCH_RANKED_RESULTS = 100
FILE_SEARCH_SNIPPET_CONTEXT_WORDS = 50
MAX_FILE_SEARCH_SNIPPET_CHARS = 4_000
MAX_FILE_SEARCH_SNIPPET_ANCHOR_SCAN_CHARS = 1_000_000
MAX_FILE_SEARCH_SNIPPET_QUERY_TOKENS = 32
MAX_FILE_SEARCH_SNIPPET_QUERY_TOKEN_CHARS = 128
MAX_FILE_SEARCH_HIGHLIGHTS = 32


class FileSearchStrategy(StrEnum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class FileSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    strategy: FileSearchStrategy = FileSearchStrategy.HYBRID
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)
    source_kind: str | None = Field(default=None, min_length=1, max_length=80)
    author: str | None = Field(default=None, min_length=1, max_length=512)
    department: str | None = Field(default=None, min_length=1, max_length=512)
    document_type: str | None = Field(default=None, min_length=1, max_length=255)
    authored_from: datetime | None = None
    authored_to: datetime | None = None

    @field_validator("source_kind", "author", "department", "document_type")
    @classmethod
    def normalize_metadata_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split()).strip()
        if not normalized:
            raise ValueError("metadata filters must not be blank")
        return normalized

    @field_validator("authored_from", "authored_to")
    @classmethod
    def normalize_datetime_filter(cls, value: datetime | None) -> datetime | None:
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    @model_validator(mode="after")
    def validate_ranked_window(self) -> FileSearchRequest:
        if self.page * self.page_size > MAX_FILE_SEARCH_RANKED_RESULTS:
            raise ValueError(
                f"page and page_size must stay within the first "
                f"{MAX_FILE_SEARCH_RANKED_RESULTS} ranked results"
            )
        if (
            self.authored_from is not None
            and self.authored_to is not None
            and self.authored_from > self.authored_to
        ):
            raise ValueError("authored_from must not be after authored_to")
        return self


class FileSearchHighlight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: int
    end: int


class FileSearchSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    highlights: list[FileSearchHighlight] = Field(default_factory=list)


class FileSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    file_id: str
    filename: str
    title: str
    folder_id: str | None = None
    content_type: str
    size_bytes: int
    score: float
    methods: list[str] = Field(default_factory=list)
    snippet: FileSearchSnippet
    updated_at: datetime
    source_kind: str
    author: str | None = None
    authored_at: datetime | None = None
    department: str | None = None
    document_type: str | None = None
    source_updated_at: datetime | None = None


class FileSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    strategy: FileSearchStrategy
    page: int
    page_size: int
    hits: list[FileSearchHit] = Field(default_factory=list)
    has_more: bool = False
    max_ranked_results: int = MAX_FILE_SEARCH_RANKED_RESULTS
    latency_ms: int = 0
    trace_id: str | None = None


class FileSearchUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FileSearchRuntime:
    keyword_client: KeywordSearchClient
    rag_query_service: RagQueryService | None
    rag_collection: str | None


@dataclass(frozen=True, slots=True)
class _FileSearchSource:
    file_id: str
    filename: str
    folder_id: str | None
    content_type: str
    size_bytes: int
    updated_at: datetime
    title: str | None = None
    source_kind: str = "files"
    author: str | None = None
    authored_at: datetime | None = None
    department: str | None = None
    document_type: str | None = None
    source_updated_at: datetime | None = None


def resolve_file_search_runtime(db: Session) -> FileSearchRuntime:
    if not FILES_RETRIEVAL_ACTIVE:
        raise FileSearchUnavailable("partitioned Files retrieval is not active")
    try:
        runtime = resolve_partitioned_files_query_runtime(db)
    except PartitionedRetrievalRuntimeUnavailable as error:
        raise FileSearchUnavailable(error.reason) from error
    return FileSearchRuntime(
        keyword_client=runtime.keyword_search_client,
        rag_query_service=runtime.rag_query_service,
        rag_collection=runtime.rag_collection,
    )


def query_files(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: FileSearchRequest,
    runtime: FileSearchRuntime,
) -> FileSearchResponse:
    offset = (request.page - 1) * request.page_size
    strategy = RetrievalStrategy(request.strategy.value)
    sources = {
        FileSearchStrategy.KEYWORD: ["keyword"],
        FileSearchStrategy.SEMANTIC: ["generic_rag"],
        FileSearchStrategy.HYBRID: ["keyword", "generic_rag"],
    }[request.strategy]
    retrieval_filters = _file_search_retrieval_filters(request)
    response = query_retrieval(
        db,
        workspace=workspace,
        user=user,
        request=RetrievalQueryRequest(
            query=request.query,
            strategy=strategy,
            sources=sources,
            source_kinds=["files"],
            filters=retrieval_filters,
            # Every page is ranked against the same bounded candidate window. ACL is
            # still rechecked from PostgreSQL for every request, so authorization
            # changes take effect immediately while stable backends produce stable
            # pages.
            top_k=MAX_FILE_SEARCH_RANKED_RESULTS,
            answer_mode=RetrievalAnswerMode.SEARCH_ONLY,
        ),
        source="api.files.search",
        keyword_search_client=runtime.keyword_client,
        keyword_evaluation_entity_types=("file",),
        keyword_strict_text_match=request.strategy
        in {FileSearchStrategy.KEYWORD, FileSearchStrategy.HYBRID},
        rag_allowed_unlisted_source_kinds=frozenset({"files"}),
        rag_query_service=runtime.rag_query_service,
        rag_collection=runtime.rag_collection,
        partitioned_generation=True,
    )
    ranked_hits = sorted(
        (hit for hit in response.hits if hit.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE),
        key=lambda hit: (-float(hit.score), hit.resource_id),
    )[:MAX_FILE_SEARCH_RANKED_RESULTS]
    rerank_profile = response.profile.backend_profiles.get("rerank")
    ranked_hits = _filter_file_search_relevance(
        ranked_hits,
        strategy=request.strategy,
        rerank_profile=rerank_profile,
    )
    file_ids = [hit.resource_id for hit in ranked_hits]
    policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
    allowed = policy.authorize_many_resources(
        (FILE_MANAGER_FILE_RESOURCE_TYPE, file_id) for file_id in file_ids
    )
    authorized_hits = [
        hit for hit in ranked_hits if (FILE_MANAGER_FILE_RESOURCE_TYPE, hit.resource_id) in allowed
    ]
    candidate_sources_by_id = _load_file_search_sources(
        db,
        [hit.resource_id for hit in authorized_hits],
        request=request,
    )
    # Candidate hydration can leave source-owned ACL entities in SQLAlchemy's
    # identity map. Expire them, then re-authorize the entire bounded ranked
    # window before page slicing so revoke/move changes can refill from later
    # authorized hits and has_more reflects the same authorization snapshot.
    db.expire_all()
    window_policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
    window_allowed = window_policy.authorize_many_resources(
        (FILE_MANAGER_FILE_RESOURCE_TYPE, file_id) for file_id in file_ids
    )
    final_authorized_hits = [
        hit
        for hit in ranked_hits
        if (FILE_MANAGER_FILE_RESOURCE_TYPE, hit.resource_id) in window_allowed
        and hit.resource_id in candidate_sources_by_id
    ]

    # Keep the response-bound metadata, snippet source, and has_more window fresh.
    # If a revoke or delete commits while this page is hydrated, re-authorize the
    # whole bounded window, remove every invalid candidate, and refill the page
    # deterministically. Every retry removes at least one candidate, so the loop
    # is bounded by MAX_FILE_SEARCH_RANKED_RESULTS.
    while True:
        page_hits = final_authorized_hits[offset : offset + request.page_size]
        page_file_ids = [hit.resource_id for hit in page_hits]
        page_sources_by_id = _load_file_search_sources(
            db,
            page_file_ids,
            request=request,
        )
        extraction_text_by_id = _load_file_search_extraction_texts(
            db,
            _snippet_extraction_file_ids(
                page_hits,
                rerank_profile=rerank_profile,
            ),
        )
        if not page_file_ids:
            final_page_hits: list[Any] = []
            break

        db.expire_all()
        refreshed_window_policy = SourceAclPolicy.for_workspace(
            db,
            workspace=workspace,
            user=user,
        )
        refreshed_window_allowed = refreshed_window_policy.authorize_many_resources(
            (FILE_MANAGER_FILE_RESOURCE_TYPE, hit.resource_id) for hit in final_authorized_hits
        )
        valid_page_file_ids = {
            file_id
            for file_id in page_file_ids
            if (FILE_MANAGER_FILE_RESOURCE_TYPE, file_id) in refreshed_window_allowed
            and file_id in page_sources_by_id
        }
        invalid_window_file_ids = {
            hit.resource_id
            for hit in final_authorized_hits
            if (FILE_MANAGER_FILE_RESOURCE_TYPE, hit.resource_id) not in refreshed_window_allowed
        } | (set(page_file_ids) - valid_page_file_ids)
        if not invalid_window_file_ids:
            final_page_hits = page_hits
            break
        final_authorized_hits = [
            hit for hit in final_authorized_hits if hit.resource_id not in invalid_window_file_ids
        ]

    return FileSearchResponse(
        query=request.query,
        strategy=request.strategy,
        page=request.page,
        page_size=request.page_size,
        hits=[
            _file_search_hit(
                hit=hit,
                file=page_sources_by_id[hit.resource_id],
                extraction_text=extraction_text_by_id.get(hit.resource_id),
                query=request.query,
                rank=offset + index + 1,
            )
            for index, hit in enumerate(final_page_hits)
        ],
        has_more=len(final_authorized_hits) > offset + request.page_size,
        latency_ms=response.latency_ms,
        trace_id=response.trace_id,
    )


def _filter_file_search_relevance(
    hits: list[Any],
    *,
    strategy: FileSearchStrategy,
    rerank_profile: Any,
) -> list[Any]:
    """Remove calibrated low-relevance tails before ACL checks and pagination."""

    if strategy == FileSearchStrategy.KEYWORD or not isinstance(rerank_profile, dict):
        return hits
    if rerank_profile.get("score_semantics") != "normalized_relevance":
        return hits
    if rerank_profile.get("applied") is True:
        return [
            hit
            for hit in hits
            if "cross_encoder" not in hit.methods or float(hit.score) >= MIN_NORMALIZED_RERANK_SCORE
        ]
    if rerank_profile.get("error_type") == "LowConfidenceRerankScores":
        if strategy == FileSearchStrategy.HYBRID:
            # A low-confidence reranker cannot safely break a disagreement
            # between lexical and semantic retrieval. The Files hybrid surface
            # prefers the semantic leader; users can select BM25 explicitly for
            # strict lexical ranking. Fall back to keyword only if vector search
            # produced no candidate.
            for backend in ("generic_rag", "keyword"):
                leader = _backend_leader(hits, backend=backend)
                if leader is not None:
                    return [leader]
        # Single-backend retrieval has one trustworthy pre-rerank ordering.
        return hits[:1]
    return hits


def _backend_leader(hits: list[Any], *, backend: str) -> Any | None:
    ranked: list[tuple[int, int, Any]] = []
    for index, hit in enumerate(hits):
        metadata = getattr(hit, "metadata", None)
        retrieval = metadata.get("retrieval") if isinstance(metadata, dict) else None
        backend_ranks = retrieval.get("backend_ranks") if isinstance(retrieval, dict) else None
        rank = backend_ranks.get(backend) if isinstance(backend_ranks, dict) else None
        if isinstance(rank, int) and not isinstance(rank, bool) and rank > 0:
            ranked.append((rank, index, hit))
    if not ranked:
        return None
    return min(ranked, key=lambda item: (item[0], item[1]))[2]


def _snippet_extraction_file_ids(
    hits: list[Any],
    *,
    rerank_profile: Any,
) -> list[str]:
    low_confidence = (
        isinstance(rerank_profile, dict)
        and rerank_profile.get("error_type") == "LowConfidenceRerankScores"
    )
    return [str(hit.resource_id) for hit in hits if low_confidence or "bm25" in hit.methods]


def _load_file_search_sources(
    db: Session,
    file_ids: list[str],
    *,
    request: FileSearchRequest,
) -> dict[str, _FileSearchSource]:
    if not file_ids:
        return {}
    return {
        row.id: _FileSearchSource(
            file_id=row.id,
            filename=row.filename,
            title=external_source_title(row),
            folder_id=row.folder_id,
            content_type=row.content_type,
            size_bytes=row.size_bytes,
            updated_at=row.updated_at,
            source_kind=external_source_kind(row),
            author=(row.source_metadata.author if row.source_metadata is not None else None),
            authored_at=(
                row.source_metadata.authored_at if row.source_metadata is not None else None
            ),
            department=(
                row.source_metadata.department if row.source_metadata is not None else None
            ),
            document_type=(
                row.source_metadata.document_type if row.source_metadata is not None else None
            ),
            source_updated_at=(
                row.source_metadata.source_updated_at if row.source_metadata is not None else None
            ),
        )
        for row in db.scalars(
            select(FileManagerFile)
            .options(joinedload(FileManagerFile.source_metadata))
            .where(
                FileManagerFile.id.in_(file_ids),
                FileManagerFile.deleted_at.is_(None),
            )
        )
        if _file_source_matches_request(row, request=request)
    }


def _load_file_search_extraction_texts(
    db: Session,
    file_ids: list[str],
) -> dict[str, str | None]:
    if not file_ids:
        return {}
    return dict(
        db.execute(
            select(FileManagerFile.id, FileManagerFile.extraction_text).where(
                FileManagerFile.id.in_(file_ids),
                FileManagerFile.deleted_at.is_(None),
            )
        ).all()
    )


def _file_search_hit(
    *,
    hit: Any,
    file: _FileSearchSource,
    extraction_text: str | None,
    query: str,
    rank: int,
) -> FileSearchHit:
    lexical = bool(extraction_text)
    snippet = (
        _lexical_snippet(extraction_text or "", query=query)
        if lexical
        else FileSearchSnippet(
            text=(hit.excerpt or hit.summary or "").strip()[:MAX_FILE_SEARCH_SNIPPET_CHARS]
        )
    )
    return FileSearchHit(
        rank=rank,
        file_id=file.file_id,
        filename=file.filename,
        title=file.title or file.filename,
        folder_id=file.folder_id,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        score=float(hit.score),
        methods=list(hit.methods),
        snippet=snippet,
        updated_at=file.updated_at,
        source_kind=file.source_kind,
        author=file.author,
        authored_at=file.authored_at,
        department=file.department,
        document_type=file.document_type,
        source_updated_at=file.source_updated_at,
    )


def _file_search_retrieval_filters(request: FileSearchRequest) -> dict[str, Any]:
    keyword: dict[str, Any] = {"entity_types": ["file"]}
    target_refs: list[dict[str, str]] = []
    for field in ("source_kind", "author", "department", "document_type"):
        value = getattr(request, field)
        if value is None:
            continue
        target_refs.append(
            {
                "app": EXTERNAL_SOURCE_TARGET_APP,
                "type": EXTERNAL_SOURCE_TARGET_TYPES[
                    "origin_source_kind" if field == "source_kind" else field
                ],
                "id": external_source_target_id(value),
            }
        )
    if target_refs:
        keyword["target_refs"] = target_refs
        keyword["target_ref_match"] = "all"
    if request.authored_from is not None or request.authored_to is not None:
        keyword["date_filters"] = [
            {
                "field": "authored_at",
                "from": request.authored_from,
                "to": request.authored_to,
            }
        ]

    rag: dict[str, Any] = {}
    for request_field, metadata_field in (
        ("source_kind", "origin_source_kind_filter"),
        ("author", "author_filter"),
        ("department", "department_filter"),
        ("document_type", "document_type_filter"),
    ):
        value = getattr(request, request_field)
        if value is not None:
            rag[f"metadata.{metadata_field}"] = external_source_filter_value(value)
    authored_range = {
        key: value
        for key, value in {
            "gte": request.authored_from,
            "lte": request.authored_to,
        }.items()
        if value is not None
    }
    if authored_range:
        rag["metadata.authored_at"] = authored_range
    return {"keyword": keyword, **({"rag": rag} if rag else {})}


def _file_source_matches_request(
    file: FileManagerFile,
    *,
    request: FileSearchRequest,
) -> bool:
    metadata = file.source_metadata
    values = {
        "source_kind": external_source_kind(file),
        "author": metadata.author if metadata is not None else None,
        "department": metadata.department if metadata is not None else None,
        "document_type": metadata.document_type if metadata is not None else None,
    }
    for field, actual in values.items():
        expected = getattr(request, field)
        if expected is not None and _normalized_filter_value(actual) != _normalized_filter_value(
            expected
        ):
            return False
    authored_at = metadata.authored_at if metadata is not None else None
    if request.authored_from is not None and (
        authored_at is None or authored_at < request.authored_from
    ):
        return False
    if request.authored_to is not None and (
        authored_at is None or authored_at > request.authored_to
    ):
        return False
    return True


def _normalized_filter_value(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()).casefold()


def _lexical_snippet(text: str, *, query: str) -> FileSearchSnippet:
    if not text or not text.strip():
        return FileSearchSnippet(text="")

    query_tokens = _bounded_snippet_query_tokens(query)
    token_pattern = _snippet_token_pattern(query_tokens)
    anchor_match = (
        token_pattern.search(text, 0, MAX_FILE_SEARCH_SNIPPET_ANCHOR_SCAN_CHARS)
        if token_pattern is not None
        else None
    )
    anchor_start = anchor_match.start() if anchor_match is not None else 0
    anchor_end = anchor_match.end() if anchor_match is not None else anchor_start

    context_scan_start = max(0, anchor_start - MAX_FILE_SEARCH_SNIPPET_CHARS)
    context_scan_end = min(
        len(text),
        max(anchor_end, anchor_start + 1) + MAX_FILE_SEARCH_SNIPPET_CHARS,
    )
    context = text[context_scan_start:context_scan_end]
    words = list(re.finditer(r"\S+", context))
    if not words:
        return FileSearchSnippet(text="")
    relative_anchor = anchor_start - context_scan_start
    anchor_index = next(
        (index for index, word in enumerate(words) if word.start() <= relative_anchor < word.end()),
        0,
    )
    start_index = max(0, anchor_index - FILE_SEARCH_SNIPPET_CONTEXT_WORDS)
    end_index = min(len(words), anchor_index + FILE_SEARCH_SNIPPET_CONTEXT_WORDS + 1)
    snippet_start = context_scan_start + words[start_index].start()
    snippet_end = context_scan_start + words[end_index - 1].end()
    snippet_start, snippet_end = _bounded_snippet_range(
        text_length=len(text),
        start=snippet_start,
        end=snippet_end,
        anchor_start=anchor_start,
        anchor_end=anchor_end,
    )
    snippet_text = text[snippet_start:snippet_end]
    highlights: list[FileSearchHighlight] = []
    if anchor_match is not None and token_pattern is not None:
        for match in token_pattern.finditer(snippet_text):
            highlights.append(
                FileSearchHighlight(
                    start=_utf16_offset(snippet_text, match.start()),
                    end=_utf16_offset(snippet_text, match.end()),
                )
            )
            if len(highlights) >= MAX_FILE_SEARCH_HIGHLIGHTS:
                break
    return FileSearchSnippet(text=snippet_text, highlights=highlights)


def _bounded_snippet_query_tokens(query: str) -> tuple[str, ...]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\S+", query):
        token = match.group(0)[:MAX_FILE_SEARCH_SNIPPET_QUERY_TOKEN_CHARS]
        normalized = token.casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(token)
        if len(tokens) >= MAX_FILE_SEARCH_SNIPPET_QUERY_TOKENS:
            break
    return tuple(tokens)


def _snippet_token_pattern(tokens: tuple[str, ...]) -> re.Pattern[str] | None:
    if not tokens:
        return None
    alternatives = sorted((re.escape(token) for token in tokens), key=len, reverse=True)
    return re.compile("|".join(alternatives), flags=re.IGNORECASE)


def _bounded_snippet_range(
    *,
    text_length: int,
    start: int,
    end: int,
    anchor_start: int,
    anchor_end: int,
) -> tuple[int, int]:
    if end - start <= MAX_FILE_SEARCH_SNIPPET_CHARS:
        return start, end
    half_window = MAX_FILE_SEARCH_SNIPPET_CHARS // 2
    bounded_start = max(start, anchor_start - half_window)
    bounded_end = min(end, bounded_start + MAX_FILE_SEARCH_SNIPPET_CHARS)
    if anchor_end > bounded_end:
        bounded_end = min(text_length, anchor_end)
        bounded_start = max(start, bounded_end - MAX_FILE_SEARCH_SNIPPET_CHARS)
    return bounded_start, bounded_end


def _utf16_offset(value: str, codepoint_offset: int) -> int:
    return len(value[:codepoint_offset].encode("utf-16-le")) // 2


__all__ = [
    "FileSearchRequest",
    "FileSearchResponse",
    "FileSearchRuntime",
    "FileSearchStrategy",
    "FileSearchUnavailable",
    "query_files",
    "resolve_file_search_runtime",
]
