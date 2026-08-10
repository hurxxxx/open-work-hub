from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.retrieval.models import RetrievalProjectionHead
from ai_do_api.domains.search.backend_contracts import KeywordSearchClient
from ai_do_api.domains.search.backend_contracts import KeywordSearchBackendError
from ai_do_api.domains.search.backend_factory import build_keyword_search_client
from ai_do_api.domains.search.models import SearchIndexJob
from ai_do_api.domains.search.outbox import enqueue_search_index_job
from ai_do_api.domains.search.default_projection_adapters import (
    ensure_search_projection_adapters_registered,
)
from ai_do_api.domains.search.projection_registry import get_search_projection_adapter
from ai_do_api.domains.search.projection_identity import (
    SearchProjectionIdentityError as SearchProjectionIdentityError,
    ensure_search_document_identity,
)
from ai_do_api.domains.search.projections import load_search_document
from ai_do_api.domains.search.schemas import SearchEntityType
from ai_do_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
)


class UnsupportedSearchEntityError(RuntimeError):
    pass


SEARCH_INDEX_PROCESSING_LEASE_SECONDS = 2100


def process_search_index_job(
    db: Session,
    job_id: str,
    *,
    client: KeywordSearchClient | None = None,
) -> str:
    job, claim_outcome = _claim_search_index_job(db, job_id)
    if claim_outcome == "missing":
        return "missing"
    if claim_outcome != "claimed" or job is None:
        return "ignored"

    versioned = _job_has_projection_fence(job)
    if not versioned:
        superseding = _latest_superseding_search_index_job(db, job)
        if superseding is not None:
            _cancel_superseded_search_index_job(
                db,
                job,
                superseding_job=superseding,
                phase="before_mutation",
            )
            return "superseded"

    search_client = client or _search_client()
    if job.operation == "delete":
        if versioned and not _lock_matching_projection_head(db, job):
            _cancel_projection_fenced_search_index_job(db, job)
            return "superseded"
        mutation_result = _delete_search_document(
            search_client,
            job=job,
            versioned=versioned,
        )
        if mutation_result == "superseded":
            _cancel_backend_superseded_search_index_job(db, job)
            return "superseded"
        result = "deleted"
    else:
        _ensure_search_projection_adapter(job.entity_type)
        document = load_search_document(db, entity_type=job.entity_type, entity_id=job.entity_id)
        if document is None:
            if versioned and not _lock_matching_projection_head(db, job):
                _cancel_projection_fenced_search_index_job(db, job)
                return "superseded"
            mutation_result = _delete_search_document(
                search_client,
                job=job,
                versioned=versioned,
            )
            if mutation_result == "superseded":
                _cancel_backend_superseded_search_index_job(db, job)
                return "superseded"
            result = "deleted_missing_projection"
        else:
            _ensure_search_document_matches_job(document, job)
            if versioned and not _lock_matching_projection_head(db, job):
                _cancel_projection_fenced_search_index_job(db, job)
                return "superseded"
            mutation_result = _upsert_search_document(
                search_client,
                document=document,
                job=job,
                versioned=versioned,
            )
            if mutation_result == "superseded":
                _cancel_backend_superseded_search_index_job(db, job)
                return "superseded"
            result = "upserted"

    if not versioned:
        superseding = _latest_superseding_search_index_job(db, job)
        if superseding is not None:
            if superseding.status == "succeeded" and not _job_has_projection_fence(superseding):
                enqueue_search_index_job(
                    db,
                    workspace_id=superseding.workspace_id,
                    entity_type=superseding.entity_type,
                    entity_id=superseding.entity_id,
                    operation=superseding.operation,
                    trace_context=superseding.trace_context,
                )
            _cancel_superseded_search_index_job(
                db,
                job,
                superseding_job=superseding,
                phase="after_mutation",
            )
            return "superseded"

    job.status = "succeeded"
    job.last_error = None
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(job)
    db.commit()
    return result


def _claim_search_index_job(
    db: Session,
    job_id: str,
) -> tuple[SearchIndexJob | None, str]:
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=SEARCH_INDEX_PROCESSING_LEASE_SECONDS)
    claimed = db.execute(
        update(SearchIndexJob)
        .where(
            SearchIndexJob.id == job_id,
            _search_index_claimable_clause(now=now, lease_cutoff=lease_cutoff),
        )
        .values(
            status="processing",
            attempts=SearchIndexJob.attempts + 1,
            last_error=None,
            next_retry_at=None,
            updated_at=now,
        )
    )
    db.commit()
    db.expire_all()
    if claimed.rowcount == 1:
        return db.get(SearchIndexJob, job_id), "claimed"

    existing = db.get(SearchIndexJob, job_id)
    if existing is None:
        return None, "missing"
    return existing, "ignored"


def _latest_superseding_search_index_job(
    db: Session,
    job: SearchIndexJob,
) -> SearchIndexJob | None:
    return db.scalar(
        select(SearchIndexJob)
        .where(
            SearchIndexJob.id != job.id,
            SearchIndexJob.workspace_id == job.workspace_id,
            SearchIndexJob.entity_type == job.entity_type,
            SearchIndexJob.entity_id == job.entity_id,
            SearchIndexJob.created_at > job.created_at,
            SearchIndexJob.status != "cancelled",
        )
        .order_by(SearchIndexJob.created_at.desc(), SearchIndexJob.id.desc())
        .limit(1)
    )


