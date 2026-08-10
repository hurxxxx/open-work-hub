from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import select

from open_alm_worker.celery_app import celery_app
from open_alm_worker.queue_contract import (
    LEGACY_ISSUE_ATTACHMENT_CLEANUP_TASK_NAME,
    LEGACY_ISSUE_ATTACHMENT_INDEX_TASK_NAME,
    LEGACY_ISSUE_ATTACHMENT_ORPHAN_RECONCILE_TASK_NAME,
)
from open_alm_worker.runtime import db_session as _db_session
from open_alm_worker.runtime import minio_client as _minio_client
from open_alm_worker.settings import get_settings

from open_alm_api.domains.legacy_issues.attachment_indexing import (
    mark_legacy_issue_attachment_index_job_for_retry,
    process_legacy_issue_attachment_index_job,
)
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueAttachmentIndexJob,
    LegacyIssueRevisionMeetingAttachment,
    LegacyIssueVehicleModuleChecklistAttachment,
)
from open_alm_api.domains.legacy_issues.vehicle_module_checklist_attachments import (
    VehicleModuleChecklistAttachmentStorage,
    process_all_pending_vehicle_module_checklist_attachment_cleanups,
)
from open_alm_api.domains.legacy_issues.revision_meeting_attachments import (
    RevisionMeetingAttachmentStorage,
    process_all_pending_revision_meeting_attachment_cleanups,
)


logger = logging.getLogger(__name__)
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_PREFIX = "legacy-issues/vehicle-module-checklists/"
REVISION_MEETING_ATTACHMENT_PREFIX = "legacy-issues/revision-meeting-attachments/"
LEGACY_ISSUE_ATTACHMENT_ORPHAN_GRACE = timedelta(hours=1)
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_ORPHAN_GRACE = LEGACY_ISSUE_ATTACHMENT_ORPHAN_GRACE
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_CLEANUP_BATCH_SIZE = 1000
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_ORPHAN_QUERY_BATCH_SIZE = 500
VEHICLE_MODULE_CHECKLIST_ATTACHMENT_ORPHAN_DELETE_BATCH_SIZE = 100


@celery_app.task(
    name=LEGACY_ISSUE_ATTACHMENT_INDEX_TASK_NAME,
    bind=True,
    acks_late=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
)
def index_legacy_issue_attachment(self, job_id: str) -> str:
    session = _db_session()
    try:
        return process_legacy_issue_attachment_index_job(session, job_id)
    except Exception as error:
        return _handle_attachment_index_failure(session, task=self, job_id=job_id, error=error)
    finally:
        session.close()


@celery_app.task(
    name=LEGACY_ISSUE_ATTACHMENT_CLEANUP_TASK_NAME,
    task_time_limit=240,
    task_soft_time_limit=210,
)
def cleanup_vehicle_module_checklist_attachment_objects(
    limit: int = VEHICLE_MODULE_CHECKLIST_ATTACHMENT_CLEANUP_BATCH_SIZE,
) -> dict[str, int]:
    """Drain committed attachment cleanup rows; failed rows remain for the next run."""

    session = _db_session()
    try:
        settings = get_settings()
        storage = VehicleModuleChecklistAttachmentStorage(
            bucket_name=settings.minio_bucket,
            client=_minio_client(),
        )
        deleted, failed = process_all_pending_vehicle_module_checklist_attachment_cleanups(
            session,
            limit=_bounded_limit(
                limit,
                maximum=VEHICLE_MODULE_CHECKLIST_ATTACHMENT_CLEANUP_BATCH_SIZE,
            ),
            storage=storage,
        )
        meeting_deleted, meeting_failed = process_all_pending_revision_meeting_attachment_cleanups(
            session,
            limit=_bounded_limit(
                limit,
                maximum=VEHICLE_MODULE_CHECKLIST_ATTACHMENT_CLEANUP_BATCH_SIZE,
            ),
            storage=RevisionMeetingAttachmentStorage(
                bucket_name=settings.minio_bucket,
                client=storage.client,
            ),
        )
        return {
            "deleted": deleted + meeting_deleted,
            "failed": failed + meeting_failed,
        }
    finally:
        session.close()


