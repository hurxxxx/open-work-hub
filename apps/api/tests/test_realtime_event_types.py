from __future__ import annotations

from open_alm_api.domains.realtime import realtime_event_types


def test_realtime_event_type_constants_match_client_contract() -> None:
    assert realtime_event_types.REALTIME_AUTH == "auth"
    assert realtime_event_types.REALTIME_SUBSCRIBE == "subscribe"
    assert realtime_event_types.REALTIME_UNSUBSCRIBE == "unsubscribe"
    assert realtime_event_types.REALTIME_AUTH_OK == "realtime.auth.ok"
    assert realtime_event_types.REALTIME_KEEPALIVE == "realtime.keepalive"


def test_realtime_protocol_classifies_client_and_server_events() -> None:
    assert realtime_event_types.is_realtime_client_event_type("auth")
    assert realtime_event_types.is_realtime_client_event_type("subscribe")
    assert not realtime_event_types.is_realtime_client_event_type("realtime.keepalive")

    assert realtime_event_types.is_realtime_server_event_type("realtime.auth.ok")
    assert realtime_event_types.is_realtime_server_event_type("realtime.keepalive")
    assert not realtime_event_types.is_realtime_server_event_type("subscribe")


def test_build_realtime_event_uses_shared_wire_shape() -> None:
    assert realtime_event_types.build_realtime_event(
        realtime_event_types.REALTIME_AUTH_OK,
    ) == {"type": "realtime.auth.ok", "data": {}}
    assert realtime_event_types.build_realtime_event(
        realtime_event_types.REALTIME_KEEPALIVE,
        {"now": 123},
    ) == {"type": "realtime.keepalive", "data": {"now": 123}}
