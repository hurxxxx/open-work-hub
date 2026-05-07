from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
import logging
import time

from opentelemetry.trace import SpanKind
from sqlalchemy import Engine, and_, create_engine, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ai_do_api.core.telemetry import start_as_current_span
from ai_do_api.domains.rag.contracts import RagJobStatus, RagSyncLane, RagSyncOperation
from ai_do_api.domains.docs.models import DocMeetingAccess
from ai_do_api.domains.docs.rag_sync import MEETING_VISIBILITY_SCOPE
from ai_do_api.domains.pms.models import Issue, IssueLabel, IssueUserAccess
from ai_do_api.domains.pms.rag_sync import (
    PMS_LABEL_RECOMPUTE_SCOPE,
    PMS_MEETING_VISIBILITY_SCOPE,
    PMS_MILESTONE_RECOMPUTE_SCOPE,
    PMS_TASK_LIST_RECOMPUTE_SCOPE,
)
from ai_do_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE, load_native_doc_projection
from ai_do_api.domains.rag.meeting_projection import MEETING_RESOURCE_TYPE, load_meeting_projection
from ai_do_api.domains.rag.metrics import (
    record_sync_job_lag,
    record_sync_job_result,
    record_sync_queue_depth,
)
from ai_do_api.domains.rag.models import RagSyncJob, RagVisibilityRecomputeJob
from ai_do_api.domains.rag.outbox import enqueue_rag_sync_job
from ai_do_api.domains.rag.planner_projection import (
    PLANNER_EVENT_RESOURCE_TYPE,
    load_planner_event_projection,
)
from ai_do_api.domains.rag.pms_projection import (
    PMS_ISSUE_RESOURCE_TYPE,
    load_issue_projection,
)
from ai_do_api.domains.rag.providers import (
    RagProviderConfigurationError,
    RagProviderError,
    RagProviderTimeoutError,
    RagProviderTransientError,
)
from ai_do_api.domains.rag.providers.base import RagProviderBundle
from ai_do_api.domains.rag.runtime import build_provider_bundle, resolve_default_collection_name
from ai_do_api.domains.rag.service import RagService
from ai_do_api.domains.rag.telemetry import rag_span_attributes
from ai_do_api.domains.meeting.models import Meeting, MeetingDocLink, MeetingTaskLink
from ai_do_worker.celery_app import celery_app
from ai_do_worker.settings import get_settings


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.postgres_dsn, pool_pre_ping=True)


@lru_cache(maxsize=1)
def _session_factory():
    return sessionmaker(bind=_engine(), class_=Session)


def _db_session() -> Session:
    return _session_factory()()


@lru_cache(maxsize=1)
def _provider_bundle() -> RagProviderBundle:
    return build_provider_bundle(get_settings())


@lru_cache(maxsize=1)
def _rag_service() -> RagService:
    settings = get_settings()
    providers = _provider_bundle()
    return RagService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        ocr_client=providers.ocr,
        rerank_client=providers.rerank,
        default_collection=resolve_default_collection_name(settings),
    )


def _job_lag_ms(created_at: datetime) -> int:
    now = datetime.now(UTC).replace(tzinfo=None)
    return max(int((now - created_at).total_seconds() * 1000), 0)


