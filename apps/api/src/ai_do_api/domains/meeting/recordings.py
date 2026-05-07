from __future__ import annotations

import os
import re
import socket
import shutil
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from celery import Celery, chain
from fastapi import UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.meeting import service as meeting_service
from ai_do_api.domains.meeting.models import (
    Meeting,
    MeetingRecording,
    MeetingRecordingStaging,
    MeetingTaskLink,
)
from ai_do_api.domains.meeting.permissions import ensure_meeting_participant
from ai_do_api.domains.pms.access import _ensure_issue_readable as ensure_issue_readable
from ai_do_api.domains.recording import service as canonical_recording_service
from ai_do_api.domains.recording.schemas import (
    RecordingUploadCompleteRequest as CanonicalRecordingCompleteRequest,
    RecordingUploadInitRequest as CanonicalRecordingStagingInitRequest,
)
from ai_do_api.domains.meeting.schemas import (
    MeetingDetail,
    RecordingChunkAck,
    RecordingCompleteRequest,
    RecordingPlaybackResponse,
    RecordingStagingInitRequest,
    RecordingStagingItem,
)


ALLOWED_RECORDING_MIME_TYPES = {
    "audio/webm": ".webm",
    "audio/webm;codecs=opus": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".mp4",
    "audio/x-m4a": ".m4a",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
}
ACTIVE_RECORDING_STATUSES = {
    "pending",
    "transcribing",
    "summarizing",
    "extracting_insights",
    "generating_doc",
}
ENQUEUE_FAILURE_REASON = "Background processing queue is unavailable. Raw audio was saved; retry later."

# How long an active staging row may go without a chunk upload before we
# consider it abandoned (recorder crashed / browser closed / network died).
# After this window, the single-recorder lock auto-releases so other
# participants can start their own recording. The abandoned row stays in the
# DB so a separate cleanup beat can promote / discard it later.
RECORDING_STALE_AFTER_SECONDS = 60


def _staging_is_stale(staging: "MeetingRecordingStaging", *, now: datetime | None = None) -> bool:
    if staging.completed_at is not None:
        return True
    reference = now or _utcnow()
    threshold = reference - timedelta(seconds=RECORDING_STALE_AFTER_SECONDS)
    return staging.last_chunk_at < threshold


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _require_allowed_mime(mime_type: str | None) -> str:
    normalized = (mime_type or "").strip().lower()
    if normalized not in ALLOWED_RECORDING_MIME_TYPES:
        raise localized_http_exception(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="meeting.unsupported_recording_audio_format",
        )
    return normalized


def _extension_for_mime(mime_type: str) -> str:
    return ALLOWED_RECORDING_MIME_TYPES[mime_type]


def _recording_spool_root() -> Path:
    settings = get_settings()
    path = Path(settings.recording_spool_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _spool_dir_for_recording(recording_id: str) -> Path:
    return _recording_spool_root() / recording_id


def _chunk_path(spool_path: str, seq: int) -> Path:
    return Path(spool_path) / f"{seq:08d}.chunk"


def _assembled_path(spool_path: str) -> Path:
    return Path(spool_path) / "assembled.bin"


def _fsync_path(path: Path, data: bytes) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _cleanup_spool_dir(spool_path: str | None) -> None:
    if not spool_path:
        return
    try:
        shutil.rmtree(spool_path, ignore_errors=True)
    except Exception:
        pass


def _serialize_staging(staging: MeetingRecordingStaging) -> RecordingStagingItem:
    return RecordingStagingItem.model_validate(staging)


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
    staging = canonical_recording_service._load_staging_or_404(  # noqa: SLF001
        db,
        workspace=workspace,
        staging_id=staging_id,
    )
    if (
        staging.initial_container_app != "meeting"
        or staging.initial_container_type != "meeting"
        or staging.initial_container_id != meeting_id
    ):
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="meeting.recording_staging_not_found",
        )
    return staging


def _meeting_task_link_exists(db: Session, *, meeting_id: str, issue_id: str) -> bool:
    return (
        db.scalar(
            select(MeetingTaskLink.id).where(
                MeetingTaskLink.meeting_id == meeting_id,
                MeetingTaskLink.issue_id == issue_id,
            )
        )
        is not None
    )


