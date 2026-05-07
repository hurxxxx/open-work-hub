from __future__ import annotations

import hashlib
import os
import shutil
import socket
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from celery import Celery, chain
from fastapi import HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import get_minio_client
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.docs.models import NativeDoc
from ai_do_api.domains.docs.registry import (
    ContainerRef,
    container_access_allowed as docs_container_access_allowed,
    project_container_access,
)
from ai_do_api.domains.docs.service import can_read_native_doc_for_rag
from ai_do_api.domains.meeting.models import Meeting, MeetingTaskLink
from ai_do_api.domains.meeting.permissions import is_organizer, is_participant
from ai_do_api.domains.pms.access import _ensure_issue_readable, ensure_issue_attachable
from ai_do_api.domains.pms.models import Issue
from ai_do_api.domains.recording.models import Recording, RecordingContainer, RecordingStaging
from ai_do_api.domains.recording.schemas import (
    RecordingContainerCreateRequest,
    RecordingListResponse,
    RecordingOut,
    RecordingPlaybackResponse,
    RecordingUpdateRequest,
    RecordingUploadChunkAck,
    RecordingUploadCompleteRequest,
    RecordingUploadInitRequest,
    RecordingUploadOut,
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
ENQUEUE_FAILURE_REASON = "Background processing queue is unavailable. Raw audio was saved; retry later."
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
        .options(selectinload(Recording.containers))
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
        .options(selectinload(Recording.containers))
        .where(Recording.id == recording_id)
        .with_for_update()
    )
    if recording is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    return recording


def _container_ref(container: RecordingContainer) -> ContainerRef:
    return ContainerRef(
        app=container.container_app,
        type=container.container_type,
        id=container.container_id,
    )


def _meeting_container_access_allowed(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    container_type: str,
    container_id: str,
) -> bool:
    if container_type != "meeting":
        return False
    meeting = db.scalar(
        select(Meeting).where(
            Meeting.id == container_id,
            Meeting.workspace_id == workspace.id,
        )
    )
    return meeting is not None and is_participant(user, meeting)


def _pms_container_access_allowed(
    db: Session,
    *,
    user: User,
    container_type: str,
    container_id: str,
) -> bool:
    if container_type not in {"issue", "task"}:
        return False
    try:
        _ensure_issue_readable(db, user, container_id)
    except HTTPException:
        return False
    return True


def _docs_container_access_allowed(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    container_type: str,
    container_id: str,
) -> bool:
    if container_type in {"native_doc", "doc"}:
        return can_read_native_doc_for_rag(db, user=user, doc_id=container_id)
    return docs_container_access_allowed(
        db=db,
        user=user,
        workspace=workspace,
        ref=ContainerRef(app="docs", type=container_type, id=container_id),
    )


def container_access_allowed(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    container_app: str,
    container_type: str,
    container_id: str,
) -> bool:
    if container_app == "meeting":
        return _meeting_container_access_allowed(
            db,
            user=user,
            workspace=workspace,
            container_type=container_type,
            container_id=container_id,
        )
    if container_app == "pms":
        if _pms_container_access_allowed(
            db,
            user=user,
            container_type=container_type,
            container_id=container_id,
        ):
            return True
        return docs_container_access_allowed(
            db=db,
            user=user,
            workspace=workspace,
            ref=ContainerRef(app="pms", type=container_type, id=container_id),
        )
    if container_app == "docs":
        return _docs_container_access_allowed(
            db,
            user=user,
            workspace=workspace,
            container_type=container_type,
            container_id=container_id,
        )
    return False


def _container_attach_allowed(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    container_app: str,
    container_type: str,
    container_id: str,
) -> bool:
    if container_app == "pms" and container_type in {"issue", "task"}:
        try:
            ensure_issue_attachable(db, user, container_id)
        except HTTPException:
            return False
        return True
    return container_access_allowed(
        db,
        user=user,
        workspace=workspace,
        container_app=container_app,
        container_type=container_type,
        container_id=container_id,
    )


def _container_detach_allowed(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    container: RecordingContainer,
) -> bool:
    if container.added_by_id == user.id:
        return True
    if container.container_app == "meeting" and container.container_type == "meeting":
        meeting = db.scalar(
            select(Meeting).where(
                Meeting.id == container.container_id,
                Meeting.workspace_id == workspace.id,
            )
        )
        return meeting is not None and is_organizer(user, meeting)
    if container.container_app in {"docs", "pms"}:
        projection = project_container_access(
            db=db,
            user=user,
            workspace=workspace,
            ref=_container_ref(container),
        )
        return projection.can_manage
    return False


