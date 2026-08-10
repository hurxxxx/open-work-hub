from __future__ import annotations

from open_work_hub_api.domains.docs import realtime_protocol


def test_docs_realtime_protocol_constants_match_client_contract() -> None:
    assert realtime_protocol.DOCS_PAGES_TOPIC == "docs.pages"
    assert realtime_protocol.DOCS_PAGES_CHANGED == "docs.pages.changed"
    assert realtime_protocol.DOCS_PAGES_SNAPSHOT == "docs.pages.snapshot"
    assert realtime_protocol.docs_pages_topic("doc-1") == "docs.pages:doc-1"
