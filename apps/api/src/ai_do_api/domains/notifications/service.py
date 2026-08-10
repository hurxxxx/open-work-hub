from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_do_api.domains.notifications.schemas import GlobalNotificationItem
from ai_do_api.domains.pms.links import normalize_pms_deep_link
from ai_do_api.domains.pms.models import Notification

EXCLUDED_GLOBAL_NOTIFICATION_TYPES = ("dm_message",)


def serialize_notification(notification: Notification) -> GlobalNotificationItem:
    return GlobalNotificationItem(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        reference_type=notification.reference_type,
        reference_id=notification.reference_id,
        action_url=normalize_pms_deep_link(notification.action_url),
        is_read=notification.is_read,
        created_at=notification.created_at,
    )


def unread_count(db: Session, user_id: str) -> int:
    return (
        db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
                Notification.type.notin_(EXCLUDED_GLOBAL_NOTIFICATION_TYPES),
            )
        )
        or 0
    )
