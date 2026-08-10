from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Form, Header, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.recording import service as recording_service
from open_alm_api.domains.recording import tus_protocol
from open_alm_api.domains.recording.app_catalog import RECORDING_WORKSPACE_APP
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


require_recording_app_enabled = require_workspace_app_enabled(
    RECORDING_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/recording",
    tags=["recording"],
    dependencies=[Depends(require_recording_app_enabled)],
)


def _tus_location(request: Request, staging_id: str) -> str:
    return str(request.url).rstrip("/").rsplit("/recordings/tus", 1)[0] + (
        f"/recordings/staging/{staging_id}/tus"
    )


@router.options("/recordings/tus")
def recording_tus_options() -> Response:
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers=tus_protocol.response_headers(),
    )


@router.get("/recordings", response_model=RecordingListResponse)
def list_recordings(
    view: Literal["mine", "needs_review", "processing", "failed", "archived"] = "mine",
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    target_app: str | None = Query(default=None, min_length=1, max_length=64),
    target_type: str | None = Query(default=None, min_length=1, max_length=64),
    target_id: str | None = Query(default=None, min_length=1, max_length=128),
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
        target_app=target_app,
        target_type=target_type,
        target_id=target_id,
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


@router.post("/recordings/tus", status_code=status.HTTP_201_CREATED)
def create_recording_tus_upload(
    request: Request,
    tus_resumable: str | None = Header(default=None, alias="Tus-Resumable"),
    upload_metadata: str | None = Header(default=None, alias="Upload-Metadata"),
    upload_length: int | None = Header(default=None, alias="Upload-Length"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    tus_protocol.require_version(tus_resumable)
    staging = recording_service.init_tus_staging(
        db,
        workspace=workspace,
        user=current_user,
        upload_metadata=upload_metadata,
        upload_length=upload_length,
    )
    headers = tus_protocol.response_headers(upload_offset=staging.bytes_received)
    headers["Location"] = _tus_location(request, staging.id)
    return Response(status_code=status.HTTP_201_CREATED, headers=headers)


@router.options("/recordings/staging/{staging_id}/tus")
def recording_staging_tus_options(staging_id: str) -> Response:
    del staging_id
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers=tus_protocol.response_headers(),
    )


@router.head("/recordings/staging/{staging_id}/tus")
def head_recording_tus_upload(
    staging_id: str,
    tus_resumable: str | None = Header(default=None, alias="Tus-Resumable"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    tus_protocol.require_version(tus_resumable)
    staging = recording_service.read_tus_upload(
        db,
        workspace=workspace,
        user=current_user,
        staging_id=staging_id,
    )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers=tus_protocol.response_headers(
            upload_offset=staging.bytes_received,
            upload_length=tus_protocol.upload_length_from_meta(staging.chunks_meta),
        ),
    )


@router.patch("/recordings/staging/{staging_id}/tus")
async def patch_recording_tus_upload(
    staging_id: str,
    request: Request,
    tus_resumable: str | None = Header(default=None, alias="Tus-Resumable"),
    upload_offset: int = Header(..., alias="Upload-Offset"),
    upload_checksum: str | None = Header(default=None, alias="Upload-Checksum"),
    upload_length: int | None = Header(default=None, alias="Upload-Length"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    tus_protocol.require_version(tus_resumable)
    staging = recording_service.upload_tus_chunk(
        db,
        workspace=workspace,
        user=current_user,
        staging_id=staging_id,
        upload_offset=upload_offset,
        data=await request.body(),
        upload_checksum=upload_checksum,
        upload_length=upload_length,
    )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers=tus_protocol.response_headers(
            upload_offset=staging.bytes_received,
            upload_length=tus_protocol.upload_length_from_meta(staging.chunks_meta),
        ),
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
    initial_target_app: str | None = Query(default=None, min_length=1, max_length=64),
    initial_target_type: str | None = Query(default=None, min_length=1, max_length=64),
    initial_target_id: str | None = Query(default=None, min_length=1, max_length=128),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> list[RecordingUploadOut]:
    return recording_service.list_my_staging(
        db,
        workspace=workspace,
        user=current_user,
        initial_target_app=initial_target_app,
        initial_target_type=initial_target_type,
        initial_target_id=initial_target_id,
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
    initial_target_app: str | None = Form(default=None, min_length=1, max_length=64),
    initial_target_type: str | None = Form(default=None, min_length=1, max_length=64),
    initial_target_id: str | None = Form(default=None, min_length=1, max_length=128),
    linked_task_id: str | None = Form(default=None, max_length=36),
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
        initial_target_app=initial_target_app,
        initial_target_type=initial_target_type,
        initial_target_id=initial_target_id,
        linked_task_id=linked_task_id,
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


@router.post("/recordings/{recording_id}/targets", response_model=RecordingOut)
def create_target(
    recording_id: str,
    payload: RecordingTargetCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.create_target(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
        payload=payload,
    )


@router.delete("/recordings/{recording_id}/targets/{target_id}", response_model=RecordingOut)
def delete_target(
    recording_id: str,
    target_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingOut:
    return recording_service.delete_target(
        db,
        workspace=workspace,
        user=current_user,
        recording_id=recording_id,
        target_id=target_id,
    )
