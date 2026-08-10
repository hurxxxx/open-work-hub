from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.dm import conversation_membership


NOW = datetime(2026, 5, 21, 12, 0, 0)


class _FakeDb:
    def __init__(self, *, scalar_results=None, scalars_result=None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.scalars_result = scalars_result or []
        self.added = []
        self.added_all = []
        self.commit_count = 0
        self.rollback_count = 0

    def scalar(self, query):  # noqa: ANN001
        return self.scalar_results.pop(0) if self.scalar_results else None

    def scalars(self, query):  # noqa: ANN001
        return self.scalars_result

    def add(self, row) -> None:  # noqa: ANN001
        self.added.append(row)

    def add_all(self, rows) -> None:  # noqa: ANN001
        self.added_all.extend(list(rows))

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1


def test_get_or_create_direct_conversation_restores_missing_direct_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user = _user("current")
    recipient = _user("recipient")
    active_current = _participant(current_user)
    left_recipient = _participant(recipient, left_at=NOW - timedelta(days=1))
    conversation = _conversation(
        conversation_type="direct",
        participants=[active_current, left_recipient],
    )
    db = _FakeDb(scalar_results=[recipient, conversation])
    monkeypatch.setattr(conversation_membership, "utcnow_naive", lambda: NOW)
    monkeypatch.setattr(
        conversation_membership.conversation_queries,
        "latest_message",
        lambda db, conversation_id: SimpleNamespace(id="message-1"),
    )

    result = conversation_membership.get_or_create_direct_conversation(
        db,
        current_user=current_user,
        recipient_user_id="recipient",
    )

    assert result is conversation
    assert db.commit_count == 1
    assert len(db.added_all) == 1
    restored = db.added_all[0]
    assert restored.conversation_id == "conversation-1"
    assert restored.user_id == "recipient"
    assert restored.last_read_message_id == "message-1"


def test_create_group_conversation_adds_conversation_and_participants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(scalars_result=[_user("first"), _user("second")])
    monkeypatch.setattr(conversation_membership, "utcnow_naive", lambda: NOW)

    conversation = conversation_membership.create_group_conversation(
        db,
        current_user=_user("owner"),
        participant_user_ids=["first", "second", "first"],
        title=" Launch ",
    )

    assert conversation.conversation_type == "group"
    assert conversation.title == "Launch"
    assert db.added == [conversation]
    assert [(row.user_id, row.role) for row in db.added_all] == [
        ("owner", "owner"),
        ("first", "member"),
        ("second", "member"),
    ]
    assert db.commit_count == 1


def test_create_group_conversation_rejects_missing_active_recipient() -> None:
    with pytest.raises(HTTPException) as excinfo:
        conversation_membership.create_group_conversation(
            _FakeDb(scalars_result=[_user("first")]),
            current_user=_user("owner"),
            participant_user_ids=["first", "second"],
            title=None,
        )

    assert excinfo.value.status_code == 404


def test_add_participants_skips_existing_members_and_carries_latest_read_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _user("owner")
    existing = _user("existing")
    conversation = _conversation(
        participants=[
            _participant(owner, role="owner"),
            _participant(existing),
        ]
    )
    db = _FakeDb(scalars_result=[_user("new")])
    _patch_required_conversation(monkeypatch, conversation)
    monkeypatch.setattr(conversation_membership, "utcnow_naive", lambda: NOW)
    monkeypatch.setattr(
        conversation_membership.conversation_queries,
        "latest_message",
        lambda db, conversation_id: SimpleNamespace(id="message-1"),
    )

    result = conversation_membership.add_participants(
        db,
        current_user=owner,
        conversation_id="conversation-1",
        user_ids=["existing", "new", "new"],
    )

    assert result is conversation
    assert len(db.added_all) == 1
    added = db.added_all[0]
    assert added.user_id == "new"
    assert added.last_read_message_id == "message-1"
    assert conversation.updated_at == NOW
    assert db.commit_count == 1


def test_remove_participant_marks_target_left_and_promotes_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_admin = _participant(_user("admin"), role="admin", joined_at=NOW)
    target_owner = _participant(_user("owner"), role="owner", joined_at=NOW + timedelta(minutes=1))
    conversation = _conversation(participants=[current_admin, target_owner])
    db = _FakeDb()
    _patch_required_conversation(monkeypatch, conversation)
    monkeypatch.setattr(conversation_membership, "utcnow_naive", lambda: NOW + timedelta(hours=1))

    result = conversation_membership.remove_participant(
        db,
        current_user=current_admin.user,
        conversation_id="conversation-1",
        user_id="owner",
    )

    assert result is conversation
    assert target_owner.left_at == NOW + timedelta(hours=1)
    assert current_admin.role == "owner"
    assert db.added == [target_owner, conversation]
    assert db.commit_count == 1


def test_leave_conversation_marks_current_user_left_and_promotes_next_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _participant(_user("owner"), role="owner", joined_at=NOW)
    oldest = _participant(_user("oldest"), joined_at=NOW + timedelta(minutes=1))
    newest = _participant(_user("newest"), joined_at=NOW + timedelta(minutes=2))
    conversation = _conversation(participants=[owner, oldest, newest])
    db = _FakeDb()
    _patch_required_conversation(monkeypatch, conversation)
    monkeypatch.setattr(conversation_membership, "utcnow_naive", lambda: NOW + timedelta(hours=1))

    conversation_membership.leave_conversation(
        db,
        current_user=owner.user,
        conversation_id="conversation-1",
    )

    assert owner.left_at == NOW + timedelta(hours=1)
    assert oldest.role == "owner"
    assert newest.role == "member"
    assert db.added == [owner, conversation]
    assert db.commit_count == 1


def _patch_required_conversation(
    monkeypatch: pytest.MonkeyPatch,
    conversation: SimpleNamespace,
) -> None:
    monkeypatch.setattr(
        conversation_membership.conversation_queries,
        "require_user_conversation",
        lambda db, *, current_user, conversation_id: conversation,
    )


def _conversation(
    *,
    conversation_type: str = "group",
    participants: list[SimpleNamespace],
) -> SimpleNamespace:
    return SimpleNamespace(
        id="conversation-1",
        conversation_type=conversation_type,
        title=None,
        participants=participants,
        updated_at=None,
    )


def _participant(
    user: SimpleNamespace,
    *,
    role: str = "member",
    joined_at: datetime = NOW,
    left_at=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        conversation_id="conversation-1",
        user_id=user.id,
        user=user,
        role=role,
        joined_at=joined_at,
        left_at=left_at,
        last_read_message_id=None,
    )


def _user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, status="active", email=f"{user_id}@example.test")
