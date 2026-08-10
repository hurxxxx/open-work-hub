from __future__ import annotations

import hashlib
import socket
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from celery import Celery, chain
from fastapi import Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import get_settings
from open_alm_api.core.worker_task_publisher import create_fail_fast_celery_publisher
from open_alm_api.core.worker_queue_contract import MEETING_TRANSCRIBE_QUEUE
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.meeting.models import Meeting
from open_alm_api.domains.recording import blob_store
from open_alm_api.domains.recording.chunk_sequence import plan_chunk_assembly
from open_alm_api.domains.recording.target_plan import (
    RecordingTargetRef,
    plan_recording_ingest_targets,
    recording_target_ref,
)
from open_alm_api.domains.recording.target_access import (
    can_attach_recording_target,
    can_detach_recording_target,
    can_view_recording_target,
    recording_access_allowed,
)
from open_alm_api.domains.recording.target_projection import (
    serialize_recording_with_target_titles as _serialize_recording,
    serialize_recordings_with_target_titles as _serialize_recordings,
)
from open_alm_api.domains.recording.initial_target import resolve_initial_recording_target
from open_alm_api.domains.recording.models import Recording, RecordingTarget, RecordingStaging
from open_alm_api.domains.recording.schemas import (
    RecordingTargetCreateRequest,
    RecordingListResponse,
    RecordingOut,
    RecordingPlaybackResponse,
    RecordingUpdateRequest,
    RecordingUploadChunkAck,
    RecordingUploadCompleteRequest,
    RecordingUploadInitRequest,
    RecordingUploadOut,
)
from open_alm_api.domains.recording.tus_protocol import (
    parse_checksum,
    parse_upload_metadata,
    response_headers as tus_response_headers,
    upload_length_from_meta,
    with_upload_length,
)


_AUDIO_EXTENSIONS = {
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
ENQUEUE_FAILURE_REASON = (
    "Background processing queue is unavailable. Raw audio was saved; retry later."
)
RECORDING_STALE_AFTER_SECONDS = 60
_STAGING_META_LINKED_TASK_ID = "__linked_task_id"
_STAGING_META_TITLE = "__title"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _load_recording(db: Session, recording_id: str) -> Recording | None:
    return db.scalar(
        select(Recording)
        .options(selectinload(Recording.targets))
        .where(Recording.id == recording_id)
    )


def _load_recording_or_404(db: Session, recording_id: str) -> Recording:
    recording = _load_recording(db, recording_id)
    if recording is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    return recording


def _load_recording_for_update_or_404(db: Session, recording_id: str) -> Recording:
    recording = db.scalar(
        select(Recording)
        .options(selectinload(Recording.targets))
        .where(Recording.id == recording_id)
        .with_for_update()
    )
    if recording is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    return recording


def _ensure_recording_access(
    db: Session, *, workspace: Workspace, user: User, recording: Recording
) -> None:
    if not recording_access_allowed(db, workspace=workspace, user=user, recording=recording):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.access_required",
        )


def _ensure_recording_owner(*, user: User, recording: Recording) -> None:
    if recording.owner_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.owner_required",
        )


def _require_allowed_mime(mime_type: str | None) -> str:
    raw = (mime_type or "").strip().lower()
    if raw in _AUDIO_EXTENSIONS:
        return raw
    base = raw.split(";", 1)[0].strip()
    if base in _AUDIO_EXTENSIONS:
        return base
    raise localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="recording.unsupported_audio_format",
    )


def _extension_for_mime(mime_type: str) -> str:
    return _AUDIO_EXTENSIONS.get(mime_type, Path(mime_type.split("/", 1)[-1]).suffix or ".bin")


def _default_title(started_at: datetime) -> str:
    return f"Recording {started_at:%Y-%m-%d %H:%M:%S UTC}"


@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    return create_fail_fast_celery_publisher(
        "open_alm_api_recording_app",
        broker=settings.worker_broker_url,
        backend=settings.worker_result_backend,
    )


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
        celery_client.signature("recording.transcribe", args=[recording_id], immutable=True),
        celery_client.signature("recording.create_raw_transcript_doc"),
        celery_client.signature("recording.analyze_transcript"),
        celery_client.signature("recording.verify_transcript_summary"),
        celery_client.signature("recording.create_minutes_doc"),
    ).apply_async(queue=MEETING_TRANSCRIBE_QUEUE, retry=False)
    return str(result.id)


def revoke_recording_task(task_id: str) -> None:
    if not task_id:
        return
    try:
        _get_celery_client().control.revoke(task_id, terminate=True, signal="SIGKILL")
    except Exception:
        pass


def _recording_has_meeting_target(recording: Recording) -> bool:
    return any(
        target.target_app == "meeting" and target.target_type == "meeting"
        for target in recording.targets
    )


def _enqueue_pipeline_or_mark_failed(db: Session, *, recording: Recording) -> None:
    if recording.celery_task_id:
        return
    if not _broker_is_reachable():
        recording.transcript_status = "failed"
        recording.failure_reason = ENQUEUE_FAILURE_REASON
        recording.updated_at = _utcnow()
        db.add(recording)
        db.commit()
        db.refresh(recording)
        return
    try:
        recording.celery_task_id = enqueue_recording_pipeline(recording.id)
        recording.transcript_status = "pending"
        recording.failure_reason = None
    except Exception:
        recording.transcript_status = "failed"
        recording.failure_reason = ENQUEUE_FAILURE_REASON
    recording.updated_at = _utcnow()
    db.add(recording)
    db.commit()
    db.refresh(recording)


