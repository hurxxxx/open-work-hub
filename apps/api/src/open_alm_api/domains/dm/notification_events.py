from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.orm import Session

from open_alm_api.domains.notifications import realtime_event_types
from open_alm_api.domains.notifications import service as notification_service


class DmNotificationEventPublisher(Protocol):
    def publish_notification(
        self,
        user_id: str,
        *,
        notification: dict[str, Any] | None,
        unread_count: int,
        event_type: str = realtime_event_types.NOTIFICATION_CREATED,
    ) -> None: ...


class DmNotificationRecipient(Protocol):
    user: Any
    notification: Any


def _serialize_notification_payload(notification: Any) -> dict[str, Any]:
    return notification_service.serialize_notification(notification).model_dump(mode="json")


def _recipient_user_id(recipient: DmNotificationRecipient) -> str:
    return recipient.user.id


def publish_created_notifications(
    db: Session,
    *,
    recipients: list[DmNotificationRecipient],
    events: DmNotificationEventPublisher,
) -> None:
    for recipient in recipients:
        publish_notification_event(
            db,
            user_id=_recipient_user_id(recipient),
            notification=_serialize_notification_payload(recipient.notification),
            events=events,
        )


def publish_read_notification(
    db: Session,
    *,
    user_id: str,
    events: DmNotificationEventPublisher,
) -> None:
    publish_notification_event(
        db,
        user_id=user_id,
        notification=None,
        event_type=realtime_event_types.NOTIFICATION_READ,
        events=events,
    )


def publish_notification_event(
    db: Session,
    *,
    user_id: str,
    notification: dict[str, Any] | None,
    events: DmNotificationEventPublisher,
    event_type: str = realtime_event_types.NOTIFICATION_CREATED,
) -> None:
    events.publish_notification(
        user_id,
        notification=notification,
        unread_count=notification_service.unread_count(db, user_id),
        event_type=event_type,
    )
