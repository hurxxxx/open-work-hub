from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Form, Header, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.dependencies import require_current_user, require_current_workspace
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.recording import service as recording_service
from aidoo_api.domains.recording.schemas import (
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


router = APIRouter(prefix="/recording", tags=["recording"])


@router.get("/recordings", response_model=RecordingListResponse)
def list_recordings(
    view: Literal["mine", "needs_review", "processing", "failed", "archived"] = "mine",
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    container_app: str | None = Query(default=None, min_length=1, max_length=64),
    container_type: str | None = Query(default=None, min_length=1, max_length=64),
    container_id: str | None = Query(default=None, min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingListResponse:
    return recording_service.list_recordings(
        db,
        workspace=workspace,
        user=current_user,
        view=view,
        from_=from_,
        to=to,
        container_app=container_app,
        container_type=container_type,
        container_id=container_id,
    )


@router.post(
    "/recordings/staging",
    response_model=RecordingUploadOut,
    status_code=status.HTTP_201_CREATED,
)
def init_recording_staging(
    payload: RecordingUploadInitRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingUploadOut:
    return recording_service.init_staging(
        db,
        workspace=workspace,
        user=current_user,
        payload=payload,
    )


@router.put(
    "/recordings/staging/{staging_id}/chunks/{seq}",
    response_model=RecordingUploadChunkAck,
)
async def upload_recording_chunk(
    staging_id: str,
    seq: int,
    file: UploadFile,
    x_chunk_sha256: str | None = Header(default=None, alias="X-Chunk-Sha256"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingUploadChunkAck:
    return await recording_service.upload_chunk(
        db,
        workspace=workspace,
        user=current_user,
        staging_id=staging_id,
        seq=seq,
        upload=file,
        chunk_sha256=x_chunk_sha256,
    )


@router.post("/recordings/staging/{staging_id}/complete", response_model=RecordingOut)
def complete_recording_staging(
    staging_id: str,
    payload: RecordingUploadCompleteRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.complete_staging(
        db,
        workspace=workspace,
        user=current_user,
        staging_id=staging_id,
        payload=payload,
    )


@router.get("/recordings/staging", response_model=list[RecordingUploadOut])
def list_recording_staging(
    initial_container_app: str | None = Query(default=None, min_length=1, max_length=64),
    initial_container_type: str | None = Query(default=None, min_length=1, max_length=64),
    initial_container_id: str | None = Query(default=None, min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> list[RecordingUploadOut]:
    return recording_service.list_my_staging(
        db,
        workspace=workspace,
        user=current_user,
        initial_container_app=initial_container_app,
        initial_container_type=initial_container_type,
        initial_container_id=initial_container_id,
    )


@router.delete("/recordings/staging/{staging_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_recording_staging(
    staging_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    recording_service.discard_staging(
        db,
        workspace=workspace,
        user=current_user,
        staging_id=staging_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/recordings/import", response_model=RecordingOut, status_code=status.HTTP_201_CREATED)
def import_recording(
    file: UploadFile,
    title: str | None = Form(default=None, max_length=200),
    started_at: datetime | None = Form(default=None),
    ended_at: datetime | None = Form(default=None),
    duration_sec: int | None = Form(default=None),
    source: Literal["quick_record", "manual_upload"] = Form(default="quick_record"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.import_recording(
        db,
        workspace=workspace,
        user=current_user,
        upload=file,
        title=title,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=duration_sec,
        source=source,
    )


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
def get_recording(
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.get_recording(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
    )


@router.patch("/recordings/{recording_id}", response_model=RecordingOut)
def update_recording(
    recording_id: str,
    payload: RecordingUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.update_recording(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
        payload=payload,
    )


@router.delete("/recordings/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
):
    return recording_service.delete_recording(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
    )


@router.post("/recordings/{recording_id}/retry", response_model=RecordingOut)
def retry_recording(
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.retry_recording(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
    )


@router.get("/recordings/{recording_id}/playback", response_model=RecordingPlaybackResponse)
def get_recording_playback(
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingPlaybackResponse:
    return recording_service.get_recording_playback(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
    )


@router.get("/recordings/{recording_id}/media")
def stream_recording_media(
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
):
    return recording_service.stream_recording_media(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
    )


@router.post("/recordings/{recording_id}/containers", response_model=RecordingOut)
def create_container(
    recording_id: str,
    payload: RecordingContainerCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.create_container(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
        payload=payload,
    )


@router.delete("/recordings/{recording_id}/containers/{container_id}", response_model=RecordingOut)
def delete_container(
    recording_id: str,
    container_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.delete_container(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
        container_id=container_id,
    )