def _failed_filter():
    return or_(
        Recording.audio_status == "failed",
        Recording.transcript_status == "failed",
        Recording.raw_transcript_doc_status == "failed",
        Recording.minutes_doc_status == "failed",
        Recording.meeting_insight_status == "failed",
    )


def _processing_filter():
    return or_(
        Recording.audio_status == "uploading",
        Recording.transcript_status == "transcribing",
        Recording.raw_transcript_doc_status == "creating",
        Recording.minutes_doc_status == "creating",
        Recording.meeting_insight_status.in_(["pending", "extracting"]),
    )


def _staging_linked_task_id(staging: RecordingStaging) -> str | None:
    value = (staging.chunks_meta or {}).get(_STAGING_META_LINKED_TASK_ID)
    return value if isinstance(value, str) and value.strip() else None


def _staging_title(staging: RecordingStaging) -> str | None:
    value = (staging.chunks_meta or {}).get(_STAGING_META_TITLE)
    return value if isinstance(value, str) and value.strip() else None


def _staging_tus_upload_length(staging: RecordingStaging) -> int | None:
    return upload_length_from_meta(staging.chunks_meta)


def _serialize_staging(staging: RecordingStaging) -> RecordingUploadOut:
    return RecordingUploadOut(
        id=staging.id,
        workspace_id=staging.workspace_id,
        uploaded_by_id=staging.uploaded_by_id,
        idempotency_key=staging.idempotency_key,
        status=staging.status,
        mime_type=staging.mime_type,
        bytes_received=staging.bytes_received,
        chunk_count=staging.chunk_count,
        highest_seq=staging.highest_seq,
        initial_target_app=staging.initial_target_app,
        initial_target_type=staging.initial_target_type,
        initial_target_id=staging.initial_target_id,
        linked_task_id=_staging_linked_task_id(staging),
        started_at=staging.started_at,
        last_chunk_at=staging.last_chunk_at,
        completed_at=staging.completed_at,
    )


def staging_is_stale(staging: RecordingStaging, *, now: datetime | None = None) -> bool:
    if staging.completed_at is not None:
        return True
    reference = now or _utcnow()
    threshold = reference - timedelta(seconds=RECORDING_STALE_AFTER_SECONDS)
    return staging.last_chunk_at < threshold


def _load_staging_or_404(db: Session, *, workspace: Workspace, staging_id: str) -> RecordingStaging:
    staging = db.scalar(
        select(RecordingStaging).where(
            RecordingStaging.id == staging_id,
            RecordingStaging.workspace_id == workspace.id,
        )
    )
    if staging is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="recording.staging_not_found",
        )
    return staging


def load_staging_or_404(db: Session, *, workspace: Workspace, staging_id: str) -> RecordingStaging:
    return _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)


def assemble_staging_chunks(staging: RecordingStaging) -> Path:
    return blob_store.assemble_chunks(
        spool_path=staging.spool_path,
        sequences=_assert_contiguous_chunks(staging),
    )


def _next_target_sort_order(
    db: Session,
    *,
    target_app: str,
    target_type: str,
    target_id: str,
) -> int:
    if target_app == "meeting" and target_type == "meeting":
        db.execute(select(Meeting.id).where(Meeting.id == target_id).with_for_update())
    current_max = db.scalar(
        select(func.max(RecordingTarget.sort_order)).where(
            RecordingTarget.target_app == target_app,
            RecordingTarget.target_type == target_type,
            RecordingTarget.target_id == target_id,
        )
    )
    return int(current_max or 0) + 1


def _target_for_recording(
    db: Session,
    *,
    recording_id: str,
    target_app: str,
    target_type: str,
    target_id: str,
    added_by_id: str,
    is_primary: bool = True,
    sort_order: int | None = None,
) -> RecordingTarget:
    if sort_order is None:
        sort_order = _next_target_sort_order(
            db,
            target_app=target_app,
            target_type=target_type,
            target_id=target_id,
        )
    return RecordingTarget(
        id=new_id(),
        recording_id=recording_id,
        target_app=target_app,
        target_type=target_type,
        target_id=target_id,
        is_primary=is_primary,
        sort_order=sort_order,
        added_by_id=added_by_id,
    )


def _new_saved_recording(
    *,
    recording_id: str,
    workspace_id: str,
    owner_id: str,
    title: str,
    started_at: datetime,
    ended_at: datetime | None,
    duration_sec: int | None,
    source: str,
    storage_key: str,
    file_size: int,
    mime_type: str,
) -> Recording:
    return Recording(
        id=recording_id,
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=title,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=duration_sec,
        source=source,
        storage_key=storage_key,
        file_size=file_size,
        mime_type=mime_type,
        audio_status="saved",
        transcript_status="pending",
        raw_transcript_doc_status="pending",
        minutes_doc_status="pending",
        meeting_insight_status="none",
        progress_pct=0,
    )


