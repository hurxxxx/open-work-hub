from __future__ import annotations

import re
from collections.abc import Callable
from collections import defaultdict
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from sqlalchemy import Uuid, bindparam, case, delete, func, or_, select, text as sa_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.auth.models import Workspace, utcnow_naive
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.legacy_issues.dataset_records import (
    DATASET_DEFINITIONS,
    LEGACY_ISSUE_MODULE_KEYS,
    LegacyIssueDatasetDefinition,
    field_labels,
    get_dataset_definition_with_all_module_fields,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueAiChunk,
    LegacyIssueAttachment,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from ai_do_api.domains.legacy_issues.revisioning import (
    REVISION_STATUS_DRAFT,
    REVISION_STATUS_PUBLISHED,
    legacy_issue_dataset_revision_key,
)
from ai_do_api.domains.legacy_issues.partitioning import (
    ensure_record_partition,
    ensure_revision_partition,
)
from ai_do_api.domains.legacy_issues.settings import get_legacy_issue_settings
from ai_do_api.domains.rag.contracts import RagProjection
from ai_do_api.domains.rag.contracts import RagVectorSearchHit
from ai_do_api.domains.rag.provider_factory import RagProviderFactory
from ai_do_api.domains.retrieval.partitioning import resolve_read_scope
from ai_do_api.domains.source_access.resource_types import (
    LEGACY_ISSUE_RECORD_RESOURCE_TYPE,
)


SUMMARY_CHUNK_KEY = "summary"
LEGACY_ISSUE_PGVECTOR_INDEX_NAME = "ix_legacy_issue_ai_chunks_embedding_hnsw"
LEGACY_ISSUE_RAG_SOURCE_KIND = "legacy_issues"
LEGACY_ISSUE_RAG_RESOURCE_TYPE = LEGACY_ISSUE_RECORD_RESOURCE_TYPE
EMBEDDING_STATUS_EMBEDDED = "embedded"
EMBEDDING_STATUS_FAILED = "failed"
EMBEDDING_STATUS_SKIPPED = "skipped"
_PARTITION_COMPATIBILITY_SQL = (
    "(retrieval_partition_id IS NULL OR retrieval_partition_id IN :partition_ids)"
)
EMBEDDING_STATUS_PENDING = "pending"
EMBEDDING_STATUS_NOT_INDEXED = "not_indexed"
LONG_FIELD_HINTS = (
    "problem",
    "symptom",
    "cause",
    "countermeasure",
    "measure",
    "result",
    "review",
    "check",
    "note",
    "opinion",
    "action",
    "evaluation",
    "attachment",
    "confirmation",
)
ASCII_WORD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./+-]*$")
SEARCH_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./+-]*|[가-힣]+")
MAX_SEARCH_TERMS = 512
MAX_EFFECTIVE_REVISION_SELECTION_ATTEMPTS = 2
MAX_ATTACHMENT_RECONCILIATION_JOBS_PER_REQUEST = 25
MAX_SEARCH_PLAN_PRIMARY_KEYWORDS = 8
MAX_SEARCH_PLAN_KEYWORDS = 12
MAX_SEARCH_PLAN_SUPPORTING_KEYWORDS = 12
MAX_SEARCH_PLAN_FIELD_HINTS = 8
MAX_SEARCH_PLAN_REPORT_FOCUS = 6
MAX_SEARCH_PLAN_RELATED_FIELDS = 4
MAX_SEARCH_PLAN_ITEM_CHARS = 80


CandidateRecordAuthorizer = Callable[[tuple[str, ...]], frozenset[str]]


@dataclass(frozen=True)
class LegacyIssueAssistantSearchPlan:
    query: str
    dataset_keys: tuple[str, ...]
    primary_keywords: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    supporting_keywords: tuple[str, ...] = ()
    field_hints: tuple[str, ...] = ()
    intent: str = "investigate"
    report_focus: tuple[str, ...] = ()
    related_field_expansions: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegacyIssueSearchProfile:
    semantic_enabled: bool
    vector_extension_available: bool
    vector_index_available: bool
    trigram_extension_available: bool
    full_text_enabled: bool
    searched_dataset_keys: tuple[str, ...]
    searched_revision_ids: tuple[str, ...]
    candidate_count: int
    evidence_count: int
    methods: tuple[str, ...]


@dataclass(frozen=True)
class LegacyIssueMatchedChunk:
    chunk_id: str
    chunk_key: str
    chunk_kind: str
    field_key: str | None
    field_label: str | None
    field_value: str | None
    attachment_id: str | None
    attachment_filename: str | None
    attachment_page: int | None
    attachment_artifact_type: str | None
    excerpt: str
    methods: tuple[str, ...]
    score: float


@dataclass(frozen=True)
class LegacyIssueEvidenceAttachment:
    id: str
    filename: str
    description: str | None
    content_type: str
    size_bytes: int
    index_status: str
    indexed_at: Any | None
    matched_chunks: tuple[LegacyIssueMatchedChunk, ...]
    score: float
    methods: tuple[str, ...]


@dataclass(frozen=True)
class LegacyIssueEvidence:
    evidence_id: str
    dataset_key: str
    dataset_title: str
    revision_id: str | None
    revision_no: int | None
    record_id: str
    stable_record_id: str | None
    label: str
    values: dict[str, str]
    matched_fields: tuple[str, ...]
    matched_chunks: tuple[LegacyIssueMatchedChunk, ...]
    score: float
    methods: tuple[str, ...]
    attachments: tuple[LegacyIssueEvidenceAttachment, ...] = ()


@dataclass
class _Candidate:
    chunk: LegacyIssueAiChunk
    methods: set[str] = field(default_factory=set)
    score: float = 0.0


@dataclass(frozen=True)
class _WeightedToken:
    value: str
    weight: float
    category: str


def sanitize_legacy_issue_search_plan(
    *,
    question: str,
    dataset_keys: list[str] | tuple[str, ...] | None,
    primary_keywords: list[str] | tuple[str, ...] | str | None = None,
    keywords: list[str] | tuple[str, ...] | str | None = None,
    supporting_keywords: list[str] | tuple[str, ...] | str | None = None,
    field_hints: list[str] | tuple[str, ...] | str | None = None,
    intent: str | None = None,
    report_focus: list[str] | tuple[str, ...] | str | None = None,
    related_field_expansions: list[str] | tuple[str, ...] | str | None = None,
) -> LegacyIssueAssistantSearchPlan:
    normalized_query = " ".join(question.split())
    allowed_dataset_keys = tuple(DATASET_DEFINITIONS)
    normalized_dataset_keys = tuple(
        key for key in (dataset_keys or allowed_dataset_keys) if key in DATASET_DEFINITIONS
    )
    cleaned_primary_keywords = _unique_limited(
        _coerce_text_items(primary_keywords),
        max_items=MAX_SEARCH_PLAN_PRIMARY_KEYWORDS,
        max_length=MAX_SEARCH_PLAN_ITEM_CHARS,
    )
    cleaned_keywords = _unique_limited(
        _coerce_text_items(keywords),
        max_items=MAX_SEARCH_PLAN_KEYWORDS,
        max_length=MAX_SEARCH_PLAN_ITEM_CHARS,
    )
    cleaned_supporting_keywords = _unique_limited(
        _coerce_text_items(supporting_keywords),
        max_items=MAX_SEARCH_PLAN_SUPPORTING_KEYWORDS,
        max_length=MAX_SEARCH_PLAN_ITEM_CHARS,
    )
    cleaned_field_hints = _unique_limited(
        _coerce_text_items(field_hints),
        max_items=MAX_SEARCH_PLAN_FIELD_HINTS,
        max_length=MAX_SEARCH_PLAN_ITEM_CHARS,
    )
    cleaned_focus = _unique_limited(
        _coerce_text_items(report_focus),
        max_items=MAX_SEARCH_PLAN_REPORT_FOCUS,
        max_length=MAX_SEARCH_PLAN_ITEM_CHARS,
    )
    cleaned_related_fields = tuple(
        field_key
        for field_key in _unique_limited(
            _coerce_text_items(related_field_expansions),
            max_items=MAX_SEARCH_PLAN_RELATED_FIELDS,
            max_length=MAX_SEARCH_PLAN_ITEM_CHARS,
        )
        if field_key in _known_field_keys()
    )
    return LegacyIssueAssistantSearchPlan(
        query=normalized_query,
        dataset_keys=normalized_dataset_keys or allowed_dataset_keys,
        primary_keywords=tuple(cleaned_primary_keywords),
        keywords=tuple(cleaned_keywords),
        supporting_keywords=tuple(cleaned_supporting_keywords),
        field_hints=tuple(cleaned_field_hints),
        intent=(intent or "investigate").strip()[:80] or "investigate",
        report_focus=tuple(cleaned_focus),
        related_field_expansions=cleaned_related_fields,
    )


