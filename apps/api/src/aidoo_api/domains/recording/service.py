from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.core.i18n import localized_http_exception
from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import get_minio_client
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.registry import (
    ContainerRef,
    container_access_allowed as docs_container_access_allowed,
    project_container_access,
)
from aidoo_api.domains.docs.service import can_read_native_doc_for_rag
from aidoo_api.domains.meeting.models import Meeting
from aidoo_api.domains.meeting.permissions import is_organizer, is_participant
from aidoo_api.domains.pms.access import _ensure_issue_readable, ensure_issue_attachable
from aidoo_api.domains.recording.models import Recording, RecordingContainer
from aidoo_api.domains.recording.schemas import (
    RecordingContainerCreateRequest,
    RecordingListResponse,
    RecordingOut,
    RecordingPlaybackResponse,
    RecordingUpdateRequest,
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


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
            Meeting.trashed_at.is_(None),
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
                Meeting.trashed_at.is_(None),
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
    return RecordingListResponse(items=[RecordingOut.model_validate(item) for item in recordings])


def get_recording(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
) -> RecordingOut:
    recording = _load_recording_or_404(db, recording_id)
    _ensure_recording_access(db, workspace=workspace, user=user, recording=recording)
    return RecordingOut.model_validate(recording)


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
    return RecordingOut.model_validate(recording)


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
    recording.trashed_at = _utcnow()
    recording.updated_at = recording.trashed_at
    db.add(recording)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def create_container(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    recording_id: str,
    payload: RecordingContainerCreateRequest,
) -> RecordingOut:
    recording = _load_recording_or_404(db, recording_id)
    if recording.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND, code="recording.not_found"
        )
    _ensure_recording_owner(user=user, recording=recording)
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
            item.is_primary = False
            db.add(item)
    if existing is None:
        existing = RecordingContainer(
            id=new_id(),
            recording_id=recording.id,
            container_app=payload.container_app,
            container_type=payload.container_type,
            container_id=payload.container_id,
            is_primary=payload.is_primary,
            sort_order=payload.sort_order,
            added_by_id=user.id,
        )
    else:
        existing.is_primary = payload.is_primary
        existing.sort_order = payload.sort_order
    db.add(existing)
    recording.updated_at = _utcnow()
    db.add(recording)
    db.commit()
    fresh = _load_recording_or_404(db, recording.id)
    return RecordingOut.model_validate(fresh)


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
    return RecordingOut.model_validate(fresh)


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


def _extension_for_mime(mime_type: str) -> str:
    return _AUDIO_EXTENSIONS.get(mime_type, Path(mime_type.split("/", 1)[-1]).suffix or ".bin")


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
