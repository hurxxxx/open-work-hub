from __future__ import annotations

from typing import Any

from open_work_hub_api.domains.notifications import realtime_event_types, realtime_events


def test_build_notification_realtime_event_uses_shared_payload_contract() -> None:
    assert realtime_events.build_notification_realtime_event(
        realtime_event_types.NOTIFICATION_READ,
        notification={"id": "notification-1"},
        unread_count=2,
    ) == {
        "type": "notification.read",
        "data": {
            "notification": {"id": "notification-1"},
            "unread_count": 2,
        },
    }


def test_publish_notification_event_uses_shared_payload_contract() -> None:
    realtime = _FakeRealtime()

    realtime_events.publish_notification_event(
        realtime,
        "user-1",
        realtime_event_types.NOTIFICATION_READ,
        notification={"id": "notification-1"},
        unread_count=2,
    )

    assert realtime.published == [
        (
            "user-1",
            {
                "type": "notification.read",
                "data": {
                    "notification": {"id": "notification-1"},
                    "unread_count": 2,
                },
            },
        )
    ]


class _FakeRealtime:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish_user(self, user_id: str, event: dict[str, Any]) -> None:
        self.published.append((user_id, event))