def _add_initial_recording_targets(
    db: Session,
    *,
    recording_id: str,
    added_by_id: str,
    initial_target: RecordingTargetRef | None,
    linked_task_id: str | None,
) -> str | None:
    primary_target_id: str | None = None
    for plan in plan_recording_ingest_targets(
        initial_target=initial_target,
        linked_task_id=linked_task_id,
    ):
        target = _target_for_recording(
            db,
            recording_id=recording_id,
            target_app=plan.ref.target_app,
            target_type=plan.ref.target_type,
            target_id=plan.ref.target_id,
            added_by_id=added_by_id,
            is_primary=plan.is_primary,
            sort_order=plan.sort_order,
        )
        if plan.is_primary:
            primary_target_id = target.id
        db.add(target)
    return primary_target_id


def init_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    payload: RecordingUploadInitRequest,
) -> RecordingUploadOut:
    mime_type = _require_allowed_mime(payload.mime_type)
    initial_resolution = resolve_initial_recording_target(
        db,
        workspace=workspace,
        user=user,
        target_app=payload.initial_target_app,
        target_type=payload.initial_target_type,
        target_id=payload.initial_target_id,
        linked_task_id=payload.linked_task_id,
    )
    initial_target = initial_resolution.ref
    linked_task_id = initial_resolution.linked_task_id

    existing = db.scalar(
        select(RecordingStaging).where(
            RecordingStaging.workspace_id == workspace.id,
            RecordingStaging.uploaded_by_id == user.id,
            RecordingStaging.idempotency_key == payload.idempotency_key,
            RecordingStaging.completed_at.is_(None),
        )
    )
    if existing is not None:
        return _serialize_staging(existing)

    if (
        initial_target is not None
        and initial_target.target_app == "meeting"
        and initial_target.target_type == "meeting"
    ):
        meeting_id = initial_target.target_id
        db.execute(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update())
        stale_cutoff = _utcnow() - timedelta(seconds=RECORDING_STALE_AFTER_SECONDS)
        other_active = db.scalar(
            select(RecordingStaging)
            .options(selectinload(RecordingStaging.uploaded_by))
            .where(
                RecordingStaging.workspace_id == workspace.id,
                RecordingStaging.initial_target_app == "meeting",
                RecordingStaging.initial_target_type == "meeting",
                RecordingStaging.initial_target_id == meeting_id,
                RecordingStaging.uploaded_by_id != user.id,
                RecordingStaging.completed_at.is_(None),
                RecordingStaging.last_chunk_at >= stale_cutoff,
            )
        )
        if other_active is not None:
            recorder_name = (
                other_active.uploaded_by.full_name
                if other_active.uploaded_by is not None
                else "다른 사용자"
            )
            raise localized_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                code="meeting.recording_in_progress",
                recorder_name=recorder_name,
                active_recorder_id=other_active.uploaded_by_id,
                active_recorder_name=recorder_name,
                active_staging_id=other_active.id,
            )

    staging_id = new_id()
    started_at = _utcnow()
    spool_store = blob_store.default_spool_store()
    spool_dir = spool_store.allocate(staging_id)
    meta: dict[str, str] = {}
    if linked_task_id:
        meta[_STAGING_META_LINKED_TASK_ID] = linked_task_id
    title = payload.title.strip() if payload.title else ""
    if title:
        meta[_STAGING_META_TITLE] = title
    staging = RecordingStaging(
        id=staging_id,
        workspace_id=workspace.id,
        uploaded_by_id=user.id,
        idempotency_key=payload.idempotency_key,
        status="recording",
        spool_path=str(spool_dir),
        storage_key=blob_store.build_recording_storage_key(
            workspace_id=workspace.id,
            user_id=user.id,
            recording_id=staging_id,
            started_at=started_at,
            file_extension=_extension_for_mime(mime_type),
        ),
        mime_type=mime_type,
        chunks_meta=meta,
        started_at=started_at,
        last_chunk_at=started_at,
        initial_target_app=initial_target.target_app if initial_target else None,
        initial_target_type=initial_target.target_type if initial_target else None,
        initial_target_id=initial_target.target_id if initial_target else None,
    )
    db.add(staging)
    db.commit()
    db.refresh(staging)
    return _serialize_staging(staging)


def init_tus_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    upload_metadata: str | None,
    upload_length: int | None,
) -> RecordingUploadOut:
    metadata = parse_upload_metadata(upload_metadata)
    idempotency_key = metadata.get("idempotency_key") or metadata.get("idempotencyKey")
    mime_type = metadata.get("mime_type") or metadata.get("mimeType")
    if not idempotency_key or not mime_type:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.tus_metadata_required",
            headers=tus_response_headers(),
        )
    staging = init_staging(
        db,
        workspace=workspace,
        user=user,
        payload=RecordingUploadInitRequest(
            idempotency_key=idempotency_key,
            mime_type=mime_type,
            title=metadata.get("title") or None,
            initial_target_app=metadata.get("initial_target_app")
            or metadata.get("initialTargetApp")
            or None,
            initial_target_type=metadata.get("initial_target_type")
            or metadata.get("initialTargetType")
            or None,
            initial_target_id=metadata.get("initial_target_id")
            or metadata.get("initialTargetId")
            or None,
            linked_task_id=metadata.get("linked_task_id") or metadata.get("linkedTaskId") or None,
        ),
    )
    if upload_length is not None:
        current = _load_staging_or_404(db, workspace=workspace, staging_id=staging.id)
        current.chunks_meta = with_upload_length(current.chunks_meta, upload_length)
        db.add(current)
        db.commit()
        db.refresh(current)
        return _serialize_staging(current)
    return staging