@celery_app.task(
    name="rag.sync_resource",
    bind=True,
    acks_late=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_resource(self, job_id: str) -> str:
    return _run_sync_job(
        task=self,
        job_id=job_id,
        span_name="rag.sync_resource",
        job_kind="resource_sync",
    )


@celery_app.task(
    name="rag.sync_backfill_resource",
    bind=True,
    acks_late=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def sync_backfill_resource(self, job_id: str) -> str:
    settings = get_settings()
    return _run_sync_job(
        task=self,
        job_id=job_id,
        span_name="rag.sync_backfill_resource",
        job_kind="backfill_sync",
        batch_size=settings.rag_backfill_batch_size,
        throttle_ms=settings.rag_backfill_throttle_ms,
        drain_lane=RagSyncLane.BACKFILL.value,
    )


def _run_sync_job(
    *,
    task,
    job_id: str,
    span_name: str,
    job_kind: str,
    batch_size: int = 1,
    throttle_ms: int = 0,
    drain_lane: str | None = None,
) -> str:
    settings = get_settings()
    session = _db_session()
    try:
        job, claim_outcome = _claim_sync_job(session, job_id)
        if claim_outcome == "missing":
            logger.warning("RAG sync job not found: %s", job_id)
            record_sync_job_result(status="missing", job_kind=job_kind)
            return "missing"
        if claim_outcome != "claimed" or job is None:
            logger.info("Ignoring RAG sync job already claimed or closed: %s", job_id)
            record_sync_job_result(status="ignored", job_kind=job_kind)
            return "ignored"
        result = _execute_sync_job(
            session,
            task=task,
            job=job,
            span_name=span_name,
            job_kind=job_kind,
            rag_enabled=settings.rag_enabled,
        )
        if drain_lane is None or batch_size <= 1:
            return result

        drained = 1
        while drained < batch_size:
            next_job = _claim_next_sync_job(session, lane=drain_lane)
            if next_job is None:
                break
            if throttle_ms > 0:
                time.sleep(throttle_ms / 1000)
            _execute_sync_job(
                session,
                task=task,
                job=next_job,
                span_name=span_name,
                job_kind=job_kind,
                rag_enabled=settings.rag_enabled,
            )
            drained += 1
        return result
    finally:
        session.close()


def _execute_sync_job(
    session: Session,
    *,
    task,
    job: RagSyncJob,
    span_name: str,
    job_kind: str,
    rag_enabled: bool,
) -> str:
    record_sync_job_lag(
        lag_ms=_job_lag_ms(job.created_at),
        workspace_id=job.workspace_id,
        resource_type=job.resource_type,
        resource_id=job.resource_id,
        operation=job.operation,
        job_lane=job.lane,
        job_kind=job_kind,
    )
    with start_as_current_span(
        tracer_name="ai_do_worker.rag",
        span_name=span_name,
        kind=SpanKind.CONSUMER,
        parent_trace_context=job.trace_context,
        attributes=rag_span_attributes(
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_id=job.id,
            job_lane=job.lane,
        ),
    ):
        if not rag_enabled:
            logger.info("Skipping RAG sync because RAG is disabled: %s", job.id)
            record_sync_job_result(
                workspace_id=job.workspace_id,
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                operation=job.operation,
                job_lane=job.lane,
                status="disabled",
                job_kind=job_kind,
            )
            _mark_sync_job(session, job, status=RagJobStatus.CANCELLED.value)
            return "disabled"
        try:
            result = _process_sync_job(session, job)
            record_sync_job_result(
                status=result,
                workspace_id=job.workspace_id,
                resource_type=job.resource_type,
                resource_id=job.resource_id,
                operation=job.operation,
                job_lane=job.lane,
                job_kind=job_kind,
            )
            final_status = (
                RagJobStatus.CANCELLED.value
                if result == "unsupported_resource_type"
                else RagJobStatus.SUCCEEDED.value
            )
            _mark_sync_job(session, job, status=final_status)
            return result
        except Exception as error:
            return _handle_sync_job_failure(
                session,
                task=task,
                job=job,
                error=error,
                job_kind=job_kind,
            )


@celery_app.task(
    name="rag.recompute_visibility",
    bind=True,
    acks_late=True,
    task_time_limit=1800,
    task_soft_time_limit=1500,
)
def recompute_visibility(self, job_id: str) -> str:
    settings = get_settings()
    session = _db_session()
    try:
        job, claim_outcome = _claim_visibility_job(session, job_id)
        if claim_outcome == "missing":
            logger.warning("RAG visibility recompute job not found: %s", job_id)
            record_sync_job_result(status="missing", job_kind="visibility_recompute")
            return "missing"
        if claim_outcome != "claimed" or job is None:
            logger.info("Ignoring RAG visibility job already claimed or closed: %s", job_id)
            record_sync_job_result(status="ignored", job_kind="visibility_recompute")
            return "ignored"
        return _execute_visibility_job(
            session,
            task=self,
            job=job,
            rag_enabled=settings.rag_enabled,
        )
    finally:
        session.close()


def _execute_visibility_job(
    session: Session,
    *,
    task,
    job: RagVisibilityRecomputeJob,
    rag_enabled: bool,
) -> str:
    record_sync_job_lag(
        lag_ms=_job_lag_ms(job.created_at),
        workspace_id=job.workspace_id,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        job_kind="visibility_recompute",
    )
    with start_as_current_span(
        tracer_name="ai_do_worker.rag",
        span_name="rag.recompute_visibility",
        kind=SpanKind.CONSUMER,
        parent_trace_context=job.trace_context,
        attributes=rag_span_attributes(
            workspace_id=job.workspace_id,
            scope_type=job.scope_type,
            scope_id=job.scope_id,
            job_id=job.id,
        ),
    ):
        if not rag_enabled:
            logger.info("Skipping RAG visibility recompute because RAG is disabled: %s", job.id)
            record_sync_job_result(
                status="disabled",
                workspace_id=job.workspace_id,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                job_kind="visibility_recompute",
            )
            _mark_visibility_job(session, job, status=RagJobStatus.CANCELLED.value)
            return "disabled"
        try:
            result, last_error = _process_visibility_job(session, job)
            record_sync_job_result(
                status=result,
                workspace_id=job.workspace_id,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
                job_kind="visibility_recompute",
            )
            final_status = (
                RagJobStatus.CANCELLED.value
                if result == "unsupported_scope_type"
                else RagJobStatus.SUCCEEDED.value
            )
            _mark_visibility_job(session, job, status=final_status, last_error=last_error)
            return result
        except Exception as error:
            return _handle_visibility_job_failure(
                session,
                task=task,
                job=job,
                error=error,
            )


def _process_sync_job(session: Session, job: RagSyncJob) -> str:
    collection = _collection_name()
    service = _rag_service()

    if job.operation == RagSyncOperation.DELETE.value:
        service.delete_projection(
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            collection=collection,
        )
        logger.info("Deleted RAG projection for %s:%s", job.resource_type, job.resource_id)
        return "deleted"

    projection = _load_projection_for_job(session, job)
    if projection == "unsupported":
        logger.warning("Unsupported RAG resource type: %s", job.resource_type)
        return "unsupported_resource_type"
    if projection is None:
        service.delete_projection(
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            collection=collection,
        )
        logger.info(
            "Projection missing during RAG sync; deleted stale vectors for %s:%s",
            job.resource_type,
            job.resource_id,
        )
        return "deleted_missing_projection"

    service.sync_projection(projection, collection=collection)
    logger.info("Synced RAG projection for %s:%s", job.resource_type, job.resource_id)
    return "succeeded"


def _load_projection_for_job(session: Session, job: RagSyncJob):
    if job.resource_type == NATIVE_DOC_RESOURCE_TYPE:
        return load_native_doc_projection(session, doc_id=job.resource_id)
    if job.resource_type == MEETING_RESOURCE_TYPE:
        return load_meeting_projection(session, meeting_id=job.resource_id)
    if job.resource_type == PLANNER_EVENT_RESOURCE_TYPE:
        return load_planner_event_projection(session, event_id=job.resource_id)
    if job.resource_type == PMS_ISSUE_RESOURCE_TYPE:
        return load_issue_projection(session, issue_id=job.resource_id)
    return "unsupported"


def _process_visibility_job(
    session: Session,
    job: RagVisibilityRecomputeJob,
) -> tuple[str, str | None]:
    if job.scope_type == MEETING_VISIBILITY_SCOPE:
        doc_ids = _resolve_meeting_doc_ids(session, meeting_id=job.scope_id, cursor=job.cursor)
        if not doc_ids:
            logger.info(
                "No affected docs for RAG visibility recompute meeting scope: %s",
                job.scope_id,
            )
            return "noop", None

        _enqueue_resource_sync_jobs(
            session,
            workspace_id=job.workspace_id,
            resource_type=NATIVE_DOC_RESOURCE_TYPE,
            resource_ids=doc_ids,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
            lane=RagSyncLane.BACKFILL,
        )
        session.commit()
        logger.info(
            "Queued %s RAG visibility update sync job(s) for meeting scope %s",
            len(doc_ids),
            job.scope_id,
        )
        return "queued", None

    if job.scope_type == PMS_MEETING_VISIBILITY_SCOPE:
        issue_ids = _resolve_meeting_issue_ids(session, meeting_id=job.scope_id, cursor=job.cursor)
        if not issue_ids:
            logger.info(
                "No affected issues for PMS meeting visibility recompute scope: %s",
                job.scope_id,
            )
            return "noop", None
        _enqueue_resource_sync_jobs(
            session,
            workspace_id=job.workspace_id,
            resource_type=PMS_ISSUE_RESOURCE_TYPE,
            resource_ids=issue_ids,
            operation=RagSyncOperation.VISIBILITY_UPDATE,
            lane=RagSyncLane.BACKFILL,
        )
        session.commit()
        logger.info(
            "Queued %s PMS visibility update sync job(s) for meeting scope %s",
            len(issue_ids),
            job.scope_id,
        )
        return "queued", None

    if job.scope_type == PMS_TASK_LIST_RECOMPUTE_SCOPE:
        issue_ids = _resolve_task_list_issue_ids(session, list_id=job.scope_id)
        return _queue_pms_issue_recompute(session, job=job, issue_ids=issue_ids, scope_label="task_list")

    if job.scope_type == PMS_LABEL_RECOMPUTE_SCOPE:
        issue_ids = _resolve_label_issue_ids(session, label_id=job.scope_id, cursor=job.cursor)
        return _queue_pms_issue_recompute(session, job=job, issue_ids=issue_ids, scope_label="label")

    if job.scope_type == PMS_MILESTONE_RECOMPUTE_SCOPE:
        issue_ids = _resolve_milestone_issue_ids(session, milestone_id=job.scope_id)
        return _queue_pms_issue_recompute(session, job=job, issue_ids=issue_ids, scope_label="milestone")

    logger.warning("Unsupported RAG visibility recompute scope: %s", job.scope_type)
    return "unsupported_scope_type", f"unsupported scope_type: {job.scope_type}"


def _queue_pms_issue_recompute(
    session: Session,
    *,
    job: RagVisibilityRecomputeJob,
    issue_ids: list[str],
    scope_label: str,
) -> tuple[str, str | None]:
    if not issue_ids:
        logger.info(
            "No affected issues for PMS %s recompute scope: %s",
            scope_label,
            job.scope_id,
        )
        return "noop", None
    _enqueue_resource_sync_jobs(
        session,
        workspace_id=job.workspace_id,
        resource_type=PMS_ISSUE_RESOURCE_TYPE,
        resource_ids=issue_ids,
        operation=RagSyncOperation.UPSERT,
        lane=RagSyncLane.BACKFILL,
    )
    session.commit()
    logger.info(
        "Queued %s PMS sync job(s) for %s scope %s",
        len(issue_ids),
        scope_label,
        job.scope_id,
    )
    return "queued", None


def _enqueue_resource_sync_jobs(
    session: Session,
    *,
    workspace_id: str,
    resource_type: str,
    resource_ids: list[str],
    operation: RagSyncOperation,
    lane: RagSyncLane = RagSyncLane.REALTIME,
) -> None:
    for resource_id in resource_ids:
        enqueue_rag_sync_job(
            session,
            workspace_id=workspace_id,
            resource_type=resource_type,
            resource_id=resource_id,
            operation=operation,
            lane=lane,
        )


def _resolve_meeting_doc_ids(
    session: Session,
    *,
    meeting_id: str,
    cursor: dict | None,
) -> list[str]:
    doc_ids = set()
    if isinstance(cursor, dict):
        doc_ids.update(str(doc_id) for doc_id in cursor.get("doc_ids") or [] if doc_id)

    doc_ids.update(
        session.scalars(select(MeetingDocLink.doc_id).where(MeetingDocLink.meeting_id == meeting_id))
    )
    doc_ids.update(
        session.scalars(
            select(DocMeetingAccess.doc_id).where(DocMeetingAccess.granted_by_meeting_id == meeting_id)
        )
    )
    meeting = session.get(Meeting, meeting_id)
    if meeting is not None and meeting.notes_doc_id:
        doc_ids.add(meeting.notes_doc_id)

    return sorted(doc_id for doc_id in doc_ids if doc_id)


def _resolve_meeting_issue_ids(
    session: Session,
    *,
    meeting_id: str,
    cursor: dict | None,
) -> list[str]:
    issue_ids = set()
    if isinstance(cursor, dict):
        issue_ids.update(str(issue_id) for issue_id in cursor.get("issue_ids") or [] if issue_id)

    issue_ids.update(
        session.scalars(select(MeetingTaskLink.issue_id).where(MeetingTaskLink.meeting_id == meeting_id))
    )
    issue_ids.update(
        session.scalars(
            select(IssueUserAccess.issue_id).where(IssueUserAccess.granted_by_meeting_id == meeting_id)
        )
    )
    return sorted(issue_id for issue_id in issue_ids if issue_id)


def _resolve_task_list_issue_ids(session: Session, *, list_id: str) -> list[str]:
    return sorted(
        str(issue_id)
        for issue_id in session.scalars(select(Issue.id).where(Issue.list_id == list_id))
        if issue_id
    )


def _resolve_label_issue_ids(
    session: Session,
    *,
    label_id: str,
    cursor: dict | None,
) -> list[str]:
    issue_ids = set()
    if isinstance(cursor, dict):
        issue_ids.update(str(issue_id) for issue_id in cursor.get("issue_ids") or [] if issue_id)
    issue_ids.update(
        session.scalars(select(IssueLabel.issue_id).where(IssueLabel.label_id == label_id))
    )
    return sorted(issue_id for issue_id in issue_ids if issue_id)


def _resolve_milestone_issue_ids(session: Session, *, milestone_id: str) -> list[str]:
    return sorted(
        str(issue_id)
        for issue_id in session.scalars(select(Issue.id).where(Issue.milestone_id == milestone_id))
        if issue_id
    )


def _mark_sync_job(
    session: Session,
    job: RagSyncJob,
    *,
    status: str,
    increment_attempts: bool = False,
    last_error: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    job.status = status
    if increment_attempts:
        job.attempts += 1
    job.last_error = last_error
    job.next_retry_at = next_retry_at
    session.add(job)
    session.commit()
    _record_sync_queue_depth_snapshot(session, workspace_id=job.workspace_id, lane=job.lane)


def _claim_sync_job(
    session: Session,
    job_id: str,
) -> tuple[RagSyncJob | None, str]:
    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=settings.rag_job_processing_lease_seconds)
    claimed = session.execute(
        update(RagSyncJob)
        .where(
            RagSyncJob.id == job_id,
            _sync_claimable_clause(now=now, lease_cutoff=lease_cutoff),
        )
        .values(
            status=RagJobStatus.PROCESSING.value,
            attempts=RagSyncJob.attempts + 1,
            last_error=None,
            next_retry_at=None,
            updated_at=now,
        )
    )
    session.commit()
    session.expire_all()
    if claimed.rowcount == 1:
        job = session.get(RagSyncJob, job_id)
        if job is not None:
            _record_sync_queue_depth_snapshot(session, workspace_id=job.workspace_id, lane=job.lane)
        return job, "claimed"

    existing = session.get(RagSyncJob, job_id)
    if existing is None:
        return None, "missing"
    return existing, "ignored"


def _mark_visibility_job(
    session: Session,
    job: RagVisibilityRecomputeJob,
    *,
    status: str,
    increment_attempts: bool = False,
    last_error: str | None = None,
    next_retry_at: datetime | None = None,
) -> None:
    job.status = status
    if increment_attempts:
        job.attempts += 1
    job.last_error = last_error
    job.next_retry_at = next_retry_at
    session.add(job)
    session.commit()
    _record_visibility_queue_depth_snapshot(session, workspace_id=job.workspace_id)


def _claim_visibility_job(
    session: Session,
    job_id: str,
) -> tuple[RagVisibilityRecomputeJob | None, str]:
    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=settings.rag_job_processing_lease_seconds)
    claimed = session.execute(
        update(RagVisibilityRecomputeJob)
        .where(
            RagVisibilityRecomputeJob.id == job_id,
            _visibility_claimable_clause(now=now, lease_cutoff=lease_cutoff),
        )
        .values(
            status=RagJobStatus.PROCESSING.value,
            attempts=RagVisibilityRecomputeJob.attempts + 1,
            last_error=None,
            next_retry_at=None,
            updated_at=now,
        )
    )
    session.commit()
    session.expire_all()
    if claimed.rowcount == 1:
        job = session.get(RagVisibilityRecomputeJob, job_id)
        if job is not None:
            _record_visibility_queue_depth_snapshot(session, workspace_id=job.workspace_id)
        return job, "claimed"

    existing = session.get(RagVisibilityRecomputeJob, job_id)
    if existing is None:
        return None, "missing"
    return existing, "ignored"


def _collection_name() -> str:
    return resolve_default_collection_name(get_settings())


def _claim_next_sync_job(
    session: Session,
    *,
    lane: str,
) -> RagSyncJob | None:
    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    lease_cutoff = now - timedelta(seconds=settings.rag_job_processing_lease_seconds)
    candidate_ids = list(
        session.scalars(
            select(RagSyncJob.id)
            .where(
                RagSyncJob.lane == lane,
                _sync_claimable_clause(now=now, lease_cutoff=lease_cutoff),
            )
            .order_by(RagSyncJob.created_at.asc(), RagSyncJob.id.asc())
            .limit(max(settings.rag_backfill_batch_size, 1))
        )
    )
    for candidate_id in candidate_ids:
        job, outcome = _claim_sync_job(session, candidate_id)
        if outcome == "claimed":
            return job
    return None


def _sync_claimable_clause(*, now: datetime, lease_cutoff: datetime):
    return or_(
        and_(
            RagSyncJob.status == RagJobStatus.PENDING.value,
            or_(RagSyncJob.next_retry_at.is_(None), RagSyncJob.next_retry_at <= now),
        ),
        and_(
            RagSyncJob.status == RagJobStatus.PROCESSING.value,
            RagSyncJob.updated_at <= lease_cutoff,
        ),
    )


def _visibility_claimable_clause(*, now: datetime, lease_cutoff: datetime):
    return or_(
        and_(
            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
            or_(
                RagVisibilityRecomputeJob.next_retry_at.is_(None),
                RagVisibilityRecomputeJob.next_retry_at <= now,
            ),
        ),
        and_(
            RagVisibilityRecomputeJob.status == RagJobStatus.PROCESSING.value,
            RagVisibilityRecomputeJob.updated_at <= lease_cutoff,
        ),
    )


def _handle_sync_job_failure(
    session: Session,
    *,
    task,
    job: RagSyncJob,
    error: Exception,
    job_kind: str,
) -> str:
    settings = get_settings()
    error_text = str(error)
    if _is_non_retryable_rag_error(error):
        record_sync_job_result(
            status="non_retryable_error",
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_lane=job.lane,
            job_kind=job_kind,
        )
        _mark_sync_job(
            session,
            job,
            status=RagJobStatus.CANCELLED.value,
            last_error=f"non_retryable: {error_text}",
        )
        logger.error("Cancelling non-retryable RAG sync job %s after failure: %s", job.id, error_text)
        return "non_retryable_error"
    if job.attempts >= settings.rag_job_max_attempts:
        record_sync_job_result(
            status="dead_letter",
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=job.operation,
            job_lane=job.lane,
            job_kind=job_kind,
        )
        _mark_sync_job(
            session,
            job,
            status=RagJobStatus.CANCELLED.value,
            last_error=f"dead_letter: {error_text}",
        )
        logger.error("Dead-lettered RAG sync job %s after %s attempts", job.id, job.attempts)
        return "dead_letter"

    countdown = _resolve_retry_countdown_seconds(
        error,
        default_backoff_seconds=settings.rag_job_retry_backoff_seconds,
        attempts=job.attempts,
    )
    next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=countdown)
    record_sync_job_result(
        status="retry_scheduled",
        workspace_id=job.workspace_id,
        resource_type=job.resource_type,
        resource_id=job.resource_id,
        operation=job.operation,
        job_lane=job.lane,
        job_kind=job_kind,
    )
    try:
        _mark_sync_job(
            session,
            job,
            status=RagJobStatus.PENDING.value,
            last_error=error_text,
            next_retry_at=next_retry_at,
        )
    except IntegrityError:
        session.rollback()
        merged_job = enqueue_rag_sync_job(
            session,
            workspace_id=job.workspace_id,
            resource_type=job.resource_type,
            resource_id=job.resource_id,
            operation=RagSyncOperation(job.operation),
            lane=RagSyncLane(job.lane),
            content_checksum=job.content_checksum,
            visibility_checksum=job.visibility_checksum,
            trace_context=job.trace_context,
        )
        current_job = session.get(RagSyncJob, job.id)
        if current_job is not None:
            current_job.status = RagJobStatus.CANCELLED.value
            current_job.last_error = f"merged_retry_into:{merged_job.id}: {error_text}"
            current_job.next_retry_at = None
            session.add(current_job)
            session.commit()
            _record_sync_queue_depth_snapshot(
                session,
                workspace_id=current_job.workspace_id,
                lane=current_job.lane,
            )
        logger.warning(
            "Merged retry for RAG sync job %s into pending job %s after failure: %s",
            job.id,
            merged_job.id,
            error_text,
        )
        return "retry_merged"
    logger.warning(
        "Retrying RAG sync job %s in %ss after failure: %s",
        job.id,
        countdown,
        error_text,
    )
    raise task.retry(exc=error, countdown=countdown)


