from __future__ import annotations

from typing import Any

from open_work_hub_api.domains.dm import realtime_payloads


def test_conversation_snapshot_payload_keeps_thread_aliases_and_optional_message() -> None:
    payload = realtime_payloads.conversation_snapshot_payload(
        conversation_id="conversation-1",
        conversation=_Dumpable({"id": "conversation-1", "viewer_id": "user-1"}),
        message=_Dumpable({"id": "message-1"}),
    )

    assert payload == {
        "conversation": {"id": "conversation-1", "viewer_id": "user-1"},
        "thread": {"id": "conversation-1", "viewer_id": "user-1"},
        "conversation_id": "conversation-1",
        "thread_id": "conversation-1",
        "message": {"id": "message-1"},
    }


def test_conversation_lifecycle_payloads_keep_legacy_thread_fields() -> None:
    assert realtime_payloads.conversation_removed_payload(
        conversation_id="conversation-1",
    ) == {"conversation_id": "conversation-1"}

    assert realtime_payloads.conversation_read_payload(
        user_id="user-1",
        conversation_id="conversation-1",
        conversation=_Dumpable({"id": "conversation-1", "unread_count": 0}),
    ) == {
        "conversation_id": "conversation-1",
        "thread_id": "conversation-1",
        "user_id": "user-1",
        "conversation": {"id": "conversation-1", "unread_count": 0},
        "thread": {"id": "conversation-1", "unread_count": 0},
    }


class _Dumpable:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str) -> dict[str, Any]:
        assert mode == "json"
        return self.payload
