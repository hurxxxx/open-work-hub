from __future__ import annotations

import logging
from typing import Any, Protocol

WHITEBOARD_ACCESS_TOPIC = "whiteboard.access"
WHITEBOARD_ACCESS_CHANGED = "whiteboard.access.changed"

logger = logging.getLogger(__name__)


class WhiteboardRealtimePublisher(Protocol):
    def publish(self, topic: str, event: dict[str, Any]) -> None: ...


def whiteboard_access_topic(whiteboard_id: str) -> str:
    return f"{WHITEBOARD_ACCESS_TOPIC}:{whiteboard_id}"


def publish_whiteboard_access_changed(
    realtime: WhiteboardRealtimePublisher | None, whiteboard_id: str
) -> None:
    """Invalidate only this board's subscribers after the owning transaction commits.

    Existing subscribers include viewers whose access was just revoked. This control
    event carries no content, identities, permission details, or shared-link token.
    """
    if realtime is None:
        return
    try:
        realtime.publish(
            whiteboard_access_topic(whiteboard_id),
            {"type": WHITEBOARD_ACCESS_CHANGED, "data": {"whiteboard_id": whiteboard_id}},
        )
    except Exception:  # pragma: no cover - transport failure; reconnect rechecks source ACL
        logger.exception("Could not publish whiteboard access invalidation")
