from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GlobalNotificationItem(BaseModel):
    id: str
    type: str
    title: str
    body: str
    source_type: str
    source_id: str | None
    origin_app_id: str
    origin_workspace_id: str | None
    action_url: str | None = None
    is_read: bool
    created_at: datetime


class GlobalNotificationListResponse(BaseModel):
    items: list[GlobalNotificationItem]
    total: int
    page: int
    page_size: int


class GlobalUnreadCountResponse(BaseModel):
    count: int


class NotificationStreamPayload(BaseModel):
    notification: GlobalNotificationItem | None = None
    unread_count: int
