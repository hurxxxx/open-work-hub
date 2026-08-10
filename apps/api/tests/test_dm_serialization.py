from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from ai_do_api.domains.dm import serialization


NOW = datetime(2026, 5, 21, 12, 0, 0)


def test_serialize_message_uses_sender_email_when_names_are_missing() -> None:
    item = serialization.serialize_message(
        SimpleNamespace(
            id="message-1",
            conversation_id="conversation-1",
            sequence=3,
            sender_id="sender",
            sender=_user("sender", full_name="", email="sender@example.test"),
            body="Hello",
            attachments=[],
            created_at=NOW,
        )
    )

    assert item.sender_name == "sender@example.test"
    assert item.thread_id == "conversation-1"
    assert item.read_state.unread_count == 0
    assert item.read_state.read_by_all is True
    assert item.reply_to is None


def test_serialize_message_falls_back_to_sender_id_when_sender_row_is_missing() -> None:
    item = serialization.serialize_message(
        SimpleNamespace(
            id="message-1",
            conversation_id="conversation-1",
            sequence=3,
            sender_id="sender",
            sender=None,
            body="Hello",
            attachments=[],
            created_at=NOW,
        )
    )

    assert item.sender_name == "sender"


def test_serialize_message_includes_reply_summary() -> None:
    reply_to = SimpleNamespace(
        id="reply-1",
        sender_id="sender",
        sender=_user("sender", full_name="Sender User"),
        body="Original message",
        attachments=[SimpleNamespace(id="attachment-1")],
        created_at=NOW,
    )

    item = serialization.serialize_message(
        SimpleNamespace(
            id="message-1",
            conversation_id="conversation-1",
            sequence=3,
            sender_id="current",
            sender=_user("current"),
            reply_to=reply_to,
            body="Reply",
            attachments=[],
            created_at=NOW,
        )
    )

    assert item.reply_to is not None
    assert item.reply_to.id == "reply-1"
    assert item.reply_to.sender_name == "Sender User"
    assert item.reply_to.body_preview == "Original message"
    assert item.reply_to.attachment_count == 1


def test_serialize_message_hides_reply_summary_before_viewer_join() -> None:
    viewer = _user("viewer")
    viewer_participant = _participant(
        viewer,
        joined_at=datetime(2026, 5, 21, 12, 5, 0),
    )
    reply_to = SimpleNamespace(
        id="reply-1",
        sender_id="sender",
        sender=_user("sender", full_name="Sender User"),
        body="Original before join",
        attachments=[],
        created_at=NOW,
    )

    item = serialization.serialize_message(
        SimpleNamespace(
            id="message-1",
            conversation_id="conversation-1",
            sequence=3,
            sender_id="current",
            sender=_user("current"),
            reply_to=reply_to,
            body="Reply",
            attachments=[],
            created_at=datetime(2026, 5, 21, 12, 10, 0),
        ),
        viewer_participant=viewer_participant,
    )

    assert item.reply_to is None


def test_serialize_attachment_adds_preview_url_for_images(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        serialization.attachment_links,
        "build_dm_attachment_content_url",
        lambda attachment, *, disposition: f"/content/{attachment.id}/{disposition}",
    )

    item = serialization.serialize_attachment(
        SimpleNamespace(
            id="attachment-1",
            conversation_id="conversation-1",
            message_id="message-1",
            filename="image.png",
            content_type="image/png",
            size_bytes=123,
            created_at=NOW,
        )
    )

    assert item.is_image is True
    assert item.download_url == "/content/attachment-1/attachment"
    assert item.preview_url == "/content/attachment-1/inline"


def test_serialize_conversation_builds_direct_conversation_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = _user("current", full_name="Current User")
    other_user = _user("other", full_name="Other User")
    current_participant = _participant(current_user, last_read_message_id="message-1")
    other_participant = _participant(other_user)
    latest_message = SimpleNamespace(
        id="message-2",
        conversation_id="conversation-1",
        sequence=2,
        sender_id="other",
        sender=other_user,
        body="Latest",
        attachments=[],
        created_at=NOW,
    )
    monkeypatch.setattr(
        serialization.read_state,
        "latest_visible_message",
        lambda db, conversation_id, participant: latest_message,
    )
    monkeypatch.setattr(
        serialization.read_state,
        "unread_count",
        lambda db, *, conversation, user_id: 2,
    )

    item = serialization.serialize_conversation(
        SimpleNamespace(),
        SimpleNamespace(
            id="conversation-1",
            conversation_type="direct",
            title=None,
            participants=[current_participant, other_participant],
            created_by_id="current",
            created_at=NOW,
            updated_at=NOW,
        ),
        current_user=current_user,
    )

    assert item.display_name == "Other User"
    assert item.other_user is not None
    assert item.other_user.id == "other"
    assert item.participant_count == 2
    assert item.last_message is not None
    assert item.last_message.id == "message-2"
    assert item.unread_count == 2
    assert item.last_read_message_id == "message-1"


def test_serialize_participant_requires_user() -> None:
    with pytest.raises(HTTPException) as excinfo:
        serialization.serialize_participant(
            SimpleNamespace(
                user=None,
                role="member",
                joined_at=NOW,
                left_at=None,
                muted_at=None,
                last_read_message_id=None,
            )
        )

    assert excinfo.value.status_code == 404


def _participant(
    user: SimpleNamespace,
    *,
    last_read_message_id: str | None = None,
    joined_at: datetime = NOW,
    left_at=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user.id,
        user=user,
        role="member",
        joined_at=joined_at,
        left_at=left_at,
        muted_at=None,
        last_read_message_id=last_read_message_id,
    )


def _user(
    user_id: str,
    *,
    full_name: str = "User Name",
    display_name: str | None = None,
    email: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        email=email or f"{user_id}@example.test",
        full_name=full_name,
        display_name=display_name,
        job_title=None,
    )
