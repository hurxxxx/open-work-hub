from __future__ import annotations

from typing import Any

from open_alm_api.domains.dm import thread_projection


def conversation_snapshot_payload(
    *,
    conversation_id: str,
    conversation: Any,
    message: Any | None = None,
) -> dict[str, Any]:
    return thread_projection.conversation_snapshot_payload(
        conversation_id=conversation_id,
        conversation=conversation,
        message=message,
    )


def conversation_removed_payload(*, conversation_id: str) -> dict[str, Any]:
    return thread_projection.conversation_removed_payload(conversation_id=conversation_id)


def conversation_read_payload(
    *,
    user_id: str,
    conversation_id: str,
    conversation: Any,
) -> dict[str, Any]:
    return thread_projection.conversation_read_payload(
        user_id=user_id,
        conversation_id=conversation_id,
        conversation=conversation,
    )


def dump_realtime_payload(payload: Any) -> dict[str, Any]:
    return thread_projection.dump_realtime_payload(payload)
