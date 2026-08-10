from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from open_alm_api.domains.notifications import service
from open_alm_api.domains.notifications.schemas import (
    GlobalNotificationItem,
    GlobalNotificationListResponse,
)
from open_alm_api.domains.pms.models import Notification


@dataclass(frozen=True)
class NotificationReadResult:
    item: GlobalNotificationItem
    unread_count: int


def build_notification_list_response(
    rows: Sequence[Notification],
    *,
    page: int,
    page_size: int,
) -> GlobalNotificationListResponse:
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    return GlobalNotificationListResponse(
        items=[service.serialize_notification(row) for row in page_rows],
        total=len(rows),
        page=page,
        page_size=page_size,
    )


def notification_event_payload(
    item: GlobalNotificationItem | None,
) -> dict[str, Any] | None:
    if item is None:
        return None
    return item.model_dump(mode="json")
