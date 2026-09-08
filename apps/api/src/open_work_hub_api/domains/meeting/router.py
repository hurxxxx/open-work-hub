from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Form, Header, Query, Response, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.content_access.dependencies import require_content_grant_issuer
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer
from open_work_hub_api.domains.meeting import recordings as recording_service
from open_work_hub_api.domains.meeting import service as meeting_service
from open_work_hub_api.domains.meeting.app_catalog import MEETING_APP
from open_work_hub_api.domains.meeting.models import Meeting
from open_work_hub_api.domains.meeting.schemas import (
    MeetingAttendeesAddRequest,
    MeetingAvailabilityResponse,
    MeetingCreateRequest,
    MeetingDetail,
    MeetingDocAttachRequest,
    MeetingListResponse,
    MeetingTaskAttachRequest,
    MeetingUpdateRequest,
    MeetingUserItem,
    RecordingChunkAck,
    RecordingCompleteRequest,
    RecordingPlaybackResponse,
    RecordingStagingInitRequest,
    RecordingStagingItem,
)
from open_work_hub_api.domains.planner.event_time import parse_iso_or_date

require_meeting_app_enabled = require_app_access(
    MEETING_APP.app_id,
    error_code="app.access_required",
)

router = APIRouter(
    prefix="/meeting",
    tags=["meeting"],
    dependencies=[Depends(require_meeting_app_enabled)],
)


