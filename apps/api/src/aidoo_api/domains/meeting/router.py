from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_feature_access,
)
from aidoo_api.domains.auth.models import User
from aidoo_api.domains.meeting import service as meeting_service
from aidoo_api.domains.meeting.schemas import (
    MeetingCreateRequest,
    MeetingDetail,
    MeetingDocAttachRequest,
    MeetingListResponse,
    MeetingTaskAttachRequest,
    MeetingUpdateRequest,
    MeetingUserItem,
)


router = APIRouter(
    prefix="/meeting",
    tags=["meeting"],
    dependencies=[Depends(require_feature_access("nav.meeting"))],
)


@router.get("/meetings", response_model=MeetingListResponse)
def list_meetings(
    scope: Literal["mine", "upcoming", "all"] = Query(default="mine"),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingListResponse:
    return meeting_service.list_meetings(
        db,
        user=current_user,
        scope=scope,
        from_at=from_at,
        to_at=to_at,
    )


@router.post(
    "/meetings",
    response_model=MeetingDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_meeting(
    payload: MeetingCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.create_meeting(
        db, organizer=current_user, payload=payload
    )


@router.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.get_meeting(
        db, user=current_user, meeting_id=meeting_id
    )


@router.patch("/meetings/{meeting_id}", response_model=MeetingDetail)
def update_meeting(
    meeting_id: str,
    payload: MeetingUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.update_meeting(
        db, user=current_user, meeting_id=meeting_id, payload=payload
    )


@router.delete(
    "/meetings/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_meeting(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    meeting_service.delete_meeting(
        db, user=current_user, meeting_id=meeting_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/meetings/{meeting_id}/tasks", response_model=MeetingDetail)
def attach_task(
    meeting_id: str,
    payload: MeetingTaskAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.attach_task(
        db, user=current_user, meeting_id=meeting_id, issue_id=payload.issue_id
    )


@router.delete(
    "/meetings/{meeting_id}/tasks/{issue_id}",
    response_model=MeetingDetail,
)
def detach_task(
    meeting_id: str,
    issue_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.detach_task(
        db, user=current_user, meeting_id=meeting_id, issue_id=issue_id
    )


@router.post("/meetings/{meeting_id}/docs", response_model=MeetingDetail)
def attach_doc(
    meeting_id: str,
    payload: MeetingDocAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.attach_doc(
        db, user=current_user, meeting_id=meeting_id, doc_id=payload.doc_id
    )


@router.delete(
    "/meetings/{meeting_id}/docs/{doc_id}",
    response_model=MeetingDetail,
)
def detach_doc(
    meeting_id: str,
    doc_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.detach_doc(
        db, user=current_user, meeting_id=meeting_id, doc_id=doc_id
    )


@router.post("/meetings/{meeting_id}/files", response_model=MeetingDetail)
async def attach_file(
    meeting_id: str,
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return await meeting_service.attach_file(
        db, user=current_user, meeting_id=meeting_id, upload=file
    )


@router.delete(
    "/meetings/{meeting_id}/files/{file_id}",
    response_model=MeetingDetail,
)
def detach_file(
    meeting_id: str,
    file_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingDetail:
    return meeting_service.detach_file(
        db, user=current_user, meeting_id=meeting_id, file_id=file_id
    )


@router.get("/users", response_model=list[MeetingUserItem])
def list_meeting_users(
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[MeetingUserItem]:
    """Search active users for meeting attendee selection.

    Returns active users matching the query against full_name or email.
    Gated only by ``nav.meeting`` (router-level), so meeting users do not
    need PMS or Docs workspace access to find attendees.
    """
    del current_user
    query = select(User).where(User.status == "active")
    search = q.strip()
    if search:
        like = f"%{search}%"
        query = query.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    query = query.order_by(User.full_name.asc(), User.email.asc()).limit(limit)
    users = list(db.scalars(query))
    return [
        MeetingUserItem(id=user.id, email=user.email, full_name=user.full_name)
        for user in users
    ]
