from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from open_work_hub_api.domains.dm import message_delivery, message_flow


NOW = datetime(2026, 5, 21, 12, 0, 0)


class _FakeDb:
    def __init__(self) -> None:
        self.added = []
        self.added_batches = []
        self.refreshed = []
        self.commit_count = 0

    def add(self, row) -> None:  # noqa: ANN001
        self.added.append(row)

    def add_all(self, rows) -> None:  # noqa: ANN001
        self.added_batches.append(list(rows))

    def commit(self) -> None:
        self.commit_count += 1

    def refresh(self, row) -> None:  # noqa: ANN001
        self.refreshed.append(row)


def test_send_message_persists_delivery_without_global_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = _user("sender")
    recipient = _user("recipient")
    conversation_row = SimpleNamespace(id="conversation-1")
    message = SimpleNamespace(id="message-1", attachments=[])
    sender_participant = SimpleNamespace(id="participant-1")
    attachment_rows = [SimpleNamespace(id="attachment-1")]
    db = _FakeDb()

    monkeypatch.setattr(message_delivery, "utcnow_naive", lambda: NOW)
    monkeypatch.setattr(
        message_delivery.conversation_queries,
        "require_user_conversation",
        lambda db, *, current_user, conversation_id: conversation_row,
    )

    def compose_dm_message(db, *, conversation, sender, body, attachment_ids, now):  # noqa: ANN001
        assert conversation is conversation_row
        assert sender.id == "sender"
        assert body == "  Hello  "
        assert attachment_ids == ["attachment-1"]
        assert now == NOW
        return message_flow.DmMessageDraft(
            conversation=conversation,
            sender_participant=sender_participant,
            message=message,
            attachments=attachment_rows,
            recipients=[recipient],
            body="Hello",
        )

    monkeypatch.setattr(message_delivery.message_flow, "compose_dm_message", compose_dm_message)

    result = message_delivery.send_message(
        db,
        sender=sender,
        conversation_id="conversation-1",
        body="  Hello  ",
        attachment_ids=["attachment-1"],
    )

    assert result.message is message
    assert result.recipients == [recipient]
    assert db.added == [message, conversation_row, sender_participant]
    assert db.added_batches == [[attachment_rows[0]]]
    assert db.commit_count == 1
    assert db.refreshed == [message]
    assert message.attachments == attachment_rows


def _user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, email=f"{user_id}@example.test")