def _recording_access_allowed(
    db: Session, *, workspace: Workspace, user: User, recording: Recording
) -> bool:
    if recording.workspace_id != workspace.id:
        return False
    if recording.owner_id == user.id:
        return True
    return any(
        container_access_allowed(
            db,
            user=user,
            workspace=workspace,
            container_app=container.container_app,
            container_type=container.container_type,
            container_id=container.container_id,
        )
        for container in recording.containers
    )


def _ensure_recording_access(
    db: Session, *, workspace: Workspace, user: User, recording: Recording
) -> None:
    if not _recording_access_allowed(db, workspace=workspace, user=user, recording=recording):
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


def _recording_spool_root() -> Path:
    path = Path(get_settings().recording_spool_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _spool_dir_for_recording(staging_id: str) -> Path:
    return _recording_spool_root() / staging_id


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


def _default_title(started_at: datetime) -> str:
    return f"Recording {started_at:%Y-%m-%d %H:%M:%S UTC}"


def _storage_key_for_recording(
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
    mime_type: str,
    started_at: datetime,
) -> str:
    timestamp = f"{started_at:%Y%m%dT%H%M%SZ}"
    extension = _extension_for_mime(mime_type)
    return (
        f"recordings/{workspace.id}/{user.id}/{started_at:%Y/%m/%d}/"
        f"{timestamp}-{recording_id}{extension}"
    )


@lru_cache(maxsize=1)
def _get_celery_client() -> Celery:
    settings = get_settings()
    celery_client = Celery(
        "ai_do_api_recording_app",
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
        celery_client.signature("recording.transcribe", args=[recording_id], immutable=True),
        celery_client.signature("recording.create_raw_transcript_doc"),
        celery_client.signature("recording.analyze_transcript"),
        celery_client.signature("recording.verify_transcript_summary"),
        celery_client.signature("recording.create_minutes_doc"),
    ).apply_async(queue="meeting_transcribe", retry=False)
    return str(result.id)


def revoke_recording_task(task_id: str) -> None:
    if not task_id:
        return
    try:
        _get_celery_client().control.revoke(task_id, terminate=True, signal="SIGKILL")
    except Exception:
        pass


def _recording_has_meeting_container(recording: Recording) -> bool:
    return any(
        container.container_app == "meeting" and container.container_type == "meeting"
        for container in recording.containers
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
        initial_container_app=staging.initial_container_app,
        initial_container_type=staging.initial_container_type,
        initial_container_id=staging.initial_container_id,
        linked_task_id=_staging_linked_task_id(staging),
        started_at=staging.started_at,
        last_chunk_at=staging.last_chunk_at,
        completed_at=staging.completed_at,
    )


def _container_title_map(
    db: Session,
    containers: list[RecordingContainer],
) -> dict[tuple[str, str, str], str]:
    meeting_ids = {
        item.container_id
        for item in containers
        if item.container_app == "meeting" and item.container_type == "meeting"
    }
    issue_ids = {
        item.container_id
        for item in containers
        if item.container_app == "pms" and item.container_type in {"issue", "task"}
    }
    doc_ids = {
        item.container_id
        for item in containers
        if item.container_app == "docs" and item.container_type in {"native_doc", "doc"}
    }

    titles: dict[tuple[str, str, str], str] = {}
    if meeting_ids:
        for meeting_id, title in db.execute(
            select(Meeting.id, Meeting.title).where(Meeting.id.in_(meeting_ids))
        ):
            titles[("meeting", "meeting", meeting_id)] = title
    if issue_ids:
        for issue_id, title in db.execute(
            select(Issue.id, Issue.title).where(Issue.id.in_(issue_ids))
        ):
            titles[("pms", "issue", issue_id)] = title
            titles[("pms", "task", issue_id)] = title
    if doc_ids:
        for doc_id, title in db.execute(
            select(NativeDoc.id, NativeDoc.title).where(NativeDoc.id.in_(doc_ids))
        ):
            titles[("docs", "native_doc", doc_id)] = title
            titles[("docs", "doc", doc_id)] = title
    return titles


def _serialize_recording(
    db: Session,
    recording: Recording,
    title_map: dict[tuple[str, str, str], str] | None = None,
) -> RecordingOut:
    out = RecordingOut.model_validate(recording)
    resolved_title_map = (
        title_map
        if title_map is not None
        else _container_title_map(db, list(recording.containers))
    )
    out.containers = [
        container.model_copy(
            update={
                "container_title": resolved_title_map.get(
                    (container.container_app, container.container_type, container.container_id)
                )
            }
        )
        for container in out.containers
    ]
    return out


def _serialize_recordings(db: Session, recordings: list[Recording]) -> list[RecordingOut]:
    title_map = _container_title_map(
        db,
        [container for recording in recordings for container in recording.containers],
    )
    return [
        _serialize_recording(db, recording, title_map=title_map)
        for recording in recordings
    ]


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


def _normalize_initial_container(payload: RecordingUploadInitRequest) -> tuple[str, str, str] | None:
    values = [
        payload.initial_container_app,
        payload.initial_container_type,
        payload.initial_container_id,
    ]
    if not any(values):
        return None
    if not all(values):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.container_attach_required",
        )
    return (
        str(payload.initial_container_app),
        str(payload.initial_container_type),
        str(payload.initial_container_id),
    )