@celery_app.task(
    name=LEGACY_ISSUE_ATTACHMENT_ORPHAN_RECONCILE_TASK_NAME,
    task_time_limit=240,
    task_soft_time_limit=210,
)
def reconcile_vehicle_module_checklist_attachment_orphans(
    delete_limit: int = VEHICLE_MODULE_CHECKLIST_ATTACHMENT_ORPHAN_DELETE_BATCH_SIZE,
) -> dict[str, int]:
    """Delete old MinIO objects that have no attachment row in the database."""

    session = _db_session()
    try:
        settings = get_settings()
        return _reconcile_legacy_issue_attachment_orphans(
            session,
            client=_minio_client(),
            bucket_name=settings.minio_bucket,
            now=datetime.now(UTC),
            delete_limit=delete_limit,
        )
    finally:
        session.close()


def _reconcile_vehicle_module_checklist_attachment_orphans(
    session,
    *,
    client,
    bucket_name: str,
    now: datetime,
    delete_limit: int,
) -> dict[str, int]:
    return _reconcile_attachment_orphans(
        session,
        client=client,
        bucket_name=bucket_name,
        now=now,
        delete_limit=delete_limit,
        attachment_sources=(
            (
                VEHICLE_MODULE_CHECKLIST_ATTACHMENT_PREFIX,
                LegacyIssueVehicleModuleChecklistAttachment,
            ),
        ),
    )


def _reconcile_legacy_issue_attachment_orphans(
    session,
    *,
    client,
    bucket_name: str,
    now: datetime,
    delete_limit: int,
) -> dict[str, int]:
    return _reconcile_attachment_orphans(
        session,
        client=client,
        bucket_name=bucket_name,
        now=now,
        delete_limit=delete_limit,
        attachment_sources=(
            (
                VEHICLE_MODULE_CHECKLIST_ATTACHMENT_PREFIX,
                LegacyIssueVehicleModuleChecklistAttachment,
            ),
            (
                REVISION_MEETING_ATTACHMENT_PREFIX,
                LegacyIssueRevisionMeetingAttachment,
            ),
        ),
    )


def _reconcile_attachment_orphans(
    session,
    *,
    client,
    bucket_name: str,
    now: datetime,
    delete_limit: int,
    attachment_sources,
) -> dict[str, int]:
    bounded_delete_limit = _bounded_limit(
        delete_limit,
        maximum=VEHICLE_MODULE_CHECKLIST_ATTACHMENT_ORPHAN_DELETE_BATCH_SIZE,
    )
    cutoff = _as_utc(now) - LEGACY_ISSUE_ATTACHMENT_ORPHAN_GRACE
    scanned = 0
    eligible = 0
    orphan_storage_keys: list[str] = []

    for prefix, attachment_model in attachment_sources:
        storage_key_batch: list[str] = []
        try:
            for storage_object in client.list_objects(
                bucket_name,
                prefix=prefix,
                recursive=True,
            ):
                scanned += 1
                storage_key = str(getattr(storage_object, "object_name", "") or "")
                last_modified = getattr(storage_object, "last_modified", None)
                if (
                    not storage_key.startswith(prefix)
                    or not isinstance(last_modified, datetime)
                    or _as_utc(last_modified) > cutoff
                ):
                    continue
                eligible += 1
                storage_key_batch.append(storage_key)
                if (
                    len(storage_key_batch)
                    >= VEHICLE_MODULE_CHECKLIST_ATTACHMENT_ORPHAN_QUERY_BATCH_SIZE
                ):
                    orphan_storage_keys.extend(
                        _unreferenced_attachment_storage_keys(
                            session,
                            storage_keys=storage_key_batch,
                            attachment_model=attachment_model,
                        )
                    )
                    storage_key_batch = []
        except Exception:
            logger.exception(
                "Failed to list legacy issue attachment objects",
                extra={"storage_prefix": prefix},
            )
            return {"scanned": scanned, "eligible": 0, "deleted": 0, "failed": 1}

        if storage_key_batch:
            orphan_storage_keys.extend(
                _unreferenced_attachment_storage_keys(
                    session,
                    storage_keys=storage_key_batch,
                    attachment_model=attachment_model,
                )
            )
    orphan_storage_keys = _rotating_storage_key_batch(
        orphan_storage_keys,
        limit=bounded_delete_limit,
        now=now,
    )

    deleted = 0
    failed = 0
    for storage_key in orphan_storage_keys:
        try:
            client.remove_object(bucket_name, storage_key)
        except Exception:
            failed += 1
            logger.exception(
                "Failed to remove orphan legacy issue attachment object",
                extra={"storage_key": storage_key},
            )
        else:
            deleted += 1

    return {
        "scanned": scanned,
        "eligible": eligible,
        "deleted": deleted,
        "failed": failed,
    }


