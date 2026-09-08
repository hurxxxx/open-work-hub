from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_work_hub_api.core.realtime import AppRealtimeHub


@dataclass(frozen=True, slots=True)
class _RealtimeTopicDescriptor:
    topic: str

    def event_type(self, event_name: str) -> str:
        return f"{self.topic}.{event_name}"

    def topic_key(self, key: str) -> str:
        return f"{self.topic}:{key}"


_DOCS_PAGES_REALTIME_TOPIC = _RealtimeTopicDescriptor(topic="docs.pages")

DOCS_PAGES_TOPIC = _DOCS_PAGES_REALTIME_TOPIC.topic

DOCS_PAGES_CHANGED = _DOCS_PAGES_REALTIME_TOPIC.event_type("changed")
DOCS_PAGES_SNAPSHOT = _DOCS_PAGES_REALTIME_TOPIC.event_type("snapshot")
DOCS_ACCESS_CHANGED = "docs.access.changed"


def docs_pages_topic(doc_id: str) -> str:
    return _DOCS_PAGES_REALTIME_TOPIC.topic_key(doc_id)


def publish_doc_access_changed(hub: AppRealtimeHub | None, doc_id: str) -> None:
    """Invalidate only existing document observers, including newly revoked readers."""
    if hub is not None:
        hub.publish(
            docs_pages_topic(doc_id), {"type": DOCS_ACCESS_CHANGED, "data": {"doc_id": doc_id}}
        )
