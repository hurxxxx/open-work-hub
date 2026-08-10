from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.domains.auth.dependencies import require_current_user
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.notifications import read_service
from open_alm_api.domains.notifications import service
from open_alm_api.domains.notifications.schemas import (
    GlobalNotificationItem,
    GlobalNotificationListResponse,
    GlobalUnreadCountResponse,
)


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=GlobalNotificationListResponse)
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> GlobalNotificationListResponse:
    return read_service.list_user_notifications(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=GlobalUnreadCountResponse)
def get_unread_count(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> GlobalUnreadCountResponse:
    return GlobalUnreadCountResponse(count=service.unread_count(db, current_user.id))


@router.patch("/{notification_id}/read", response_model=GlobalNotificationItem)
def mark_notification_read(
    notification_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> GlobalNotificationItem:
    return read_service.mark_one_read_and_publish(
        db,
        user_id=current_user.id,
        notification_id=notification_id,
        events=read_service.RealtimeNotificationEventPublisher(
            request.app.state.app_realtime
        ),
    )


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_read(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    read_service.mark_all_read_and_publish(
        db,
        user_id=current_user.id,
        events=read_service.RealtimeNotificationEventPublisher(
            request.app.state.app_realtime
        ),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
