from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import AuthSession, CompanyAppControl, User
from open_work_hub_api.domains.auth.security import hash_token
from open_work_hub_api.domains.realtime import router
from open_work_hub_api.domains.realtime.resource_subscriptions import (
    requested_resource_subscription,
)


def _resource(client, app):
    owner = dev_login(client, "delivery-hub-admin")
    reader = dev_login(client, "delivery-hub-member")
    response = client.post(
        f"/api/v1/{app}/items",
        headers=auth_headers(owner["token"]),
        json={"title": "Private source"},
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["id"]
    link = client.put(
        f"/api/v1/{app}/items/{item_id}/sharing/link",
        headers=auth_headers(owner["token"]),
        json={"access_level": "edit", "active": True},
    )
    assert link.status_code == 200, link.text
    return owner, reader, item_id, link.json()["link_share"]["token"]


def _connect(socket, token):
    socket.send_json({"type": "auth", "token": token})
    assert socket.receive_json()["type"] == "realtime.auth.ok"
    assert socket.receive_json()["type"] == "notification.snapshot"


def _subscribe(socket, app, item_id, share_token):
    socket.send_json(
        {
            "type": "subscribe",
            "topic": f"{app}.pages" if app == "docs" else "whiteboard.access",
            "key": item_id,
            "share_token": share_token,
        }
    )


def _control(app, item_id):
    return {
        "type": f"{app}.access.changed",
        "data": {"doc_id" if app == "docs" else "whiteboard_id": item_id},
    }


def _assert_initial(socket, app, item_id):
    initial = socket.receive_json()
    if app == "docs":
        assert initial["type"] == "docs.pages.snapshot"
        assert initial["data"]["doc_id"] == item_id
    else:
        assert initial == _control(app, item_id)


@pytest.mark.parametrize("app", ["docs", "whiteboard"])
@pytest.mark.parametrize("change", ["revoke", "regenerate", "downgrade"])
def test_websocket_observes_current_link_policy_and_detaches_revoked_reader(client, app, change):
    owner, reader, item_id, link = _resource(client, app)
    with client.websocket_connect("/api/v1/realtime/ws") as socket:
        _connect(socket, reader["token"])
        _subscribe(socket, app, item_id, link)
        _assert_initial(socket, app, item_id)
        url = f"/api/v1/{app}/items/{item_id}/sharing/link"
        if change == "revoke":
            response = client.delete(url, headers=auth_headers(owner["token"]))
        else:
            response = client.put(
                url,
                headers=auth_headers(owner["token"]),
                json={
                    "access_level": "read",
                    "active": True,
                    "regenerate_token": change == "regenerate",
                },
            )
        assert response.status_code == 200, response.text
        assert socket.receive_json() == _control(app, item_id)
        # A marker through the same hub is an ordering barrier. A revoked viewer
        # must not observe subsequent changes even if it never unsubscribes.
        hub = client.app.state.app_realtime
        channel = f"docs.pages:{item_id}" if app == "docs" else f"whiteboard.access:{item_id}"
        hub.publish(channel, _control(app, item_id))
        hub.publish_user(reader["user"]["id"], {"type": "test.barrier", "data": {}})
        if change == "downgrade":
            assert socket.receive_json() == _control(app, item_id)
            current = client.get(
                f"/api/v1/{app}/shared-links/{link}", headers=auth_headers(reader["token"])
            )
            assert current.status_code == 200, current.text
            assert current.json()["item"]["can_edit"] is False
        barrier = socket.receive_json()
        assert barrier["type"] == "test.barrier"
        assert barrier["data"] == {}
        socket.close()


@pytest.mark.parametrize("app", ["docs", "whiteboard"])
@pytest.mark.parametrize("reason", ["no_acl", "other_resource_link", "app_disabled"])
def test_websocket_denies_unauthorized_subscription_with_only_requested_id(client, app, reason):
    owner, reader, item_id, link = _resource(client, app)
    if reason == "other_resource_link":
        other = client.post(
            f"/api/v1/{app}/items",
            headers=auth_headers(owner["token"]),
            json={"title": "Other private source"},
        )
        assert other.status_code == 201
        item_id = other.json()["id"]
    if reason == "app_disabled":
        with get_session_factory()() as db:
            db.get(CompanyAppControl, app).enabled = False
            db.commit()
    with client.websocket_connect("/api/v1/realtime/ws") as socket:
        _connect(socket, reader["token"])
        _subscribe(socket, app, item_id, None if reason == "no_acl" else link)
        assert socket.receive_json() == _control(app, item_id)
        assert socket.receive_json()["type"] == "realtime.error"
        hub = client.app.state.app_realtime
        channel = f"docs.pages:{item_id}" if app == "docs" else f"whiteboard.access:{item_id}"
        hub.publish(channel, _control(app, item_id))
        hub.publish_user(reader["user"]["id"], {"type": "test.barrier", "data": {}})
        barrier = socket.receive_json()
        assert barrier["type"] == "test.barrier"
        assert barrier["data"] == {}
        socket.close()


@pytest.mark.parametrize("direction", ["incoming", "outgoing"])
@pytest.mark.parametrize("change", ["revoke", "suspended", "login_blocked", "must_change_password"])
def test_websocket_rechecks_session_for_every_message_without_waiting_for_monitor(
    client, direction, change
):
    user = dev_login(client, "delivery-hub-member")
    with client.websocket_connect("/api/v1/realtime/ws") as socket:
        _connect(socket, user["token"])
        with get_session_factory()() as db:
            session = db.scalar(
                select(AuthSession).where(AuthSession.token_hash == hash_token(user["token"]))
            )
            if change == "revoke":
                session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
            else:
                current_user = db.get(User, user["user"]["id"])
                if change == "suspended":
                    current_user.status = "suspended"
                else:
                    setattr(current_user, change, True)
            db.commit()
        if direction == "incoming":
            socket.send_json({"type": "unsupported"})
        else:
            client.app.state.app_realtime.publish_user(
                user["user"]["id"], {"type": "test.private", "data": {"body": "must never arrive"}}
            )
        with pytest.raises(WebSocketDisconnect) as denied:
            socket.receive_json()
        assert denied.value.code == 1008


def test_queued_docs_content_is_redacted_after_revocation_and_stale_envelopes_discarded(client):
    _owner, reader, item_id, link = _resource(client, "docs")
    from open_work_hub_api.domains.docs.models import NativeDocLinkShare
    from open_work_hub_api.core.realtime import InProcessAppRealtimeHub

    async def exercise():
        hub = InProcessAppRealtimeHub(instance_id="queued-revocation")
        await hub.startup()
        outbound = asyncio.Queue()
        payload = {"topic": "docs.pages", "key": item_id, "share_token": link}
        resource = requested_resource_subscription(payload)
        subscription = router._subscribe_topic(
            hub, resource.channel, outbound, client_payload=payload, resource=resource
        )
        subscriptions = {router._subscription_id(resource.topic, resource.key, link): subscription}
        # Both frames are already queued before the canonical ACL changes.
        for value in ("first secret", "second secret"):
            outbound.put_nowait(
                router.OutboundEvent(
                    {"type": "docs.pages.changed", "data": {"doc_id": item_id, "pages": [value]}},
                    subscription,
                )
            )
        with get_session_factory()() as db:
            stored_link = db.scalar(
                select(NativeDocLinkShare).where(NativeDocLinkShare.token == link)
            )
            stored_link.active = False
            db.commit()

        class Probe:
            headers = {}
            sent = []

            async def send_json(self, event):
                self.sent.append(event)
                if event["type"] == "test.barrier":
                    raise WebSocketDisconnect()

        probe = Probe()
        outbound.put_nowait(router.OutboundEvent({"type": "test.barrier", "data": {}}))
        try:
            with pytest.raises(WebSocketDisconnect):
                await asyncio.wait_for(
                    router._send_outbound_events(
                        probe,
                        outbound,
                        hub=hub,
                        subscriptions=subscriptions,
                        token=reader["token"],
                        user_id=reader["user"]["id"],
                    ),
                    timeout=3,
                )
            assert probe.sent == [_control("docs", item_id), {"type": "test.barrier", "data": {}}]
            assert not subscription.active
            assert not subscriptions
            assert not hub._queues
        finally:
            await hub.shutdown()

    asyncio.run(exercise())


def test_direct_and_shared_link_subscriptions_keep_distinct_authority_and_refcounts(client):
    owner, _reader, item_id, link = _resource(client, "docs")
    from open_work_hub_api.core.realtime import InProcessAppRealtimeHub
    from open_work_hub_api.domains.docs.models import NativeDocLinkShare

    async def exercise():
        hub = InProcessAppRealtimeHub(instance_id="distinct-link-contexts")
        await hub.startup()
        outbound = asyncio.Queue()
        subscriptions = {}
        direct_payload = {"type": "subscribe", "topic": "docs.pages", "key": item_id}
        link_payload = {**direct_payload, "share_token": link}
        for payload in (direct_payload, link_payload, link_payload):
            await router._handle_subscribe(
                payload,
                hub=hub,
                outbound=outbound,
                subscriptions=subscriptions,
                token=owner["token"],
                user_id=owner["user"]["id"],
            )
        direct_id = router._subscription_id("docs.pages", item_id)
        link_id = router._subscription_id("docs.pages", item_id, link)
        assert len(subscriptions) == 2
        assert subscriptions[direct_id].ref_count == 1
        assert subscriptions[link_id].ref_count == 2
        router._handle_unsubscribe(link_payload, hub=hub, subscriptions=subscriptions)
        assert subscriptions[link_id].ref_count == 1
        assert subscriptions[direct_id].active
        # Discard only initial snapshots; the following frames model a queued
        # content update with separate original authority bindings.
        while not outbound.empty():
            outbound.get_nowait()
        direct = subscriptions[direct_id]
        linked = subscriptions[link_id]
        content = {
            "type": "docs.pages.changed",
            "data": {"doc_id": item_id, "pages": ["owner content"]},
        }
        outbound.put_nowait(router.OutboundEvent(content, direct))
        outbound.put_nowait(router.OutboundEvent(content, linked))
        with get_session_factory()() as db:
            stored = db.scalar(select(NativeDocLinkShare).where(NativeDocLinkShare.token == link))
            stored.active = False
            db.commit()
        outbound.put_nowait(router.OutboundEvent({"type": "test.barrier", "data": {}}))

        class Probe:
            headers = {}
            sent = []

            async def send_json(self, event):
                if event["type"] == "test.barrier":
                    raise WebSocketDisconnect()
                self.sent.append(event)

        probe = Probe()
        try:
            with pytest.raises(WebSocketDisconnect):
                await asyncio.wait_for(
                    router._send_outbound_events(
                        probe,
                        outbound,
                        hub=hub,
                        subscriptions=subscriptions,
                        token=owner["token"],
                        user_id=owner["user"]["id"],
                    ),
                    timeout=3,
                )
            assert probe.sent == [content, _control("docs", item_id)]
            assert link not in str(probe.sent)
            assert list(subscriptions) == [direct_id]
            assert direct.active and not linked.active
            router._handle_unsubscribe(direct_payload, hub=hub, subscriptions=subscriptions)
            assert not subscriptions
        finally:
            router._unsubscribe_topic(hub, direct)
            router._unsubscribe_topic(hub, linked)
            await hub.shutdown()

    asyncio.run(exercise())


@pytest.mark.parametrize("app", ["docs", "whiteboard"])
def test_periodic_resource_recheck_sends_control_and_detaches_if_invalidation_was_lost(
    client, monkeypatch, app
):
    _owner, reader, item_id, link = _resource(client, app)
    monkeypatch.setattr(router, "REALTIME_ACCESS_RECHECK_SECONDS", 0.02)
    with client.websocket_connect("/api/v1/realtime/ws") as socket:
        _connect(socket, reader["token"])
        _subscribe(socket, app, item_id, link)
        _assert_initial(socket, app, item_id)
        with get_session_factory()() as db:
            db.get(CompanyAppControl, app).enabled = False
            db.commit()
        assert socket.receive_json() == _control(app, item_id)
        hub = client.app.state.app_realtime
        hub.publish_user(reader["user"]["id"], {"type": "test.barrier", "data": {}})
        assert socket.receive_json()["type"] == "test.barrier"
        socket.close()


@pytest.mark.parametrize("query", ["token=", "token=legacy-query-secret"])
def test_realtime_rejects_query_token_authentication(client, query):
    with client.websocket_connect(f"/api/v1/realtime/ws?{query}") as socket:
        with pytest.raises(WebSocketDisconnect) as denied:
            socket.receive_json()
        assert denied.value.code == 1008


@pytest.mark.parametrize("payload", [None, [], "token", 7, {"type": "auth", "token": []}])
def test_realtime_rejects_malformed_first_auth_frame(client, payload):
    with client.websocket_connect("/api/v1/realtime/ws") as socket:
        socket.send_json(payload)
        with pytest.raises(WebSocketDisconnect) as denied:
            socket.receive_json()
        assert denied.value.code == 1008