def _ensure_staging_writable(
    staging: RecordingStaging,
    *,
    user: User,
) -> None:
    if staging.uploaded_by_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.uploader_resume_required",
        )
    if staging.completed_at is not None or staging.status == "promoted":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.staging_finalized",
        )


def _store_chunk_bytes(
    db: Session,
    *,
    staging: RecordingStaging,
    seq: int,
    data: bytes,
    chunk_sha256: str | None,
) -> RecordingUploadChunkAck:
    if seq < 0:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.chunk_sequence_non_negative",
        )
    if not data:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.empty_chunk",
        )
    digest = hashlib.sha256(data).hexdigest()
    if chunk_sha256 and chunk_sha256 != digest:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.chunk_checksum_mismatch",
        )

    settings = get_settings()
    if staging.bytes_received + len(data) > settings.recording_max_size_bytes:
        raise localized_http_exception(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="recording.size_limit_exceeded",
        )

    meta = dict(staging.chunks_meta or {})
    existing = meta.get(str(seq))
    if existing is not None:
        if (
            not isinstance(existing, dict)
            or existing.get("sha256") != digest
            or int(existing.get("size", -1)) != len(data)
        ):
            raise localized_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                code="recording.chunk_payload_conflict",
            )
        return RecordingUploadChunkAck(
            seq=seq,
            bytes_received=staging.bytes_received,
            highest_seq=staging.highest_seq,
        )

    blob_store.default_spool_store().write_chunk(
        spool_path=staging.spool_path,
        seq=seq,
        data=data,
    )
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
    return RecordingUploadChunkAck(
        seq=seq,
        bytes_received=staging.bytes_received,
        highest_seq=staging.highest_seq,
    )


async def upload_chunk(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    staging_id: str,
    seq: int,
    upload: UploadFile,
    chunk_sha256: str | None,
) -> RecordingUploadChunkAck:
    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
    _ensure_staging_writable(staging, user=user)
    data = await upload.read()
    return _store_chunk_bytes(
        db,
        staging=staging,
        seq=seq,
        data=data,
        chunk_sha256=chunk_sha256,
    )


def read_tus_upload(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    staging_id: str,
) -> RecordingStaging:
    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
    if staging.uploaded_by_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.uploader_read_staging_required",
            headers=tus_response_headers(upload_offset=staging.bytes_received),
        )
    return staging


def upload_tus_chunk(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    staging_id: str,
    upload_offset: int,
    data: bytes,
    upload_checksum: str | None,
    upload_length: int | None,
) -> RecordingStaging:
    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
    _ensure_staging_writable(staging, user=user)
    if upload_offset != staging.bytes_received:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.tus_offset_conflict",
            headers=tus_response_headers(
                upload_offset=staging.bytes_received,
                upload_length=_staging_tus_upload_length(staging),
            ),
        )
    if upload_length is not None:
        staging.chunks_meta = with_upload_length(staging.chunks_meta, upload_length)
    expected_length = (
        upload_length if upload_length is not None else _staging_tus_upload_length(staging)
    )
    if expected_length is not None and upload_offset + len(data) > expected_length:
        raise localized_http_exception(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="recording.size_limit_exceeded",
            headers=tus_response_headers(
                upload_offset=staging.bytes_received,
                upload_length=expected_length,
            ),
        )
    checksum = parse_checksum(upload_checksum)
    _store_chunk_bytes(
        db,
        staging=staging,
        seq=staging.highest_seq + 1,
        data=data,
        chunk_sha256=checksum,
    )
    return _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)


def list_my_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    initial_target_app: str | None = None,
    initial_target_type: str | None = None,
    initial_target_id: str | None = None,
) -> list[RecordingUploadOut]:
    cutoff = _utcnow() - timedelta(hours=get_settings().recording_staging_retention_hours)
    query = select(RecordingStaging).where(
        RecordingStaging.workspace_id == workspace.id,
        RecordingStaging.uploaded_by_id == user.id,
        RecordingStaging.completed_at.is_(None),
        RecordingStaging.started_at >= cutoff,
    )
    if initial_target_app is not None:
        query = query.where(RecordingStaging.initial_target_app == initial_target_app)
    if initial_target_type is not None:
        query = query.where(RecordingStaging.initial_target_type == initial_target_type)
    if initial_target_id is not None:
        query = query.where(RecordingStaging.initial_target_id == initial_target_id)
    rows = db.scalars(query.order_by(RecordingStaging.started_at.asc())).all()
    return [_serialize_staging(item) for item in rows]


def discard_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    staging_id: str,
) -> None:
    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
    if staging.uploaded_by_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.uploader_discard_required",
        )
    if staging.promoted_recording_id:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.finalized_staging_discard_denied",
        )
    blob_store.default_spool_store().cleanup(staging.spool_path)
    db.delete(staging)
    db.commit()


def _assert_contiguous_chunks(staging: RecordingStaging) -> list[int]:
    plan = plan_chunk_assembly(
        chunks_meta=staging.chunks_meta,
        highest_seq=staging.highest_seq,
    )
    if plan.error == "no_chunks_to_finalize":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.no_chunks_to_finalize",
        )
    if plan.error == "chunks_incomplete":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.chunks_incomplete",
        )
    return plan.sequences


