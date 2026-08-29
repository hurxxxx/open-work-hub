from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.meeting import service as meeting_service
from open_work_hub_api.domains.meeting.models import (
    Meeting,
    MeetingTaskLink,
)
from open_work_hub_api.domains.meeting.permissions import ensure_meeting_participant
from open_work_hub_api.domains.pms.access import _ensure_task_readable as ensure_task_readable
from open_work_hub_api.domains.recording import blob_store as recording_blob_store
from open_work_hub_api.domains.recording import service as canonical_recording_service
from open_work_hub_api.domains.recording.schemas import (
    RecordingUploadCompleteRequest as CanonicalRecordingCompleteRequest,
    RecordingUploadInitRequest as CanonicalRecordingStagingInitRequest,
)
from open_work_hub_api.domains.meeting.schemas import (
    RecordingChunkAck,
    RecordingCompleteRequest,
    RecordingPlaybackResponse,
    RecordingStagingInitRequest,
    RecordingStagingItem,
)

def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _serialize_canonical_staging(staging, *, meeting_id: str) -> RecordingStagingItem:
    return RecordingStagingItem(
        id=staging.id,
        meeting_id=meeting_id,
        uploaded_by_id=staging.uploaded_by_id,
        idempotency_key=staging.idempotency_key,
        status=staging.status,
        mime_type=staging.mime_type,
        bytes_received=staging.bytes_received,
        chunk_count=staging.chunk_count,
        highest_seq=staging.highest_seq,
        linked_task_id=staging.linked_task_id,
        started_at=staging.started_at,
        last_chunk_at=staging.last_chunk_at,
        completed_at=staging.completed_at,
    )


def _ensure_canonical_staging_for_meeting(db: Session, *, workspace: Workspace, meeting_id: str, staging_id: str):
    staging = canonical_recording_service.load_staging_or_404(
        db,
        workspace=workspace,
        staging_id=staging_id,
    )
    if (
        staging.initial_target_app != "meeting"
        or staging.initial_target_type != "meeting"
        or staging.initial_target_id != meeting_id
    ):
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="meeting.recording_staging_not_found",
        )
    return staging


def _meeting_task_link_exists(db: Session, *, meeting_id: str, task_id: str) -> bool:
    return (
        db.scalar(
            select(MeetingTaskLink.id).where(
                MeetingTaskLink.meeting_id == meeting_id,
                MeetingTaskLink.task_id == task_id,
            )
        )
        is not None
    )


def _validate_linked_task_id(db: Session, *, meeting: Meeting, user: User, linked_task_id: str | None) -> None:
    if linked_task_id is None:
        return
    ensure_task_readable(db, user, linked_task_id)
    if not _meeting_task_link_exists(db, meeting_id=meeting.id, task_id=linked_task_id):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="meeting.linked_task_attached_required",
        )


def init_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    payload: RecordingStagingInitRequest,
) -> RecordingStagingItem:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    _validate_linked_task_id(db, meeting=meeting, user=user, linked_task_id=payload.linked_task_id)
    staging = canonical_recording_service.init_staging(
        db,
        workspace=workspace,
        user=user,
        payload=CanonicalRecordingStagingInitRequest(
            idempotency_key=payload.idempotency_key,
            mime_type=payload.mime_type,
            initial_target_app="meeting",
            initial_target_type="meeting",
            initial_target_id=meeting.id,
            linked_task_id=payload.linked_task_id,
            title=meeting.title,
        ),
    )
    return _serialize_canonical_staging(staging, meeting_id=meeting.id)


async def upload_chunk(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    staging_id: str,
    seq: int,
    upload: UploadFile,
    chunk_sha256: str | None,
) -> RecordingChunkAck:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    _ensure_canonical_staging_for_meeting(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        staging_id=staging_id,
    )
    return await canonical_recording_service.upload_chunk(
        db,
        workspace=workspace,
        user=user,
        staging_id=staging_id,
        seq=seq,
        upload=upload,
        chunk_sha256=chunk_sha256,
    )


def list_my_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
) -> list[RecordingStagingItem]:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    items = canonical_recording_service.list_my_staging(
        db,
        workspace=workspace,
        user=user,
        initial_target_app="meeting",
        initial_target_type="meeting",
        initial_target_id=meeting.id,
    )
    return [_serialize_canonical_staging(item, meeting_id=meeting.id) for item in items]


def discard_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    staging_id: str,
) -> None:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    _ensure_canonical_staging_for_meeting(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        staging_id=staging_id,
    )
    canonical_recording_service.discard_staging(
        db,
        workspace=workspace,
        user=user,
        staging_id=staging_id,
    )


def complete_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    staging_id: str,
    payload: RecordingCompleteRequest,
) -> Meeting:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    _ensure_canonical_staging_for_meeting(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        staging_id=staging_id,
    )
    canonical_recording_service.complete_staging(
        db,
        workspace=workspace,
        user=user,
        staging_id=staging_id,
        payload=CanonicalRecordingCompleteRequest(
            title=meeting.title,
            duration_sec_estimate=payload.duration_sec_estimate,
            source="live_recording",
        ),
    )
    fresh = meeting_service._load_meeting(db, workspace, meeting.id)
    return fresh


