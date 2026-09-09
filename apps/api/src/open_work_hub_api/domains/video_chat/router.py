from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.video_chat import service
from open_work_hub_api.domains.video_chat.app_catalog import VIDEO_CHAT_APP
from open_work_hub_api.domains.video_chat.schemas import (
    VideoChatJoinTokenResponse,
    VideoChatSessionCreateRequest,
    VideoChatSessionListResponse,
    VideoChatSessionOut,
)

require_video_chat_app_enabled = require_app_access(
    VIDEO_CHAT_APP.app_id,
    error_code="app.access_required",
)

router = APIRouter(
    prefix="/video-chat",
    tags=["video-chat"],
    dependencies=[Depends(require_video_chat_app_enabled)],
)


@router.get("/sessions", response_model=VideoChatSessionListResponse)
def list_sessions(
    status_filter: Literal["open", "ended"] | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionListResponse:
    return service.list_sessions(
        db,
        user=current_user,
        status_filter=status_filter,
    )


@router.post(
    "/sessions",
    response_model=VideoChatSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: VideoChatSessionCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionOut:
    return service.create_session(
        db,
        user=current_user,
        payload=payload,
    )


@router.get("/sessions/{session_id}", response_model=VideoChatSessionOut)
def get_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionOut:
    return service.get_session(
        db,
        user=current_user,
        session_id=session_id,
    )


@router.post("/sessions/{session_id}/join-token", response_model=VideoChatJoinTokenResponse)
def create_join_token(
    request: Request,
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatJoinTokenResponse:
    return service.create_join_token(
        db,
        user=current_user,
        session_id=session_id,
        request_host=request.url.hostname,
    )


@router.post("/sessions/{session_id}/end", response_model=VideoChatSessionOut)
def end_session(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionOut:
    return service.end_session(
        db,
        user=current_user,
        session_id=session_id,
    )


@router.post("/sessions/{session_id}/recording/start", response_model=VideoChatSessionOut)
def start_recording(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionOut:
    return service.start_recording(
        db,
        user=current_user,
        session_id=session_id,
    )


@router.post("/sessions/{session_id}/recording/stop", response_model=VideoChatSessionOut)
def stop_recording(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionOut:
    return service.stop_recording(
        db,
        user=current_user,
        session_id=session_id,
    )


@router.post("/sessions/{session_id}/captions/start", response_model=VideoChatSessionOut)
def start_captions(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionOut:
    return service.start_captions(
        db,
        user=current_user,
        session_id=session_id,
    )


@router.post("/sessions/{session_id}/captions/stop", response_model=VideoChatSessionOut)
def stop_captions(
    session_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> VideoChatSessionOut:
    return service.stop_captions(
        db,
        user=current_user,
        session_id=session_id,
    )
