from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.retrieval_contract import FILES_RETRIEVAL_ACTIVE
from open_work_hub_api.domains.rag.models import RagSyncJob
from open_work_hub_api.domains.retrieval.models import (
    RetrievalProjectionEvent,
    RetrievalProjectionHead,
)
from open_work_hub_api.domains.retrieval.runtime_binding import (
    PartitionedRetrievalRuntimeUnavailable,
    resolve_active_partitioned_generation_pair,
)
from open_work_hub_api.domains.search.models import SearchIndexJob
from open_work_hub_api.domains.search.schemas import SearchEntityType
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE

FileRagStatus = Literal[
    "disabled",
    "pending",
    "processing",
    "ready",
    "unsupported",
    "failed",
]


@dataclass(frozen=True)
class FileRagState:
    status: FileRagStatus
    updated_at: datetime | None


@dataclass(frozen=True)
class _JobState:
    status: str
    updated_at: datetime


def load_file_rag_states(
    db: Session,
    *,
    files: list[FileManagerFile],
) -> dict[str, FileRagState]:
    """Return the user-safe searchable state for a batch of Files rows.

    Extraction readiness alone is not sufficient: a file is ready only after
    both the vector RAG job and the keyword-search job have succeeded.
    """

    if not files:
        return {}
    if not FILES_RETRIEVAL_ACTIVE:
        return {file.id: FileRagState(status="disabled", updated_at=None) for file in files}

    file_ids = [file.id for file in files]
    rag_jobs = _latest_rag_upserts(db, file_ids=file_ids)
    search_jobs = _latest_search_upserts(db, file_ids=file_ids)
    generation_covered_file_ids = _generation_covered_file_ids(db, file_ids=file_ids)
    return {
        file.id: _derive_file_rag_state(
            file=file,
            rag_job=rag_jobs.get(file.id),
            search_job=search_jobs.get(file.id),
            generation_covered=file.id in generation_covered_file_ids,
        )
        for file in files
    }


def _derive_file_rag_state(
    *,
    file: FileManagerFile,
    rag_job: _JobState | None,
    search_job: _JobState | None,
    generation_covered: bool,
) -> FileRagState:
    updated_at = _latest_timestamp(
        file.extracted_at,
        rag_job.updated_at if rag_job else None,
        search_job.updated_at if search_job else None,
    )

    if file.extraction_status == "unsupported":
        return FileRagState(status="unsupported", updated_at=updated_at)
    if file.extraction_status == "failed":
        return FileRagState(status="failed", updated_at=updated_at)

    if rag_job is None:
        if search_job is None and file.extraction_status == "ready" and generation_covered:
            return FileRagState(status="ready", updated_at=updated_at)
        return FileRagState(status="pending", updated_at=updated_at)
    if rag_job.status == "pending":
        return FileRagState(status="pending", updated_at=updated_at)
    if rag_job.status == "processing":
        return FileRagState(status="processing", updated_at=updated_at)
    if rag_job.status in {"failed", "cancelled"}:
        return FileRagState(status="failed", updated_at=updated_at)

    if file.extraction_status != "ready":
        return FileRagState(status="processing", updated_at=updated_at)

    if search_job is None or search_job.status in {"pending", "processing"}:
        return FileRagState(status="processing", updated_at=updated_at)
    if search_job.status == "succeeded":
        return FileRagState(status="ready", updated_at=updated_at)
    return FileRagState(status="failed", updated_at=updated_at)


