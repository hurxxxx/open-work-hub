from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.notifications.schemas import GlobalNotificationItem
from open_work_hub_api.domains.notifications.visibility import (
    iter_visible_notification_batches,
)
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.pms.models import Notification


def serialize_notification(notification: Notification) -> GlobalNotificationItem:
    if notification.origin_app_id is None:
        raise ValueError("global notification is missing origin_app_id")
    return GlobalNotificationItem(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        source_type=notification.source_type,
        source_id=notification.source_id,
        origin_app_id=notification.origin_app_id,
        origin_workspace_id=notification.origin_workspace_id,
        action_url=notification.action_url,
        is_read=notification.is_read,
        created_at=notification.created_at,
    )


def unread_count(db: Session, user_id: str) -> int:
    user = db.get(User, user_id)
    if user is None:
        return 0
    statement = select(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    )
    return sum(
        len(rows)
        for rows in iter_visible_notification_batches(
            db,
            user=user,
            statement=statement,
        )
    )