def complete_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    staging_id: str,
    payload: RecordingUploadCompleteRequest,
) -> RecordingOut:
    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
    if staging.uploaded_by_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.uploader_finalize_required",
        )
    if staging.promoted_recording_id:
        recording = _load_recording_or_404(db, staging.promoted_recording_id)
        return _serialize_recording(db, recording)

    staging.status = "assembling"
    staging.duration_sec_estimate = payload.duration_sec_estimate
    db.add(staging)
    db.commit()
    spool_store = blob_store.default_spool_store()
    assembled_path = spool_store.assemble_chunks(
        spool_path=staging.spool_path,
        sequences=_assert_contiguous_chunks(staging),
    )

    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
    if staging.promoted_recording_id:
        recording = _load_recording_or_404(db, staging.promoted_recording_id)
        return _serialize_recording(db, recording)

    staging.status = "uploading"
    db.add(staging)
    db.commit()

    blob_store.put_recording_file(
        storage_key=staging.storage_key,
        path=assembled_path,
        content_type=staging.mime_type,
    )

    title = (payload.title or _staging_title(staging) or "").strip()
    recording = _new_saved_recording(
        recording_id=staging.id,
        workspace_id=workspace.id,
        owner_id=user.id,
        title=title or _default_title(staging.started_at),
        started_at=staging.started_at,
        ended_at=_utcnow(),
        duration_sec=payload.duration_sec_estimate,
        source=payload.source,
        storage_key=staging.storage_key,
        file_size=staging.bytes_received,
        mime_type=staging.mime_type,
    )
    db.add(recording)
    db.flush()

    linked_task_id = _staging_linked_task_id(staging)
    primary_target_id = _add_initial_recording_targets(
        db,
        recording_id=recording.id,
        added_by_id=user.id,
        initial_target=recording_target_ref(
            staging.initial_target_app,
            staging.initial_target_type,
            staging.initial_target_id,
        ),
        linked_task_id=linked_task_id,
    )

    staging.promoted_recording_id = recording.id
    staging.completed_at = _utcnow()
    staging.status = "promoted"
    db.add(staging)
    db.add(recording)
    db.commit()
    if primary_target_id:
        db.expire(recording, ["targets"])
    fresh = _load_recording_or_404(db, recording.id)
    _enqueue_pipeline_or_mark_failed(db, recording=fresh)
    spool_store.cleanup(staging.spool_path)
    fresh = _load_recording_or_404(db, recording.id)
    return _serialize_recording(db, fresh)


def list_recordings(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    view: str = "mine",
    from_: datetime | None = None,
    to: datetime | None = None,
    target_app: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> RecordingListResponse:
    query = (
        select(Recording)
        .options(selectinload(Recording.targets))
        .where(Recording.workspace_id == workspace.id)
    )
    if view != "archived":
        query = query.where(Recording.trashed_at.is_(None))
    else:
        query = query.where(Recording.trashed_at.is_not(None))

    has_target_filter = any([target_app, target_type, target_id])
    if has_target_filter:
        if not (target_app and target_type and target_id):
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="recording.target_filter_required",
            )
        if not can_view_recording_target(
            db,
            user=user,
            workspace=workspace,
            target_app=target_app,
            target_type=target_type,
            target_id=target_id,
        ):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="recording.target_access_required",
            )
        query = query.join(RecordingTarget).where(
            RecordingTarget.target_app == target_app,
            RecordingTarget.target_type == target_type,
            RecordingTarget.target_id == target_id,
        )
    else:
        query = query.where(Recording.owner_id == user.id)

    if view == "failed":
        query = query.where(_failed_filter())
    elif view == "processing":
        query = query.where(_processing_filter())
    elif view == "needs_review":
        query = query.where(
            Recording.transcript_status == "done",
            Recording.minutes_doc_status != "done",
        )
    if from_ is not None:
        query = query.where(Recording.started_at >= from_)
    if to is not None:
        query = query.where(Recording.started_at <= to)

    recordings = db.scalars(
        query.order_by(Recording.started_at.desc(), Recording.created_at.desc())
    ).all()
    return RecordingListResponse(items=_serialize_recordings(db, recordings))


def get_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
) -> RecordingOut:
    recording = _load_recording_or_404(db, recording_id)
    _ensure_recording_access(db, workspace=workspace, user=user, recording=recording)
    return _serialize_recording(db, recording)


def update_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
    payload: RecordingUpdateRequest,
) -> RecordingOut:
    recording = _load_recording_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    _ensure_recording_owner(user=user, recording=recording)
    if payload.title is not None:
        recording.title = payload.title.strip()
    recording.updated_at = _utcnow()
    db.add(recording)
    db.commit()
    db.refresh(recording)
    return _serialize_recording(db, recording)


