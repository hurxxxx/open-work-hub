from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Path, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import load_active_workspace_by_key, resolve_workspace_role
from open_alm_api.domains.auth.dependencies import require_current_user
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.dm import attachment_application
from open_alm_api.domains.dm import conversation_application
from open_alm_api.domains.dm import message_application
from open_alm_api.domains.dm import realtime_events
from open_alm_api.domains.dm import user_directory
from open_alm_api.domains.dm.attachment_links import DmAttachmentDisposition
from open_alm_api.domains.dm.schemas import (
    DmAddParticipantsRequest,
    DmAttachmentUrlResponse,
    DmMessageAttachmentItem,
    DmConversationItem,
    DmConversationListResponse,
    DmCreateConversationRequest,
    DmMessageItem,
    DmMessageListResponse,
    DmSendMessageRequest,
    DmUpdateConversationRequest,
    DmUserItem,
)
from open_alm_api.domains.dm.request_normalization import (
    DM_ROUTE_ID_ALLOWED_PATTERN,
    DM_ROUTE_ID_MAX_LENGTH,
)


router = APIRouter(prefix="/dm", tags=["dm"])
public_router = APIRouter(prefix="/dm", tags=["dm"])
DmRouteIdPath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=DM_ROUTE_ID_MAX_LENGTH,
        pattern=DM_ROUTE_ID_ALLOWED_PATTERN,
    ),
]


def _dm_events(request: Request, db: Session) -> realtime_events.DmEventPublisher:
    return realtime_events.DmEventPublisher(db=db, realtime=request.app.state.app_realtime)


@router.get("/users", response_model=list[DmUserItem])
def search_dm_users(
    include_current: bool = Query(default=False),
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=100),
    workspace_key: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[DmUserItem]:
    workspace_id = None
    if workspace_key is not None:
        workspace = load_active_workspace_by_key(db, workspace_key)
        if workspace is None:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="workspace.not_found",
            )
        if resolve_workspace_role(db, current_user, workspace.id) is None:
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="workspace.membership_required",
                workspace=workspace.key,
            )
        workspace_id = workspace.id

    return user_directory.search_users(
        db,
        current_user=current_user,
        include_current=include_current,
        q=q,
        limit=limit,
        workspace_id=workspace_id,
    )


@router.get("/conversations", response_model=DmConversationListResponse)
@router.get("/threads", response_model=DmConversationListResponse, include_in_schema=False)
def list_dm_conversations(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmConversationListResponse:
    return conversation_application.list_dm_conversations(db, current_user=current_user)


@router.post(
    "/conversations", response_model=DmConversationItem, status_code=status.HTTP_201_CREATED
)
@router.post(
    "/threads",
    response_model=DmConversationItem,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_dm_conversation(
    payload: DmCreateConversationRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmConversationItem:
    return conversation_application.create_dm_conversation(
        db,
        current_user=current_user,
        recipient_user_id=payload.recipient_user_id,
        participant_user_ids=payload.participant_user_ids,
        title=payload.title,
        events=_dm_events(request, db),
    )


@router.patch("/conversations/{conversation_id}", response_model=DmConversationItem)
def update_dm_conversation(
    conversation_id: DmRouteIdPath,
    payload: DmUpdateConversationRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmConversationItem:
    return conversation_application.update_dm_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        title=payload.title,
        events=_dm_events(request, db),
    )


@router.post("/conversations/{conversation_id}/participants", response_model=DmConversationItem)
def add_dm_conversation_participants(
    conversation_id: DmRouteIdPath,
    payload: DmAddParticipantsRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmConversationItem:
    return conversation_application.add_dm_conversation_participants(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        user_ids=payload.user_ids,
        events=_dm_events(request, db),
    )


@router.delete(
    "/conversations/{conversation_id}/participants/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
def leave_dm_conversation(
    conversation_id: DmRouteIdPath,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    conversation_application.leave_dm_conversation(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        events=_dm_events(request, db),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/conversations/{conversation_id}/participants/{user_id}", response_model=DmConversationItem
)
def remove_dm_conversation_participant(
    conversation_id: DmRouteIdPath,
    user_id: DmRouteIdPath,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmConversationItem:
    return conversation_application.remove_dm_conversation_participant(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        user_id=user_id,
        events=_dm_events(request, db),
    )


@router.get("/conversations/{conversation_id}/messages", response_model=DmMessageListResponse)
@router.get(
    "/threads/{conversation_id}/messages",
    response_model=DmMessageListResponse,
    include_in_schema=False,
)
def list_dm_messages(
    conversation_id: DmRouteIdPath,
    limit: int = Query(default=50, ge=1, le=100),
    before: datetime | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmMessageListResponse:
    return message_application.list_dm_messages(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        limit=limit,
        before=before,
    )


@router.post(
    "/conversations/{conversation_id}/attachments",
    response_model=DmMessageAttachmentItem,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dm_attachment(
    conversation_id: DmRouteIdPath,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmMessageAttachmentItem:
    return await attachment_application.upload_dm_attachment(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        file=file,
        content_length=request.headers.get("content-length"),
    )


@router.get("/attachments/{attachment_id}/download", response_model=DmAttachmentUrlResponse)
def get_dm_attachment_download_url(
    attachment_id: DmRouteIdPath,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmAttachmentUrlResponse:
    return attachment_application.get_dm_attachment_download_url(
        db,
        current_user=current_user,
        attachment_id=attachment_id,
    )


@router.get("/attachments/{attachment_id}/preview", response_model=DmAttachmentUrlResponse)
def get_dm_attachment_preview_url(
    attachment_id: DmRouteIdPath,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmAttachmentUrlResponse:
    return attachment_application.get_dm_attachment_preview_url(
        db,
        current_user=current_user,
        attachment_id=attachment_id,
    )


@public_router.get("/attachments/{attachment_id}/content")
def proxy_dm_attachment_content(
    attachment_id: DmRouteIdPath,
    expires: int = Query(..., ge=1),
    signature: str = Query(..., min_length=1),
    disposition: DmAttachmentDisposition = "attachment",
    db: Session = Depends(get_db_session),
) -> StreamingResponse:
    content = attachment_application.open_dm_attachment_content(
        db,
        attachment_id=attachment_id,
        expires=expires,
        signature=signature,
        disposition=disposition,
    )
    return StreamingResponse(
        content.body,
        media_type=content.media_type,
        headers=content.headers,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=DmMessageItem)
@router.post(
    "/threads/{conversation_id}/messages",
    response_model=DmMessageItem,
    include_in_schema=False,
)
def send_dm_message(
    conversation_id: DmRouteIdPath,
    payload: DmSendMessageRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmMessageItem:
    return message_application.send_dm_message(
        db,
        sender=current_user,
        conversation_id=conversation_id,
        body=payload.body,
        attachment_ids=payload.attachment_ids or [],
        reply_to_message_id=payload.reply_to_message_id,
        events=_dm_events(request, db),
    )


@router.patch("/conversations/{conversation_id}/read", response_model=DmConversationItem)
@router.patch(
    "/threads/{conversation_id}/read",
    response_model=DmConversationItem,
    include_in_schema=False,
)
def mark_dm_conversation_read(
    conversation_id: DmRouteIdPath,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> DmConversationItem:
    return conversation_application.mark_dm_conversation_read(
        db,
        current_user=current_user,
        conversation_id=conversation_id,
        events=_dm_events(request, db),
    )