@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    celery_client = Celery(
        "ai_do_api_recordings",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )
    celery_client.conf.update(
        broker_connection_retry=False,
        broker_connection_retry_on_startup=False,
        broker_connection_max_retries=0,
        task_publish_retry=False,
        broker_transport_options={
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "retry_on_timeout": False,
        },
    )
    return celery_client


def _broker_is_reachable() -> bool:
    parsed = urlparse(get_settings().worker_broker_url)
    host = parsed.hostname
    if not host:
        return True
    port = parsed.port
    if port is None:
        if parsed.scheme in {"redis", "rediss"}:
            port = 6379
        elif parsed.scheme in {"amqp", "amqps"}:
            port = 5672
        else:
            return True
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def enqueue_recording_pipeline(recording_id: str) -> str:
    celery_client = _get_celery_client()
    result = chain(
        celery_client.signature("meeting.transcribe", args=[recording_id], immutable=True),
        celery_client.signature("meeting.summarize"),
        celery_client.signature("meeting.extract_insights"),
        celery_client.signature("meeting.generate_doc"),
    ).apply_async(queue="meeting_transcribe", retry=False)
    return str(result.id)


def revoke_recording_task(task_id: str) -> None:
    if not task_id:
        return
    try:
        _get_celery_client().control.revoke(task_id, terminate=True, signal="SIGKILL")
    except Exception:
        pass


def _enqueue_pipeline_or_mark_failed(db: Session, *, recording: MeetingRecording) -> None:
    if recording.celery_task_id:
        return
    if not _broker_is_reachable():
        recording.transcription_status = "failed"
        recording.failure_reason = ENQUEUE_FAILURE_REASON
        db.add(recording)
        db.commit()
        db.refresh(recording)
        return
    try:
        recording.celery_task_id = enqueue_recording_pipeline(recording.id)
        recording.transcription_status = "pending"
        recording.failure_reason = None
    except Exception:
        recording.transcription_status = "failed"
        recording.failure_reason = ENQUEUE_FAILURE_REASON
    db.add(recording)
    db.commit()
    db.refresh(recording)


def _load_staging_or_404(db: Session, *, meeting_id: str, staging_id: str) -> MeetingRecordingStaging:
    staging = db.scalar(
        select(MeetingRecordingStaging).where(
            MeetingRecordingStaging.id == staging_id,
            MeetingRecordingStaging.meeting_id == meeting_id,
        )
    )
    if staging is None:
        raise localized_http_exception(status_code=status.HTTP_404_NOT_FOUND, code="meeting.recording_staging_not_found")
    return staging


def _load_recording_or_404(db: Session, *, meeting_id: str, recording_id: str) -> MeetingRecording:
    recording = db.scalar(
        select(MeetingRecording).where(
            MeetingRecording.id == recording_id,
            MeetingRecording.meeting_id == meeting_id,
        )
    )
    if recording is None:
        raise localized_http_exception(status_code=status.HTTP_404_NOT_FOUND, code="meeting.recording_not_found")
    return recording


def _recording_started_at_token(started_at: datetime | None = None) -> str:
    value = started_at or _utcnow()
    return value.strftime("%Y%m%dT%H%M%SZ")


def _storage_key_for_recording(
    meeting_id: str,
    recording_id: str,
    mime_type: str,
    *,
    started_at: datetime | None = None,
) -> str:
    filename = f"{_recording_started_at_token(started_at)}{_extension_for_mime(mime_type)}"
    return f"meeting-recordings/{meeting_id}/{recording_id}/{filename}"


def _download_filename_for_recording(recording: MeetingRecording) -> str:
    filename = Path(recording.storage_key).name
    if not filename or re.fullmatch(r"\d{8}T\d{6}Z\.[A-Za-z0-9]+", filename) is None:
        filename = f"{_recording_started_at_token(recording.created_at)}{_extension_for_mime(recording.mime_type)}"
    return filename.replace('"', "")


def _next_recording_sequence_no(db: Session, *, meeting_id: str) -> int:
    db.execute(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update())
    current_max = db.scalar(
        select(func.max(MeetingRecording.sequence_no)).where(MeetingRecording.meeting_id == meeting_id)
    )
    return int(current_max or 0) + 1