def delete_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
) -> Response:
    recording = _load_recording_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    _ensure_recording_owner(user=user, recording=recording)
    if recording.celery_task_id:
        revoke_recording_task(recording.celery_task_id)
    recording.trashed_at = _utcnow()
    recording.updated_at = recording.trashed_at
    db.add(recording)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def import_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    upload: UploadFile,
    title: str | None,
    started_at: datetime | None,
    ended_at: datetime | None,
    duration_sec: int | None,
    source: str = "quick_record",
    initial_target_app: str | None = None,
    initial_target_type: str | None = None,
    initial_target_id: str | None = None,
    linked_task_id: str | None = None,
) -> RecordingOut:
    mime_type = _require_allowed_mime(upload.content_type)
    resolved_started_at = _as_utc_naive(started_at) if started_at else _utcnow()
    resolved_ended_at = _as_utc_naive(ended_at) if ended_at else None
    if duration_sec is not None and duration_sec < 0:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.invalid_duration",
        )
    if resolved_ended_at is not None and resolved_ended_at < resolved_started_at:
        resolved_ended_at = resolved_started_at

    data = upload.file.read()
    if not data:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.uploaded_audio_empty",
        )
    settings = get_settings()
    if len(data) > settings.recording_max_size_bytes:
        raise localized_http_exception(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="recording.size_limit_exceeded",
        )
    initial_resolution = resolve_initial_recording_target(
        db,
        workspace=workspace,
        user=user,
        target_app=initial_target_app,
        target_type=initial_target_type,
        target_id=initial_target_id,
        linked_task_id=linked_task_id,
    )
    initial_target = initial_resolution.ref
    normalized_linked_task_id = initial_resolution.linked_task_id

    recording_id = new_id()
    storage_key = blob_store.build_recording_storage_key(
        workspace_id=workspace.id,
        user_id=user.id,
        recording_id=recording_id,
        started_at=resolved_started_at,
        file_extension=_extension_for_mime(mime_type),
    )
    blob_store.put_recording_bytes(
        storage_key=storage_key,
        data=data,
        content_type=mime_type,
    )

    normalized_source = source if source in {"quick_record", "manual_upload"} else "quick_record"
    trimmed_title = title.strip() if title else ""
    recording = _new_saved_recording(
        recording_id=recording_id,
        workspace_id=workspace.id,
        owner_id=user.id,
        title=trimmed_title or _default_title(resolved_started_at),
        started_at=resolved_started_at,
        ended_at=resolved_ended_at,
        duration_sec=duration_sec,
        source=normalized_source,
        storage_key=storage_key,
        file_size=len(data),
        mime_type=mime_type,
    )
    db.add(recording)
    if initial_target is not None:
        db.flush()
        _add_initial_recording_targets(
            db,
            recording_id=recording.id,
            added_by_id=user.id,
            initial_target=initial_target,
            linked_task_id=normalized_linked_task_id,
        )
    db.commit()
    fresh = _load_recording_or_404(db, recording_id)
    _enqueue_pipeline_or_mark_failed(db, recording=fresh)
    fresh = _load_recording_or_404(db, recording_id)
    return _serialize_recording(db, fresh)


def retry_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
) -> RecordingOut:
    recording = _load_recording_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    _ensure_recording_owner(user=user, recording=recording)
    if recording.audio_status != "saved" or not recording.storage_key:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT, code="recording.audio_unavailable"
        )
    if (
        recording.transcript_status == "transcribing"
        or recording.raw_transcript_doc_status == "creating"
        or recording.minutes_doc_status == "creating"
    ):
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT, code="recording.processing_in_progress"
        )
    if (
        recording.transcript_status == "done"
        and recording.raw_transcript_doc_status == "done"
        and recording.minutes_doc_status == "done"
    ):
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT, code="recording.processing_already_done"
        )

    if recording.celery_task_id:
        revoke_recording_task(recording.celery_task_id)
    recording.celery_task_id = None
    recording.failure_reason = None
    if recording.transcript_status != "done":
        recording.transcript_status = "pending"
        recording.transcribe_started_at = None
        recording.transcribe_completed_at = None
        recording.progress_pct = 0
    else:
        recording.progress_pct = max(recording.progress_pct, 60)
    if recording.raw_transcript_doc_status != "done":
        recording.raw_transcript_doc_status = "pending"
        recording.raw_transcript_doc_id = None
    if recording.minutes_doc_status != "done":
        recording.minutes_doc_status = "pending"
        recording.minutes_doc_id = None
    recording.meeting_insight_status = "none"
    recording.updated_at = _utcnow()
    db.add(recording)
    db.commit()
    fresh = _load_recording_or_404(db, recording.id)
    _enqueue_pipeline_or_mark_failed(db, recording=fresh)
    fresh = _load_recording_or_404(db, recording.id)
    return _serialize_recording(db, fresh)


