from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.dm import participants


def test_active_participant_helpers_ignore_left_participants() -> None:
    current = _participant("current", _user("current"))
    active = _participant("active", _user("active"))
    inactive = _participant("inactive", _user("inactive"), left_at=object())
    conversation = _conversation(participants=[current, active, inactive])

    assert participants.active_participants(conversation) == [current, active]
    assert participants.active_participant(conversation, "active") is active
    assert participants.active_participant(conversation, "inactive") is None
    assert participants.other_active_participant(conversation, "current") is active
    assert participants.active_participant_users(conversation) == [current.user, active.user]


def test_ensure_group_conversation_rejects_direct_conversations() -> None:
    with pytest.raises(HTTPException) as excinfo:
        participants.ensure_group_conversation(_conversation(conversation_type="direct"))

    assert excinfo.value.status_code == 422


def test_ensure_conversation_manager_requires_owner_or_admin() -> None:
    conversation = _conversation(
        participants=[
            _participant("owner", _user("owner"), role="owner"),
            _participant("admin", _user("admin"), role="admin"),
            _participant("member", _user("member"), role="member"),
        ]
    )

    participants.ensure_conversation_manager(conversation, "owner")
    participants.ensure_conversation_manager(conversation, "admin")
    with pytest.raises(HTTPException) as excinfo:
        participants.ensure_conversation_manager(conversation, "member")

    assert excinfo.value.status_code == 403


def test_ensure_group_conversation_manager_applies_group_and_role_rules() -> None:
    conversation = _conversation(
        participants=[
            _participant("owner", _user("owner"), role="owner"),
            _participant("member", _user("member"), role="member"),
        ]
    )

    participants.ensure_group_conversation_manager(conversation, "owner")

    with pytest.raises(HTTPException) as member_excinfo:
        participants.ensure_group_conversation_manager(conversation, "member")
    with pytest.raises(HTTPException) as direct_excinfo:
        participants.ensure_group_conversation_manager(
            _conversation(conversation_type="direct", participants=conversation.participants),
            "owner",
        )

    assert member_excinfo.value.status_code == 403
    assert direct_excinfo.value.status_code == 422


def test_promote_owner_if_needed_selects_oldest_active_participant() -> None:
    now = datetime(2026, 5, 21, 12, 0, 0)
    owner = _participant("owner", _user("owner"), role="owner", joined_at=now)
    newest = _participant("newest", _user("newest"), joined_at=now + timedelta(minutes=2))
    oldest = _participant("oldest", _user("oldest"), joined_at=now + timedelta(minutes=1))
    inactive = _participant(
        "inactive",
        _user("inactive"),
        joined_at=now - timedelta(minutes=1),
        left_at=object(),
    )
    conversation = _conversation(participants=[owner, newest, oldest, inactive])

    owner.left_at = object()
    participants.promote_owner_if_needed(conversation, departing_user_id="owner")

    assert oldest.role == "owner"
    assert newest.role == "member"
    assert inactive.role == "member"


def _conversation(
    *,
    conversation_type: str = "group",
    participants: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        conversation_type=conversation_type,
        participants=participants or [],
    )


def _participant(
    user_id: str,
    user: SimpleNamespace,
    *,
    role: str = "member",
    joined_at: datetime | None = None,
    left_at=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        user=user,
        role=role,
        joined_at=joined_at or datetime(2026, 5, 21, 12, 0, 0),
        left_at=left_at,
    )


def _user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id)
