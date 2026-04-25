from __future__ import annotations

import hashlib
import os
import socket
import shutil
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from celery import Celery, chain
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import get_minio_client
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.meeting import service as meeting_service
from aidoo_api.domains.meeting.models import (
    Meeting,
    MeetingRecording,
    MeetingRecordingStaging,
    MeetingTaskLink,
)
from aidoo_api.domains.meeting.permissions import ensure_meeting_participant
from aidoo_api.domains.pms.access import _ensure_issue_readable as ensure_issue_readable
from aidoo_api.domains.meeting.schemas import (
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
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported recording audio format.",
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
        "aidoo_api_recordings",
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording staging not found.")
    return staging


def _load_recording_or_404(db: Session, *, meeting_id: str, recording_id: str) -> MeetingRecording:
    recording = db.scalar(
        select(MeetingRecording).where(
            MeetingRecording.id == recording_id,
            MeetingRecording.meeting_id == meeting_id,
        )
    )
    if recording is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found.")
    return recording


def _storage_key_for_recording(meeting_id: str, recording_id: str, mime_type: str) -> str:
    return f"meeting-recordings/{meeting_id}/{recording_id}/recording{_extension_for_mime(mime_type)}"


def _validate_linked_task_id(db: Session, *, meeting: Meeting, user: User, linked_task_id: str | None) -> None:
    if linked_task_id is None:
        return
    ensure_issue_readable(db, user, linked_task_id)
    if not _meeting_task_link_exists(db, meeting_id=meeting.id, issue_id=linked_task_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Linked task must already be attached to the meeting.",
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
    mime_type = _require_allowed_mime(payload.mime_type)
    _validate_linked_task_id(db, meeting=meeting, user=user, linked_task_id=payload.linked_task_id)

    # Idempotent resume: same user + same idempotency key → return existing row.
    # This must come BEFORE the cross-user lock check so that retrying a request
    # the user already owns never trips the "someone else is recording" guard.
    existing = db.scalar(
        select(MeetingRecordingStaging).where(
            MeetingRecordingStaging.meeting_id == meeting.id,
            MeetingRecordingStaging.uploaded_by_id == user.id,
            MeetingRecordingStaging.idempotency_key == payload.idempotency_key,
            MeetingRecordingStaging.completed_at.is_(None),
        )
    )
    if existing is not None:
        return _serialize_staging(existing)

    # Single-recorder lock: only one user may have an active staging on a
    # meeting at any time. We serialize concurrent inits by acquiring a row
    # lock on the meeting before inspecting active staging rows.
    #
    # Stale stagings (recorder crashed / network died → no chunk for >
    # RECORDING_STALE_AFTER_SECONDS) are treated as released so other users
    # can take over. The abandoned row stays in the DB; only the lock relaxes.
    db.execute(
        select(Meeting.id).where(Meeting.id == meeting.id).with_for_update()
    )
    stale_cutoff = _utcnow() - timedelta(seconds=RECORDING_STALE_AFTER_SECONDS)
    other_active = db.scalar(
        select(MeetingRecordingStaging).where(
            MeetingRecordingStaging.meeting_id == meeting.id,
            MeetingRecordingStaging.uploaded_by_id != user.id,
            MeetingRecordingStaging.completed_at.is_(None),
            MeetingRecordingStaging.last_chunk_at >= stale_cutoff,
        )
    )
    if other_active is not None:
        recorder_name = (
            other_active.uploaded_by.full_name
            if other_active.uploaded_by is not None
            else "다른 사용자"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "recording_in_progress",
                "message": f"이미 {recorder_name} 님이 녹음 중입니다.",
                "active_recorder_id": other_active.uploaded_by_id,
                "active_recorder_name": recorder_name,
                "active_staging_id": other_active.id,
            },
        )

    staging_id = new_id()
    spool_dir = _spool_dir_for_recording(staging_id)
    spool_dir.mkdir(parents=True, exist_ok=True)
    staging = MeetingRecordingStaging(
        id=staging_id,
        meeting_id=meeting.id,
        uploaded_by_id=user.id,
        idempotency_key=payload.idempotency_key,
        status="recording",
        spool_path=str(spool_dir),
        storage_key=_storage_key_for_recording(meeting.id, staging_id, mime_type),
        mime_type=mime_type,
        linked_task_id=payload.linked_task_id,
        chunks_meta={},
    )
    db.add(staging)
    db.commit()
    db.refresh(staging)
    return _serialize_staging(staging)


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
    if seq < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk sequence must be non-negative.")

    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    staging = _load_staging_or_404(db, meeting_id=meeting.id, staging_id=staging_id)
    if staging.uploaded_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the uploader can resume this staging.")
    if staging.completed_at is not None or staging.status == "promoted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recording staging is already finalized.")

    data = await upload.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty recording chunk.")

    digest = hashlib.sha256(data).hexdigest()
    if chunk_sha256 and chunk_sha256 != digest:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chunk checksum mismatch.")

    settings = get_settings()
    if staging.bytes_received + len(data) > settings.recording_max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Recording exceeds the configured size limit.",
        )

    meta = dict(staging.chunks_meta or {})
    existing = meta.get(str(seq))
    if existing is not None:
        if existing.get("sha256") != digest or int(existing.get("size", -1)) != len(data):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Chunk payload conflicts with existing sequence.")
        return RecordingChunkAck(seq=seq, bytes_received=staging.bytes_received, highest_seq=staging.highest_seq)

    _fsync_path(_chunk_path(staging.spool_path, seq), data)
    meta[str(seq)] = {
        "size": len(data),
        "sha256": digest,
        "stored_at": _utcnow().isoformat(),
    }
    staging.chunks_meta = meta
    staging.bytes_received += len(data)
    staging.chunk_count += 1
    staging.highest_seq = max(staging.highest_seq, seq)
    staging.last_chunk_at = _utcnow()
    db.add(staging)
    db.commit()
    return RecordingChunkAck(seq=seq, bytes_received=staging.bytes_received, highest_seq=staging.highest_seq)


