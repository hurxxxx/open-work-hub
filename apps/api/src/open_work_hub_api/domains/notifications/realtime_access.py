from __future__ import annotations

from sqlalchemy.orm import Session

from open_work_hub_api.core.realtime import RealtimeEvent
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.notifications import realtime_event_types, service, visibility
from open_work_hub_api.domains.notifications.realtime_events import (
    build_notification_realtime_event,
)
from open_work_hub_api.domains.pms.models import Notification


def authorize_notification_realtime_event(
    db: Session, *, user: User, event: RealtimeEvent
) -> RealtimeEvent | None:
    event_type = event.get("type")
    if not realtime_event_types.is_notification_realtime_event_type(event_type):
        return None
    data = event.get("data")
    if not isinstance(data, dict):
        return None
    queued = data.get("notification")
    notification_id = queued.get("id") if isinstance(queued, dict) else None
    notification = (
        db.get(Notification, notification_id) if isinstance(notification_id, str) else None
    )
    projected = None
    if notification is not None and visibility.notification_is_visible(
        db, notification=notification, user=user
    ):
        projected = service.serialize_notification(notification).model_dump(mode="json")
    # Stored text and counts are projections, not a grant. Rebuild both from
    # the current source/recipient policy rather than forwarding queued values.
    return {
        **event,
        **build_notification_realtime_event(
            event_type, notification=projected, unread_count=service.unread_count(db, user.id)
        ),
    }
