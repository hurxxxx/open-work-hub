from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from open_work_hub_api.domains.dm import realtime_events


def test_publish_conversation_snapshot_sends_viewer_specific_payloads(monkeypatch) -> None:
    conversation = SimpleNamespace(id="conversation-1")
    message = SimpleNamespace(id="message-1", body="hello")
    first_user = SimpleNamespace(id="user-1")
    second_user = SimpleNamespace(id="user-2")
    first_participant = SimpleNamespace(user_id="user-1")
    second_participant = SimpleNamespace(user_id="user-2")
    db = _FakeDb({"user-1": first_user, "user-2": second_user})
    realtime = _FakeRealtime()

    monkeypatch.setattr(
        realtime_events.participants,
        "active_participant_users",
        lambda value: [first_user, second_user],
    )
    monkeypatch.setattr(
        realtime_events.participants,
        "active_participant",
        lambda value, user_id: {
            "user-1": first_participant,
            "user-2": second_participant,
        }.get(user_id),
    )
    monkeypatch.setattr(
        realtime_events.serialization,
        "serialize_conversation",
        lambda db, conversation, *, current_user: _Dumpable(
            {"id": conversation.id, "viewer_id": current_user.id}
        ),
    )
    monkeypatch.setattr(
        realtime_events.serialization,
        "serialize_message",
        lambda message, *, conversation, viewer_participant: _Dumpable(
            {
                "id": message.id,
                "body": message.body,
                "viewer_id": viewer_participant.user_id,
            }
        ),
    )

    publisher = realtime_events.DmEventPublisher(db=db, realtime=realtime)
    publisher.publish_conversation_snapshot(
        conversation,
        "dm.message.created",
        message=message,
    )

    assert realtime.published == [
        (
            "user-1",
            {
                "type": "dm.message.created",
                "data": {
                    "conversation": {"id": "conversation-1", "viewer_id": "user-1"},
                    "thread": {"id": "conversation-1", "viewer_id": "user-1"},
                    "conversation_id": "conversation-1",
                    "thread_id": "conversation-1",
                    "message": {"id": "message-1", "body": "hello", "viewer_id": "user-1"},
                },
            },
        ),
        (
            "user-2",
            {
                "type": "dm.message.created",
                "data": {
                    "conversation": {"id": "conversation-1", "viewer_id": "user-2"},
                    "thread": {"id": "conversation-1", "viewer_id": "user-2"},
                    "conversation_id": "conversation-1",
                    "thread_id": "conversation-1",
                    "message": {"id": "message-1", "body": "hello", "viewer_id": "user-2"},
                },
            },
        ),
    ]


def test_publish_conversation_for_user_skips_missing_user(monkeypatch) -> None:
    serialize_calls = 0

    def serialize_conversation(*args, **kwargs):
        nonlocal serialize_calls
        serialize_calls += 1
        return _Dumpable({"id": "conversation-1"})

    monkeypatch.setattr(realtime_events.serialization, "serialize_conversation", serialize_conversation)
    realtime = _FakeRealtime()

    publisher = realtime_events.DmEventPublisher(db=_FakeDb({}), realtime=realtime)
    publisher.publish_conversation_for_user(
        SimpleNamespace(id="conversation-1"),
        "missing-user",
        "dm.conversation.updated",
    )

    assert serialize_calls == 0
    assert realtime.published == []


def test_publish_read_removed_and_notification_events(monkeypatch) -> None:
    conversation = SimpleNamespace(id="conversation-1")
    first_user = SimpleNamespace(id="user-1")
    second_user = SimpleNamespace(id="user-2")
    realtime = _FakeRealtime()

    monkeypatch.setattr(
        realtime_events.participants,
        "active_participant_users",
        lambda value: [first_user, second_user],
    )
    monkeypatch.setattr(
        realtime_events.serialization,
        "serialize_conversation",
        lambda db, conversation, *, current_user: _Dumpable(
            {"id": conversation.id, "viewer_id": current_user.id}
        ),
    )

    publisher = realtime_events.DmEventPublisher(
        db=_FakeDb({"user-1": first_user, "user-2": second_user}),
        realtime=realtime,
    )

    publisher.publish_conversation_removed("user-1", conversation_id="conversation-1")
    publisher.publish_conversation_read(
        "user-1",
        conversation_id="conversation-1",
        conversation=conversation,
    )
    publisher.publish_notification(
        "user-1",
        notification={"id": "notification-1"},
        unread_count=3,
    )

    assert realtime.published == [
        (
            "user-1",
            {
                "type": "dm.conversation.removed",
                "data": {"conversation_id": "conversation-1"},
            },
        ),
        (
            "user-1",
            {
                "type": "dm.conversation.read",
                "data": {
                    "conversation_id": "conversation-1",
                    "thread_id": "conversation-1",
                    "user_id": "user-1",
                    "conversation": {
                        "id": "conversation-1",
                        "viewer_id": "user-1",
                    },
                    "thread": {
                        "id": "conversation-1",
                        "viewer_id": "user-1",
                    },
                },
            },
        ),
        (
            "user-2",
            {
                "type": "dm.conversation.read",
                "data": {
                    "conversation_id": "conversation-1",
                    "thread_id": "conversation-1",
                    "user_id": "user-1",
                    "conversation": {
                        "id": "conversation-1",
                        "viewer_id": "user-2",
                    },
                    "thread": {
                        "id": "conversation-1",
                        "viewer_id": "user-2",
                    },
                },
            },
        ),
        (
            "user-1",
            {
                "type": "notification.created",
                "data": {
                    "notification": {"id": "notification-1"},
                    "unread_count": 3,
                },
            },
        ),
    ]


class _Dumpable:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload


class _FakeDb:
    def __init__(self, users_by_id: dict[str, Any]) -> None:
        self._users_by_id = users_by_id

    def get(self, model, user_id: str):
        return self._users_by_id.get(user_id)


class _FakeRealtime:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    def publish_user(self, user_id: str, event: dict[str, Any]) -> None:
        self.published.append((user_id, event))