def _validate_meeting_linked_task(
    db: Session,
    *,
    user: User,
    meeting_id: str,
    linked_task_id: str | None,
) -> None:
    if linked_task_id is None:
        return
    _ensure_issue_readable(db, user, linked_task_id)
    exists = db.scalar(
        select(MeetingTaskLink.id).where(
            MeetingTaskLink.meeting_id == meeting_id,
            MeetingTaskLink.issue_id == linked_task_id,
        )
    )
    if exists is None:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="meeting.linked_task_attached_required",
        )


def _next_container_sort_order(
    db: Session,
    *,
    container_app: str,
    container_type: str,
    container_id: str,
) -> int:
    if container_app == "meeting" and container_type == "meeting":
        db.execute(select(Meeting.id).where(Meeting.id == container_id).with_for_update())
    current_max = db.scalar(
        select(func.max(RecordingContainer.sort_order)).where(
            RecordingContainer.container_app == container_app,
            RecordingContainer.container_type == container_type,
            RecordingContainer.container_id == container_id,
        )
    )
    return int(current_max or 0) + 1


def _container_for_recording(
    db: Session,
    *,
    recording_id: str,
    container_app: str,
    container_type: str,
    container_id: str,
    added_by_id: str,
    is_primary: bool = True,
    sort_order: int | None = None,
) -> RecordingContainer:
    if sort_order is None:
        sort_order = _next_container_sort_order(
            db,
            container_app=container_app,
            container_type=container_type,
            container_id=container_id,
        )
    return RecordingContainer(
        id=new_id(),
        recording_id=recording_id,
        container_app=container_app,
        container_type=container_type,
        container_id=container_id,
        is_primary=is_primary,
        sort_order=sort_order,
        added_by_id=added_by_id,
    )


def init_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    payload: RecordingUploadInitRequest,
) -> RecordingUploadOut:
    mime_type = _require_allowed_mime(payload.mime_type)
    initial_container = _normalize_initial_container(payload)
    linked_task_id = payload.linked_task_id.strip() if payload.linked_task_id else None

    if initial_container is not None:
        container_app, container_type, container_id = initial_container
        if not _container_attach_allowed(
            db,
            user=user,
            workspace=workspace,
            container_app=container_app,
            container_type=container_type,
            container_id=container_id,
        ):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="recording.container_attach_required",
            )
        if container_app == "meeting" and container_type == "meeting":
            _validate_meeting_linked_task(
                db,
                user=user,
                meeting_id=container_id,
                linked_task_id=linked_task_id,
            )

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
        initial_container is not None
        and initial_container[0] == "meeting"
        and initial_container[1] == "meeting"
    ):
        meeting_id = initial_container[2]
        db.execute(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update())
        stale_cutoff = _utcnow() - timedelta(seconds=RECORDING_STALE_AFTER_SECONDS)
        other_active = db.scalar(
            select(RecordingStaging)
            .options(selectinload(RecordingStaging.uploaded_by))
            .where(
                RecordingStaging.workspace_id == workspace.id,
                RecordingStaging.initial_container_app == "meeting",
                RecordingStaging.initial_container_type == "meeting",
                RecordingStaging.initial_container_id == meeting_id,
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
    spool_dir = _spool_dir_for_recording(staging_id)
    spool_dir.mkdir(parents=True, exist_ok=True)
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
        storage_key=_storage_key_for_recording(
            workspace=workspace,
            user=user,
            recording_id=staging_id,
            mime_type=mime_type,
            started_at=started_at,
        ),
        mime_type=mime_type,
        chunks_meta=meta,
        started_at=started_at,
        last_chunk_at=started_at,
        initial_container_app=initial_container[0] if initial_container else None,
        initial_container_type=initial_container[1] if initial_container else None,
        initial_container_id=initial_container[2] if initial_container else None,
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
    staging_id: str,
    seq: int,
    upload: UploadFile,
    chunk_sha256: str | None,
) -> RecordingUploadChunkAck:
    if seq < 0:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="recording.chunk_sequence_non_negative",
        )
    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
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

    data = await upload.read()
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
        if not isinstance(existing, dict) or existing.get("sha256") != digest or int(existing.get("size", -1)) != len(data):
            raise localized_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                code="recording.chunk_payload_conflict",
            )
        return RecordingUploadChunkAck(
            seq=seq,
            bytes_received=staging.bytes_received,
            highest_seq=staging.highest_seq,
        )

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
    return RecordingUploadChunkAck(
        seq=seq,
        bytes_received=staging.bytes_received,
        highest_seq=staging.highest_seq,
    )


