from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from aidoo_api.domains.auth.models import (
    User,
    Workspace,
)
from aidoo_api.domains.meeting import recordings as recording_service
from aidoo_api.domains.meeting import service as meeting_service
from aidoo_api.domains.meeting.schemas import (
    MeetingAvailabilityResponse,
    MeetingAttendeesAddRequest,
    MeetingCreateRequest,
    MeetingDetail,
    MeetingDocAttachRequest,
    MeetingListResponse,
    RecordingChunkAck,
    RecordingCompleteRequest,
    RecordingPlaybackResponse,
    RecordingStagingInitRequest,
    RecordingStagingItem,
    MeetingTaskAttachRequest,
    MeetingUpdateRequest,
    MeetingUserItem,
)
from aidoo_api.domains.planner.service import parse_iso_or_date


router = APIRouter(
    prefix="/meeting",
    tags=["meeting"],
)


@router.get("/meetings", response_model=MeetingListResponse)
def list_meetings(
    scope: Literal["mine", "upcoming", "all"] = Query(default="mine"),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingListResponse:
    return meeting_service.list_meetings(
        db,
        workspace=workspace,
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
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.create_meeting(
        db, workspace=workspace, organizer=current_user, payload=payload
    )


@router.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.get_meeting(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id
    )


@router.patch("/meetings/{meeting_id}", response_model=MeetingDetail)
def update_meeting(
    meeting_id: str,
    payload: MeetingUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.update_meeting(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, payload=payload
    )


@router.post("/meetings/{meeting_id}/notes/ensure", response_model=MeetingDetail)
def ensure_meeting_notes(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.ensure_meeting_notes(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
    )


@router.delete(
    "/meetings/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_meeting(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    meeting_service.delete_meeting(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/meetings/{meeting_id}/attendees", response_model=MeetingDetail)
def add_meeting_attendees(
    meeting_id: str,
    payload: MeetingAttendeesAddRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    """Append attendees to an existing meeting.

    Permission: any current participant (organizer or existing attendee). The
    full attendee replace path stays organizer-only via ``PATCH /meetings/{id}``.
    """
    return meeting_service.add_attendees(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        attendees=list(payload.attendees),
    )


@router.post("/meetings/{meeting_id}/tasks", response_model=MeetingDetail)
def attach_task(
    meeting_id: str,
    payload: MeetingTaskAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.attach_task(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, issue_id=payload.issue_id
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
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.detach_task(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, issue_id=issue_id
    )


@router.post("/meetings/{meeting_id}/docs", response_model=MeetingDetail)
def attach_doc(
    meeting_id: str,
    payload: MeetingDocAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.attach_doc(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, doc_id=payload.doc_id
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
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.detach_doc(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, doc_id=doc_id
    )


@router.post("/meetings/{meeting_id}/files", response_model=MeetingDetail)
async def attach_file(
    meeting_id: str,
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return await meeting_service.attach_file(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, upload=file
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
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.detach_file(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, file_id=file_id
    )


@router.post(
    "/meetings/{meeting_id}/recordings/staging",
    response_model=RecordingStagingItem,
    status_code=status.HTTP_201_CREATED,
)
def init_recording_staging(
    meeting_id: str,
    payload: RecordingStagingInitRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingStagingItem:
    return recording_service.init_staging(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        payload=payload,
    )


@router.put(
    "/meetings/{meeting_id}/recordings/staging/{staging_id}/chunks/{seq}",
    response_model=RecordingChunkAck,
)
async def upload_recording_chunk(
    meeting_id: str,
    staging_id: str,
    seq: int,
    file: UploadFile,
    x_chunk_sha256: str | None = Header(default=None, alias="X-Chunk-Sha256"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingChunkAck:
    return await recording_service.upload_chunk(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        staging_id=staging_id,
        seq=seq,
        upload=file,
        chunk_sha256=x_chunk_sha256,
    )


@router.post(
    "/meetings/{meeting_id}/recordings/staging/{staging_id}/complete",
    response_model=MeetingDetail,
)
def complete_recording_staging(
    meeting_id: str,
    staging_id: str,
    payload: RecordingCompleteRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return recording_service.complete_staging(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        staging_id=staging_id,
        payload=payload,
    )


@router.get(
    "/meetings/{meeting_id}/recordings/staging",
    response_model=list[RecordingStagingItem],
)
def list_recording_staging(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> list[RecordingStagingItem]:
    return recording_service.list_my_staging(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
    )


@router.delete(
    "/meetings/{meeting_id}/recordings/staging/{staging_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def discard_recording_staging(
    meeting_id: str,
    staging_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    recording_service.discard_staging(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        staging_id=staging_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/meetings/{meeting_id}/recordings/{recording_id}",
    response_model=MeetingDetail,
)
def delete_meeting_recording(
    meeting_id: str,
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return recording_service.delete_recording(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        recording_id=recording_id,
    )


@router.post("/meetings/{meeting_id}/recordings/import", response_model=MeetingDetail)
def import_recording(
    meeting_id: str,
    file: UploadFile,
    linked_task_id: str | None = Form(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return recording_service.import_recording(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        upload=file,
        linked_task_id=linked_task_id,
    )


@router.get(
    "/meetings/{meeting_id}/recordings/{recording_id}/playback",
    response_model=RecordingPlaybackResponse,
)
def get_recording_playback(
    meeting_id: str,
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> RecordingPlaybackResponse:
    return recording_service.get_recording_playback(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        recording_id=recording_id,
    )


@router.post(
    "/meetings/{meeting_id}/recordings/{recording_id}/retry",
    response_model=MeetingDetail,
)
def retry_recording(
    meeting_id: str,
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return recording_service.retry_recording(
        db,
        workspace=workspace,
        user=current_user,
        meeting_id=meeting_id,
        recording_id=recording_id,
    )


@router.get("/users", response_model=list[MeetingUserItem])
def list_meeting_users(
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> list[MeetingUserItem]:
    """Search workspace members for meeting attendee selection."""
    member_user_ids = meeting_service.workspace_meeting_user_ids_subquery(workspace.id)
    query = (
        select(User)
        .join(member_user_ids, member_user_ids.c.user_id == User.id)
        .where(User.status == "active")
    )
    search = q.strip()
    if search:
        like = f"%{search}%"
        query = query.where(
            or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.display_name.ilike(like),
            )
        )
    query = query.order_by(User.full_name.asc(), User.email.asc()).limit(limit)
    users = db.scalars(query).all()
    return [
        MeetingUserItem(id=user.id, email=user.email, full_name=user.full_name)
        for user in users
    ]


@router.get("/availability", response_model=MeetingAvailabilityResponse)
def get_meeting_availability(
    user_ids: list[str] = Query(default=[], alias="user_ids"),
    from_param: str = Query(..., alias="from", description="Inclusive start (ISO)"),
    to_param: str = Query(..., alias="to", description="Exclusive end (ISO)"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingAvailabilityResponse:
    try:
        from_at = parse_iso_or_date(from_param)
        to_at = parse_iso_or_date(to_param)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO date/datetime: {exc}",
        ) from exc
    if to_at <= from_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Range 'to' must be strictly after 'from'.",
        )
    if (to_at - from_at) > timedelta(days=31):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Availability range exceeds maximum 31 days.",
        )
    return meeting_service.list_meeting_availability(
        db,
        workspace=workspace,
        viewer=current_user,
        user_ids=user_ids,
        from_at=from_at,
        to_at=to_at,
    )