def _handle_visibility_job_failure(
    session: Session,
    *,
    task,
    job: RagVisibilityRecomputeJob,
    error: Exception,
) -> str:
    settings = get_settings()
    error_text = str(error)
    if job.attempts >= settings.rag_job_max_attempts:
        record_sync_job_result(
            status="dead_letter",
            workspace_id=job.workspace_id,
            scope_type=job.scope_type,
            scope_id=job.scope_id,
            job_kind="visibility_recompute",
        )
        _mark_visibility_job(
            session,
            job,
            status=RagJobStatus.CANCELLED.value,
            last_error=f"dead_letter: {error_text}",
        )
        logger.error(
            "Dead-lettered RAG visibility job %s after %s attempts",
            job.id,
            job.attempts,
        )
        return "dead_letter"

    countdown = _resolve_retry_countdown_seconds(
        error,
        default_backoff_seconds=settings.rag_job_retry_backoff_seconds,
        attempts=job.attempts,
    )
    next_retry_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=countdown)
    record_sync_job_result(
        status="retry_scheduled",
        workspace_id=job.workspace_id,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        job_kind="visibility_recompute",
    )
    _mark_visibility_job(
        session,
        job,
        status=RagJobStatus.PENDING.value,
        last_error=error_text,
        next_retry_at=next_retry_at,
    )
    logger.warning(
        "Retrying RAG visibility job %s in %ss after failure: %s",
        job.id,
        countdown,
        error_text,
    )
    raise task.retry(exc=error, countdown=countdown)