def _unreferenced_attachment_storage_keys(
    session,
    *,
    storage_keys: list[str],
    attachment_model=LegacyIssueVehicleModuleChecklistAttachment,
) -> list[str]:
    if not storage_keys:
        return []
    referenced_storage_keys = set(
        session.scalars(
            select(attachment_model.storage_key).where(
                attachment_model.storage_key.in_(storage_keys)
            )
        )
    )
    return [
        storage_key for storage_key in storage_keys if storage_key not in referenced_storage_keys
    ]


def _rotating_storage_key_batch(
    storage_keys: list[str],
    *,
    limit: int,
    now: datetime,
) -> list[str]:
    ordered = sorted(set(storage_keys))
    if len(ordered) <= limit:
        return ordered
    window = int(_as_utc(now).timestamp() // 3600)
    start = (window * limit) % len(ordered)
    rotated = ordered[start:] + ordered[:start]
    return rotated[:limit]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _bounded_limit(value: int, *, maximum: int) -> int:
    return min(max(int(value), 1), maximum)


def _handle_attachment_index_failure(
    session,
    *,
    task,
    job_id: str,
    error: Exception,
) -> str:
    settings = get_settings()
    session.rollback()
    job = session.get(LegacyIssueAttachmentIndexJob, job_id)
    if job is None:
        logger.warning("Legacy issue attachment index job not found after failure: %s", job_id)
        return "missing"
    if _has_superseding_pending_job(session, job=job):
        job.status = "cancelled"
        job.last_error = f"superseded_after_failure: {error}"
        job.completed_at = datetime.now(UTC).replace(tzinfo=None)
        job.next_retry_at = None
        session.add(job)
        session.commit()
        return "superseded"
    if job.attempts >= settings.rag_job_max_attempts:
        job.status = "failed"
        job.last_error = f"dead_letter: {error}"
        job.completed_at = datetime.now(UTC).replace(tzinfo=None)
        job.next_retry_at = None
        session.add(job)
        session.commit()
        logger.error("Dead-lettered legacy issue attachment index job %s", job_id)
        return "dead_letter"
    countdown = min(settings.rag_job_retry_backoff_seconds * max(job.attempts, 1), 3600)
    mark_legacy_issue_attachment_index_job_for_retry(
        session,
        job_id=job_id,
        error=error,
        countdown_seconds=countdown,
    )
    logger.warning(
        "Retrying legacy issue attachment index job %s in %ss after failure: %s",
        job_id,
        countdown,
        error,
    )
    raise task.retry(exc=error, countdown=countdown)


def _has_superseding_pending_job(
    session,
    *,
    job: LegacyIssueAttachmentIndexJob,
) -> bool:
    return (
        session.scalar(
            select(LegacyIssueAttachmentIndexJob.id)
            .where(
                LegacyIssueAttachmentIndexJob.id != job.id,
                LegacyIssueAttachmentIndexJob.workspace_id == job.workspace_id,
                LegacyIssueAttachmentIndexJob.attachment_id == job.attachment_id,
                LegacyIssueAttachmentIndexJob.created_at > job.created_at,
                LegacyIssueAttachmentIndexJob.status == "pending",
            )
            .limit(1)
        )
        is not None
    )