def ensure_legacy_issue_ai_projection_for_effective_revisions(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    module_keys: frozenset[str] | None = None,
) -> dict[str, list[LegacyIssueDataRevision]]:
    revisions: dict[str, list[LegacyIssueDataRevision]] = {}
    attachment_index_enabled = get_legacy_issue_settings().ai_attachment_index_enabled
    attachment_reconciliation_budget = MAX_ATTACHMENT_RECONCILIATION_JOBS_PER_REQUEST
    for dataset_key in dataset_keys:
        definition = DATASET_DEFINITIONS.get(dataset_key)
        if definition is None:
            continue
        dataset_revisions: list[LegacyIssueDataRevision] = []
        effective_module_keys = LEGACY_ISSUE_MODULE_KEYS if module_keys is None else module_keys
        for module_key in sorted(effective_module_keys):
            revision_dataset_key = legacy_issue_dataset_revision_key(
                definition.key,
                module_key,
            )
            for _attempt in range(MAX_EFFECTIVE_REVISION_SELECTION_ATTEMPTS):
                revision = _effective_revision_for_ai(
                    db,
                    workspace=workspace,
                    dataset_key=revision_dataset_key,
                )
                if revision is None:
                    break
                projection_state = _legacy_issue_projection_counts(
                    db,
                    workspace_id=workspace.id,
                    dataset_key=definition.key,
                    revision_id=revision.id,
                )
                record_projection_incomplete = len(set(projection_state[:3])) != 1
                attachment_projection_incomplete = (
                    attachment_index_enabled and projection_state[3] > 0
                )
                should_repair = record_projection_incomplete or (
                    attachment_projection_incomplete and attachment_reconciliation_budget > 0
                )
                if should_repair:
                    repaired, enqueued_attachment_count = (
                        _repair_legacy_issue_ai_projection_in_new_transaction(
                            db,
                            workspace_id=workspace.id,
                            dataset_key=definition.key,
                            revision_dataset_key=revision_dataset_key,
                            revision_id=revision.id,
                            attachment_limit=(
                                attachment_reconciliation_budget if attachment_index_enabled else 0
                            ),
                        )
                    )
                    attachment_reconciliation_budget = max(
                        attachment_reconciliation_budget - enqueued_attachment_count,
                        0,
                    )
                    if not repaired:
                        continue
                confirmed_revision = _effective_revision_for_ai(
                    db,
                    workspace=workspace,
                    dataset_key=revision_dataset_key,
                )
                if confirmed_revision is None:
                    break
                if confirmed_revision.id != revision.id:
                    continue
                dataset_revisions.append(confirmed_revision)
                break
        if dataset_revisions:
            revisions[dataset_key] = dataset_revisions
    return revisions


def _legacy_issue_projection_counts(
    db: Session,
    *,
    workspace_id: str,
    dataset_key: str,
    revision_id: str,
) -> tuple[int, int, int, int]:
    record_count_query = select(func.count(LegacyIssueRecord.id)).where(
        LegacyIssueRecord.workspace_id == workspace_id,
        LegacyIssueRecord.dataset_key == dataset_key,
        LegacyIssueRecord.revision_id == revision_id,
    )
    projected_record_count_query = select(
        func.count(func.distinct(LegacyIssueAiChunk.record_id))
    ).where(
        LegacyIssueAiChunk.workspace_id == workspace_id,
        LegacyIssueAiChunk.dataset_key == dataset_key,
        LegacyIssueAiChunk.revision_id == revision_id,
        LegacyIssueAiChunk.attachment_id.is_(None),
        LegacyIssueAiChunk.chunk_key == SUMMARY_CHUNK_KEY,
    )
    valid_projected_record_count_query = (
        select(func.count(func.distinct(LegacyIssueAiChunk.record_id)))
        .select_from(LegacyIssueAiChunk)
        .join(
            LegacyIssueRecord,
            LegacyIssueRecord.id == LegacyIssueAiChunk.record_id,
        )
        .where(
            LegacyIssueAiChunk.workspace_id == workspace_id,
            LegacyIssueAiChunk.dataset_key == dataset_key,
            LegacyIssueAiChunk.revision_id == revision_id,
            LegacyIssueAiChunk.attachment_id.is_(None),
            LegacyIssueAiChunk.chunk_key == SUMMARY_CHUNK_KEY,
            LegacyIssueRecord.workspace_id == workspace_id,
            LegacyIssueRecord.dataset_key == dataset_key,
            LegacyIssueRecord.revision_id == revision_id,
        )
    )
    unindexed_attachment_count_query = select(func.count(LegacyIssueAttachment.id)).where(
        LegacyIssueAttachment.workspace_id == workspace_id,
        LegacyIssueAttachment.dataset_key == dataset_key,
        LegacyIssueAttachment.revision_id == revision_id,
        LegacyIssueAttachment.index_status == "not_indexed",
    )
    (
        record_count,
        projected_record_count,
        valid_projected_record_count,
        unindexed_attachment_count,
    ) = db.execute(
        select(
            record_count_query.scalar_subquery(),
            projected_record_count_query.scalar_subquery(),
            valid_projected_record_count_query.scalar_subquery(),
            unindexed_attachment_count_query.scalar_subquery(),
        )
    ).one()
    return (
        int(record_count or 0),
        int(projected_record_count or 0),
        int(valid_projected_record_count or 0),
        int(unindexed_attachment_count or 0),
    )


