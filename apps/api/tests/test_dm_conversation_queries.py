from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.dm import conversation_queries


NOW = datetime(2026, 5, 21, 12, 0, 0)


class _FakeDb:
    def __init__(self, *, scalar_result=None, scalars_result=None) -> None:
        self.scalar_result = scalar_result
        self.scalars_result = scalars_result or []

    def scalar(self, query):  # noqa: ANN001
        return self.scalar_result

    def scalars(self, query):  # noqa: ANN001
        return self.scalars_result


def test_require_user_conversation_returns_active_member_conversation() -> None:
    current_user = _user("current")
    conversation = _conversation(participants=[_participant("current")])

    result = conversation_queries.require_user_conversation(
        _FakeDb(scalar_result=conversation),
        current_user=current_user,
        conversation_id="conversation-1",
    )

    assert result is conversation


def test_require_user_conversation_hides_missing_or_inactive_conversation() -> None:
    current_user = _user("current")

    with pytest.raises(HTTPException) as missing_exc:
        conversation_queries.require_user_conversation(
            _FakeDb(scalar_result=None),
            current_user=current_user,
            conversation_id="conversation-1",
        )
    assert missing_exc.value.status_code == 404

    with pytest.raises(HTTPException) as inactive_exc:
        conversation_queries.require_user_conversation(
            _FakeDb(
                scalar_result=_conversation(participants=[_participant("current", left_at=NOW)])
            ),
            current_user=current_user,
            conversation_id="conversation-1",
        )
    assert inactive_exc.value.status_code == 404


def test_list_user_conversations_returns_hydrated_query_results() -> None:
    conversations = [
        _conversation(conversation_id="conversation-1", participants=[_participant("current")]),
        _conversation(conversation_id="conversation-2", participants=[_participant("current")]),
    ]

    assert (
        conversation_queries.list_user_conversations(
            _FakeDb(scalars_result=conversations),
            current_user=_user("current"),
        )
        == conversations
    )


def test_visible_messages_returns_oldest_first_after_desc_query() -> None:
    newest = SimpleNamespace(id="message-2")
    oldest = SimpleNamespace(id="message-1")

    result = conversation_queries.visible_messages(
        _FakeDb(scalars_result=[newest, oldest]),
        conversation_id="conversation-1",
        participant=_participant("current"),
        limit=20,
        before=NOW,
    )

    assert result == [oldest, newest]


def test_latest_message_returns_scalar_result() -> None:
    latest = SimpleNamespace(id="message-2")

    assert (
        conversation_queries.latest_message(_FakeDb(scalar_result=latest), "conversation-1")
        is latest
    )


def _conversation(
    *,
    participants: list[SimpleNamespace],
    conversation_id: str = "conversation-1",
) -> SimpleNamespace:
    return SimpleNamespace(id=conversation_id, participants=participants)


def _participant(user_id: str, *, left_at=None) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, joined_at=NOW, left_at=left_at)


def _user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id)