def _record_sync_queue_depth_snapshot(
    session: Session,
    *,
    workspace_id: str,
    lane: str,
) -> None:
    pending_count = session.scalar(
        select(func.count())
        .select_from(RagSyncJob)
        .where(
            RagSyncJob.workspace_id == workspace_id,
            RagSyncJob.lane == lane,
            RagSyncJob.status == RagJobStatus.PENDING.value,
        )
    )
    record_sync_queue_depth(
        depth=int(pending_count or 0),
        workspace_id=workspace_id,
        job_lane=lane,
        job_kind="resource_sync" if lane == RagSyncLane.REALTIME.value else "backfill_sync",
    )


def _record_visibility_queue_depth_snapshot(
    session: Session,
    *,
    workspace_id: str,
) -> None:
    pending_count = session.scalar(
        select(func.count())
        .select_from(RagVisibilityRecomputeJob)
        .where(
            RagVisibilityRecomputeJob.workspace_id == workspace_id,
            RagVisibilityRecomputeJob.status == RagJobStatus.PENDING.value,
        )
    )
    record_sync_queue_depth(
        depth=int(pending_count or 0),
        workspace_id=workspace_id,
        job_lane="visibility_recompute",
        job_kind="visibility_recompute",
    )


def _is_non_retryable_rag_error(error: Exception) -> bool:
    if isinstance(error, RagProviderConfigurationError):
        return True
    if isinstance(error, (RagProviderTransientError, RagProviderTimeoutError)):
        return False
    return isinstance(error, RagProviderError)


def _resolve_retry_countdown_seconds(
    error: Exception,
    *,
    default_backoff_seconds: int,
    attempts: int,
) -> int:
    retry_after_seconds = getattr(error, "retry_after_seconds", None)
    if isinstance(retry_after_seconds, int) and retry_after_seconds > 0:
        return retry_after_seconds
    return default_backoff_seconds * max(attempts, 1)
