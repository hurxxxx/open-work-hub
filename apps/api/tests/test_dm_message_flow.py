from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.dm import message_flow


NOW = datetime(2026, 5, 21, 12, 0, 0)


class _FakeDb:
    def __init__(
        self,
        attachments: list[SimpleNamespace],
        *,
        scalar_row: SimpleNamespace | None = None,
    ) -> None:
        self.attachments = attachments
        self.scalar_row = scalar_row

    def scalars(self, query):  # noqa: ANN001
        return self.attachments

    def scalar(self, query):  # noqa: ANN001
        return self.scalar_row


def test_compose_dm_message_creates_message_and_prepares_mutations() -> None:
    sender = _user("sender")
    recipient = _user("recipient")
    sender_participant = _participant(sender)
    conversation = _conversation(
        participants=[sender_participant, _participant(recipient)],
        message_seq=4,
    )
    attachment_one = _attachment("attachment-1")
    attachment_two = _attachment("attachment-2")

    draft = message_flow.compose_dm_message(
        _FakeDb([attachment_two, attachment_one]),
        conversation=conversation,
        sender=sender,
        body="  Hello  ",
        attachment_ids=["attachment-1", "attachment-2", "attachment-1"],
        now=NOW,
    )

    assert draft.conversation is conversation
    assert draft.sender_participant is sender_participant
    assert draft.recipients == [recipient]
    assert draft.body == "Hello"
    assert draft.message.conversation_id == "conversation-1"
    assert draft.message.sender_id == "sender"
    assert draft.message.sequence == 5
    assert draft.message.body == "Hello"
    assert draft.message.created_at == NOW
    assert conversation.message_seq == 5
    assert conversation.updated_at == NOW
    assert sender_participant.last_read_message_id == draft.message.id
    assert [attachment.id for attachment in draft.attachments] == [
        "attachment-1",
        "attachment-2",
    ]
    assert [attachment.message_id for attachment in draft.attachments] == [
        draft.message.id,
        draft.message.id,
    ]


def test_compose_dm_message_requires_body_or_attachments() -> None:
    sender = _user("sender")
    recipient = _user("recipient")

    with pytest.raises(HTTPException) as excinfo:
        message_flow.compose_dm_message(
            _FakeDb([]),
            conversation=_conversation(participants=[_participant(sender), _participant(recipient)]),
            sender=sender,
            body="  ",
            attachment_ids=[],
            now=NOW,
        )

    assert excinfo.value.status_code == 422


def test_compose_dm_message_allows_attachment_only_message() -> None:
    sender = _user("sender")
    recipient = _user("recipient")
    conversation = _conversation(participants=[_participant(sender), _participant(recipient)])
    attachment = _attachment("attachment-1")

    draft = message_flow.compose_dm_message(
        _FakeDb([attachment]),
        conversation=conversation,
        sender=sender,
        body="  ",
        attachment_ids=["attachment-1"],
        now=NOW,
    )

    assert draft.body == ""
    assert draft.message.body == ""
    assert draft.attachments == [attachment]
    assert attachment.message_id == draft.message.id


def test_compose_dm_message_links_reply_target_in_same_conversation() -> None:
    sender = _user("sender")
    recipient = _user("recipient")
    conversation = _conversation(participants=[_participant(sender), _participant(recipient)])
    reply_to = SimpleNamespace(
        id="reply-1",
        conversation_id="conversation-1",
        created_at=NOW,
    )

    draft = message_flow.compose_dm_message(
        _FakeDb([], scalar_row=reply_to),
        conversation=conversation,
        sender=sender,
        body="Reply",
        attachment_ids=[],
        now=NOW,
        reply_to_message_id="reply-1",
    )

    assert draft.message.reply_to_message_id == "reply-1"
    assert draft.message.reply_to is reply_to


def test_compose_dm_message_rejects_reply_target_outside_conversation() -> None:
    sender = _user("sender")
    recipient = _user("recipient")
    conversation = _conversation(participants=[_participant(sender), _participant(recipient)])
    reply_to = SimpleNamespace(
        id="reply-1",
        conversation_id="other-conversation",
        created_at=NOW,
    )

    with pytest.raises(HTTPException) as excinfo:
        message_flow.compose_dm_message(
            _FakeDb([], scalar_row=reply_to),
            conversation=conversation,
            sender=sender,
            body="Reply",
            attachment_ids=[],
            now=NOW,
            reply_to_message_id="reply-1",
        )

    assert excinfo.value.status_code == 404


def test_compose_dm_message_requires_active_sender() -> None:
    sender = _user("sender")
    recipient = _user("recipient")

    with pytest.raises(HTTPException) as excinfo:
        message_flow.compose_dm_message(
            _FakeDb([]),
            conversation=_conversation(
                participants=[
                    _participant(sender, left_at=NOW),
                    _participant(recipient),
                ],
            ),
            sender=sender,
            body="Hello",
            attachment_ids=[],
            now=NOW,
        )

    assert excinfo.value.status_code == 404


def test_compose_dm_message_requires_an_active_recipient() -> None:
    sender = _user("sender")

    with pytest.raises(HTTPException) as excinfo:
        message_flow.compose_dm_message(
            _FakeDb([]),
            conversation=_conversation(participants=[_participant(sender)]),
            sender=sender,
            body="Hello",
            attachment_ids=[],
            now=NOW,
        )

    assert excinfo.value.status_code == 404


def test_message_attachments_to_link_rejects_missing_or_foreign_attachment() -> None:
    sender = _user("sender")
    conversation = _conversation(participants=[_participant(sender), _participant(_user("recipient"))])

    with pytest.raises(HTTPException) as missing_exc:
        message_flow.message_attachments_to_link(
            _FakeDb([]),
            sender=sender,
            conversation=conversation,
            attachment_ids=["missing"],
        )
    assert missing_exc.value.status_code == 404

    with pytest.raises(HTTPException) as foreign_exc:
        message_flow.message_attachments_to_link(
            _FakeDb([_attachment("attachment-1", uploader_id="other")]),
            sender=sender,
            conversation=conversation,
            attachment_ids=["attachment-1"],
        )
    assert foreign_exc.value.status_code == 404


def test_message_attachments_to_link_rejects_already_sent_attachment() -> None:
    sender = _user("sender")
    conversation = _conversation(participants=[_participant(sender), _participant(_user("recipient"))])

    with pytest.raises(HTTPException) as excinfo:
        message_flow.message_attachments_to_link(
            _FakeDb([_attachment("attachment-1", message_id="message-1")]),
            sender=sender,
            conversation=conversation,
            attachment_ids=["attachment-1"],
        )

    assert excinfo.value.status_code == 422


def _conversation(
    *,
    participants: list[SimpleNamespace],
    message_seq: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        id="conversation-1",
        participants=participants,
        message_seq=message_seq,
        updated_at=None,
    )


def _participant(user: SimpleNamespace, *, left_at=None) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user.id,
        user=user,
        joined_at=NOW,
        left_at=left_at,
        last_read_message_id=None,
    )


def _user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, email=f"{user_id}@example.test", status="active")


def _attachment(
    attachment_id: str,
    *,
    conversation_id: str = "conversation-1",
    uploader_id: str = "sender",
    message_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=attachment_id,
        conversation_id=conversation_id,
        uploader_id=uploader_id,
        message_id=message_id,
        filename=f"{attachment_id}.txt",
    )
