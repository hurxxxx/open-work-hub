from __future__ import annotations

from typing import Any, Protocol


class UserRealtimePublisher(Protocol):
    def publish_user(self, user_id: str, event: dict[str, Any]) -> None: ...


def build_notification_realtime_event(
    event_type: str,
    *,
    notification: dict[str, Any] | None,
    unread_count: int,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "data": {
            "notification": notification,
            "unread_count": unread_count,
        },
    }


def publish_notification_event(
    realtime: UserRealtimePublisher,
    user_id: str,
    event_type: str,
    *,
    notification: dict[str, Any] | None,
    unread_count: int,
) -> None:
    realtime.publish_user(
        user_id,
        build_notification_realtime_event(
            event_type,
            notification=notification,
            unread_count=unread_count,
        ),
    )
