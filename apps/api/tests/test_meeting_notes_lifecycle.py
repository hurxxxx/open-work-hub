from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from ai_do_api.domains.meeting.notes_lifecycle import (
    meeting_notes_doc_title,
    meeting_notes_page_title,
    resolve_notes_lifecycle_action,
    should_grant_notes_doc_edit,
)


def test_meeting_notes_titles() -> None:
    meeting = SimpleNamespace(
        title="Weekly Sync",
        start_at=datetime(2026, 5, 30, 9, 0),
    )

    assert meeting_notes_doc_title(meeting) == "회의 메모: Weekly Sync (2026-05-30)"
    assert meeting_notes_page_title() == "회의 메모"


@pytest.mark.parametrize(
    ("has_active_doc", "has_active_page", "expected"),
    [
        (False, False, "create_assets"),
        (False, True, "create_assets"),
        (True, False, "create_page"),
        (True, True, "reuse"),
    ],
)
def test_resolve_notes_lifecycle_action(
    has_active_doc: bool,
    has_active_page: bool,
    expected: str,
) -> None:
    assert (
        resolve_notes_lifecycle_action(
            has_active_doc=has_active_doc,
            has_active_page=has_active_page,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("attendee_user_id", "granted_by_user_id", "doc_owner_id", "expected"),
    [
        ("attendee", "organizer", "organizer", True),
        ("organizer", "organizer", "organizer", False),
        ("organizer", "system", "organizer", False),
    ],
)
def test_should_grant_notes_doc_edit(
    attendee_user_id: str,
    granted_by_user_id: str,
    doc_owner_id: str,
    expected: bool,
) -> None:
    assert (
        should_grant_notes_doc_edit(
            attendee_user_id=attendee_user_id,
            granted_by_user_id=granted_by_user_id,
            doc_owner_id=doc_owner_id,
        )
        is expected
    )