def list_my_staging(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    initial_container_app: str | None = None,
    initial_container_type: str | None = None,
    initial_container_id: str | None = None,
) -> list[RecordingUploadOut]:
    cutoff = _utcnow() - timedelta(hours=get_settings().recording_staging_retention_hours)
    query = select(RecordingStaging).where(
        RecordingStaging.workspace_id == workspace.id,
        RecordingStaging.uploaded_by_id == user.id,
        RecordingStaging.completed_at.is_(None),
        RecordingStaging.started_at >= cutoff,
    )
    if initial_container_app is not None:
        query = query.where(RecordingStaging.initial_container_app == initial_container_app)
    if initial_container_type is not None:
        query = query.where(RecordingStaging.initial_container_type == initial_container_type)
    if initial_container_id is not None:
        query = query.where(RecordingStaging.initial_container_id == initial_container_id)
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
    _cleanup_spool_dir(staging.spool_path)
    db.delete(staging)
    db.commit()


def _chunk_sequences(staging: RecordingStaging) -> list[int]:
    return sorted(int(seq) for seq in (staging.chunks_meta or {}).keys() if str(seq).isdigit())


def _assert_contiguous_chunks(staging: RecordingStaging) -> list[int]:
    if staging.highest_seq < 0:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.no_chunks_to_finalize",
        )
    seqs = _chunk_sequences(staging)
    expected = list(range(seqs[0], seqs[-1] + 1)) if seqs else []
    if not seqs or seqs != expected:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="recording.chunks_incomplete",
        )
    return seqs


