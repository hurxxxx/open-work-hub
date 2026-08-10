from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import utcnow_naive
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.usage.models import UsageEvent

USAGE_EVENT_APP_OPEN = "app.open"
USAGE_EVENT_CONTENT_VIEW = "content.view"
USAGE_EVENT_CONTENT_CREATE = "content.create"
USAGE_EVENT_CONTENT_REGISTER = "content.register"
USAGE_EVENT_SEARCH_QUERY = "search.query"

ALLOWED_USAGE_EVENT_TYPES = {
    USAGE_EVENT_APP_OPEN,
    USAGE_EVENT_CONTENT_VIEW,
    USAGE_EVENT_CONTENT_CREATE,
    USAGE_EVENT_CONTENT_REGISTER,
    USAGE_EVENT_SEARCH_QUERY,
}


def _limit(value: object, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def _safe_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = _limit(key, 80)
        if key_text is None:
            continue
        if isinstance(value, str):
            safe[key_text] = _limit(value, 200)
        elif isinstance(value, (int, float, bool)) or value is None:
            safe[key_text] = value
        else:
            safe[key_text] = _limit(value, 200)
    return safe or None


def usage_hash(value: str, *, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def usage_query_metadata(query: str) -> dict[str, object]:
    normalized = " ".join(query.strip().lower().split())
    return {
        "query_length": len(query.strip()),
        "query_hash": usage_hash(normalized or query.strip()),
    }


def _bucket_start(occurred_at: datetime, dedupe_minutes: int) -> datetime:
    minute_window = max(1, min(dedupe_minutes, 1440))
    aware = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=UTC)
    seconds = int(aware.timestamp())
    window_seconds = minute_window * 60
    bucket_seconds = seconds - (seconds % window_seconds)
    return datetime.fromtimestamp(bucket_seconds, UTC).replace(tzinfo=None)


def _dedupe_key(
    *,
    actor_user_id: str,
    app_id: str,
    event_type: str,
    workspace_id: str | None,
    content_kind: str | None,
    content_id: str | None,
    route_path: str | None,
    source: str | None,
    bucket_started_at: datetime,
) -> str:
    raw = "|".join(
        [
            actor_user_id,
            workspace_id or "",
            app_id,
            event_type,
            content_kind or "",
            content_id or "",
            route_path or "",
            source or "",
            bucket_started_at.isoformat(),
        ]
    )
    return usage_hash(raw, length=64)


def record_usage_event(
    db: Session,
    *,
    actor_user_id: str,
    app_id: str,
    event_type: str,
    workspace_id: str | None = None,
    content_kind: str | None = None,
    content_id: str | None = None,
    content_title: str | None = None,
    route_path: str | None = None,
    source: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
    dedupe_minutes: int = 30,
) -> UsageEvent:
    if event_type not in ALLOWED_USAGE_EVENT_TYPES:
        raise ValueError(f"unsupported usage event type: {event_type}")
    event_time = occurred_at or utcnow_naive()
    bucket_started_at = _bucket_start(event_time, dedupe_minutes)
    normalized_app_id = _limit(app_id, 64)
    if normalized_app_id is None:
        raise ValueError("app_id is required")
    normalized_content_id = _limit(content_id, 512)
    normalized_route_path = _limit(route_path, 240)
    normalized_source = _limit(source, 120)
    dedupe_key = _dedupe_key(
        actor_user_id=actor_user_id,
        workspace_id=_limit(workspace_id, 36),
        app_id=normalized_app_id,
        event_type=event_type,
        content_kind=_limit(content_kind, 64),
        content_id=normalized_content_id,
        route_path=normalized_route_path,
        source=normalized_source,
        bucket_started_at=bucket_started_at,
    )
    for pending in db.new:
        if isinstance(pending, UsageEvent) and pending.dedupe_key == dedupe_key:
            pending.count += 1
            pending.last_occurred_at = event_time
            if content_title and not pending.content_title:
                pending.content_title = _limit(content_title, 300)
            return pending
    existing = db.scalar(
        select(UsageEvent).where(UsageEvent.dedupe_key == dedupe_key).limit(1)
    )
    if existing is not None:
        existing.count += 1
        existing.last_occurred_at = event_time
        if content_title and not existing.content_title:
            existing.content_title = _limit(content_title, 300)
        return existing

    event = UsageEvent(
        id=new_id(),
        actor_user_id=actor_user_id,
        workspace_id=_limit(workspace_id, 36),
        app_id=normalized_app_id,
        event_type=event_type,
        content_kind=_limit(content_kind, 64),
        content_id=normalized_content_id,
        content_title=_limit(content_title, 300),
        route_path=normalized_route_path,
        source=normalized_source,
        event_metadata=_safe_metadata(metadata),
        dedupe_key=dedupe_key,
        bucket_started_at=bucket_started_at,
        occurred_at=event_time,
        last_occurred_at=event_time,
        count=1,
    )
    db.add(event)
    return event