def list_my_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
) -> list[RecordingStagingItem]:
    meeting = meeting_service._load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    cutoff = _utcnow() - timedelta(hours=get_settings().recording_staging_retention_hours)
    items = db.scalars(
        select(MeetingRecordingStaging)
        .where(
            MeetingRecordingStaging.meeting_id == meeting.id,
            MeetingRecordingStaging.uploaded_by_id == user.id,
            MeetingRecordingStaging.completed_at.is_(None),
            MeetingRecordingStaging.started_at >= cutoff,
        )
        .order_by(MeetingRecordingStaging.started_at.asc())
    ).all()
    return [_serialize_staging(item) for item in items]


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
    staging = _load_staging_or_404(db, meeting_id=meeting.id, staging_id=staging_id)
    if staging.uploaded_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the uploader can discard this staging.")
    if staging.promoted_recording_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Finalized recording staging cannot be discarded.")
    _cleanup_spool_dir(staging.spool_path)
    db.delete(staging)
    db.commit()


def _assert_contiguous_chunks(staging: MeetingRecordingStaging) -> list[int]:
    if staging.highest_seq < 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No uploaded chunks to finalize.")
    seqs = sorted(int(seq) for seq in (staging.chunks_meta or {}).keys())
    expected = list(range(seqs[0], seqs[-1] + 1))
    if seqs != expected:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Recording chunks are incomplete.")
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
    staging = _load_staging_or_404(db, meeting_id=meeting.id, staging_id=staging_id)
    if staging.uploaded_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the uploader can finalize this recording.")

    if staging.promoted_recording_id:
        fresh = meeting_service._load_meeting(db, workspace, meeting.id)
        return meeting_service._serialize_meeting(db, fresh)

    staging.status = "assembling"
    staging.duration_sec_estimate = payload.duration_sec_estimate
    db.add(staging)
    db.commit()

    assembled_path = _assemble_chunks(staging)

    staging = _load_staging_or_404(db, meeting_id=meeting.id, staging_id=staging_id)
    if staging.promoted_recording_id:
        fresh = meeting_service._load_meeting(db, workspace, meeting.id)
        return meeting_service._serialize_meeting(db, fresh)

    staging.status = "uploading"
    db.add(staging)
    db.commit()

    settings = get_settings()
    client = get_minio_client()
    client.fput_object(
        settings.minio_bucket,
        staging.storage_key,
        str(assembled_path),
        content_type=staging.mime_type,
    )

    recording = db.get(MeetingRecording, staging.id)
    if recording is None:
        recording = MeetingRecording(
            id=staging.id,
            meeting_id=meeting.id,
            storage_key=staging.storage_key,
            duration_sec=payload.duration_sec_estimate,
            file_size=staging.bytes_received,
            mime_type=staging.mime_type,
            idempotency_key=staging.idempotency_key,
            uploaded_by_id=user.id,
            source="live_recording",
            transcription_status="pending",
            progress_pct=10,
            linked_task_id=staging.linked_task_id,
        )
        db.add(recording)
        db.flush()

    staging.promoted_recording_id = recording.id
    staging.completed_at = _utcnow()
    staging.status = "promoted"
    db.add(staging)
    db.add(recording)
    db.commit()
    _enqueue_pipeline_or_mark_failed(db, recording=recording)
    _cleanup_spool_dir(staging.spool_path)
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
    mime_type = _require_allowed_mime(upload.content_type)
    _validate_linked_task_id(db, meeting=meeting, user=user, linked_task_id=linked_task_id)
    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded recording file is empty.")
    settings = get_settings()
    if len(data) > settings.recording_max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Recording exceeds the configured size limit.",
        )

    recording_id = new_id()
    storage_key = _storage_key_for_recording(meeting.id, recording_id, mime_type)
    from io import BytesIO

    get_minio_client().put_object(
        settings.minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=mime_type,
    )

    recording = MeetingRecording(
        id=recording_id,
        meeting_id=meeting.id,
        storage_key=storage_key,
        duration_sec=None,
        file_size=len(data),
        mime_type=mime_type,
        idempotency_key=new_id(),
        uploaded_by_id=user.id,
        source="manual_upload",
        transcription_status="pending",
        progress_pct=10,
        linked_task_id=linked_task_id,
    )
    db.add(recording)
    db.commit()
    _enqueue_pipeline_or_mark_failed(db, recording=recording)
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
    recording = _load_recording_or_404(db, meeting_id=meeting.id, recording_id=recording_id)
    if recording.transcription_status == "cancelled":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording is not available.")
    expires_at = _utcnow() + timedelta(hours=1)
    url = get_minio_client().presigned_get_object(
        get_settings().minio_bucket,
        recording.storage_key,
        expires=timedelta(hours=1),
    )
    return RecordingPlaybackResponse(url=url, expires_at=expires_at)


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
    recording = _load_recording_or_404(db, meeting_id=meeting.id, recording_id=recording_id)
    if recording.transcription_status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed recordings can be retried.")
    recording.transcription_status = "pending"
    recording.progress_pct = 10
    recording.failure_reason = None
    recording.celery_task_id = None
    db.add(recording)
    db.commit()
    _enqueue_pipeline_or_mark_failed(db, recording=recording)
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

    recording = db.scalar(
        select(MeetingRecording).where(
            MeetingRecording.id == recording_id,
            MeetingRecording.meeting_id == meeting.id,
        )
    )
    if recording is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found.",
        )

    if recording.uploaded_by_id != user.id and meeting.organizer_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting organizer or the recording uploader can delete this recording.",
        )

    if recording.celery_task_id:
        revoke_recording_task(recording.celery_task_id)

    settings = get_settings()
    client = get_minio_client()
    try:
        client.remove_object(settings.minio_bucket, recording.storage_key)
    except Exception:
        # The DB row deletion is the source of truth for "deleted". If the
        # blob removal fails, the orphan-media sweeper will pick it up later.
        pass

    # The promoted staging row still has a FK on this recording. Clean up the
    # staging artifact entirely (spool dir + DB row) so the FK is gone before
    # we delete the recording itself. The staging is a transient upload
    # artifact; once the recording is removed, there's no reason to keep it.
    promoted_stagings = db.scalars(
        select(MeetingRecordingStaging).where(
            MeetingRecordingStaging.promoted_recording_id == recording.id,
        )
    ).all()
    for staging in promoted_stagings:
        _cleanup_spool_dir(staging.spool_path)
        db.delete(staging)
    db.flush()

    db.delete(recording)
    from aidoo_api.domains.meeting.rag_sync import enqueue_meeting_rag_sync
    from aidoo_api.domains.rag.contracts import RagSyncOperation

    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()

    fresh = meeting_service._load_meeting(db, workspace, meeting.id)
    return meeting_service._serialize_meeting(db, fresh)