def _assemble_chunks(staging: RecordingStaging) -> Path:
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
    assembled_path = _assemble_chunks(staging)

    staging = _load_staging_or_404(db, workspace=workspace, staging_id=staging_id)
    if staging.promoted_recording_id:
        recording = _load_recording_or_404(db, staging.promoted_recording_id)
        return _serialize_recording(db, recording)

    staging.status = "uploading"
    db.add(staging)
    db.commit()

    settings = get_settings()
    get_minio_client().fput_object(
        settings.minio_bucket,
        staging.storage_key,
        str(assembled_path),
        content_type=staging.mime_type,
    )

    title = (payload.title or _staging_title(staging) or "").strip()
    recording = Recording(
        id=staging.id,
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
        audio_status="saved",
        transcript_status="pending",
        raw_transcript_doc_status="pending",
        minutes_doc_status="pending",
        meeting_insight_status="none",
        progress_pct=0,
    )
    db.add(recording)
    db.flush()

    primary_container_id: str | None = None
    if (
        staging.initial_container_app
        and staging.initial_container_type
        and staging.initial_container_id
    ):
        container = _container_for_recording(
            db,
            recording_id=recording.id,
            container_app=staging.initial_container_app,
            container_type=staging.initial_container_type,
            container_id=staging.initial_container_id,
            added_by_id=user.id,
            is_primary=True,
        )
        primary_container_id = container.id
        db.add(container)
    linked_task_id = _staging_linked_task_id(staging)
    if (
        linked_task_id
        and staging.initial_container_app == "meeting"
        and staging.initial_container_type == "meeting"
    ):
        db.add(
            _container_for_recording(
                db,
                recording_id=recording.id,
                container_app="pms",
                container_type="issue",
                container_id=linked_task_id,
                added_by_id=user.id,
                is_primary=False,
                sort_order=0,
            )
        )

    staging.promoted_recording_id = recording.id
    staging.completed_at = _utcnow()
    staging.status = "promoted"
    db.add(staging)
    db.add(recording)
    db.commit()
    if primary_container_id:
        db.expire(recording, ["containers"])
    fresh = _load_recording_or_404(db, recording.id)
    _enqueue_pipeline_or_mark_failed(db, recording=fresh)
    _cleanup_spool_dir(staging.spool_path)
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
    container_app: str | None = None,
    container_type: str | None = None,
    container_id: str | None = None,
) -> RecordingListResponse:
    query = (
        select(Recording)
        .options(selectinload(Recording.containers))
        .where(Recording.workspace_id == workspace.id)
    )
    if view != "archived":
        query = query.where(Recording.trashed_at.is_(None))
    else:
        query = query.where(Recording.trashed_at.is_not(None))

    has_container_filter = any([container_app, container_type, container_id])
    if has_container_filter:
        if not (container_app and container_type and container_id):
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="recording.container_filter_required",
            )
        if not container_access_allowed(
            db,
            user=user,
            workspace=workspace,
            container_app=container_app,
            container_type=container_type,
            container_id=container_id,
        ):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="recording.container_access_required",
            )
        query = query.join(RecordingContainer).where(
            RecordingContainer.container_app == container_app,
            RecordingContainer.container_type == container_type,
            RecordingContainer.container_id == container_id,
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
    initial_container_app: str | None = None,
    initial_container_type: str | None = None,
    initial_container_id: str | None = None,
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
    initial_container: tuple[str, str, str] | None = None
    if any([initial_container_app, initial_container_type, initial_container_id]):
        if not (initial_container_app and initial_container_type and initial_container_id):
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="recording.container_attach_required",
            )
        if not _container_attach_allowed(
            db,
            user=user,
            workspace=workspace,
            container_app=initial_container_app,
            container_type=initial_container_type,
            container_id=initial_container_id,
        ):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="recording.container_attach_required",
            )
        normalized_linked_task_id = linked_task_id.strip() if linked_task_id else None
        if initial_container_app == "meeting" and initial_container_type == "meeting":
            _validate_meeting_linked_task(
                db,
                user=user,
                meeting_id=initial_container_id,
                linked_task_id=normalized_linked_task_id,
            )
        initial_container = (initial_container_app, initial_container_type, initial_container_id)
    else:
        normalized_linked_task_id = linked_task_id.strip() if linked_task_id else None

    recording_id = new_id()
    storage_key = _storage_key_for_recording(
        workspace=workspace,
        user=user,
        recording_id=recording_id,
        mime_type=mime_type,
        started_at=resolved_started_at,
    )
    get_minio_client().put_object(
        settings.minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=mime_type,
    )

    normalized_source = source if source in {"quick_record", "manual_upload"} else "quick_record"
    trimmed_title = title.strip() if title else ""
    recording = Recording(
        id=recording_id,
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
        audio_status="saved",
        transcript_status="pending",
        raw_transcript_doc_status="pending",
        minutes_doc_status="pending",
        meeting_insight_status="none",
        progress_pct=0,
    )
    db.add(recording)
    if initial_container is not None:
        db.flush()
        db.add(
            _container_for_recording(
                db,
                recording_id=recording.id,
                container_app=initial_container[0],
                container_type=initial_container[1],
                container_id=initial_container[2],
                added_by_id=user.id,
                is_primary=True,
            )
        )
        if (
            normalized_linked_task_id
            and initial_container[0] == "meeting"
            and initial_container[1] == "meeting"
        ):
            db.add(
                _container_for_recording(
                    db,
                    recording_id=recording.id,
                    container_app="pms",
                    container_type="issue",
                    container_id=normalized_linked_task_id,
                    added_by_id=user.id,
                    is_primary=False,
                    sort_order=0,
                )
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


def create_container(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
    payload: RecordingContainerCreateRequest,
) -> RecordingOut:
    recording = _load_recording_for_update_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    _ensure_recording_owner(user=user, recording=recording)
    recording_pk = recording.id
    if not _container_attach_allowed(
        db,
        user=user,
        workspace=workspace,
        container_app=payload.container_app,
        container_type=payload.container_type,
        container_id=payload.container_id,
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.container_attach_required",
        )
    existing = next(
        (
            item
            for item in recording.containers
            if item.container_app == payload.container_app
            and item.container_type == payload.container_type
            and item.container_id == payload.container_id
        ),
        None,
    )
    if payload.is_primary:
        for item in recording.containers:
            if item is not existing and item.is_primary:
                item.is_primary = False
                db.add(item)
        db.flush()
    if existing is None:
        sort_order = payload.sort_order
        if sort_order is None:
            sort_order = _next_container_sort_order(
                db,
                container_app=payload.container_app,
                container_type=payload.container_type,
                container_id=payload.container_id,
            )
        existing = RecordingContainer(
            id=new_id(),
            recording_id=recording.id,
            container_app=payload.container_app,
            container_type=payload.container_type,
            container_id=payload.container_id,
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
                for item in fresh.containers
                if item.container_app == payload.container_app
                and item.container_type == payload.container_type
                and item.container_id == payload.container_id
            ),
            None,
        )
        if duplicate is None:
            raise
        return _serialize_recording(db, fresh)
    fresh = _load_recording_or_404(db, recording_pk)
    return _serialize_recording(db, fresh)


