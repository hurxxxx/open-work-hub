from __future__ import annotations

from typing import Literal, TypeAlias, TypeGuard


NOTIFICATION_SNAPSHOT = "notification.snapshot"
NOTIFICATION_CREATED = "notification.created"
NOTIFICATION_READ = "notification.read"
NOTIFICATIONS_READ_ALL = "notifications.read_all"

NotificationRealtimeEventType: TypeAlias = Literal[
    "notification.snapshot",
    "notification.created",
    "notification.read",
    "notifications.read_all",
]

NOTIFICATION_REALTIME_EVENT_TYPES: tuple[NotificationRealtimeEventType, ...] = (
    NOTIFICATION_SNAPSHOT,
    NOTIFICATION_CREATED,
    NOTIFICATION_READ,
    NOTIFICATIONS_READ_ALL,
)
NOTIFICATION_REALTIME_EVENT_TYPE_VALUES = NOTIFICATION_REALTIME_EVENT_TYPES
NOTIFICATION_REALTIME_EVENT_TYPE_SET = frozenset(NOTIFICATION_REALTIME_EVENT_TYPES)


def is_notification_realtime_event_type(
    value: object,
) -> TypeGuard[NotificationRealtimeEventType]:
    return isinstance(value, str) and value in NOTIFICATION_REALTIME_EVENT_TYPE_SET
