"""Source-fresh Files evidence retrieval for grounded chat experiences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.retrieval_contract import FILES_RAG_SOURCE_KIND
from open_work_hub_api.domains.files.search import (
    FileSearchUnavailable,
    resolve_file_search_runtime,
)
from open_work_hub_api.domains.retrieval.application import query_retrieval
from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalAnswerMode,
    RetrievalQueryRequest,
    RetrievalStrategy,
)
from open_work_hub_api.domains.retrieval.ranking import MIN_NORMALIZED_RERANK_SCORE
from open_work_hub_api.domains.source_access import SourceAclPolicy
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


MAX_FILE_CHAT_EVIDENCE_ITEMS = 8
MAX_FILE_CHAT_EVIDENCE_CANDIDATES = 100
MAX_FILE_CHAT_EVIDENCE_EXCERPT_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class FileChatEvidenceItem:
    file_id: str
    filename: str
    locator: str | None
    excerpt: str
    methods: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FileChatEvidenceResult:
    items: tuple[FileChatEvidenceItem, ...]
    trace_id: str | None = None
    latency_ms: int = 0


@dataclass(frozen=True, slots=True)
class _FileChatSource:
    file_id: str
    filename: str
    folder_id: str | None


def query_file_chat_evidence(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    query: str,
    limit: int = MAX_FILE_CHAT_EVIDENCE_ITEMS,
    conversation_id: str | None = None,
) -> FileChatEvidenceResult:
    """Return Files-only evidence from the active partitioned retrieval pair.

    Retrieval backends are candidate indexes, never authorization sources. The
    final source-owned ACL runs against refreshed PostgreSQL state after source
    hydration and immediately before the result is assembled.
    """

    if limit < 1 or limit > MAX_FILE_CHAT_EVIDENCE_ITEMS:
        raise ValueError(f"limit must be between 1 and {MAX_FILE_CHAT_EVIDENCE_ITEMS}")

    runtime = resolve_file_search_runtime(db)
    response = query_retrieval(
        db,
        workspace=workspace,
        user=user,
        request=RetrievalQueryRequest(
            query=query,
            strategy=RetrievalStrategy.HYBRID,
            sources=["keyword", "generic_rag"],
            source_kinds=[FILES_RAG_SOURCE_KIND],
            filters={"keyword": {"entity_types": ["file"]}},
            # Keep a bounded refill window so stale or newly unauthorized index
            # candidates do not prevent later authorized evidence from filling
            # the caller's small context pack.
            top_k=MAX_FILE_CHAT_EVIDENCE_CANDIDATES,
            answer_mode=RetrievalAnswerMode.SEARCH_ONLY,
        ),
        source="api.files.chat.evidence",
        conversation_id=conversation_id,
        keyword_search_client=runtime.keyword_client,
        keyword_evaluation_entity_types=("file",),
        # Chat questions are natural language: keyword retrieval must use the
        # platform OR/30% contract rather than the Files search UI's strict AND.
        keyword_strict_text_match=False,
        rag_allowed_unlisted_source_kinds=frozenset({FILES_RAG_SOURCE_KIND}),
        rag_query_service=runtime.rag_query_service,
        rag_collection=runtime.rag_collection,
        partitioned_generation=True,
    )
    ranked_hits = [
        hit
        for hit in response.hits
        if hit.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
        and hit.source_kind == FILES_RAG_SOURCE_KIND
    ][:MAX_FILE_CHAT_EVIDENCE_CANDIDATES]
    profile = getattr(response, "profile", None)
    backend_profiles = getattr(profile, "backend_profiles", None)
    rerank_profile = backend_profiles.get("rerank") if isinstance(backend_profiles, dict) else None
    ranked_hits = _filter_file_chat_relevance(
        ranked_hits,
        rerank_profile=rerank_profile,
    )
    if not ranked_hits:
        return FileChatEvidenceResult(
            items=(),
            trace_id=response.trace_id,
            latency_ms=response.latency_ms,
        )

    sources_by_id = _load_file_chat_sources(
        db,
        [str(hit.resource_id) for hit in ranked_hits],
    )

    # Source hydration may populate stale ORM identity-map entries. Expire them
    # before the final ACL query so deletes, moves, and scope revocations that
    # committed during retrieval take effect on this response.
    db.expire_all()
    policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
    allowed = policy.authorize_many_resources(
        (FILE_MANAGER_FILE_RESOURCE_TYPE, str(hit.resource_id))
        for hit in ranked_hits
        if str(hit.resource_id) in sources_by_id
    )

    items: list[FileChatEvidenceItem] = []
    for hit in ranked_hits:
        file_id = str(hit.resource_id)
        source = sources_by_id.get(file_id)
        if source is None or (FILE_MANAGER_FILE_RESOURCE_TYPE, file_id) not in allowed:
            continue
        excerpt = _bounded_evidence_excerpt(hit)
        if not excerpt:
            continue
        items.append(
            FileChatEvidenceItem(
                file_id=file_id,
                filename=source.filename,
                locator=_evidence_locator(
                    hit,
                    workspace=workspace,
                    source=source,
                ),
                excerpt=excerpt,
                methods=tuple(
                    dict.fromkeys(
                        str(method).strip() for method in hit.methods if str(method).strip()
                    )
                ),
            )
        )
        if len(items) >= limit:
            break

    return FileChatEvidenceResult(
        items=tuple(items),
        trace_id=response.trace_id,
        latency_ms=response.latency_ms,
    )


def _load_file_chat_sources(
    db: Session,
    file_ids: list[str],
) -> dict[str, _FileChatSource]:
    normalized_ids = tuple(dict.fromkeys(file_id for file_id in file_ids if file_id))
    if not normalized_ids:
        return {}
    return {
        row.id: _FileChatSource(
            file_id=row.id,
            filename=row.filename,
            folder_id=row.folder_id,
        )
        for row in db.execute(
            select(
                FileManagerFile.id,
                FileManagerFile.filename,
                FileManagerFile.folder_id,
            ).where(
                FileManagerFile.id.in_(normalized_ids),
                FileManagerFile.deleted_at.is_(None),
            )
        )
    }


def _bounded_evidence_excerpt(hit: Any) -> str:
    value = str(hit.excerpt or hit.summary or "").strip()
    return value[:MAX_FILE_CHAT_EVIDENCE_EXCERPT_CHARS].rstrip()


def _filter_file_chat_relevance(
    hits: list[Any],
    *,
    rerank_profile: Any,
) -> list[Any]:
    """Only admit evidence with a healthy calibrated relevance score."""

    if not isinstance(rerank_profile, dict):
        return []
    if rerank_profile.get("score_semantics") != "normalized_relevance":
        return []
    if rerank_profile.get("applied") is not True or rerank_profile.get("degraded") is not False:
        return []
    return [
        hit
        for hit in hits
        if "cross_encoder" in hit.methods and float(hit.score) >= MIN_NORMALIZED_RERANK_SCORE
    ]


def _evidence_locator(
    hit: Any,
    *,
    workspace: Workspace,
    source: _FileChatSource,
) -> str | None:
    metadata = hit.metadata if isinstance(hit.metadata, dict) else {}
    for key in ("locator_label", "section_path"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value

    query = {"file": source.file_id}
    if source.folder_id:
        query["folder"] = source.folder_id
    return f"/w/{workspace.key}/files?{urlencode(query)}"


__all__ = [
    "FileChatEvidenceItem",
    "FileChatEvidenceResult",
    "FileSearchUnavailable",
    "MAX_FILE_CHAT_EVIDENCE_EXCERPT_CHARS",
    "MAX_FILE_CHAT_EVIDENCE_ITEMS",
    "query_file_chat_evidence",
]
