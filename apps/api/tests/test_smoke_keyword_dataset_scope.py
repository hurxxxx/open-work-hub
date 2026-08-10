from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from ai_do_api.domains.search.backend_contracts import (
    KeywordSearchHit,
    KeywordSearchQuery,
    KeywordSearchResult,
)
from ai_do_api import smoke_keyword_dataset_scope
from ai_do_api.smoke_keyword_dataset_scope import verify_workspace_keyword_index


@dataclass(frozen=True)
class FakeWorkspace:
    id: str = "workspace-1"
    key: str = "workspace"


class FakeKeywordClient:
    def __init__(
        self,
        *,
        index_exists: bool = True,
        document_count: int = 1,
        entity_counts: dict[str, int] | None = None,
        hit_workspace_id: str = "workspace-1",
        hit_entity_type: str = "doc",
    ) -> None:
        self._index_exists = index_exists
        self._document_count = document_count
        self._entity_counts = entity_counts or {}
        self._hit_workspace_id = hit_workspace_id
        self._hit_entity_type = hit_entity_type
        self.query: KeywordSearchQuery | None = None

    def index_exists(self) -> bool:
        return self._index_exists

    def count_workspace_documents(
        self,
        *,
        workspace_id: str,
        entity_types: tuple[str, ...] = (),
    ) -> int:
        assert workspace_id == "workspace-1"
        if entity_types:
            assert len(entity_types) == 1
            return self._entity_counts.get(entity_types[0], self._document_count)
        return self._document_count

    def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
        self.query = query
        if not self._hit_workspace_id:
            return KeywordSearchResult(hits=())
        return KeywordSearchResult(
            hits=(
                KeywordSearchHit(
                    document={
                        "workspace_id": self._hit_workspace_id,
                        "entity_type": self._hit_entity_type,
                    },
                    score=1.0,
                ),
            )
        )


def test_keyword_dataset_scope_smoke_checks_workspace_search() -> None:
    client = FakeKeywordClient(document_count=3)

    assert (
        verify_workspace_keyword_index(
            client,
            workspace=FakeWorkspace(),
            allowed_entity_types=("doc",),
            expected_active_document_counts={"doc": 3},
        )
        == 3
    )
    assert client.query == KeywordSearchQuery(
        workspace_id="workspace-1",
        entity_types=("doc",),
        size=1,
    )


@pytest.mark.parametrize(
    ("client", "message"),
    [
        (FakeKeywordClient(index_exists=False), "not initialized"),
        (FakeKeywordClient(hit_workspace_id="workspace-2"), "different workspace"),
        (FakeKeywordClient(hit_entity_type="meeting"), "disabled entity type"),
    ],
)
def test_keyword_dataset_scope_smoke_rejects_unready_index(
    client: FakeKeywordClient,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        verify_workspace_keyword_index(
            client,
            workspace=FakeWorkspace(),
            allowed_entity_types=("doc",),
            expected_active_document_counts={"doc": 1},
        )


def test_keyword_dataset_scope_smoke_accepts_empty_workspace() -> None:
    client = FakeKeywordClient(document_count=0)

    assert (
        verify_workspace_keyword_index(
            client,
            workspace=FakeWorkspace(),
            allowed_entity_types=("doc",),
            expected_active_document_counts={"doc": 0},
        )
        == 0
    )
    assert client.query is None


def test_keyword_dataset_scope_smoke_accepts_retained_disabled_documents() -> None:
    client = FakeKeywordClient(
        document_count=3,
        entity_counts={"doc": 0},
        hit_workspace_id="",
    )

    assert (
        verify_workspace_keyword_index(
            client,
            workspace=FakeWorkspace(),
            allowed_entity_types=("doc",),
            expected_active_document_counts={"doc": 0},
        )
        == 3
    )
    assert client.query is None


def test_keyword_dataset_scope_smoke_rejects_missing_expected_active_projection_hits() -> None:
    client = FakeKeywordClient(document_count=3, hit_workspace_id="")

    with pytest.raises(RuntimeError, match="expected 3 active projection document"):
        verify_workspace_keyword_index(
            client,
            workspace=FakeWorkspace(),
            allowed_entity_types=("doc",),
            expected_active_document_counts={"doc": 3},
        )


def test_keyword_dataset_scope_smoke_rejects_partial_entity_index() -> None:
    client = FakeKeywordClient(
        document_count=4,
        entity_counts={"doc": 2, "project": 1},
    )

    with pytest.raises(
        RuntimeError,
        match="active entity project expected 2 projection document.*index has 1",
    ):
        verify_workspace_keyword_index(
            client,
            workspace=FakeWorkspace(),
            allowed_entity_types=("doc", "project"),
            expected_active_document_counts={"doc": 2, "project": 2},
        )


def test_keyword_dataset_scope_smoke_skips_retained_disabled_entity_documents() -> None:
    client = FakeKeywordClient(document_count=3, hit_entity_type="meeting")

    assert (
        verify_workspace_keyword_index(
            client,
            workspace=FakeWorkspace(),
            allowed_entity_types=(),
            expected_active_document_counts={},
        )
        == 3
    )
    assert client.query is None


def test_keyword_dataset_scope_cli_counts_only_active_source_projections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeWorkspace()
    captured: dict[str, object] = {}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def scalars(self, _query: object) -> list[FakeWorkspace]:
            return [workspace]

    monkeypatch.setattr(
        smoke_keyword_dataset_scope,
        "get_session_factory",
        lambda: lambda: FakeSession(),
    )
    monkeypatch.setattr(smoke_keyword_dataset_scope, "_search_client", lambda: object())
    monkeypatch.setattr(
        smoke_keyword_dataset_scope,
        "resolve_workspace_enabled_app_ids",
        lambda _db, _workspace_id: {"docs"},
    )
    monkeypatch.setattr(
        smoke_keyword_dataset_scope,
        "resolve_workspace_keyword_search_scope",
        lambda _app_ids: SimpleNamespace(entity_types=("doc",)),
    )
    monkeypatch.setattr(
        smoke_keyword_dataset_scope,
        "all_workspace_search_documents",
        lambda _db, *, workspace: [
            {"entity_type": "doc", "entity_id": "doc-1"},
            {"entity_type": "meeting", "entity_id": "meeting-retained"},
        ],
    )

    def verify(_client, **kwargs):
        captured.update(kwargs)
        return 2

    monkeypatch.setattr(smoke_keyword_dataset_scope, "verify_workspace_keyword_index", verify)
    monkeypatch.setattr("sys.argv", ["smoke_keyword_dataset_scope", "--all-active"])

    smoke_keyword_dataset_scope.main()

    assert captured["allowed_entity_types"] == ("doc",)
    assert captured["expected_active_document_counts"] == {"doc": 1}