def cleanup_meeting_recordings(db: Session, *, meeting: Meeting) -> None:
    settings = get_settings()
    client = get_minio_client()
    recordings = db.scalars(
        select(MeetingRecording).where(MeetingRecording.meeting_id == meeting.id)
    ).all()
    staging_rows = db.scalars(
        select(MeetingRecordingStaging).where(MeetingRecordingStaging.meeting_id == meeting.id)
    ).all()

    for recording in recordings:
        if recording.celery_task_id:
            revoke_recording_task(recording.celery_task_id)
        try:
            client.remove_object(settings.minio_bucket, recording.storage_key)
        except Exception:
            pass
        recording.transcription_status = "cancelled"
        db.add(recording)

    for staging in staging_rows:
        _cleanup_spool_dir(staging.spool_path)
        db.delete(staging)

    db.flush()


def cleanup_stale_staging_once(db: Session) -> dict[str, int]:
    cutoff = _utcnow() - timedelta(hours=get_settings().recording_staging_retention_hours)
    rows = db.scalars(
        select(MeetingRecordingStaging).where(
            MeetingRecordingStaging.completed_at.is_(None),
            MeetingRecordingStaging.last_chunk_at < cutoff,
        )
    ).all()
    deleted = 0
    for staging in rows:
        _cleanup_spool_dir(staging.spool_path)
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
    staging = _load_staging_or_404(db, meeting_id=meeting.id, staging_id=staging_id)
    if staging.uploaded_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the uploader can read this staging.")
    assembled_path = _assemble_chunks(staging)
    return assembled_path.read_bytes()