def import_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    upload: UploadFile,
    linked_task_id: str | None,
) -> Meeting:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    _validate_linked_task_id(db, meeting=meeting, user=user, linked_task_id=linked_task_id)
    canonical_recording_service.import_recording(
        db,
        workspace=workspace,
        user=user,
        upload=upload,
        title=meeting.title,
        started_at=None,
        ended_at=None,
        duration_sec=None,
        source="manual_upload",
        initial_target_app="meeting",
        initial_target_type="meeting",
        initial_target_id=meeting.id,
        linked_task_id=linked_task_id,
    )
    fresh = meeting_service._load_meeting(db, workspace, meeting.id)
    return fresh


def get_recording_playback(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    recording_id: str,
) -> RecordingPlaybackResponse:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    canonical_recording_service.load_meeting_recording_or_404(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        recording_id=recording_id,
    )
    playback = canonical_recording_service.get_recording_playback(
        db,
        workspace=workspace,
        user=user,
        recording_id=recording_id,
    )
    return RecordingPlaybackResponse(
        url=(
            f"/api/v1/workspaces/{workspace.key}/meeting/meetings/{meeting.id}"
            f"/recordings/{recording_id}/media"
        ),
        expires_at=playback.expires_at,
    )


def stream_recording_media(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    recording_id: str,
) -> StreamingResponse:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    canonical_recording_service.load_meeting_recording_or_404(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        recording_id=recording_id,
    )
    return canonical_recording_service.stream_recording_media(
        db,
        workspace=workspace,
        user=user,
        recording_id=recording_id,
    )


def retry_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    recording_id: str,
) -> Meeting:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    canonical_recording_service.retry_meeting_recording(
        db,
        workspace=workspace,
        user=user,
        meeting=meeting,
        recording_id=recording_id,
    )
    fresh = meeting_service._load_meeting(db, workspace, meeting.id)
    return fresh


def delete_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    recording_id: str,
) -> Meeting:
    """Hard-delete a finalized meeting recording.

    Permission: organizer of the meeting OR the user who originally uploaded
    the recording. Mirrors ``canRemoveAttachment`` for tasks/docs — attendees
    cannot delete each other's recordings, organizer can delete any.

    Side effects: cancels any pending celery transcription task, removes the
    minio object, and clears any auto-generated notes doc reference if this
    recording produced one. The DB row is removed entirely.
    """
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    canonical_recording_service.archive_meeting_recording(
        db,
        workspace=workspace,
        user=user,
        meeting=meeting,
        recording_id=recording_id,
    )
    from open_work_hub_api.domains.meeting.rag_sync import enqueue_meeting_rag_sync
    from open_work_hub_api.domains.rag.contracts import RagSyncOperation

    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()

    fresh = meeting_service._load_meeting(db, workspace, meeting.id)
    return fresh


def cleanup_meeting_recordings(db: Session, *, meeting: Meeting) -> None:
    from open_work_hub_api.domains.recording.models import Recording, RecordingTarget, RecordingStaging

    recordings = db.scalars(
        select(Recording)
        .join(RecordingTarget)
        .where(
            RecordingTarget.target_app == "meeting",
            RecordingTarget.target_type == "meeting",
            RecordingTarget.target_id == meeting.id,
            Recording.trashed_at.is_(None),
        )
    ).all()
    for recording in recordings:
        if recording.celery_task_id:
            canonical_recording_service.revoke_recording_task(recording.celery_task_id)
        recording.trashed_at = _utcnow()
        recording.updated_at = recording.trashed_at
        db.add(recording)

    staging_rows = db.scalars(
        select(RecordingStaging).where(
            RecordingStaging.initial_target_app == "meeting",
            RecordingStaging.initial_target_type == "meeting",
            RecordingStaging.initial_target_id == meeting.id,
            RecordingStaging.completed_at.is_(None),
        )
    ).all()
    for staging in staging_rows:
        recording_blob_store.cleanup_spool_dir(staging.spool_path)
        db.delete(staging)
    db.flush()


def cleanup_stale_staging_once(db: Session) -> dict[str, int]:
    from open_work_hub_api.domains.recording.models import RecordingStaging

    cutoff = _utcnow() - timedelta(hours=get_settings().recording_staging_retention_hours)
    rows = db.scalars(
        select(RecordingStaging).where(
            RecordingStaging.completed_at.is_(None),
            RecordingStaging.last_chunk_at < cutoff,
        )
    ).all()
    deleted = 0
    for staging in rows:
        recording_blob_store.cleanup_spool_dir(staging.spool_path)
        db.delete(staging)
        deleted += 1
    db.commit()
    return {"deleted": deleted}


def fetch_local_recording_blob(
    db: Session,
    *,
    workspace: Workspace,
    meeting_id: str,
    staging_id: str,
    user: User,
) -> bytes:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    staging = _ensure_canonical_staging_for_meeting(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        staging_id=staging_id,
    )
    if staging.uploaded_by_id != user.id:
        raise localized_http_exception(status_code=status.HTTP_403_FORBIDDEN, code="meeting.uploader_read_staging_required")
    assembled_path = canonical_recording_service.assemble_staging_chunks(staging)
    return assembled_path.read_bytes()
