from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from ai_do_api.domains.dm import read_state
from ai_do_api.domains.dm.models import DmMessage


NOW = datetime(2026, 5, 21, 12, 0, 0)


class _FakeDb:
    def __init__(
        self,
        *,
        scalar_result=None,
        scalars_result: list[SimpleNamespace] | None = None,
        get_result=None,
    ) -> None:
        self.scalar_result = scalar_result
        self.scalars_result = scalars_result or []
        self.get_result = get_result
        self.get_calls: list[tuple[object, str]] = []

    def scalar(self, query):  # noqa: ANN001
        return self.scalar_result

    def scalars(self, query):  # noqa: ANN001
        return self.scalars_result

    def get(self, model, key: str):  # noqa: ANN001
        self.get_calls.append((model, key))
        return self.get_result


def test_mark_conversation_read_updates_participant_and_notifications() -> None:
    participant = _participant("user-1")
    conversation = _conversation(participants=[participant])
    latest_message = SimpleNamespace(id="message-1")
    notifications = [_notification("notification-1"), _notification("notification-2")]

    receipt = read_state.mark_conversation_read(
        _FakeDb(scalar_result=latest_message, scalars_result=notifications),
        conversation=conversation,
        user_id="user-1",
    )

    assert receipt.participant is participant
    assert receipt.latest_message is latest_message
    assert receipt.notifications == notifications
    assert participant.last_read_message_id == "message-1"
    assert [notification.is_read for notification in notifications] == [True, True]


def test_mark_conversation_read_clears_marker_when_no_visible_message() -> None:
    participant = _participant("user-1", last_read_message_id="message-previous")

    receipt = read_state.mark_conversation_read(
        _FakeDb(scalar_result=None),
        conversation=_conversation(participants=[participant]),
        user_id="user-1",
    )

    assert receipt.latest_message is None
    assert participant.last_read_message_id is None


def test_mark_conversation_read_requires_active_participant() -> None:
    with pytest.raises(HTTPException) as excinfo:
        read_state.mark_conversation_read(
            _FakeDb(),
            conversation=_conversation(participants=[]),
            user_id="user-1",
        )

    assert excinfo.value.status_code == 404


def test_unread_count_returns_zero_without_active_participant() -> None:
    assert (
        read_state.unread_count(
            _FakeDb(scalar_result=5),
            conversation=_conversation(participants=[]),
            user_id="user-1",
        )
        == 0
    )


def test_unread_count_uses_last_read_marker_when_present() -> None:
    participant = _participant("user-1", last_read_message_id="message-1")
    last_read = SimpleNamespace(sequence=7)
    db = _FakeDb(scalar_result=3, get_result=last_read)

    result = read_state.unread_count(
        db,
        conversation=_conversation(participants=[participant]),
        user_id="user-1",
    )

    assert result == 3
    assert db.get_calls == [(DmMessage, "message-1")]


def _conversation(*, participants: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(id="conversation-1", participants=participants)


def _participant(
    user_id: str,
    *,
    left_at=None,
    last_read_message_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        left_at=left_at,
        joined_at=NOW,
        last_read_message_id=last_read_message_id,
    )


def _notification(notification_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=notification_id, is_read=False)