def _repair_legacy_issue_ai_projection_in_new_transaction(
    db: Session,
    *,
    workspace_id: str,
    dataset_key: str,
    revision_dataset_key: str,
    revision_id: str,
    attachment_limit: int,
    session_factory: Callable[[], Session] | None = None,
) -> tuple[bool, int]:
    factory = session_factory or sessionmaker(
        bind=db.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    with factory() as repair_db:
        repair_workspace = repair_db.get(Workspace, workspace_id)
        if repair_workspace is None:
            return False, 0
        repair_revision = _effective_revision_for_ai(
            repair_db,
            workspace=repair_workspace,
            dataset_key=revision_dataset_key,
            for_update=True,
        )
        if repair_revision is None or repair_revision.id != revision_id:
            return False, 0
        projection_state = _legacy_issue_projection_counts(
            repair_db,
            workspace_id=workspace_id,
            dataset_key=dataset_key,
            revision_id=revision_id,
        )
        changed = False
        if len(set(projection_state[:3])) != 1:
            reindex_definition = get_dataset_definition_with_all_module_fields(
                repair_db,
                dataset_key=dataset_key,
                workspace=repair_workspace,
            )
            changed = _repair_legacy_issue_record_projection_without_embeddings(
                repair_db,
                reindex_definition,
                workspace=repair_workspace,
                revision=repair_revision,
            )
        enqueued_attachment_count = 0
        if attachment_limit > 0 and projection_state[3] > 0:
            from ai_do_api.domains.legacy_issues.attachment_indexing import (
                enqueue_legacy_issue_attachment_index_job,
            )

            attachments = list(
                repair_db.scalars(
                    select(LegacyIssueAttachment)
                    .where(
                        LegacyIssueAttachment.workspace_id == workspace_id,
                        LegacyIssueAttachment.dataset_key == dataset_key,
                        LegacyIssueAttachment.revision_id == revision_id,
                        LegacyIssueAttachment.index_status == "not_indexed",
                    )
                    .order_by(LegacyIssueAttachment.created_at, LegacyIssueAttachment.id)
                    .limit(attachment_limit)
                )
            )
            for attachment in attachments:
                enqueue_legacy_issue_attachment_index_job(
                    repair_db,
                    attachment=attachment,
                    trigger="effective_revision_reconcile",
                )
            enqueued_attachment_count = len(attachments)
            changed = changed or bool(attachments)
        if changed:
            repair_db.commit()
        return True, enqueued_attachment_count


def _repair_legacy_issue_record_projection_without_embeddings(
    db: Session,
    definition: LegacyIssueDatasetDefinition,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
) -> bool:
    valid_record_ids = select(LegacyIssueRecord.id).where(
        LegacyIssueRecord.workspace_id == workspace.id,
        LegacyIssueRecord.dataset_key == definition.key,
        LegacyIssueRecord.revision_id == revision.id,
    )
    db.execute(
        delete(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.workspace_id == workspace.id,
            LegacyIssueAiChunk.dataset_key == definition.key,
            LegacyIssueAiChunk.revision_id == revision.id,
            LegacyIssueAiChunk.attachment_id.is_(None),
            LegacyIssueAiChunk.record_id.not_in(valid_record_ids),
        )
    )
    projected_record_ids = select(LegacyIssueAiChunk.record_id).where(
        LegacyIssueAiChunk.workspace_id == workspace.id,
        LegacyIssueAiChunk.dataset_key == definition.key,
        LegacyIssueAiChunk.revision_id == revision.id,
        LegacyIssueAiChunk.attachment_id.is_(None),
        LegacyIssueAiChunk.chunk_key == SUMMARY_CHUNK_KEY,
    )
    missing_records = list(
        db.scalars(
            select(LegacyIssueRecord)
            .where(
                LegacyIssueRecord.workspace_id == workspace.id,
                LegacyIssueRecord.dataset_key == definition.key,
                LegacyIssueRecord.revision_id == revision.id,
                LegacyIssueRecord.id.not_in(projected_record_ids),
            )
            .order_by(LegacyIssueRecord.created_at, LegacyIssueRecord.id)
        )
    )
    for record in missing_records:
        reindex_legacy_issue_record_ai_chunks(
            db,
            definition,
            workspace=workspace,
            revision=revision,
            record=record,
            embed=False,
        )
    return True


def _effective_revision_for_ai(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    for_update: bool = False,
) -> LegacyIssueDataRevision | None:
    statement = (
        select(LegacyIssueDataRevision)
        .where(
            LegacyIssueDataRevision.workspace_id == workspace.id,
            LegacyIssueDataRevision.dataset_key == dataset_key,
            LegacyIssueDataRevision.status.in_((REVISION_STATUS_DRAFT, REVISION_STATUS_PUBLISHED)),
        )
        .order_by(
            case(
                (LegacyIssueDataRevision.status == REVISION_STATUS_DRAFT, 0),
                else_=1,
            ),
            LegacyIssueDataRevision.revision_no.desc().nullslast(),
            LegacyIssueDataRevision.published_at.desc().nullslast(),
            LegacyIssueDataRevision.created_at.desc(),
        )
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def reindex_legacy_issue_record_ai_chunks(
    db: Session,
    definition: LegacyIssueDatasetDefinition,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
    record: LegacyIssueRecord,
    embed: bool | None = None,
) -> None:
    ensure_revision_partition(db, revision)
    ensure_record_partition(db, record, revision=revision)
    db.execute(
        delete(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.workspace_id == workspace.id,
            LegacyIssueAiChunk.dataset_key == definition.key,
            LegacyIssueAiChunk.record_id == record.id,
            LegacyIssueAiChunk.attachment_id.is_(None),
        )
    )
    chunks = _build_chunks_for_record(
        definition, workspace=workspace, revision=revision, record=record
    )
    db.add_all(chunks)
    db.flush()
    _embed_chunks(db, chunks, embed=embed)
    db.flush()


def embed_legacy_issue_ai_chunks(
    db: Session,
    chunks: list[LegacyIssueAiChunk],
    *,
    embed: bool | None = None,
    cap: int | None = None,
) -> None:
    _embed_chunks(db, chunks, embed=embed, cap=cap)


def reindex_legacy_issue_revision_ai_chunks(
    db: Session,
    definition: LegacyIssueDatasetDefinition,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
    embed: bool | None = None,
    reuse_embeddings_from_revision: LegacyIssueDataRevision | None = None,
) -> None:
    ensure_revision_partition(db, revision)
    reusable_embeddings = _reusable_record_embeddings(
        db,
        definition=definition,
        workspace=workspace,
        revision=reuse_embeddings_from_revision,
    )
    db.execute(
        delete(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.workspace_id == workspace.id,
            LegacyIssueAiChunk.dataset_key == definition.key,
            LegacyIssueAiChunk.revision_id == revision.id,
            LegacyIssueAiChunk.attachment_id.is_(None),
        )
    )
    records = list(
        db.scalars(
            select(LegacyIssueRecord)
            .where(
                LegacyIssueRecord.workspace_id == workspace.id,
                LegacyIssueRecord.dataset_key == definition.key,
                LegacyIssueRecord.revision_id == revision.id,
            )
            .order_by(LegacyIssueRecord.updated_at.desc(), LegacyIssueRecord.created_at.desc())
        )
    )
    chunks: list[LegacyIssueAiChunk] = []
    for record in records:
        ensure_record_partition(db, record, revision=revision)
        chunks.extend(
            _build_chunks_for_record(
                definition, workspace=workspace, revision=revision, record=record
            )
        )
    if chunks:
        db.add_all(chunks)
        db.flush()
        if embed is False and reusable_embeddings:
            _mark_embedding_skipped(chunks)
            _reuse_record_embeddings(
                chunks,
                reusable_embeddings=reusable_embeddings,
                dataset_title=definition.title_ko,
            )
        else:
            _embed_chunks(
                db,
                chunks,
                embed=embed,
                cap=get_legacy_issue_settings().ai_max_sync_embedding_chunks,
            )
    db.flush()


def _reusable_record_embeddings(
    db: Session,
    *,
    definition: LegacyIssueDatasetDefinition,
    workspace: Workspace,
    revision: LegacyIssueDataRevision | None,
) -> dict[tuple[str, str, str], LegacyIssueAiChunk]:
    if revision is None:
        return {}
    settings = get_settings()
    embedding_dimensions = get_legacy_issue_settings().ai_embedding_dimensions
    rows = db.execute(
        select(
            LegacyIssueAiChunk,
            LegacyIssueRecord.stable_record_id,
            LegacyIssueRecord.id,
        )
        .join(
            LegacyIssueRecord,
            LegacyIssueRecord.id == LegacyIssueAiChunk.record_id,
        )
        .where(
            LegacyIssueAiChunk.workspace_id == workspace.id,
            LegacyIssueAiChunk.dataset_key == definition.key,
            LegacyIssueAiChunk.revision_id == revision.id,
            LegacyIssueAiChunk.attachment_id.is_(None),
            LegacyIssueAiChunk.embedding_status == EMBEDDING_STATUS_EMBEDDED,
            LegacyIssueAiChunk.embedding_vector.is_not(None),
            LegacyIssueAiChunk.embedding_model == settings.rag_local_embedding_model,
            LegacyIssueAiChunk.embedding_dimensions == embedding_dimensions,
            LegacyIssueRecord.workspace_id == workspace.id,
            LegacyIssueRecord.dataset_key == definition.key,
            LegacyIssueRecord.revision_id == revision.id,
        )
    ).all()
    reusable: dict[tuple[str, str, str], LegacyIssueAiChunk] = {}
    for chunk, record_stable_id, record_id in rows:
        stable_record_id = chunk.stable_record_id or record_stable_id or record_id
        reusable[
            (
                stable_record_id,
                chunk.chunk_key,
                _embedding_reuse_search_text(
                    chunk,
                    dataset_title=definition.title_ko,
                ),
            )
        ] = chunk
    return reusable


def _reuse_record_embeddings(
    chunks: list[LegacyIssueAiChunk],
    *,
    reusable_embeddings: dict[tuple[str, str, str], LegacyIssueAiChunk],
    dataset_title: str,
) -> None:
    for chunk in chunks:
        stable_record_id = chunk.stable_record_id or chunk.record_id
        reusable = reusable_embeddings.get(
            (
                stable_record_id,
                chunk.chunk_key,
                _embedding_reuse_search_text(
                    chunk,
                    dataset_title=dataset_title,
                ),
            )
        )
        if reusable is None:
            continue
        chunk.embedding_vector = reusable.embedding_vector
        chunk.embedding_model = reusable.embedding_model
        chunk.embedding_dimensions = reusable.embedding_dimensions
        chunk.embedding_status = EMBEDDING_STATUS_EMBEDDED
        chunk.embedding_error = None


def _embedding_reuse_search_text(
    chunk: LegacyIssueAiChunk,
    *,
    dataset_title: str,
) -> str:
    if chunk.chunk_key != SUMMARY_CHUNK_KEY:
        return chunk.search_text
    legacy_prefix = f"{dataset_title} revision: "
    if not chunk.search_text.casefold().startswith(legacy_prefix.casefold()):
        return chunk.search_text
    legacy_suffix = chunk.search_text[len(legacy_prefix) :]
    _revision_value, separator, content = legacy_suffix.partition(" ")
    return f"{dataset_title}{separator}{content}"


def delete_legacy_issue_record_ai_chunks(
    db: Session,
    *,
    workspace: Workspace,
    dataset_key: str,
    record_id: str,
) -> None:
    db.execute(
        delete(LegacyIssueAiChunk).where(
            LegacyIssueAiChunk.workspace_id == workspace.id,
            LegacyIssueAiChunk.dataset_key == dataset_key,
            LegacyIssueAiChunk.record_id == record_id,
        )
    )
    db.flush()


def backfill_legacy_issue_pgvector_embeddings(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    module_keys: frozenset[str] | None = None,
    limit: int | None = None,
) -> int:
    revisions_by_dataset_key = ensure_legacy_issue_ai_projection_for_effective_revisions(
        db,
        workspace=workspace,
        dataset_keys=dataset_keys,
        module_keys=module_keys,
    )
    revision_ids = tuple(
        revision.id
        for dataset_revisions in revisions_by_dataset_key.values()
        for revision in dataset_revisions
    )
    if not revision_ids:
        return 0
    query = (
        select(LegacyIssueAiChunk)
        .where(
            LegacyIssueAiChunk.workspace_id == workspace.id,
            LegacyIssueAiChunk.dataset_key.in_(tuple(revisions_by_dataset_key)),
            LegacyIssueAiChunk.revision_id.in_(revision_ids),
            or_(
                LegacyIssueAiChunk.embedding_vector.is_(None),
                LegacyIssueAiChunk.embedding_status != EMBEDDING_STATUS_EMBEDDED,
            ),
        )
        .order_by(LegacyIssueAiChunk.updated_at.desc(), LegacyIssueAiChunk.created_at.desc())
    )
    if limit is not None:
        query = query.limit(max(limit, 0))
    chunks = list(db.scalars(query))
    if not chunks:
        return 0
    _embed_chunks(db, chunks, embed=True)
    db.flush()
    return sum(
        1
        for chunk in chunks
        if chunk.embedding_status == EMBEDDING_STATUS_EMBEDDED and chunk.embedding_vector
    )


def search_legacy_issue_evidence(
    db: Session,
    *,
    workspace: Workspace,
    plan: LegacyIssueAssistantSearchPlan,
    limit: int,
    module_keys: frozenset[str] | None = None,
    candidate_record_authorizer: CandidateRecordAuthorizer | None = None,
) -> tuple[list[LegacyIssueEvidence], LegacyIssueSearchProfile]:
    revisions_by_dataset_key = ensure_legacy_issue_ai_projection_for_effective_revisions(
        db,
        workspace=workspace,
        dataset_keys=plan.dataset_keys,
        module_keys=module_keys,
    )
    revision_ids = tuple(
        revision.id
        for dataset_revisions in revisions_by_dataset_key.values()
        for revision in dataset_revisions
    )
    if not revision_ids:
        profile = LegacyIssueSearchProfile(
            semantic_enabled=False,
            vector_extension_available=False,
            vector_index_available=False,
            trigram_extension_available=False,
            full_text_enabled=False,
            searched_dataset_keys=tuple(revisions_by_dataset_key),
            searched_revision_ids=(),
            candidate_count=0,
            evidence_count=0,
            methods=(),
        )
        return [], profile

    partition_ids = resolve_read_scope(
        db,
        source_namespaces=["legacy_issues"],
        workspace_id=workspace.id,
        user_id=None,
    ).for_source("legacy_issues")

    vector_available = _pg_extension_available(db, "vector")
    pgvector_available = vector_available and _is_postgres(db)
    vector_index_available = pgvector_available and _pg_index_available(
        db, LEGACY_ISSUE_PGVECTOR_INDEX_NAME
    )
    trigram_available = _pg_extension_available(db, "pg_trgm")
    semantic_enabled = (
        get_legacy_issue_settings().ai_semantic_enabled
        and pgvector_available
        and _embedding_available()
    )
    candidates: dict[str, _Candidate] = {}
    methods: set[str] = set()
    text_limit = max(limit * 8, 40)
    token_specs = _discriminative_token_specs(
        db,
        workspace=workspace,
        dataset_keys=tuple(revisions_by_dataset_key),
        revision_ids=revision_ids,
        partition_ids=partition_ids,
        plan=plan,
        result_limit=limit,
    )

    for chunk, score, method in _exact_candidates(
        db,
        workspace=workspace,
        dataset_keys=tuple(revisions_by_dataset_key),
        revision_ids=revision_ids,
        partition_ids=partition_ids,
        token_specs=token_specs,
        limit=text_limit,
    ):
        _merge_candidate(candidates, chunk=chunk, score=score, method=method)
        methods.add(method)

    if _is_postgres(db):
        for chunk, score, method in _term_index_candidates(
            db,
            workspace=workspace,
            dataset_keys=tuple(revisions_by_dataset_key),
            revision_ids=revision_ids,
            partition_ids=partition_ids,
            plan=plan,
            limit=text_limit,
        ):
            _merge_candidate(candidates, chunk=chunk, score=score, method=method)
            methods.add(method)
        for chunk, score, method in _full_text_candidates(
            db,
            workspace=workspace,
            dataset_keys=tuple(revisions_by_dataset_key),
            revision_ids=revision_ids,
            partition_ids=partition_ids,
            plan=plan,
            limit=text_limit,
        ):
            _merge_candidate(candidates, chunk=chunk, score=score, method=method)
            methods.add(method)
        if trigram_available:
            for chunk, score, method in _trigram_candidates(
                db,
                workspace=workspace,
                dataset_keys=tuple(revisions_by_dataset_key),
                revision_ids=revision_ids,
                partition_ids=partition_ids,
                plan=plan,
                limit=text_limit,
            ):
                _merge_candidate(candidates, chunk=chunk, score=score, method=method)
                methods.add(method)

    if semantic_enabled:
        semantic_query = _semantic_query(plan)
        query_embedding = _embed_query(semantic_query)
        if query_embedding:
            if pgvector_available:
                for chunk, score, method in _pgvector_candidates(
                    db,
                    workspace=workspace,
                    dataset_keys=tuple(revisions_by_dataset_key),
                    revision_ids=revision_ids,
                    partition_ids=partition_ids,
                    query_embedding=query_embedding,
                    limit=text_limit,
                ):
                    _merge_candidate(candidates, chunk=chunk, score=score, method=method)
                    methods.add(method)

    _retain_authorized_candidates(
        candidates,
        authorizer=candidate_record_authorizer,
    )
    _apply_planner_hint_boosts(candidates, plan=plan, token_specs=token_specs)

    if _merge_related_field_candidates(
        db,
        candidates,
        workspace=workspace,
        dataset_keys=tuple(revisions_by_dataset_key),
        revision_ids=revision_ids,
        partition_ids=partition_ids,
        plan=plan,
        limit=max(limit * 6, 24),
        candidate_record_authorizer=candidate_record_authorizer,
    ):
        methods.add("related_field")

    if _rerank_candidates(
        candidates,
        query=_semantic_query(plan),
        limit=max(text_limit, get_settings().rag_rerank_candidate_k),
    ):
        methods.add("rerank")

    evidence = _merge_evidence(
        candidates,
        revisions_by_dataset_key=revisions_by_dataset_key,
        limit=limit,
    )
    evidence = attach_record_values_to_evidence(db, evidence)
    profile = LegacyIssueSearchProfile(
        semantic_enabled=semantic_enabled,
        vector_extension_available=vector_available,
        vector_index_available=vector_index_available,
        trigram_extension_available=trigram_available,
        full_text_enabled=_is_postgres(db),
        searched_dataset_keys=tuple(revisions_by_dataset_key),
        searched_revision_ids=revision_ids,
        candidate_count=len(candidates),
        evidence_count=len(evidence),
        methods=tuple(sorted(methods)),
    )
    return evidence, profile


def _build_chunks_for_record(
    definition: LegacyIssueDatasetDefinition,
    *,
    workspace: Workspace,
    revision: LegacyIssueDataRevision,
    record: LegacyIssueRecord,
) -> list[LegacyIssueAiChunk]:
    values = {
        key: str(value).strip()
        for key, value in (record.field_values or {}).items()
        if str(value).strip()
    }
    labels = field_labels(definition)
    now = utcnow_naive()
    metadata = {
        "dataset_title_ko": definition.title_ko,
        "dataset_title_en": definition.title_en,
        "hierarchy_ko": list(definition.hierarchy_ko),
        "hierarchy_en": list(definition.hierarchy_en),
        "record_label": _record_label(record, values),
    }
    summary_lines = [
        definition.title_ko,
        *[f"{labels.get(key, key)}: {value}" for key, value in values.items() if value],
    ]
    chunks = [
        LegacyIssueAiChunk(
            id=new_id(),
            workspace_id=workspace.id,
            dataset_key=definition.key,
            revision_id=revision.id,
            record_id=record.id,
            retrieval_partition_id=record.retrieval_partition_id,
            stable_record_id=record.stable_record_id,
            chunk_key=SUMMARY_CHUNK_KEY,
            chunk_kind="record_summary",
            field_key=None,
            field_label=None,
            field_value=None,
            search_text=_compact_text("\n".join(summary_lines), limit=8000),
            search_terms=build_legacy_issue_search_terms("\n".join(summary_lines)),
            evidence_metadata=metadata,
            created_at=now,
            updated_at=now,
        )
    ]
    for field_definition in definition.fields:
        value = values.get(field_definition.key, "")
        if not value or not _should_create_field_chunk(field_definition.key, value):
            continue
        label = labels.get(field_definition.key, field_definition.key)
        search_text = _compact_text(
            "\n".join(
                (
                    definition.title_ko,
                    f"{label}: {value}",
                    f"record: {_record_label(record, values)}",
                )
            ),
            limit=4000,
        )
        chunks.append(
            LegacyIssueAiChunk(
                id=new_id(),
                workspace_id=workspace.id,
                dataset_key=definition.key,
                revision_id=revision.id,
                record_id=record.id,
                retrieval_partition_id=record.retrieval_partition_id,
                stable_record_id=record.stable_record_id,
                chunk_key=f"field:{field_definition.key}",
                chunk_kind="field_detail",
                field_key=field_definition.key,
                field_label=label,
                field_value=value,
                search_text=search_text,
                search_terms=build_legacy_issue_search_terms(search_text),
                evidence_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
        )
    return chunks


def build_legacy_issue_search_terms(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        normalized = value.casefold().strip()
        if len(normalized) < 2 or len(normalized) > 80 or normalized in seen:
            return
        seen.add(normalized)
        terms.append(normalized)

    for match in SEARCH_TOKEN_RE.finditer(text):
        token = match.group(0).casefold()
        add(token)
        if any("가" <= char <= "힣" for char in token):
            compact = re.sub(r"\s+", "", token)
            for size in (2, 3):
                if len(compact) >= size:
                    for index in range(0, len(compact) - size + 1):
                        add(compact[index : index + size])
        elif len(token) > 4:
            for part in re.split(r"[./+-]+", token):
                add(part)
    return terms[:MAX_SEARCH_TERMS]


def _embed_chunks(
    db: Session,
    chunks: list[LegacyIssueAiChunk],
    *,
    embed: bool | None,
    cap: int | None = None,
) -> None:
    settings = get_settings()
    legacy_settings = get_legacy_issue_settings()
    should_embed = (
        legacy_settings.ai_semantic_enabled and legacy_settings.ai_index_embeddings_on_write
    )
    if embed is not None:
        should_embed = should_embed and embed
    if not should_embed:
        _mark_embedding_skipped(chunks)
        return
    capped_chunks = _cap_chunks_by_record(chunks, cap=cap)
    capped_ids = {chunk.id for chunk in capped_chunks}
    overflow_chunks = [chunk for chunk in chunks if chunk.id not in capped_ids]
    for chunk in overflow_chunks:
        chunk.embedding_status = EMBEDDING_STATUS_PENDING
        chunk.embedding_error = "sync_embedding_cap_exceeded"
    if not capped_chunks:
        return
    try:
        embeddings = _legacy_embedding_client().embed_texts(
            [chunk.search_text for chunk in capped_chunks],
            timeout_seconds=max(settings.rag_query_timeout_ms / 1000, 1.0),
        )
    except Exception as error:  # pragma: no cover - provider/runtime dependent
        message = _compact_text(str(error), limit=1000)
        for chunk in capped_chunks:
            chunk.embedding_status = EMBEDDING_STATUS_FAILED
            chunk.embedding_error = message
        return
    for chunk, embedding in zip(capped_chunks, embeddings, strict=False):
        chunk.embedding_vector = _pgvector_literal(embedding)
        chunk.embedding_model = settings.rag_local_embedding_model
        chunk.embedding_dimensions = len(embedding)
        chunk.embedding_status = EMBEDDING_STATUS_EMBEDDED
        chunk.embedding_error = None
    # Legacy issue retrieval uses PostgreSQL/pgvector as its source of truth.
    # Generic RAG vector indexes such as Qdrant must not become a second,
    # business-opaque source for these rows.


def _mark_embedding_skipped(chunks: list[LegacyIssueAiChunk]) -> None:
    for chunk in chunks:
        chunk.embedding_status = EMBEDDING_STATUS_SKIPPED
        chunk.embedding_error = None


def _cap_chunks_by_record(
    chunks: list[LegacyIssueAiChunk],
    *,
    cap: int | None,
) -> list[LegacyIssueAiChunk]:
    if cap is None or len(chunks) <= cap:
        return list(chunks)
    if cap <= 0:
        return []
    result: list[LegacyIssueAiChunk] = []
    chunks_by_record: dict[str, list[LegacyIssueAiChunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_record[chunk.record_id].append(chunk)
    for record_chunks in chunks_by_record.values():
        if result and len(result) + len(record_chunks) > cap:
            break
        if not result and len(record_chunks) > cap:
            return record_chunks[:cap]
        result.extend(record_chunks)
    return result


def _exact_candidates(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    revision_ids: tuple[str, ...],
    partition_ids: tuple[str, ...],
    token_specs: tuple[_WeightedToken, ...],
    limit: int,
) -> list[tuple[LegacyIssueAiChunk, float, str]]:
    if not token_specs:
        return []
    conditions = [
        LegacyIssueAiChunk.search_text.ilike(_contains_like_pattern(token.value), escape="\\")
        for token in token_specs[:16]
    ]
    rows = list(
        db.scalars(
            select(LegacyIssueAiChunk)
            .where(
                LegacyIssueAiChunk.workspace_id == workspace.id,
                LegacyIssueAiChunk.dataset_key.in_(dataset_keys),
                LegacyIssueAiChunk.revision_id.in_(revision_ids),
                _partition_compatibility_predicate(
                    LegacyIssueAiChunk.retrieval_partition_id,
                    partition_ids,
                ),
                or_(*conditions),
            )
            .order_by(LegacyIssueAiChunk.updated_at.desc())
            .limit(limit)
        )
    )
    result: list[tuple[LegacyIssueAiChunk, float, str]] = []
    for chunk in rows:
        matched_specs = [
            spec for spec in token_specs if _keyword_present(chunk.search_text, spec.value)
        ]
        if not matched_specs:
            continue
        score = _keyword_score(chunk.search_text, token_specs)
        method = (
            "keyword"
            if any(spec.category in {"primary", "keyword"} for spec in matched_specs)
            else "supporting_keyword"
        )
        result.append((chunk, score, method))
    return result


def _partition_compatibility_predicate(
    column: Any,
    partition_ids: tuple[str, ...],
) -> Any:
    """Keep pre-expand NULL rows while enforcing server-resolved IDs for bound rows."""

    return or_(column.is_(None), column.in_(partition_ids))


def _full_text_candidates(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    revision_ids: tuple[str, ...],
    partition_ids: tuple[str, ...],
    plan: LegacyIssueAssistantSearchPlan,
    limit: int,
) -> list[tuple[LegacyIssueAiChunk, float, str]]:
    sql = sa_text(
        f"""
        SELECT id,
               ts_rank_cd(
                   to_tsvector('simple', coalesce(search_text, '')),
                   websearch_to_tsquery('simple', :query)
               ) AS score
        FROM legacy_issue_ai_chunks
        WHERE workspace_id = :workspace_id
          AND dataset_key IN :dataset_keys
          AND revision_id IN :revision_ids
          AND {_PARTITION_COMPATIBILITY_SQL}
          AND to_tsvector('simple', coalesce(search_text, ''))
              @@ websearch_to_tsquery('simple', :query)
        ORDER BY score DESC, updated_at DESC
        LIMIT :limit
        """
    ).bindparams(
        bindparam("dataset_keys", expanding=True),
        bindparam("revision_ids", expanding=True),
        bindparam(
            "partition_ids",
            expanding=True,
            type_=Uuid(as_uuid=False),
        ),
    )
    try:
        rows = db.execute(
            sql,
            {
                "workspace_id": workspace.id,
                "dataset_keys": dataset_keys,
                "revision_ids": revision_ids,
                "partition_ids": partition_ids,
                "query": plan.query,
                "limit": limit,
            },
        ).all()
    except SQLAlchemyError:
        return []
    return _chunks_for_scored_ids(
        db,
        rows,
        method="fulltext",
        partition_ids=partition_ids,
    )


def _trigram_candidates(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    revision_ids: tuple[str, ...],
    partition_ids: tuple[str, ...],
    plan: LegacyIssueAssistantSearchPlan,
    limit: int,
) -> list[tuple[LegacyIssueAiChunk, float, str]]:
    sql = sa_text(
        f"""
        SELECT id, similarity(lower(search_text), lower(:query)) AS score
        FROM legacy_issue_ai_chunks
        WHERE workspace_id = :workspace_id
          AND dataset_key IN :dataset_keys
          AND revision_id IN :revision_ids
          AND {_PARTITION_COMPATIBILITY_SQL}
          AND similarity(lower(search_text), lower(:query)) > 0.06
        ORDER BY score DESC, updated_at DESC
        LIMIT :limit
        """
    ).bindparams(
        bindparam("dataset_keys", expanding=True),
        bindparam("revision_ids", expanding=True),
        bindparam(
            "partition_ids",
            expanding=True,
            type_=Uuid(as_uuid=False),
        ),
    )
    try:
        rows = db.execute(
            sql,
            {
                "workspace_id": workspace.id,
                "dataset_keys": dataset_keys,
                "revision_ids": revision_ids,
                "partition_ids": partition_ids,
                "query": plan.query,
                "limit": limit,
            },
        ).all()
    except SQLAlchemyError:
        return []
    return _chunks_for_scored_ids(
        db,
        rows,
        method="trigram",
        partition_ids=partition_ids,
    )


def _term_index_candidates(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    revision_ids: tuple[str, ...],
    partition_ids: tuple[str, ...],
    plan: LegacyIssueAssistantSearchPlan,
    limit: int,
) -> list[tuple[LegacyIssueAiChunk, float, str]]:
    terms = _candidate_search_terms(plan)
    if not terms:
        return []
    placeholders = ", ".join(f":term_{index}" for index, _term in enumerate(terms))
    sql = sa_text(
        f"""
        SELECT id
        FROM legacy_issue_ai_chunks
        WHERE workspace_id = :workspace_id
          AND dataset_key IN :dataset_keys
          AND revision_id IN :revision_ids
          AND {_PARTITION_COMPATIBILITY_SQL}
          AND search_terms IS NOT NULL
          AND search_terms ?| ARRAY[{placeholders}]
        ORDER BY updated_at DESC
        LIMIT :limit
        """
    ).bindparams(
        bindparam("dataset_keys", expanding=True),
        bindparam("revision_ids", expanding=True),
        bindparam(
            "partition_ids",
            expanding=True,
            type_=Uuid(as_uuid=False),
        ),
    )
    params: dict[str, Any] = {
        "workspace_id": workspace.id,
        "dataset_keys": dataset_keys,
        "revision_ids": revision_ids,
        "partition_ids": partition_ids,
        "limit": limit,
    }
    for index, term in enumerate(terms):
        params[f"term_{index}"] = term
    try:
        rows = db.execute(sql, params).all()
    except SQLAlchemyError:
        return []
    chunks_by_id = {
        chunk.id: chunk
        for chunk in db.scalars(
            select(LegacyIssueAiChunk).where(
                LegacyIssueAiChunk.id.in_(tuple(row.id for row in rows)),
                _partition_compatibility_predicate(
                    LegacyIssueAiChunk.retrieval_partition_id,
                    partition_ids,
                ),
            )
        )
    }
    result: list[tuple[LegacyIssueAiChunk, float, str]] = []
    for row in rows:
        chunk = chunks_by_id.get(row.id)
        if chunk is None:
            continue
        result.append((chunk, _term_index_score(chunk, terms), "term_index"))
    return result


def _pgvector_candidates(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    revision_ids: tuple[str, ...],
    partition_ids: tuple[str, ...],
    query_embedding: list[float],
    limit: int,
) -> list[tuple[LegacyIssueAiChunk, float, str]]:
    query_vector = _pgvector_literal(query_embedding)
    if not query_vector:
        return []
    dimension = _validated_vector_dimension(len(query_embedding))
    sql = sa_text(
        f"""
        SELECT id,
               greatest(0, 1 - (embedding_vector::vector({dimension}) <=> CAST(:query_embedding AS vector({dimension})))) AS score
        FROM legacy_issue_ai_chunks
        WHERE workspace_id = :workspace_id
          AND dataset_key IN :dataset_keys
          AND revision_id IN :revision_ids
          AND {_PARTITION_COMPATIBILITY_SQL}
          AND embedding_status = 'embedded'
          AND embedding_vector IS NOT NULL
          AND embedding_dimensions = :embedding_dimensions
        ORDER BY embedding_vector::vector({dimension}) <=> CAST(:query_embedding AS vector({dimension})), updated_at DESC
        LIMIT :limit
        """
    ).bindparams(
        bindparam("dataset_keys", expanding=True),
        bindparam("revision_ids", expanding=True),
        bindparam(
            "partition_ids",
            expanding=True,
            type_=Uuid(as_uuid=False),
        ),
    )
    try:
        rows = db.execute(
            sql,
            {
                "workspace_id": workspace.id,
                "dataset_keys": dataset_keys,
                "revision_ids": revision_ids,
                "partition_ids": partition_ids,
                "query_embedding": query_vector,
                "embedding_dimensions": dimension,
                "limit": limit,
            },
        ).all()
    except SQLAlchemyError:
        return []
    return _chunks_for_scored_ids(
        db,
        rows,
        method="pgvector",
        partition_ids=partition_ids,
    )


def _chunks_for_scored_ids(
    db: Session,
    rows: list[Any],
    *,
    method: str,
    partition_ids: tuple[str, ...],
) -> list[tuple[LegacyIssueAiChunk, float, str]]:
    ids = [row.id for row in rows]
    if not ids:
        return []
    chunks_by_id = {
        chunk.id: chunk
        for chunk in db.scalars(
            select(LegacyIssueAiChunk).where(
                LegacyIssueAiChunk.id.in_(ids),
                _partition_compatibility_predicate(
                    LegacyIssueAiChunk.retrieval_partition_id,
                    partition_ids,
                ),
            )
        )
    }
    result: list[tuple[LegacyIssueAiChunk, float, str]] = []
    for row in rows:
        chunk = chunks_by_id.get(row.id)
        if chunk is None:
            continue
        result.append((chunk, float(row.score or 0.0), method))
    return result


def _merge_candidate(
    candidates: dict[str, _Candidate],
    *,
    chunk: LegacyIssueAiChunk,
    score: float,
    method: str,
) -> None:
    current = candidates.get(chunk.id)
    if current is None:
        candidates[chunk.id] = _Candidate(chunk=chunk, methods={method}, score=max(score, 0.0))
        return
    current.methods.add(method)
    current.score = max(current.score, score)


def _merge_related_field_candidates(
    db: Session,
    candidates: dict[str, _Candidate],
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    revision_ids: tuple[str, ...],
    partition_ids: tuple[str, ...],
    plan: LegacyIssueAssistantSearchPlan,
    limit: int,
    candidate_record_authorizer: CandidateRecordAuthorizer | None = None,
) -> bool:
    if not plan.related_field_expansions or not candidates:
        return False
    seed_record_ids = _seed_record_ids_for_related_field_search(candidates)
    if not seed_record_ids:
        return False
    seed_records = {
        record.id: record
        for record in db.scalars(
            select(LegacyIssueRecord).where(
                LegacyIssueRecord.id.in_(seed_record_ids),
                LegacyIssueRecord.workspace_id == workspace.id,
                _partition_compatibility_predicate(
                    LegacyIssueRecord.retrieval_partition_id,
                    partition_ids,
                ),
            )
        )
    }
    related_record_ids: list[str] = []
    for field_key in plan.related_field_expansions:
        terms = _related_field_terms(
            [
                str((record.field_values or {}).get(field_key) or "")
                for record in seed_records.values()
            ]
        )
        if not terms:
            continue
        where_terms = " OR ".join(
            f"(field_values ->> :field_key) ILIKE :term_{index}"
            for index, _term in enumerate(terms)
        )
        sql = sa_text(
            f"""
            SELECT id
            FROM legacy_issue_records
            WHERE workspace_id = :workspace_id
              AND dataset_key IN :dataset_keys
              AND revision_id IN :revision_ids
              AND {_PARTITION_COMPATIBILITY_SQL}
              AND ({where_terms})
            ORDER BY updated_at DESC, created_at DESC
            LIMIT :limit
            """
        ).bindparams(
            bindparam("dataset_keys", expanding=True),
            bindparam("revision_ids", expanding=True),
            bindparam(
                "partition_ids",
                expanding=True,
                type_=Uuid(as_uuid=False),
            ),
        )
        params: dict[str, Any] = {
            "workspace_id": workspace.id,
            "dataset_keys": dataset_keys,
            "revision_ids": revision_ids,
            "partition_ids": partition_ids,
            "field_key": field_key,
            "limit": limit,
        }
        for index, term in enumerate(terms):
            params[f"term_{index}"] = f"%{term}%"
        try:
            related_record_ids.extend(row.id for row in db.execute(sql, params).all() if row.id)
        except SQLAlchemyError:
            continue
    related_record_ids = list(dict.fromkeys(related_record_ids))
    if candidate_record_authorizer is not None and related_record_ids:
        related_record_ids = [
            record_id
            for record_id in related_record_ids
            if record_id
            in candidate_record_authorizer(tuple(related_record_ids))
        ]
    if not related_record_ids:
        return False
    chunks = list(
        db.scalars(
            select(LegacyIssueAiChunk)
            .where(
                LegacyIssueAiChunk.workspace_id == workspace.id,
                LegacyIssueAiChunk.dataset_key.in_(dataset_keys),
                LegacyIssueAiChunk.revision_id.in_(revision_ids),
                _partition_compatibility_predicate(
                    LegacyIssueAiChunk.retrieval_partition_id,
                    partition_ids,
                ),
                LegacyIssueAiChunk.record_id.in_(related_record_ids),
                LegacyIssueAiChunk.chunk_key == SUMMARY_CHUNK_KEY,
            )
            .limit(limit)
        )
    )
    changed = False
    seed_set = set(seed_record_ids)
    for chunk in chunks:
        score = 0.95 if chunk.record_id in seed_set else 0.55
        _merge_candidate(candidates, chunk=chunk, score=score, method="related_field")
        changed = True
    return changed


def _retain_authorized_candidates(
    candidates: dict[str, _Candidate],
    *,
    authorizer: CandidateRecordAuthorizer | None,
) -> None:
    """Apply final record ACL before related expansion and external reranking."""

    if authorizer is None or not candidates:
        return
    record_ids = tuple(
        dict.fromkeys(candidate.chunk.record_id for candidate in candidates.values())
    )
    allowed_ids = authorizer(record_ids)
    for chunk_id, candidate in tuple(candidates.items()):
        if candidate.chunk.record_id not in allowed_ids:
            del candidates[chunk_id]


def _seed_record_ids_for_related_field_search(
    candidates: dict[str, _Candidate],
) -> tuple[str, ...]:
    grouped: dict[str, list[_Candidate]] = defaultdict(list)
    for candidate in candidates.values():
        grouped[candidate.chunk.record_id].append(candidate)
    ranked = sorted(
        grouped.items(),
        key=lambda item: sum(candidate.score for candidate in item[1]),
        reverse=True,
    )
    record_ids: list[str] = []
    for record_id, record_candidates in ranked:
        if len(record_ids) >= 8:
            break
        methods = {method for candidate in record_candidates for method in candidate.methods}
        if "keyword" not in methods and "fulltext" not in methods:
            continue
        record_ids.append(record_id)
    return tuple(record_ids)


def _related_field_terms(raw_values: list[str]) -> tuple[str, ...]:
    terms: list[str] = []
    for raw_value in raw_values:
        for part in re.split(r"[\n\r,;]+", raw_value):
            term = re.sub(r"\s+", " ", part).strip()
            if len(term) < 2 or term.startswith("("):
                continue
            terms.append(term)
    return tuple(_unique_limited(terms, max_items=12, max_length=40))


def _rerank_candidates(
    candidates: dict[str, _Candidate],
    *,
    query: str,
    limit: int,
) -> bool:
    if not candidates:
        return False
    try:
        rerank_client = _legacy_rerank_client()
    except Exception:
        return False
    if rerank_client is None:
        return False
    ranked = sorted(candidates.values(), key=lambda item: item.score, reverse=True)[:limit]
    hits = [_candidate_hit(candidate) for candidate in ranked]
    try:
        reranked = rerank_client.rerank(
            query=query,
            hits=hits,
            timeout_seconds=max(get_settings().rag_query_timeout_ms / 1000, 1.0),
        )
    except Exception:
        return False
    total = max(len(reranked), 1)
    for rank, hit in enumerate(reranked, start=1):
        candidate = candidates.get(hit.chunk_id)
        if candidate is None:
            continue
        rank_boost = 0.25 * ((total - rank + 1) / total)
        if isfinite(rank_boost):
            candidate.score += rank_boost
        candidate.methods.add("rerank")
    return True


def _apply_planner_hint_boosts(
    candidates: dict[str, _Candidate],
    *,
    plan: LegacyIssueAssistantSearchPlan,
    token_specs: tuple[_WeightedToken, ...],
) -> None:
    if not candidates:
        return
    field_hints = {hint.casefold() for hint in plan.field_hints if hint.strip()}
    for candidate in candidates.values():
        chunk = candidate.chunk
        text = chunk.field_value or chunk.search_text
        keyword_boost = sum(
            spec.weight * 0.75 for spec in token_specs if _keyword_present(text, spec.value)
        )
        if keyword_boost:
            candidate.score += min(2.0, keyword_boost)
        field_values = {
            value.casefold()
            for value in (chunk.field_key, chunk.field_label, chunk.chunk_key)
            if value
        }
        if field_hints and field_hints.intersection(field_values):
            candidate.score += 0.35


def _candidate_hit(candidate: _Candidate) -> RagVectorSearchHit:
    chunk = candidate.chunk
    metadata = {
        "dataset_key": chunk.dataset_key,
        "revision_id": chunk.revision_id,
        "record_id": chunk.record_id,
        "stable_record_id": chunk.stable_record_id,
        "field_key": chunk.field_key,
        "field_label": chunk.field_label,
        "chunk_key": chunk.chunk_key,
        "chunk_kind": chunk.chunk_kind,
        "attachment_id": chunk.attachment_id,
        "attachment_filename": chunk.attachment_filename,
        "attachment_page": chunk.attachment_page,
        "attachment_artifact_type": chunk.attachment_artifact_type,
    }
    return RagVectorSearchHit(
        chunk_id=chunk.id,
        text=chunk.search_text,
        summary=_compact_text(chunk.field_value or chunk.search_text, limit=500),
        score=candidate.score,
        metadata=metadata,
        projection=RagProjection(
            workspace_id=chunk.workspace_id,
            resource_type=LEGACY_ISSUE_RAG_RESOURCE_TYPE,
            resource_id=chunk.record_id,
            source_kind=LEGACY_ISSUE_RAG_SOURCE_KIND,
            title=str((chunk.evidence_metadata or {}).get("record_label") or chunk.record_id),
            summary=_compact_text(chunk.search_text, limit=500),
            metadata=metadata,
        ),
    )


def _merge_evidence(
    candidates: dict[str, _Candidate],
    *,
    revisions_by_dataset_key: dict[str, list[LegacyIssueDataRevision]],
    limit: int,
) -> list[LegacyIssueEvidence]:
    revisions_by_id = {
        revision.id: revision
        for dataset_revisions in revisions_by_dataset_key.values()
        for revision in dataset_revisions
    }
    grouped: dict[str, list[_Candidate]] = defaultdict(list)
    for candidate in candidates.values():
        grouped[candidate.chunk.record_id].append(candidate)
    ranked_records = sorted(
        grouped.items(),
        key=lambda item: _record_score(item[1]),
        reverse=True,
    )
    evidence: list[LegacyIssueEvidence] = []
    for index, (_record_id, record_candidates) in enumerate(ranked_records[:limit], start=1):
        chunk = record_candidates[0].chunk
        definition = DATASET_DEFINITIONS.get(chunk.dataset_key)
        if definition is None:
            continue
        values = _record_values_from_chunk_metadata(chunk)
        label = _record_label_from_values(values, chunk.stable_record_id or chunk.record_id)
        matched_chunks = tuple(
            _matched_chunk(candidate)
            for candidate in sorted(record_candidates, key=lambda item: item.score, reverse=True)[
                :5
            ]
        )
        methods = tuple(
            sorted({method for candidate in record_candidates for method in candidate.methods})
        )
        matched_fields = tuple(
            sorted(
                {matched.field_key for matched in matched_chunks if matched.field_key is not None}
            )
        )
        revision = revisions_by_id.get(chunk.revision_id)
        evidence.append(
            LegacyIssueEvidence(
                evidence_id=f"E{index}",
                dataset_key=chunk.dataset_key,
                dataset_title=definition.title_ko,
                revision_id=chunk.revision_id,
                revision_no=revision.revision_no if revision else None,
                record_id=chunk.record_id,
                stable_record_id=chunk.stable_record_id,
                label=label,
                values=values,
                matched_fields=matched_fields,
                matched_chunks=matched_chunks,
                score=round(_record_score(record_candidates), 4),
                methods=methods,
            )
        )
    return evidence


def _record_score(candidates: list[_Candidate]) -> float:
    scores = sorted((max(candidate.score, 0.0) for candidate in candidates), reverse=True)
    if not scores:
        return 0.0
    diversity_boost = sum(min(score, 0.25) for score in scores[1:4])
    return scores[0] + diversity_boost


def _matched_chunk(candidate: _Candidate) -> LegacyIssueMatchedChunk:
    chunk = candidate.chunk
    return LegacyIssueMatchedChunk(
        chunk_id=chunk.id,
        chunk_key=chunk.chunk_key,
        chunk_kind=chunk.chunk_kind,
        field_key=chunk.field_key,
        field_label=chunk.field_label,
        field_value=chunk.field_value,
        attachment_id=chunk.attachment_id,
        attachment_filename=chunk.attachment_filename,
        attachment_page=chunk.attachment_page,
        attachment_artifact_type=chunk.attachment_artifact_type,
        excerpt=_excerpt(chunk.field_value or chunk.search_text),
        methods=tuple(sorted(candidate.methods)),
        score=round(candidate.score, 4),
    )


def _record_values_from_chunk_metadata(chunk: LegacyIssueAiChunk) -> dict[str, str]:
    record = getattr(chunk, "_legacy_issue_record", None)
    if isinstance(record, LegacyIssueRecord):
        return {key: str(value) for key, value in (record.field_values or {}).items()}
    db_record = chunk.record if hasattr(chunk, "record") else None
    if isinstance(db_record, LegacyIssueRecord):
        return {key: str(value) for key, value in (db_record.field_values or {}).items()}
    return {}


def attach_record_values_to_evidence(
    db: Session, evidence: list[LegacyIssueEvidence]
) -> list[LegacyIssueEvidence]:
    record_ids = [item.record_id for item in evidence]
    if not record_ids:
        return evidence
    records_by_id = {
        record.id: record
        for record in db.scalars(
            select(LegacyIssueRecord).where(LegacyIssueRecord.id.in_(record_ids))
        )
    }
    matched_attachment_ids = {
        chunk.attachment_id
        for item in evidence
        for chunk in item.matched_chunks
        if chunk.attachment_id
    }
    attachments_by_id = (
        {
            attachment.id: attachment
            for attachment in db.scalars(
                select(LegacyIssueAttachment).where(
                    LegacyIssueAttachment.id.in_(tuple(matched_attachment_ids))
                )
            )
        }
        if matched_attachment_ids
        else {}
    )
    updated: list[LegacyIssueEvidence] = []
    for item in evidence:
        record = records_by_id.get(item.record_id)
        values = (
            {key: str(value) for key, value in (record.field_values or {}).items()}
            if record
            else item.values
        )
        updated.append(
            LegacyIssueEvidence(
                evidence_id=item.evidence_id,
                dataset_key=item.dataset_key,
                dataset_title=item.dataset_title,
                revision_id=item.revision_id,
                revision_no=item.revision_no,
                record_id=item.record_id,
                stable_record_id=item.stable_record_id,
                label=_record_label_from_values(values, item.stable_record_id or item.record_id),
                values=values,
                matched_fields=item.matched_fields,
                matched_chunks=item.matched_chunks,
                score=item.score,
                methods=item.methods,
                attachments=_evidence_attachments(
                    item,
                    attachments_by_id=attachments_by_id,
                ),
            )
        )
    return updated


def _evidence_attachments(
    item: LegacyIssueEvidence,
    *,
    attachments_by_id: dict[str, LegacyIssueAttachment],
) -> tuple[LegacyIssueEvidenceAttachment, ...]:
    chunks_by_attachment_id: dict[str, list[LegacyIssueMatchedChunk]] = defaultdict(list)
    for chunk in item.matched_chunks:
        if chunk.attachment_id:
            chunks_by_attachment_id[chunk.attachment_id].append(chunk)
    evidence_attachments: list[LegacyIssueEvidenceAttachment] = []
    for attachment_id, chunks in chunks_by_attachment_id.items():
        attachment = attachments_by_id.get(attachment_id)
        if attachment is None:
            continue
        methods = tuple(sorted({method for chunk in chunks for method in chunk.methods}))
        score = max((chunk.score for chunk in chunks), default=0.0)
        evidence_attachments.append(
            LegacyIssueEvidenceAttachment(
                id=attachment.id,
                filename=attachment.filename,
                description=attachment.description,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                index_status=attachment.index_status,
                indexed_at=attachment.indexed_at,
                matched_chunks=tuple(sorted(chunks, key=lambda chunk: chunk.score, reverse=True)),
                score=round(score, 4),
                methods=methods,
            )
        )
    return tuple(sorted(evidence_attachments, key=lambda item: item.score, reverse=True))


def _embed_query(query: str) -> list[float] | None:
    settings = get_settings()
    try:
        return _legacy_embedding_client().embed_query(
            query,
            timeout_seconds=max(settings.rag_query_timeout_ms / 1000, 1.0),
        )
    except Exception:
        return None


def _embedding_available() -> bool:
    try:
        return _legacy_embedding_client().healthcheck().ready
    except Exception:
        return False


def _current_embedding_dimensions() -> int:
    try:
        return len(_legacy_embedding_client().embed_query("__legacy_issue_dimension_probe__"))
    except Exception:
        return get_legacy_issue_settings().ai_embedding_dimensions


def _legacy_embedding_client():
    return RagProviderFactory(get_settings()).build_embedding()


def _legacy_rerank_client():
    return RagProviderFactory(get_settings()).build_rerank()


def _pgvector_literal(embedding: list[float]) -> str | None:
    values: list[str] = []
    for item in embedding:
        value = float(item)
        if not isfinite(value):
            return None
        values.append(f"{value:.8g}")
    return "[" + ",".join(values) + "]" if values else None


def _validated_vector_dimension(dimension: int) -> int:
    if dimension < 1 or dimension > 4096:
        raise ValueError(f"Unsupported embedding dimension for pgvector search: {dimension}")
    return dimension


def _pg_extension_available(db: Session, extension_name: str) -> bool:
    if not _is_postgres(db):
        return False
    try:
        return bool(
            db.execute(
                sa_text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_available_extensions
                        WHERE name = :extension_name
                    )
                    """
                ),
                {"extension_name": extension_name},
            ).scalar()
        )
    except SQLAlchemyError:
        return False


def _pg_index_available(db: Session, index_name: str) -> bool:
    if not _is_postgres(db):
        return False
    try:
        return bool(
            db.execute(
                sa_text("SELECT to_regclass(:index_name) IS NOT NULL"),
                {"index_name": index_name},
            ).scalar()
        )
    except SQLAlchemyError:
        return False


def _is_postgres(db: Session) -> bool:
    return db.bind is not None and db.bind.dialect.name == "postgresql"


def _should_create_field_chunk(field_key: str, value: str) -> bool:
    normalized_key = field_key.lower()
    if any(hint in normalized_key for hint in LONG_FIELD_HINTS):
        return True
    return len(value) >= 80


def _record_label(record: LegacyIssueRecord, values: dict[str, str]) -> str:
    return _record_label_from_values(values, record.stable_record_id or record.id)


def _record_label_from_values(values: dict[str, str], fallback: str) -> str:
    for key in (
        "legacy_issue_number",
        "issue_no",
        "row_no",
        "problem",
        "symptom",
        "defect_type",
        "item",
    ):
        value = values.get(key)
        if value:
            return _compact_text(value, limit=120)
    return fallback


def _candidate_token_specs(plan: LegacyIssueAssistantSearchPlan) -> tuple[_WeightedToken, ...]:
    specs: list[_WeightedToken] = []

    def add_tokens(tokens: tuple[str, ...], *, weight: float, category: str) -> None:
        for token in tokens:
            if not _usable_exact_token(token):
                continue
            specs.append(_WeightedToken(value=token, weight=weight, category=category))

    if plan.primary_keywords:
        add_tokens(plan.primary_keywords, weight=1.0, category="primary")
    elif plan.keywords:
        add_tokens(plan.keywords, weight=0.8, category="keyword")
    else:
        add_tokens(plan.supporting_keywords, weight=0.35, category="supporting")

    deduped: dict[str, _WeightedToken] = {}
    for spec in specs:
        key = spec.value.casefold()
        current = deduped.get(key)
        if current is None or spec.weight > current.weight:
            deduped[key] = spec
    return tuple(list(deduped.values())[:24])


def _candidate_search_terms(plan: LegacyIssueAssistantSearchPlan) -> tuple[str, ...]:
    source_terms = _unique_limited(
        [
            *plan.primary_keywords,
            *plan.keywords,
            *plan.supporting_keywords,
            plan.query,
        ],
        max_items=24,
        max_length=120,
    )
    terms: list[str] = []
    seen: set[str] = set()
    for source in source_terms:
        for term in build_legacy_issue_search_terms(source):
            if term in seen or not _usable_search_term(term):
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= 48:
                return tuple(terms)
    return tuple(terms)


def _term_index_score(chunk: LegacyIssueAiChunk, terms: tuple[str, ...]) -> float:
    indexed_terms = {
        str(term).casefold() for term in (chunk.search_terms or []) if str(term).strip()
    }
    if not indexed_terms:
        return 0.0
    hits = [term for term in terms if term in indexed_terms]
    exact_hits = [term for term in terms if _keyword_present(chunk.search_text, term)]
    attachment_boost = 0.2 if chunk.attachment_id else 0.0
    return min(1.8, len(hits) * 0.2 + len(exact_hits) * 0.25 + attachment_boost)


def _usable_search_term(term: str) -> bool:
    if ASCII_WORD_RE.fullmatch(term):
        return len(term) >= 3 or _looks_like_compact_code(term)
    return len(term) >= 2


def _discriminative_token_specs(
    db: Session,
    *,
    workspace: Workspace,
    dataset_keys: tuple[str, ...],
    revision_ids: tuple[str, ...],
    partition_ids: tuple[str, ...],
    plan: LegacyIssueAssistantSearchPlan,
    result_limit: int,
) -> tuple[_WeightedToken, ...]:
    specs = _candidate_token_specs(plan)
    if not specs:
        return ()
    try:
        total_records = int(
            db.scalar(
                select(func.count(func.distinct(LegacyIssueAiChunk.record_id))).where(
                    LegacyIssueAiChunk.workspace_id == workspace.id,
                    LegacyIssueAiChunk.dataset_key.in_(dataset_keys),
                    LegacyIssueAiChunk.revision_id.in_(revision_ids),
                    _partition_compatibility_predicate(
                        LegacyIssueAiChunk.retrieval_partition_id,
                        partition_ids,
                    ),
                )
            )
            or 0
        )
    except SQLAlchemyError:
        return specs
    if total_records <= 0:
        return specs
    kept: list[_WeightedToken] = []
    for spec in specs:
        try:
            matched_records = int(
                db.scalar(
                    select(func.count(func.distinct(LegacyIssueAiChunk.record_id))).where(
                        LegacyIssueAiChunk.workspace_id == workspace.id,
                        LegacyIssueAiChunk.dataset_key.in_(dataset_keys),
                        LegacyIssueAiChunk.revision_id.in_(revision_ids),
                        _partition_compatibility_predicate(
                            LegacyIssueAiChunk.retrieval_partition_id,
                            partition_ids,
                        ),
                        LegacyIssueAiChunk.search_text.ilike(
                            _contains_like_pattern(spec.value),
                            escape="\\",
                        ),
                    )
                )
                or 0
            )
        except SQLAlchemyError:
            kept.append(spec)
            continue
        if matched_records <= _token_frequency_limit(
            total_records=total_records,
            result_limit=result_limit,
            spec=spec,
        ):
            kept.append(spec)
    return tuple(kept)


def _token_frequency_limit(
    *,
    total_records: int,
    result_limit: int,
    spec: _WeightedToken,
) -> int:
    if spec.category == "primary":
        return max(result_limit * 10, int(total_records * 0.30), 12)
    if spec.category == "supporting":
        return max(result_limit * 3, int(total_records * 0.04), 6)
    return max(result_limit * 6, int(total_records * 0.12), 8)


def _semantic_query(plan: LegacyIssueAssistantSearchPlan) -> str:
    weighted_terms = list(plan.primary_keywords)
    if not weighted_terms:
        weighted_terms = list(plan.keywords)
    if not weighted_terms:
        weighted_terms = list(plan.supporting_keywords)
    terms = _unique_limited(
        [
            plan.query,
            *weighted_terms,
            *plan.report_focus,
        ],
        max_items=24,
        max_length=120,
    )
    return " ".join(terms) or plan.query


def _keyword_score(text: str, token_specs: tuple[_WeightedToken, ...]) -> float:
    weighted_hits = sum(spec.weight for spec in token_specs if _keyword_present(text, spec.value))
    hits = sum(1 for spec in token_specs if _keyword_present(text, spec.value))
    return min(1.5, weighted_hits) + hits * 0.05


def _usable_exact_token(token: str) -> bool:
    normalized = token.strip()
    if not normalized:
        return False
    if ASCII_WORD_RE.fullmatch(normalized):
        return len(normalized) >= 4 or _looks_like_compact_code(normalized)
    return True


def _looks_like_compact_code(token: str) -> bool:
    if not (2 <= len(token) <= 8):
        return False
    has_letter = any(char.isalpha() for char in token)
    return has_letter and token.upper() == token


def _keyword_present(text: str, token: str) -> bool:
    normalized_token = token.strip()
    if not normalized_token:
        return False
    if ASCII_WORD_RE.fullmatch(normalized_token):
        return (
            re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(normalized_token)}(?![A-Za-z0-9_])",
                text,
                flags=re.IGNORECASE,
            )
            is not None
        )
    return normalized_token.casefold() in text.casefold()


def _contains_like_pattern(token: str) -> str:
    escaped = token.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _unique_limited(
    items: list[str] | tuple[str, ...],
    *,
    max_items: int,
    max_length: int,
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = " ".join(str(item).split()).strip()
        if not normalized:
            continue
        normalized = normalized[:max_length]
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= max_items:
            break
    return result


def _coerce_text_items(items: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if items is None:
        return []
    if isinstance(items, str):
        return [items]
    return [str(item) for item in items]


def _known_field_keys() -> set[str]:
    return {field.key for definition in DATASET_DEFINITIONS.values() for field in definition.fields}


def _compact_text(value: str, *, limit: int) -> str:
    compacted = re.sub(r"\s+", " ", value).strip()
    if len(compacted) <= limit:
        return compacted
    return compacted[: max(limit - 3, 0)].rstrip() + "..."


def _excerpt(value: str) -> str:
    return _compact_text(value, limit=360)