def create_target(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
    payload: RecordingTargetCreateRequest,
) -> RecordingOut:
    recording = _load_recording_for_update_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    _ensure_recording_owner(user=user, recording=recording)
    recording_pk = recording.id
    if not can_attach_recording_target(
        db,
        user=user,
        workspace=workspace,
        target_app=payload.target_app,
        target_type=payload.target_type,
        target_id=payload.target_id,
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.target_attach_required",
        )
    existing = next(
        (
            item
            for item in recording.targets
            if item.target_app == payload.target_app
            and item.target_type == payload.target_type
            and item.target_id == payload.target_id
        ),
        None,
    )
    if payload.is_primary:
        for item in recording.targets:
            if item is not existing and item.is_primary:
                item.is_primary = False
                db.add(item)
        db.flush()
    if existing is None:
        sort_order = payload.sort_order
        if sort_order is None:
            sort_order = _next_target_sort_order(
                db,
                target_app=payload.target_app,
                target_type=payload.target_type,
                target_id=payload.target_id,
            )
        existing = RecordingTarget(
            id=new_id(),
            recording_id=recording.id,
            target_app=payload.target_app,
            target_type=payload.target_type,
            target_id=payload.target_id,
            is_primary=payload.is_primary,
            sort_order=sort_order,
            added_by_id=user.id,
        )
    else:
        if payload.is_primary:
            existing.is_primary = True
        if payload.sort_order is not None:
            existing.sort_order = payload.sort_order
    db.add(existing)
    recording.updated_at = _utcnow()
    db.add(recording)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fresh = _load_recording_or_404(db, recording_pk)
        duplicate = next(
            (
                item
                for item in fresh.targets
                if item.target_app == payload.target_app
                and item.target_type == payload.target_type
                and item.target_id == payload.target_id
            ),
            None,
        )
        if duplicate is None:
            raise
        return _serialize_recording(db, fresh)
    fresh = _load_recording_or_404(db, recording_pk)
    return _serialize_recording(db, fresh)


def delete_target(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
    target_id: str,
) -> RecordingOut:
    recording = _load_recording_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    if recording.owner_id != user.id:
        _ensure_recording_access(db, workspace=workspace, user=user, recording=recording)
    target = next((item for item in recording.targets if item.id == target_id), None)
    if target is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.target_not_found"
        )
    if recording.owner_id != user.id and not can_detach_recording_target(
        db,
        user=user,
        workspace=workspace,
        target=target,
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.target_detach_required",
        )
    db.delete(target)
    recording.updated_at = _utcnow()
    db.add(recording)
    db.commit()
    fresh = _load_recording_or_404(db, recording.id)
    return _serialize_recording(db, fresh)


def _meeting_recording_status(recording: Recording) -> str:
    if (
        recording.audio_status == "failed"
        or recording.transcript_status == "failed"
        or recording.raw_transcript_doc_status == "failed"
        or recording.minutes_doc_status == "failed"
        or recording.meeting_insight_status == "failed"
    ):
        return "failed"
    if recording.minutes_doc_status == "done":
        return "done"
    if recording.minutes_doc_status == "creating":
        return "generating_doc"
    if recording.transcript_status == "done":
        return "summarizing"
    if recording.transcript_status == "transcribing":
        return "transcribing"
    return "pending"


def _linked_task_id(recording: Recording) -> str | None:
    for target in recording.targets:
        if target.target_app == "pms" and target.target_type in {"task", "task"}:
            return target.target_id
    return None


def _meeting_target(recording: Recording, *, meeting_id: str) -> RecordingTarget | None:
    return next(
        (
            target
            for target in recording.targets
            if target.target_app == "meeting"
            and target.target_type == "meeting"
            and target.target_id == meeting_id
        ),
        None,
    )


def list_meeting_recording_outs(db: Session, *, meeting: Meeting) -> list:
    from open_alm_api.domains.meeting.schemas import MeetingRecordingOut

    recordings = (
        db.scalars(
            select(Recording)
            .join(RecordingTarget)
            .options(selectinload(Recording.targets))
            .where(
                Recording.workspace_id == meeting.workspace_id,
                Recording.trashed_at.is_(None),
                RecordingTarget.target_app == "meeting",
                RecordingTarget.target_type == "meeting",
                RecordingTarget.target_id == meeting.id,
            )
            .order_by(
                RecordingTarget.sort_order.asc(), Recording.started_at.asc(), Recording.id.asc()
            )
        )
        .unique()
        .all()
    )
    items = []
    for recording in recordings:
        target = _meeting_target(recording, meeting_id=meeting.id)
        if target is None:
            continue
        items.append(
            MeetingRecordingOut(
                id=recording.id,
                meeting_id=meeting.id,
                uploaded_by_id=recording.owner_id,
                storage_key=recording.storage_key or "",
                duration_sec=recording.duration_sec,
                source=recording.source,
                transcription_status=_meeting_recording_status(recording),
                sequence_no=target.sort_order,
                progress_pct=recording.progress_pct,
                file_size=recording.file_size,
                mime_type=recording.mime_type,
                failure_reason=recording.failure_reason,
                linked_doc_id=recording.minutes_doc_id,
                raw_transcript_doc_id=recording.raw_transcript_doc_id,
                minutes_doc_id=recording.minutes_doc_id,
                linked_task_id=_linked_task_id(recording),
                transcript_extracted=bool((recording.transcript_text or "").strip()),
                summary_generated=recording.minutes_doc_status == "done",
                transcribe_started_at=recording.transcribe_started_at,
                transcribe_completed_at=recording.transcribe_completed_at,
                created_at=recording.created_at,
            )
        )
    return items


def resolve_active_recording_lock(db: Session, *, meeting: Meeting):
    from open_alm_api.domains.meeting.schemas import ActiveRecordingLockOut

    rows = db.scalars(
        select(RecordingStaging)
        .options(selectinload(RecordingStaging.uploaded_by))
        .where(
            RecordingStaging.workspace_id == meeting.workspace_id,
            RecordingStaging.initial_target_app == "meeting",
            RecordingStaging.initial_target_type == "meeting",
            RecordingStaging.initial_target_id == meeting.id,
            RecordingStaging.completed_at.is_(None),
        )
        .order_by(RecordingStaging.started_at.asc())
    ).all()
    active = next((row for row in rows if not staging_is_stale(row)), None)
    if active is None:
        return None
    user_name = active.uploaded_by.full_name if active.uploaded_by is not None else ""
    return ActiveRecordingLockOut(
        staging_id=active.id,
        user_id=active.uploaded_by_id,
        user_name=user_name,
        started_at=active.started_at,
        last_active_at=active.last_chunk_at,
    )


