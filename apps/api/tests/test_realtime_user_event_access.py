from __future__ import annotations

import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.realtime import InProcessAppRealtimeHub, realtime_user_topic
from open_work_hub_api.domains.auth.models import CompanyAppControl
from open_work_hub_api.domains.community.models import CommunityPost
from open_work_hub_api.domains.dm.models import DmMessage
from open_work_hub_api.domains.pms.models import Notification
from open_work_hub_api.domains.realtime import router
from test_notifications import _create_notification


def _deliver_queued(event, recipient):
    async def exercise():
        hub = InProcessAppRealtimeHub(instance_id="queued-user-event")
        await hub.startup()
        outbound = asyncio.Queue()
        subscription = router._subscribe_topic(
            hub, realtime_user_topic(recipient["user"]["id"]), outbound
        )
        outbound.put_nowait(router.OutboundEvent(event, subscription))
        outbound.put_nowait(router.OutboundEvent({"type": "test.barrier", "data": {}}))

        class Probe:
            headers = {}
            sent = []

            async def send_json(self, item):
                if item["type"] == "test.barrier":
                    raise WebSocketDisconnect()
                self.sent.append(item)

        probe = Probe()
        try:
            with pytest.raises(WebSocketDisconnect):
                await asyncio.wait_for(
                    router._send_outbound_events(
                        probe,
                        outbound,
                        hub=hub,
                        subscriptions={},
                        token=recipient["token"],
                        user_id=recipient["user"]["id"],
                    ),
                    timeout=3,
                )
            return probe.sent
        finally:
            router._unsubscribe_topic(hub, subscription)
            await hub.shutdown()

    return asyncio.run(exercise())


@pytest.mark.parametrize(
    "membership", ["active", "removed", "never_joined", "rejoined_old", "rejoined_reply"]
)
def test_queued_dm_content_rechecks_current_membership_and_join_history(
    client, monkeypatch, membership
):
    owner = dev_login(client, "administrator")
    reader = dev_login(client, "delivery-hub-member")
    outside = dev_login(client, "delivery-hub-admin")
    teammate = dev_login(client, "knowledge-base-admin")
    captured = []
    monkeypatch.setattr(
        client.app.state.app_realtime,
        "publish_user",
        lambda user_id, event: captured.append((user_id, event)),
    )
    created = client.post(
        "/api/v1/dm/conversations",
        headers=auth_headers(owner["token"]),
        json={
            "title": "Private group",
            "participant_user_ids": [reader["user"]["id"], teammate["user"]["id"]],
        },
    )
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    response = client.post(
        f"/api/v1/dm/conversations/{conversation_id}/messages",
        headers=auth_headers(owner["token"]),
        json={"body": "old private history"},
    )
    assert response.status_code == 200, response.text
    old_message_id = response.json()["id"]
    event = next(
        event
        for user_id, event in reversed(captured)
        if user_id == reader["user"]["id"] and event["type"] == "dm.message.created"
    )
    if membership.startswith("rejoined") or membership == "removed":
        removed = client.delete(
            f"/api/v1/dm/conversations/{conversation_id}/participants/{reader['user']['id']}",
            headers=auth_headers(owner["token"]),
        )
        assert removed.status_code == 200, removed.text
    if membership.startswith("rejoined"):
        joined = client.post(
            f"/api/v1/dm/conversations/{conversation_id}/participants",
            headers=auth_headers(owner["token"]),
            json={"user_ids": [reader["user"]["id"]]},
        )
        assert joined.status_code == 200, joined.text
    if membership == "rejoined_reply":
        reply = client.post(
            f"/api/v1/dm/conversations/{conversation_id}/messages",
            headers=auth_headers(owner["token"]),
            json={"body": "new visible reply", "reply_to_message_id": old_message_id},
        )
        assert reply.status_code == 200, reply.text
        event = next(
            event
            for user_id, event in reversed(captured)
            if user_id == reader["user"]["id"] and event["type"] == "dm.message.created"
        )
        # Even a stale/overbroad producer projection cannot disclose hidden reply context.
        event["data"]["message"]["reply_to"] = {"body_preview": "old private history"}
    if membership == "active":
        with get_session_factory()() as db:
            db.get(DmMessage, old_message_id).body = "current canonical content"
            db.commit()
    sent = _deliver_queued(event, outside if membership == "never_joined" else reader)
    assert len(sent) == 1
    projected = sent[0]
    if membership in {"removed", "never_joined"}:
        assert projected == {
            "type": "dm.conversation.removed",
            "data": {"conversation_id": conversation_id},
        }
    elif membership == "rejoined_old":
        assert projected["type"] == "dm.conversation.updated"
        assert "message" not in projected["data"]
        assert projected["data"]["conversation"]["last_message"] is None
        assert "old private history" not in str(projected)
    elif membership == "rejoined_reply":
        assert projected["data"]["message"]["body"] == "new visible reply"
        assert projected["data"]["message"]["reply_to"] is None
        assert "old private history" not in str(projected)
    else:
        assert projected["data"]["message"]["body"] == "current canonical content"
        assert "old private history" not in str(projected)


@pytest.mark.parametrize(
    "change",
    ["current", "source_revoked", "app_disabled", "other_recipient", "source_deleted", "read"],
)
def test_queued_notification_rechecks_recipient_source_and_current_unread_count(client, change):
    recipient = dev_login(client, "delivery-hub-member")
    commenter = dev_login(client, "administrator")
    notification_id = _create_notification(
        client,
        author_token=recipient["token"],
        commenter_token=commenter["token"],
        title="Source private notification",
    )
    with get_session_factory()() as db:
        notification = db.get(Notification, notification_id)
        event = {
            "type": "notification.created",
            "data": {
                "notification": {
                    "id": notification_id,
                    "title": "stale private notification",
                    "body": "stale body",
                },
                "unread_count": 999,
            },
        }
        if change == "source_revoked":
            post = db.get(CommunityPost, notification.source_id)
            post.channel.admin_only_content = True
        elif change == "app_disabled":
            db.get(CompanyAppControl, "community").enabled = False
        elif change == "other_recipient":
            notification.user_id = commenter["user"]["id"]
        elif change == "source_deleted":
            db.delete(db.get(CommunityPost, notification.source_id))
        elif change == "read":
            notification.is_read = True
        db.commit()
    sent = _deliver_queued(event, recipient)
    assert len(sent) == 1
    data = sent[0]["data"]
    if change in {"current", "read"}:
        assert data["notification"]["id"] == notification_id
        assert data["notification"]["is_read"] is (change == "read")
        assert data["unread_count"] == (0 if change == "read" else 1)
    else:
        assert data == {"notification": None, "unread_count": 0}
    assert "stale private notification" not in str(sent)
    assert "stale body" not in str(sent)