def delete_container(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
    container_id: str,
) -> RecordingOut:
    recording = _load_recording_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    if recording.owner_id != user.id:
        _ensure_recording_access(db, workspace=workspace, user=user, recording=recording)
    container = next((item for item in recording.containers if item.id == container_id), None)
    if container is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.container_not_found"
        )
    if recording.owner_id != user.id and not _container_detach_allowed(
        db,
        user=user,
        workspace=workspace,
        container=container,
    ):
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="recording.container_detach_required",
        )
    db.delete(container)
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
    for container in recording.containers:
        if container.container_app == "pms" and container.container_type in {"issue", "task"}:
            return container.container_id
    return None


def _meeting_container(recording: Recording, *, meeting_id: str) -> RecordingContainer | None:
    return next(
        (
            container
            for container in recording.containers
            if container.container_app == "meeting"
            and container.container_type == "meeting"
            and container.container_id == meeting_id
        ),
        None,
    )


def list_meeting_recording_outs(db: Session, *, meeting: Meeting) -> list:
    from ai_do_api.domains.meeting.schemas import MeetingRecordingOut

    recordings = db.scalars(
        select(Recording)
        .join(RecordingContainer)
        .options(selectinload(Recording.containers))
        .where(
            Recording.workspace_id == meeting.workspace_id,
            Recording.trashed_at.is_(None),
            RecordingContainer.container_app == "meeting",
            RecordingContainer.container_type == "meeting",
            RecordingContainer.container_id == meeting.id,
        )
        .order_by(RecordingContainer.sort_order.asc(), Recording.started_at.asc(), Recording.id.asc())
    ).unique().all()
    items = []
    for recording in recordings:
        container = _meeting_container(recording, meeting_id=meeting.id)
        if container is None:
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
                sequence_no=container.sort_order,
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
    from ai_do_api.domains.meeting.schemas import ActiveRecordingLockOut

    rows = db.scalars(
        select(RecordingStaging)
        .options(selectinload(RecordingStaging.uploaded_by))
        .where(
            RecordingStaging.workspace_id == meeting.workspace_id,
            RecordingStaging.initial_container_app == "meeting",
            RecordingStaging.initial_container_type == "meeting",
            RecordingStaging.initial_container_id == meeting.id,
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
        .join(RecordingContainer)
        .options(selectinload(Recording.containers))
        .where(
            Recording.id == recording_id,
            Recording.workspace_id == workspace.id,
            Recording.trashed_at.is_(None),
            RecordingContainer.container_app == "meeting",
            RecordingContainer.container_type == "meeting",
            RecordingContainer.container_id == meeting_id,
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
        .join(RecordingContainer)
        .options(selectinload(Recording.containers))
        .where(
            Recording.workspace_id == workspace_id,
            Recording.trashed_at.is_(None),
            RecordingContainer.container_app == "meeting",
            RecordingContainer.container_type == "meeting",
            RecordingContainer.container_id == meeting_id,
        )
        .order_by(RecordingContainer.sort_order.desc(), Recording.started_at.desc())
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

    obj = get_minio_client().get_object(get_settings().minio_bucket, recording.storage_key)

    def body():
        try:
            yield from obj.stream(1024 * 1024)
        finally:
            obj.close()
            obj.release_conn()

    return StreamingResponse(
        body(),
        media_type=recording.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{_download_filename(recording)}"',
            "Cache-Control": "private, max-age=3600",
        },
    )