def _validate_linked_task_id(db: Session, *, meeting: Meeting, user: User, linked_task_id: str | None) -> None:
    if linked_task_id is None:
        return
    ensure_issue_readable(db, user, linked_task_id)
    if not _meeting_task_link_exists(db, meeting_id=meeting.id, issue_id=linked_task_id):
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
            initial_container_app="meeting",
            initial_container_type="meeting",
            initial_container_id=meeting.id,
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
        initial_container_app="meeting",
        initial_container_type="meeting",
        initial_container_id=meeting.id,
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


def _assert_contiguous_chunks(staging: MeetingRecordingStaging) -> list[int]:
    if staging.highest_seq < 0:
        raise localized_http_exception(status_code=status.HTTP_409_CONFLICT, code="meeting.no_recording_chunks_to_finalize")
    seqs = sorted(int(seq) for seq in (staging.chunks_meta or {}).keys())
    expected = list(range(seqs[0], seqs[-1] + 1))
    if seqs != expected:
        raise localized_http_exception(status_code=status.HTTP_409_CONFLICT, code="meeting.recording_chunks_incomplete")
    return seqs


def _assemble_chunks(staging: MeetingRecordingStaging) -> Path:
    assembled_path = _assembled_path(staging.spool_path)
    seqs = _assert_contiguous_chunks(staging)
    with assembled_path.open("wb") as output:
        for seq in seqs:
            with _chunk_path(staging.spool_path, seq).open("rb") as handle:
                shutil.copyfileobj(handle, output)
        output.flush()
        os.fsync(output.fileno())
    return assembled_path


def complete_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    staging_id: str,
    payload: RecordingCompleteRequest,
):
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
    return meeting_service._serialize_meeting(db, fresh)


def import_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    upload: UploadFile,
    linked_task_id: str | None,
):
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
        initial_container_app="meeting",
        initial_container_type="meeting",
        initial_container_id=meeting.id,
        linked_task_id=linked_task_id,
    )
    fresh = meeting_service._load_meeting(db, workspace, meeting.id)
    return meeting_service._serialize_meeting(db, fresh)


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
):
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
    return meeting_service._serialize_meeting(db, fresh)


def delete_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    recording_id: str,
) -> MeetingDetail:
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
    from ai_do_api.domains.meeting.rag_sync import enqueue_meeting_rag_sync
    from ai_do_api.domains.rag.contracts import RagSyncOperation

    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()

    fresh = meeting_service._load_meeting(db, workspace, meeting.id)
    return meeting_service._serialize_meeting(db, fresh)


def cleanup_meeting_recordings(db: Session, *, meeting: Meeting) -> None:
    from ai_do_api.domains.recording.models import Recording, RecordingContainer, RecordingStaging

    recordings = db.scalars(
        select(Recording)
        .join(RecordingContainer)
        .where(
            RecordingContainer.container_app == "meeting",
            RecordingContainer.container_type == "meeting",
            RecordingContainer.container_id == meeting.id,
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
            RecordingStaging.initial_container_app == "meeting",
            RecordingStaging.initial_container_type == "meeting",
            RecordingStaging.initial_container_id == meeting.id,
            RecordingStaging.completed_at.is_(None),
        )
    ).all()
    for staging in staging_rows:
        canonical_recording_service._cleanup_spool_dir(staging.spool_path)  # noqa: SLF001
        db.delete(staging)
    db.flush()


def cleanup_stale_staging_once(db: Session) -> dict[str, int]:
    from ai_do_api.domains.recording.models import RecordingStaging

    cutoff = _utcnow() - timedelta(hours=get_settings().recording_staging_retention_hours)
    rows = db.scalars(
        select(RecordingStaging).where(
            RecordingStaging.completed_at.is_(None),
            RecordingStaging.last_chunk_at < cutoff,
        )
    ).all()
    deleted = 0
    for staging in rows:
        canonical_recording_service._cleanup_spool_dir(staging.spool_path)  # noqa: SLF001
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
    assembled_path = canonical_recording_service._assemble_chunks(staging)  # noqa: SLF001
    return assembled_path.read_bytes()
