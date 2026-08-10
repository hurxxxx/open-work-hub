from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_alm_api.domains.dm import conversation_lifecycle


NOW = datetime(2026, 5, 21, 12, 0, 0)


def test_direct_conversation_key_is_stable_across_user_order() -> None:
    assert conversation_lifecycle.direct_conversation_key("b", "a") == "a:b"
    assert conversation_lifecycle.direct_conversation_key("a", "b") == "a:b"


def test_unique_user_ids_trims_skips_invalid_and_preserves_first_seen_order() -> None:
    assert conversation_lifecycle.unique_user_ids(
        [" user-1 ", "", None, "user-2", "user-1", "user-3"]
    ) == ["user-1", "user-2", "user-3"]


def test_group_recipient_ids_excludes_current_user_and_requires_two_others() -> None:
    assert conversation_lifecycle.group_recipient_ids(
        current_user_id="current",
        participant_user_ids=["current", "first", "second", "first"],
    ) == ["first", "second"]

    with pytest.raises(HTTPException) as excinfo:
        conversation_lifecycle.group_recipient_ids(
            current_user_id="current",
            participant_user_ids=["current", "first"],
        )

    assert excinfo.value.status_code == 422


def test_rule_objects_select_recipients_and_assign_participant_roles() -> None:
    recipient_rules = conversation_lifecycle.DmRecipientRules()
    participant_rules = conversation_lifecycle.DmParticipantRules()

    recipient_ids = recipient_rules.group_recipient_ids(
        current_user_id="owner",
        participant_user_ids=["owner", "first", "second", "first"],
    )
    participants = participant_rules.group_participants(
        conversation_id="conversation-1",
        current_user_id="owner",
        recipient_user_ids=recipient_ids,
        joined_at=NOW,
    )

    assert recipient_ids == ["first", "second"]
    assert [(item.user_id, item.role, item.joined_at) for item in participants] == [
        ("owner", "owner", NOW),
        ("first", "member", NOW),
        ("second", "member", NOW),
    ]


def test_new_direct_conversation_draft_creates_conversation_and_member_participants() -> None:
    current_user = _user("current")
    recipient = _user("recipient")

    draft = conversation_lifecycle.new_direct_conversation(
        current_user=current_user,
        recipient=recipient,
        now=NOW,
    )

    assert draft.conversation.conversation_type == "direct"
    assert draft.conversation.direct_key == "current:recipient"
    assert draft.conversation.created_by_id == "current"
    assert [(item.user_id, item.role, item.joined_at) for item in draft.participants] == [
        ("current", "member", NOW),
        ("recipient", "member", NOW),
    ]


def test_new_group_conversation_draft_creates_owner_and_member_participants() -> None:
    draft = conversation_lifecycle.new_group_conversation(
        current_user=_user("owner"),
        recipient_user_ids=["first", "second"],
        title="  Launch Room  ",
        now=NOW,
    )

    assert draft.conversation.conversation_type == "group"
    assert draft.conversation.direct_key is None
    assert draft.conversation.title == "Launch Room"
    assert [(item.user_id, item.role) for item in draft.participants] == [
        ("owner", "owner"),
        ("first", "member"),
        ("second", "member"),
    ]


def test_restore_direct_participant_returns_new_participant_only_when_not_active() -> None:
    active = _participant("active")
    left = _participant("left", left_at=object())
    conversation = SimpleNamespace(id="conversation-1", participants=[active, left])

    assert (
        conversation_lifecycle.restore_direct_participant_if_needed(
            conversation,
            "active",
            joined_at=NOW,
            last_read_message_id="message-1",
        )
        is None
    )

    restored = conversation_lifecycle.restore_direct_participant_if_needed(
        conversation,
        "left",
        joined_at=NOW,
        last_read_message_id="message-1",
    )

    assert restored is not None
    assert restored.conversation_id == "conversation-1"
    assert restored.user_id == "left"
    assert restored.role == "member"
    assert restored.last_read_message_id == "message-1"


def test_new_member_participants_carry_latest_visible_message() -> None:
    rows = conversation_lifecycle.new_member_participants(
        conversation_id="conversation-1",
        user_ids=["first", "second"],
        joined_at=NOW,
        last_read_message_id="message-1",
    )

    assert [(row.user_id, row.last_read_message_id) for row in rows] == [
        ("first", "message-1"),
        ("second", "message-1"),
    ]


def _user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def _participant(user_id: str, *, left_at=None) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, left_at=left_at)
