from __future__ import annotations

from datetime import UTC, datetime

from open_work_hub_api.domains.search.result_projection import build_search_hit


def test_search_hit_preserves_canonical_pms_deep_link() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    hit = build_search_hit(
        {
            "entity_type": "pms_task",
            "entity_id": "task-1",
            "title": "Task",
            "summary": "Summary",
            "deep_link": "/apps/pms/workspaces/hq/lists/list-1?task=task-1",
            "created_at": timestamp,
            "source_updated_at": timestamp,
        },
        query="task",
        doc_page_lookup=lambda _doc_id: [],
    )

    assert hit.deep_link == "/apps/pms/workspaces/hq/lists/list-1?task=task-1"


def test_search_hit_snippet_centers_query_matches_in_body() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    hit = build_search_hit(
        {
            "entity_type": "file",
            "entity_id": "file-1",
            "title": "roadmap.pptx",
            "summary": "generic heater system introduction " * 12,
            "body": (
                ("common heater requirements " * 40)
                + "OPEN Alliance TC1 TC12 ethernet validation evidence"
                + (" common appendix" * 40)
            ),
            "deep_link": "/apps/files/workspaces/workspace-1?file=file-1",
            "created_at": timestamp,
            "source_updated_at": timestamp,
        },
        query="OPEN Alliance TC1 TC12",
        doc_page_lookup=lambda _doc_id: [],
    )

    assert "OPEN Alliance TC1 TC12" in hit.snippet.text
    assert len(hit.snippet.text) <= 420
    assert hit.snippet.highlights


def test_search_hit_snippet_uses_utf16_highlight_offsets() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    hit = build_search_hit(
        {
            "entity_type": "file",
            "entity_id": "file-1",
            "title": "emoji.txt",
            "summary": "😀 OPEN Alliance evidence",
            "deep_link": "/apps/files/workspaces/workspace-1?file=file-1",
            "created_at": timestamp,
            "source_updated_at": timestamp,
        },
        query="OPEN",
        doc_page_lookup=lambda _doc_id: [],
    )

    assert hit.snippet.highlights[0].start == 3
    assert hit.snippet.highlights[0].end == 7


def test_search_hit_snippet_offsets_survive_length_changing_casefold() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    hit = build_search_hit(
        {
            "entity_type": "file",
            "entity_id": "file-1",
            "title": "unicode.txt",
            "summary": "ß OPEN evidence",
            "deep_link": "/apps/files/workspaces/workspace-1?file=file-1",
            "created_at": timestamp,
            "source_updated_at": timestamp,
        },
        query="OPEN",
        doc_page_lookup=lambda _doc_id: [],
    )

    assert hit.snippet.highlights[0].start == 2
    assert hit.snippet.highlights[0].end == 6
