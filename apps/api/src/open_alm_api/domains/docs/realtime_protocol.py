from __future__ import annotations

from dataclasses import dataclass


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


def docs_pages_topic(doc_id: str) -> str:
    return _DOCS_PAGES_REALTIME_TOPIC.topic_key(doc_id)
