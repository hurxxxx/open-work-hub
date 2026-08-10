from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.notifications import realtime_event_types, realtime_events
from open_alm_api.domains.notifications import read_projection
from open_alm_api.domains.notifications import service
from open_alm_api.domains.notifications.schemas import (
    GlobalNotificationItem,
    GlobalNotificationListResponse,
)
from open_alm_api.domains.pms.models import Notification

NotificationReadResult = read_projection.NotificationReadResult


class NotificationEventPublisher(Protocol):
    def publish_notification(
        self,
        user_id: str,
        *,
        event_type: str,
        notification: dict[str, Any] | None,
        unread_count: int,
    ) -> None: ...


class RealtimeNotificationEventPublisher:
    def __init__(self, realtime: realtime_events.UserRealtimePublisher) -> None:
        self._realtime = realtime

    def publish_notification(
        self,
        user_id: str,
        *,
        event_type: str,
        notification: dict[str, Any] | None,
        unread_count: int,
    ) -> None:
        realtime_events.publish_notification_event(
            self._realtime,
            user_id,
            event_type,
            notification=notification,
            unread_count=unread_count,
        )


def list_user_notifications(
    db: Session,
    *,
    user_id: str,
    page: int,
    page_size: int,
) -> GlobalNotificationListResponse:
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .where(Notification.type.notin_(service.EXCLUDED_GLOBAL_NOTIFICATION_TYPES))
            .order_by(Notification.created_at.desc())
        )
    )
    return read_projection.build_notification_list_response(
        rows,
        page=page,
        page_size=page_size,
    )


def mark_one_read(
    db: Session,
    *,
    user_id: str,
    notification_id: str,
) -> NotificationReadResult:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    if notification is None:
        raise localized_http_exception(status_code=404, code="notifications.not_found")

    notification.is_read = True
    db.commit()
    return NotificationReadResult(
        item=service.serialize_notification(notification),
        unread_count=service.unread_count(db, user_id),
    )


def mark_one_read_and_publish(
    db: Session,
    *,
    user_id: str,
    notification_id: str,
    events: NotificationEventPublisher,
) -> GlobalNotificationItem:
    result = mark_one_read(
        db,
        user_id=user_id,
        notification_id=notification_id,
    )
    events.publish_notification(
        user_id,
        event_type=realtime_event_types.NOTIFICATION_READ,
        notification=read_projection.notification_event_payload(result.item),
        unread_count=result.unread_count,
    )
    return result.item


def mark_all_read(db: Session, *, user_id: str) -> int:
    from sqlalchemy import update as sa_update

    db.execute(
        sa_update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
            Notification.type.notin_(service.EXCLUDED_GLOBAL_NOTIFICATION_TYPES),
        )
        .values(is_read=True)
    )
    db.commit()
    return service.unread_count(db, user_id)


def mark_all_read_and_publish(
    db: Session,
    *,
    user_id: str,
    events: NotificationEventPublisher,
) -> None:
    unread_count = mark_all_read(db, user_id=user_id)
    events.publish_notification(
        user_id,
        event_type=realtime_event_types.NOTIFICATIONS_READ_ALL,
        notification=None,
        unread_count=unread_count,
    )
