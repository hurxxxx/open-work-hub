from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.realtime import RealtimeEvent
from open_work_hub_api.domains.docs import realtime_protocol as docs
from open_work_hub_api.domains.realtime.docs_pages_subscription import (
    resolve_docs_pages_subscription,
)
from open_work_hub_api.domains.realtime.whiteboard_access_subscription import (
    resolve_whiteboard_access_subscription,
)
from open_work_hub_api.domains.whiteboard import realtime as whiteboard


@dataclass(frozen=True)
class ResourceSubscription:
    topic: str
    key: str
    channel: str
    access_event_type: str
    resource_id_field: str
    snapshot: RealtimeEvent | None = None

    def access_changed_event(self) -> RealtimeEvent:
        return {"type": self.access_event_type, "data": {self.resource_id_field: self.key}}


def requested_resource_subscription(payload: dict[str, Any]) -> ResourceSubscription:
    topic, key = payload.get("topic"), payload.get("key")
    if not isinstance(key, str) or not key:
        raise localized_http_exception(status_code=400, code="validation.value_invalid")
    if topic == docs.DOCS_PAGES_TOPIC:
        return ResourceSubscription(
            topic, key, docs.docs_pages_topic(key), docs.DOCS_ACCESS_CHANGED, "doc_id"
        )
    if topic == whiteboard.WHITEBOARD_ACCESS_TOPIC:
        return ResourceSubscription(
            topic,
            key,
            whiteboard.whiteboard_access_topic(key),
            whiteboard.WHITEBOARD_ACCESS_CHANGED,
            "whiteboard_id",
        )
    raise localized_http_exception(status_code=400, code="validation.value_invalid")


def resolve_resource_subscription(
    payload: dict[str, Any], *, token: str, user_id: str
) -> ResourceSubscription:
    requested = requested_resource_subscription(payload)
    if requested.topic == docs.DOCS_PAGES_TOPIC:
        resolved = resolve_docs_pages_subscription(payload, token=token, user_id=user_id)
        if resolved.doc_id != requested.key:
            raise localized_http_exception(status_code=404, code="docs.doc_not_found")
        return ResourceSubscription(
            requested.topic,
            requested.key,
            requested.channel,
            requested.access_event_type,
            requested.resource_id_field,
            snapshot={
                "type": docs.DOCS_PAGES_SNAPSHOT,
                "data": {
                    "doc_id": resolved.doc_id,
                    "updated_at": resolved.updated_at.isoformat() if resolved.updated_at else None,
                },
            },
        )
    resolve_whiteboard_access_subscription(payload, token=token, user_id=user_id)
    return requested


@dataclass(frozen=True)
class AuthorizedResourceEvent:
    event: RealtimeEvent | None
    revoke: bool = False


def authorize_resource_event(
    subscription: ResourceSubscription,
    payload: dict[str, Any],
    event: RealtimeEvent,
    *,
    token: str,
    user_id: str,
) -> AuthorizedResourceEvent:
    """Recheck canonical ACL before disclosure, retaining one revocation control frame."""
    event_type = event.get("type")
    data = event.get("data")
    if not isinstance(data, dict) or data.get(subscription.resource_id_field) != subscription.key:
        return AuthorizedResourceEvent(None)
    control = event_type == subscription.access_event_type
    if not control and not (
        subscription.topic == docs.DOCS_PAGES_TOPIC
        and event_type in {docs.DOCS_PAGES_CHANGED, docs.DOCS_PAGES_SNAPSHOT}
    ):
        return AuthorizedResourceEvent(None)
    try:
        resolve_resource_subscription(payload, token=token, user_id=user_id)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise
        return AuthorizedResourceEvent(subscription.access_changed_event(), revoke=True)
    # Control events are always reconstructed: never forward unexpected metadata.
    return AuthorizedResourceEvent(subscription.access_changed_event() if control else event)
