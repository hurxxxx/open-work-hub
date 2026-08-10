from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_alm_api.domains.images.context_refs import (
    doc_page_snapshot,
    flatten_doc_text,
    hydrated_context_ref,
    meeting_snapshot,
    normalize_context_ref,
    task_list_snapshot,
    task_snapshot,
)
from open_alm_api.domains.images import context_ref_hydration
from open_alm_api.domains.images.context_ref_hydration import hydrate_context_refs


class _FakeDb:
    def __init__(
        self,
        *,
        scalar_values: list[object | None] | None = None,
        scalars_values: list[list[object]] | None = None,
    ) -> None:
        self.scalar_values = list(scalar_values or [])
        self.scalars_values = list(scalars_values or [])
        self.scalar_calls = 0
        self.scalars_calls = 0

    def scalar(self, _statement: object) -> object | None:
        self.scalar_calls += 1
        return self.scalar_values.pop(0) if self.scalar_values else None

    def scalars(self, _statement: object) -> list[object]:
        self.scalars_calls += 1
        return self.scalars_values.pop(0) if self.scalars_values else []


def _workspace() -> SimpleNamespace:
    return SimpleNamespace(id="workspace-1")


def _user() -> SimpleNamespace:
    return SimpleNamespace(id="user-1")


def test_normalize_context_ref_accepts_known_kinds_case_insensitively() -> None:
    assert normalize_context_ref({"kind": "Meeting", "id": "meeting-1"}) == (
        "meeting",
        "meeting-1",
    )
    assert normalize_context_ref({"kind": "task", "id": 123}) == ("task", "123")
    assert normalize_context_ref({"kind": "doc", "id": "doc-1"}) == ("doc", "doc-1")


def test_normalize_context_ref_rejects_invalid_refs() -> None:
    assert normalize_context_ref(None) is None
    assert normalize_context_ref({"kind": "file", "id": "file-1"}) is None
    assert normalize_context_ref({"kind": "doc", "id": ""}) is None


def test_flatten_doc_text_reads_page_titles_and_text_pieces_with_limit() -> None:
    pages = [
        SimpleNamespace(
            title=" Intro ",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": " alpha "}]},
                {"type": "paragraph", "content": "ignored"},
                {"type": "paragraph", "content": [{"type": "text", "text": ""}]},
                "ignored",
            ],
        ),
        SimpleNamespace(
            title="Next",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "beta"}]}
            ],
        ),
    ]

    assert flatten_doc_text(pages, max_chars=17) == "Intro\nalpha\nNext\n"


def test_snapshot_builders_preserve_existing_shapes() -> None:
    meeting = SimpleNamespace(title="Weekly", agenda="Discuss launch")
    doc = SimpleNamespace(title="Spec")
    pages = [
        SimpleNamespace(
            title="Page",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "Body"}]}
            ],
        )
    ]
    task_list = SimpleNamespace(name="Launch", description="Prep", status="active")
    tasks = [
        SimpleNamespace(title="Ship copy", status="done"),
        SimpleNamespace(title="Review art", status="todo"),
    ]
    task = SimpleNamespace(title="Make image", status="todo", description="Use refs")

    assert meeting_snapshot(meeting) == {
        "title": "Weekly",
        "agenda": "Discuss launch",
        "summary": "Discuss launch",
    }
    assert doc_page_snapshot(doc, pages) == {"title": "Spec", "body": "Page\nBody"}
    assert task_list_snapshot(task_list, tasks) == {
        "title": "Launch",
        "description": "Prep",
        "status": "active",
        "tasks": ["[done] Ship copy", "[todo] Review art"],
    }
    assert task_snapshot(task) == {
        "title": "Make image",
        "status": "todo",
        "description": "Use refs",
    }


def test_hydrated_context_ref_merges_only_missing_user_title_and_summary() -> None:
    hydrated = hydrated_context_ref(
        kind="doc",
        ref_id="doc-1",
        snapshot={"title": "Current title", "body": "Current body"},
        raw_ref={"snapshot": {"title": "Old title", "summary": " User summary "}},
    )

    assert hydrated == {
        "kind": "doc",
        "id": "doc-1",
        "snapshot": {
            "title": "Current title",
            "body": "Current body",
            "summary": "User summary",
        },
    }


def test_hydrate_context_refs_skips_inaccessible_meetings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(scalar_values=[SimpleNamespace(title="Hidden", agenda="Secret")])
    monkeypatch.setattr(
        context_ref_hydration,
        "can_read_meeting_for_rag",
        lambda *_args, **_kwargs: False,
    )

    assert hydrate_context_refs(
        db,
        workspace=_workspace(),
        user=_user(),
        raw_refs=[{"kind": "meeting", "id": "meeting-1"}],
    ) == []
    assert db.scalar_calls == 0


def test_hydrate_context_refs_loads_doc_pages_and_merges_user_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    doc = SimpleNamespace(id="doc-1", title="Current spec")
    pages = [
        SimpleNamespace(
            title="Page",
            content_blocks=[
                {"type": "paragraph", "content": [{"type": "text", "text": "Body"}]}
            ],
        )
    ]
    db = _FakeDb(scalar_values=[doc], scalars_values=[pages])
    monkeypatch.setattr(
        context_ref_hydration,
        "can_read_native_doc_for_rag",
        lambda *_args, **_kwargs: True,
    )

    assert hydrate_context_refs(
        db,
        workspace=_workspace(),
        user=_user(),
        raw_refs=[
            {
                "kind": "doc",
                "id": "doc-1",
                "snapshot": {"summary": "User selected summary"},
            }
        ],
    ) == [
        {
            "kind": "doc",
            "id": "doc-1",
            "snapshot": {
                "title": "Current spec",
                "body": "Page\nBody",
                "summary": "User selected summary",
            },
        }
    ]


def test_hydrate_context_refs_prefers_task_list_before_task_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_list = SimpleNamespace(
        id="list-1",
        name="Launch",
        description="Prep",
        status="active",
    )
    tasks = [SimpleNamespace(status="todo", title="Draft copy")]
    db = _FakeDb(scalar_values=[task_list], scalars_values=[tasks])
    monkeypatch.setattr(
        context_ref_hydration,
        "has_list_access",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        context_ref_hydration,
        "can_read_task_for_rag",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected")),
    )

    assert hydrate_context_refs(
        db,
        workspace=_workspace(),
        user=_user(),
        raw_refs=[{"kind": "task", "id": "list-1"}],
    ) == [
        {
            "kind": "task",
            "id": "list-1",
            "snapshot": {
                "title": "Launch",
                "description": "Prep",
                "status": "active",
                "tasks": ["[todo] Draft copy"],
            },
        }
    ]