def _generation_covered_file_ids(
    db: Session,
    *,
    file_ids: list[str],
) -> set[str]:
    """Return current active projections proven present in both physical backends."""

    try:
        pair = resolve_active_partitioned_generation_pair(db)
    except PartitionedRetrievalRuntimeUnavailable:
        return set()

    replay_event_sequence = min(
        pair.opensearch_replay_event_sequence,
        pair.qdrant_replay_event_sequence,
    )
    if replay_event_sequence <= 0:
        return set()

    rows = db.scalars(
        select(RetrievalProjectionEvent.resource_id)
        .join(
            RetrievalProjectionHead,
            and_(
                RetrievalProjectionHead.resource_type == RetrievalProjectionEvent.resource_type,
                RetrievalProjectionHead.resource_id == RetrievalProjectionEvent.resource_id,
                RetrievalProjectionHead.projection_version
                == RetrievalProjectionEvent.projection_version,
                RetrievalProjectionHead.retrieval_partition_id
                == RetrievalProjectionEvent.retrieval_partition_id,
                RetrievalProjectionHead.desired_state == RetrievalProjectionEvent.desired_state,
                RetrievalProjectionHead.content_checksum
                == RetrievalProjectionEvent.content_checksum,
            ),
        )
        .join(
            FileManagerFile,
            and_(
                FileManagerFile.id == RetrievalProjectionEvent.resource_id,
                FileManagerFile.retrieval_partition_id
                == RetrievalProjectionEvent.retrieval_partition_id,
                FileManagerFile.extraction_content_checksum
                == RetrievalProjectionEvent.content_checksum,
            ),
        )
        .where(
            RetrievalProjectionEvent.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            RetrievalProjectionEvent.resource_id.in_(file_ids),
            RetrievalProjectionEvent.desired_state == "active",
            RetrievalProjectionEvent.event_sequence <= replay_event_sequence,
        )
    )
    return set(rows)


def _latest_rag_upserts(
    db: Session,
    *,
    file_ids: list[str],
) -> dict[str, _JobState]:
    rank = (
        func.row_number()
        .over(
            partition_by=RagSyncJob.resource_id,
            order_by=(
                RagSyncJob.created_at.desc(),
                RagSyncJob.id.desc(),
            ),
        )
        .label("row_rank")
    )
    ranked = (
        select(
            RagSyncJob.resource_id.label("file_id"),
            RagSyncJob.status,
            RagSyncJob.updated_at,
            rank,
        )
        .join(
            RetrievalProjectionHead,
            and_(
                RetrievalProjectionHead.resource_type == RagSyncJob.resource_type,
                RetrievalProjectionHead.resource_id == RagSyncJob.resource_id,
                RetrievalProjectionHead.projection_version == RagSyncJob.projection_version,
                RetrievalProjectionHead.retrieval_partition_id == RagSyncJob.retrieval_partition_id,
                RetrievalProjectionHead.desired_state == RagSyncJob.desired_state,
            ),
        )
        .where(
            RagSyncJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            RagSyncJob.resource_id.in_(file_ids),
            RagSyncJob.operation.in_(("upsert", "visibility_update")),
            RagSyncJob.desired_state == "active",
        )
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.file_id, ranked.c.status, ranked.c.updated_at).where(ranked.c.row_rank == 1)
    )
    return {row.file_id: _JobState(status=row.status, updated_at=row.updated_at) for row in rows}


def _latest_search_upserts(
    db: Session,
    *,
    file_ids: list[str],
) -> dict[str, _JobState]:
    rank = (
        func.row_number()
        .over(
            partition_by=SearchIndexJob.entity_id,
            order_by=(
                SearchIndexJob.created_at.desc(),
                SearchIndexJob.id.desc(),
            ),
        )
        .label("row_rank")
    )
    ranked = (
        select(
            SearchIndexJob.entity_id.label("file_id"),
            SearchIndexJob.status,
            SearchIndexJob.updated_at,
            rank,
        )
        .join(
            RetrievalProjectionHead,
            and_(
                RetrievalProjectionHead.resource_type == SearchIndexJob.resource_type,
                RetrievalProjectionHead.resource_id == SearchIndexJob.entity_id,
                RetrievalProjectionHead.projection_version == SearchIndexJob.projection_version,
                RetrievalProjectionHead.retrieval_partition_id
                == SearchIndexJob.retrieval_partition_id,
                RetrievalProjectionHead.desired_state == SearchIndexJob.desired_state,
            ),
        )
        .where(
            SearchIndexJob.entity_type == SearchEntityType.FILE.value,
            SearchIndexJob.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE,
            SearchIndexJob.entity_id.in_(file_ids),
            SearchIndexJob.operation == "upsert",
            SearchIndexJob.desired_state == "active",
        )
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.file_id, ranked.c.status, ranked.c.updated_at).where(ranked.c.row_rank == 1)
    )
    return {row.file_id: _JobState(status=row.status, updated_at=row.updated_at) for row in rows}


def _latest_timestamp(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


__all__ = ["FileRagState", "FileRagStatus", "load_file_rag_states"]
