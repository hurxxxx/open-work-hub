from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
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
