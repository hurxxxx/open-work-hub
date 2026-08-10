from __future__ import annotations

from ai_do_api.domains.notifications import realtime_event_types


def test_notification_realtime_event_type_constants_match_client_contract() -> None:
    assert realtime_event_types.NOTIFICATION_SNAPSHOT == "notification.snapshot"
    assert realtime_event_types.NOTIFICATION_CREATED == "notification.created"
    assert realtime_event_types.NOTIFICATION_READ == "notification.read"
    assert realtime_event_types.NOTIFICATIONS_READ_ALL == "notifications.read_all"
    assert realtime_event_types.NOTIFICATION_REALTIME_EVENT_TYPES == (
        "notification.snapshot",
        "notification.created",
        "notification.read",
        "notifications.read_all",
    )
    assert realtime_event_types.NOTIFICATION_REALTIME_EVENT_TYPE_VALUES == (
        "notification.snapshot",
        "notification.created",
        "notification.read",
        "notifications.read_all",
    )
    assert realtime_event_types.NOTIFICATION_REALTIME_EVENT_TYPE_SET == frozenset(
        {
            "notification.snapshot",
            "notification.created",
            "notification.read",
            "notifications.read_all",
        }
    )


def test_is_notification_realtime_event_type_accepts_only_shared_event_names() -> None:
    for event_type in realtime_event_types.NOTIFICATION_REALTIME_EVENT_TYPE_VALUES:
        assert realtime_event_types.is_notification_realtime_event_type(event_type)

    assert not realtime_event_types.is_notification_realtime_event_type(
        "notification.deleted"
    )
    assert not realtime_event_types.is_notification_realtime_event_type(
        "notification.read "
    )
    assert not realtime_event_types.is_notification_realtime_event_type("")
    assert not realtime_event_types.is_notification_realtime_event_type(None)
    assert not realtime_event_types.is_notification_realtime_event_type(1)