def load_meeting_recording_or_404(
    db: Session,
    *,
    workspace: Workspace,
    meeting_id: str,
    recording_id: str,
) -> Recording:
    recording = db.scalar(
        select(Recording)
        .join(RecordingTarget)
        .options(selectinload(Recording.targets))
        .where(
            Recording.id == recording_id,
            Recording.workspace_id == workspace.id,
            Recording.trashed_at.is_(None),
            RecordingTarget.target_app == "meeting",
            RecordingTarget.target_type == "meeting",
            RecordingTarget.target_id == meeting_id,
        )
    )
    if recording is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="meeting.recording_not_found",
        )
    return recording


def latest_meeting_recording(
    db: Session,
    *,
    workspace_id: str,
    meeting_id: str,
    require_transcript: bool = False,
) -> Recording | None:
    query = (
        select(Recording)
        .join(RecordingTarget)
        .options(selectinload(Recording.targets))
        .where(
            Recording.workspace_id == workspace_id,
            Recording.trashed_at.is_(None),
            RecordingTarget.target_app == "meeting",
            RecordingTarget.target_type == "meeting",
            RecordingTarget.target_id == meeting_id,
        )
        .order_by(RecordingTarget.sort_order.desc(), Recording.started_at.desc())
    )
    if require_transcript:
        query = query.where(Recording.transcript_text.is_not(None))
    return db.scalar(query)


def retry_meeting_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting: Meeting,
    recording_id: str,
) -> RecordingOut:
    recording = load_meeting_recording_or_404(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        recording_id=recording_id,
    )
    if recording.owner_id != user.id and meeting.organizer_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.owner_required",
        )
    if recording.audio_status != "saved" or not recording.storage_key:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.audio_unavailable",
        )
    if _meeting_recording_status(recording) != "failed":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="meeting.only_failed_recordings_retry",
        )
    if recording.celery_task_id:
        revoke_recording_task(recording.celery_task_id)
    recording.celery_task_id = None
    recording.failure_reason = None
    if recording.transcript_status != "done":
        recording.transcript_status = "pending"
        recording.transcribe_started_at = None
        recording.transcribe_completed_at = None
        recording.progress_pct = 0
    else:
        recording.progress_pct = max(recording.progress_pct, 60)
    if recording.raw_transcript_doc_status != "done":
        recording.raw_transcript_doc_status = "pending"
        recording.raw_transcript_doc_id = None
    if recording.minutes_doc_status != "done":
        recording.minutes_doc_status = "pending"
        recording.minutes_doc_id = None
    recording.meeting_insight_status = "none"
    recording.updated_at = _utcnow()
    db.add(recording)
    db.commit()
    fresh = _load_recording_or_404(db, recording.id)
    _enqueue_pipeline_or_mark_failed(db, recording=fresh)
    fresh = _load_recording_or_404(db, recording.id)
    return _serialize_recording(db, fresh)


def archive_meeting_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting: Meeting,
    recording_id: str,
) -> None:
    recording = load_meeting_recording_or_404(
        db,
        workspace=workspace,
        meeting_id=meeting.id,
        recording_id=recording_id,
    )
    if recording.owner_id != user.id and meeting.organizer_id != user.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="meeting.recording_delete_permission",
        )
    if recording.celery_task_id:
        revoke_recording_task(recording.celery_task_id)
    recording.trashed_at = _utcnow()
    recording.updated_at = recording.trashed_at
    db.add(recording)
    db.commit()


def get_recording_playback(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
) -> RecordingPlaybackResponse:
    recording = _load_recording_or_404(db, recording_id)
    _ensure_recording_access(db, workspace=workspace, user=user, recording=recording)
    if not recording.storage_key or recording.audio_status != "saved":
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.audio_unavailable"
        )
    expires_at = _utcnow() + timedelta(hours=1)
    url = (
        f"{get_settings().api_prefix}/workspaces/{workspace.key}/recording"
        f"/recordings/{recording.id}/media"
    )
    return RecordingPlaybackResponse(url=url, expires_at=expires_at)


def _download_filename(recording: Recording) -> str:
    if recording.storage_key:
        filename = Path(recording.storage_key).name
        if filename:
            return filename.replace('"', "")
    return f"{recording.started_at:%Y%m%dT%H%M%SZ}{_extension_for_mime(recording.mime_type)}"


def stream_recording_media(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
) -> StreamingResponse:
    recording = _load_recording_or_404(db, recording_id)
    _ensure_recording_access(db, workspace=workspace, user=user, recording=recording)
    if not recording.storage_key or recording.audio_status != "saved":
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.audio_unavailable"
        )

    return StreamingResponse(
        blob_store.open_recording_stream(storage_key=recording.storage_key),
        media_type=recording.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{_download_filename(recording)}"',
            "Cache-Control": "private, max-age=3600",
        },
    )