def _cancel_superseded_search_index_job(
    db: Session,
    job: SearchIndexJob,
    *,
    superseding_job: SearchIndexJob,
    phase: str,
) -> None:
    job.status = "cancelled"
    job.last_error = f"superseded_by:{superseding_job.id}:{phase}"
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(job)
    db.commit()


def _job_has_projection_fence(job: SearchIndexJob) -> bool:
    return any(
        value is not None
        for value in (
            job.resource_type,
            job.projection_event_sequence,
            job.projection_version,
            job.desired_state,
        )
    )


def _lock_matching_projection_head(db: Session, job: SearchIndexJob) -> bool:
    if (
        job.resource_type is None
        or job.projection_event_sequence is None
        or job.projection_version is None
        or job.retrieval_partition_id is None
        or job.desired_state is None
    ):
        return False
    expected_operation = "delete" if job.desired_state == "deleted" else "upsert"
    if job.operation != expected_operation:
        return False
    head = db.scalar(
        select(RetrievalProjectionHead)
        .where(
            RetrievalProjectionHead.resource_type == job.resource_type,
            RetrievalProjectionHead.resource_id == job.entity_id,
        )
        .with_for_update()
    )
    return bool(
        head is not None
        and head.projection_version == job.projection_version
        and head.retrieval_partition_id == job.retrieval_partition_id
        and head.desired_state == job.desired_state
    )


def _cancel_projection_fenced_search_index_job(db: Session, job: SearchIndexJob) -> None:
    job.status = "cancelled"
    job.last_error = "superseded_by_projection_head:before_mutation"
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(job)
    db.commit()


def _cancel_backend_superseded_search_index_job(db: Session, job: SearchIndexJob) -> None:
    job.status = "cancelled"
    job.last_error = "superseded_by_backend_version:after_head_fence"
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(job)
    db.commit()


def _upsert_search_document(
    client: KeywordSearchClient,
    *,
    document: dict[str, Any],
    job: SearchIndexJob,
    versioned: bool,
) -> str:
    if not versioned or not _uses_partitioned_keyword_generation(job):
        client.upsert_document(document)
        return "upserted"
    mutation = getattr(client, "upsert_partitioned_document", None)
    if not callable(mutation):
        raise KeywordSearchBackendError(
            "Versioned search jobs require a partitioned keyword mutation client"
        )
    return str(mutation(_document_with_projection_fence(document, job=job)))


def _delete_search_document(
    client: KeywordSearchClient,
    *,
    job: SearchIndexJob,
    versioned: bool,
) -> str:
    if not versioned or not _uses_partitioned_keyword_generation(job):
        client.delete_document(
            workspace_id=job.workspace_id,
            entity_type=job.entity_type,
            entity_id=job.entity_id,
        )
        return "deleted"
    mutation = getattr(client, "delete_partitioned_document", None)
    if not callable(mutation):
        raise KeywordSearchBackendError(
            "Versioned search jobs require a partitioned keyword mutation client"
        )
    if job.resource_type is None or job.projection_version is None:
        raise KeywordSearchBackendError(
            "Versioned search delete is missing its projection identity"
        )
    return str(
        mutation(
            resource_type=job.resource_type,
            resource_id=job.entity_id,
            projection_version=job.projection_version,
        )
    )


def _uses_partitioned_keyword_generation(job: SearchIndexJob) -> bool:
    """Keep projection ordering independent from source physical activation."""

    is_files_entity = job.entity_type == SearchEntityType.FILE.value
    is_files_resource = job.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
    if is_files_entity != is_files_resource:
        raise KeywordSearchBackendError(
            "Files keyword job entity and resource identities do not match"
        )
    return is_files_entity


def _document_with_projection_fence(
    document: dict[str, Any],
    *,
    job: SearchIndexJob,
) -> dict[str, Any]:
    if (
        job.resource_type is None
        or job.retrieval_partition_id is None
        or job.projection_version is None
    ):
        raise KeywordSearchBackendError(
            "Versioned search upsert is missing its projection identity"
        )
    return {
        **document,
        "resource_type": job.resource_type,
        "retrieval_partition_id": str(job.retrieval_partition_id),
        "projection_version": job.projection_version,
    }


def _search_index_claimable_clause(*, now: datetime, lease_cutoff: datetime):
    return or_(
        and_(
            SearchIndexJob.status == "pending",
            or_(SearchIndexJob.next_retry_at.is_(None), SearchIndexJob.next_retry_at <= now),
        ),
        and_(
            SearchIndexJob.status == "processing",
            SearchIndexJob.updated_at <= lease_cutoff,
        ),
    )


def _ensure_search_projection_adapter(entity_type: str) -> None:
    ensure_search_projection_adapters_registered()
    if get_search_projection_adapter(entity_type) is None:
        raise UnsupportedSearchEntityError(
            f"Search index entity_type lacks projection adapter: {entity_type}"
        )


def _ensure_search_document_matches_job(
    document: dict[str, Any],
    job: SearchIndexJob,
) -> None:
    ensure_search_document_identity(
        document,
        workspace_id=job.workspace_id,
        allowed_entity_types=(job.entity_type,),
        expected_entity_id=job.entity_id,
        context=f"job {job.id}",
    )


def _search_client() -> KeywordSearchClient:
    return build_keyword_search_client(get_settings())
