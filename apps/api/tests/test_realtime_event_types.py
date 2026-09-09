from __future__ import annotations

from open_work_hub_api.domains.realtime import realtime_event_types
from open_work_hub_api.domains.auth.realtime import (
    AUTH_ACCESS_CHANGED,
    build_app_availability_access_changed_event,
    build_principal_access_changed_event,
    publish_principal_access_changed,
)


def test_realtime_event_type_constants_match_client_contract() -> None:
    assert realtime_event_types.REALTIME_AUTH == "auth"
    assert realtime_event_types.REALTIME_SUBSCRIBE == "subscribe"
    assert realtime_event_types.REALTIME_UNSUBSCRIBE == "unsubscribe"
    assert realtime_event_types.REALTIME_AUTH_OK == "realtime.auth.ok"
    assert realtime_event_types.REALTIME_KEEPALIVE == "realtime.keepalive"
    assert AUTH_ACCESS_CHANGED == "auth.access.changed"


def test_realtime_protocol_classifies_client_and_server_events() -> None:
    assert realtime_event_types.is_realtime_client_event_type("auth")
    assert realtime_event_types.is_realtime_client_event_type("subscribe")
    assert not realtime_event_types.is_realtime_client_event_type("realtime.keepalive")

    assert realtime_event_types.is_realtime_server_event_type("realtime.auth.ok")
    assert realtime_event_types.is_realtime_server_event_type("realtime.keepalive")
    assert not realtime_event_types.is_realtime_server_event_type("auth.access.changed")
    assert not realtime_event_types.is_realtime_server_event_type("subscribe")


def test_build_realtime_event_uses_shared_wire_shape() -> None:
    assert realtime_event_types.build_realtime_event(
        realtime_event_types.REALTIME_AUTH_OK,
    ) == {"type": "realtime.auth.ok", "data": {}}
    assert realtime_event_types.build_realtime_event(
        realtime_event_types.REALTIME_KEEPALIVE,
        {"now": 123},
    ) == {"type": "realtime.keepalive", "data": {"now": 123}}


def test_principal_access_event_uses_public_auth_contract() -> None:
    assert build_principal_access_changed_event() == {
        "type": "auth.access.changed",
        "data": {"reason": "principal"},
    }
    assert build_app_availability_access_changed_event() == {
        "type": "auth.access.changed",
        "data": {"reason": "app_availability"},
    }


def test_principal_access_publish_deduplicates_users() -> None:
    class FakeRealtime:
        def __init__(self) -> None:
            self.published: list[tuple[str, dict]] = []

        def publish_user(self, user_id: str, event: dict) -> None:
            self.published.append((user_id, event))

    realtime = FakeRealtime()
    publish_principal_access_changed(
        realtime,
        ["user-b", "user-a", "user-b", ""],
    )

    assert realtime.published == [
        (
            "user-a",
            {
                "type": "auth.access.changed",
                "data": {"reason": "principal"},
            },
        ),
        (
            "user-b",
            {
                "type": "auth.access.changed",
                "data": {"reason": "principal"},
            },
        ),
    ]