def _meeting_detail_response(
    db: Session,
    *,
    meeting: Meeting,
    user: User,
    content_grant_issuer: ContentGrantIssuer,
) -> MeetingDetail:
    return meeting_service.serialize_meeting_for_http(
        db,
        meeting,
        viewer_user_id=user.id,
        content_grant_issuer=content_grant_issuer,
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
        principal=user_principal(
            user_id=current_user.id,
            source="api.meeting.list_meetings",
        ),
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
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.create_meeting(
        db,
        organizer=current_user,
        payload=payload,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.get_meeting(
        db,
        principal=user_principal(
            user_id=current_user.id,
            source="api.meeting.get_meeting",
        ),
        user=current_user,
        meeting_id=meeting_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.patch("/meetings/{meeting_id}", response_model=MeetingDetail)
def update_meeting(
    meeting_id: str,
    payload: MeetingUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.update_meeting(
        db,
        user=current_user,
        meeting_id=meeting_id,
        payload=payload,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.post("/meetings/{meeting_id}/notes/ensure", response_model=MeetingDetail)
def ensure_meeting_notes(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.ensure_meeting_notes(
        db,
        user=current_user,
        meeting_id=meeting_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
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
    meeting_service.delete_meeting(db, user=current_user, meeting_id=meeting_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/meetings/{meeting_id}/attendees", response_model=MeetingDetail)
def add_meeting_attendees(
    meeting_id: str,
    payload: MeetingAttendeesAddRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    """Append attendees to an existing meeting.

    Permission: any current participant (organizer or existing attendee). The
    full attendee replace path stays organizer-only via ``PATCH /meetings/{id}``.
    """
    meeting = meeting_service.add_attendees(
        db,
        user=current_user,
        meeting_id=meeting_id,
        attendees=list(payload.attendees),
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.post("/meetings/{meeting_id}/tasks", response_model=MeetingDetail)
def attach_task(
    meeting_id: str,
    payload: MeetingTaskAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.attach_task(
        db,
        user=current_user,
        meeting_id=meeting_id,
        task_id=payload.task_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.delete(
    "/meetings/{meeting_id}/tasks/{task_id}",
    response_model=MeetingDetail,
)
def detach_task(
    meeting_id: str,
    task_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.detach_task(
        db,
        user=current_user,
        meeting_id=meeting_id,
        task_id=task_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.post("/meetings/{meeting_id}/docs", response_model=MeetingDetail)
def attach_doc(
    meeting_id: str,
    payload: MeetingDocAttachRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.attach_doc(
        db,
        user=current_user,
        meeting_id=meeting_id,
        doc_id=payload.doc_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
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
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.detach_doc(
        db,
        user=current_user,
        meeting_id=meeting_id,
        doc_id=doc_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.post("/meetings/{meeting_id}/files", response_model=MeetingDetail)
async def attach_file(
    meeting_id: str,
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = await meeting_service.attach_file(
        db,
        user=current_user,
        meeting_id=meeting_id,
        upload=file,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
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
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = meeting_service.detach_file(
        db,
        user=current_user,
        meeting_id=meeting_id,
        file_id=file_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
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
) -> RecordingStagingItem:
    return recording_service.init_staging(
        db,
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
) -> RecordingChunkAck:
    return await recording_service.upload_chunk(
        db,
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
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = recording_service.complete_staging(
        db,
        user=current_user,
        meeting_id=meeting_id,
        staging_id=staging_id,
        payload=payload,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.get(
    "/meetings/{meeting_id}/recordings/staging",
    response_model=list[RecordingStagingItem],
)
def list_recording_staging(
    meeting_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[RecordingStagingItem]:
    return recording_service.list_my_staging(
        db,
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
) -> Response:
    recording_service.discard_staging(
        db,
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
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = recording_service.delete_recording(
        db,
        user=current_user,
        meeting_id=meeting_id,
        recording_id=recording_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.post("/meetings/{meeting_id}/recordings/import", response_model=MeetingDetail)
def import_recording(
    meeting_id: str,
    file: UploadFile,
    linked_task_id: str | None = Form(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = recording_service.import_recording(
        db,
        user=current_user,
        meeting_id=meeting_id,
        upload=file,
        linked_task_id=linked_task_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
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
) -> RecordingPlaybackResponse:
    return recording_service.get_recording_playback(
        db,
        user=current_user,
        meeting_id=meeting_id,
        recording_id=recording_id,
    )


@router.get("/meetings/{meeting_id}/recordings/{recording_id}/media")
def stream_recording_media(
    meeting_id: str,
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
):
    return recording_service.stream_recording_media(
        db,
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
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> MeetingDetail:
    meeting = recording_service.retry_recording(
        db,
        user=current_user,
        meeting_id=meeting_id,
        recording_id=recording_id,
    )
    return _meeting_detail_response(
        db,
        meeting=meeting,
        user=current_user,
        content_grant_issuer=content_grant_issuer,
    )


@router.get("/users", response_model=list[MeetingUserItem])
def list_meeting_users(
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[MeetingUserItem]:
    """Search active users currently admitted to the meeting app."""
    query = select(User).where(User.status == "active", User.login_blocked.is_(False))
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
    from open_work_hub_api.domains.auth.app_access import can_use_app

    query = query.order_by(User.full_name.asc(), User.email.asc()).execution_options(yield_per=100)
    users = []
    for user in db.scalars(query):
        if can_use_app(db, user_id=user.id, app_id="meeting"):
            users.append(user)
            if len(users) == limit:
                break
    return [
        MeetingUserItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
        )
        for user in users
    ]


@router.get("/availability", response_model=MeetingAvailabilityResponse)
def get_meeting_availability(
    user_ids: list[str] = Query(default=[], alias="user_ids"),
    from_param: str = Query(..., alias="from", description="Inclusive start (ISO)"),
    to_param: str = Query(..., alias="to", description="Exclusive end (ISO)"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MeetingAvailabilityResponse:
    try:
        from_at = parse_iso_or_date(from_param)
        to_at = parse_iso_or_date(to_param)
    except ValueError as exc:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.invalid_iso_datetime",
            error=str(exc),
        ) from exc
    if to_at <= from_at:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.range_to_after_from",
        )
    if (to_at - from_at) > timedelta(days=31):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.availability_range_too_large",
            days=31,
        )
    return meeting_service.list_meeting_availability(
        db,
        principal=user_principal(
            user_id=current_user.id,
            source="api.meeting.find_availability",
        ),
        viewer=current_user,
        user_ids=user_ids,
        from_at=from_at,
        to_at=to_at,
    )
