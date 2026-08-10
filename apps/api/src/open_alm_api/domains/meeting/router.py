from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Form, Header, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, contains_eager

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.principal import user_principal
from open_alm_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from open_alm_api.domains.auth.models import (
    OrgUnit,
    User,
    Workspace,
)
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.meeting import recordings as recording_service
from open_alm_api.domains.meeting import service as meeting_service
from open_alm_api.domains.meeting.app_catalog import MEETING_WORKSPACE_APP
from open_alm_api.domains.meeting.availability_projection import workspace_meeting_user_ids_subquery
from open_alm_api.domains.meeting.schemas import (
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
from open_alm_api.domains.planner.event_time import parse_iso_or_date


require_meeting_app_enabled = require_workspace_app_enabled(
    MEETING_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/meeting",
    tags=["meeting"],
    dependencies=[Depends(require_meeting_app_enabled)],
)
public_router = APIRouter(
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
        principal=user_principal(
            workspace_id=workspace.id,
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
        db,
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.meeting.get_meeting",
        ),
        user=current_user,
        meeting_id=meeting_id,
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
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, task_id=payload.task_id
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
    workspace: Workspace = Depends(require_current_workspace),
) -> MeetingDetail:
    return meeting_service.detach_task(
        db, workspace=workspace, user=current_user, meeting_id=meeting_id, task_id=task_id
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


@public_router.get("/files/{file_id}/content")
def proxy_file_attachment_content(
    file_id: str,
    expires: int = Query(..., ge=1),
    signature: str = Query(..., min_length=1),
    disposition: meeting_service.MeetingAttachmentDisposition = "attachment",
    db: Session = Depends(get_db_session),
) -> StreamingResponse:
    content = meeting_service.open_file_attachment_content(
        db,
        file_id=file_id,
        expires=expires,
        signature=signature,
        disposition=disposition,
    )
    return StreamingResponse(
        content.body,
        media_type=content.media_type,
        headers=content.headers,
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


@router.get("/meetings/{meeting_id}/recordings/{recording_id}/media")
def stream_recording_media(
    meeting_id: str,
    recording_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
):
    return recording_service.stream_recording_media(
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
    member_user_ids = workspace_meeting_user_ids_subquery(workspace.id)
    query = (
        select(User)
        .join(member_user_ids, member_user_ids.c.user_id == User.id)
        .outerjoin(OrgUnit, User.primary_org_unit_id == OrgUnit.id)
        .options(contains_eager(User.primary_org_unit))
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
                OrgUnit.name.ilike(like),
            )
        )
    query = query.order_by(User.full_name.asc(), User.email.asc()).limit(limit)
    users = db.scalars(query).all()
    return [
        MeetingUserItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            primary_org_unit_name=(user.primary_org_unit.name if user.primary_org_unit else None),
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
    workspace: Workspace = Depends(require_current_workspace),
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
        workspace=workspace,
        principal=user_principal(
            workspace_id=workspace.id,
            user_id=current_user.id,
            source="api.meeting.find_availability",
        ),
        viewer=current_user,
        user_ids=user_ids,
        from_at=from_at,
        to_at=to_at,
    )
