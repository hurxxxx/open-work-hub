from __future__ import annotations

from types import SimpleNamespace

from open_work_hub_api.domains.dm import conversation_display


def test_direct_conversation_display_name_uses_other_active_user() -> None:
    sender = _user("sender", full_name="Sender Name")
    recipient = _user("recipient", full_name="Recipient Name")
    conversation = _conversation(
        conversation_type="direct",
        participants=[_participant(sender), _participant(recipient)],
    )

    assert (
        conversation_display.dm_conversation_display_name(conversation, "recipient")
        == "Sender Name"
    )


def test_group_conversation_display_name_prefers_title() -> None:
    conversation = _conversation(
        conversation_type="group",
        title="Launch Room",
        participants=[_participant(_user("sender")), _participant(_user("recipient"))],
    )

    assert (
        conversation_display.dm_conversation_display_name(conversation, "recipient")
        == "Launch Room"
    )


def test_group_conversation_display_name_falls_back_to_active_participant_names() -> None:
    current = _user("current", full_name="Current User")
    first = _user("first", display_name="First")
    second = _user("second", full_name="Second User")
    third = _user("third", email="third@example.test")
    inactive = _user("inactive", display_name="Inactive")
    conversation = _conversation(
        conversation_type="group",
        participants=[
            _participant(current),
            _participant(first),
            _participant(second),
            _participant(third),
            _participant(inactive, left_at=object()),
        ],
    )

    assert (
        conversation_display.dm_conversation_display_name(conversation, "current")
        == "First, Second User, third@example.test"
    )


def test_dm_user_name_prefers_display_name_then_full_name_then_email() -> None:
    assert (
        conversation_display.dm_user_name(
            _user("display", display_name="Display Name", full_name="Full Name"),
        )
        == "Display Name"
    )
    assert (
        conversation_display.dm_user_name(
            _user("full", full_name="Full Name"),
        )
        == "Full Name"
    )
    assert (
        conversation_display.dm_user_name(
            _user("email", full_name="", email="email@example.test"),
        )
        == "email@example.test"
    )


def _conversation(
    *,
    conversation_type: str,
    participants: list[SimpleNamespace],
    title: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        conversation_type=conversation_type,
        title=title,
        participants=participants,
    )


def _participant(user: SimpleNamespace, *, left_at=None) -> SimpleNamespace:
    return SimpleNamespace(user_id=user.id, user=user, left_at=left_at)


def _user(
    user_id: str,
    *,
    display_name: str | None = None,
    full_name: str | None = None,
    email: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        display_name=display_name,
        full_name=full_name,
        email=email or f"{user_id}@example.test",
    )
