from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.search import service as search_service
import open_work_hub_api.domains as domains_package
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordAclFilter,
    KeywordSearchHit,
    KeywordSearchQuery,
    KeywordSearchResult,
)
from open_work_hub_api.domains.search.schemas import KeywordSearchRequest
from open_work_hub_api.domains.search.default_entity_adapters import (
    ensure_search_entity_adapters_registered,
)
from open_work_hub_api.domains.search.default_index_hook_adapters import (
    ensure_search_index_hooks_registered,
)
from open_work_hub_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    search_entity_adapters,
)
from open_work_hub_api.domains.search.hook_registry import get_search_index_hook_registration
from open_work_hub_api.domains.search import projections as search_projections
from open_work_hub_api.domains.search.projection_identity import SearchProjectionIdentityError


def _request(*, entity_types: list[str] | None = None) -> KeywordSearchRequest:
    return KeywordSearchRequest(query="budget", entity_types=entity_types or [])


def _user():
    return SimpleNamespace(id="user-1")


def test_app_owned_search_adapters_match_explicit_runtime_composition() -> None:
    domains_root = Path(domains_package.__file__).parent
    discovered: set[tuple[str, str]] = set()
    for projection_path in sorted(domains_root.glob("*/search_projection.py")):
        module = importlib.import_module(
            f"open_work_hub_api.domains.{projection_path.parent.name}.search_projection"
        )
        discovered.update(
            (value.owner_app_id, value.entity_type)
            for value in vars(module).values()
            if isinstance(value, SearchEntityAdapter)
        )

    ensure_search_entity_adapters_registered()
    composed = {(adapter.owner_app_id, adapter.entity_type) for adapter in search_entity_adapters()}

    assert composed == discovered


def test_company_keyword_search_adapters_declare_registered_index_hooks() -> None:
    ensure_search_entity_adapters_registered()
    ensure_search_index_hooks_registered()

    for adapter in search_entity_adapters():
        for operation in ("create", "update", "delete"):
            hook_names = adapter.index_hooks.for_operation(operation)
            assert hook_names, (adapter.entity_type, operation)
            for hook_name in hook_names:
                registration = get_search_index_hook_registration(hook_name)
                assert registration is not None
                assert registration.owner_app is adapter.owner_app
                assert registration.entity_type == adapter.entity_type
                assert operation in registration.operations


@pytest.mark.parametrize(
    "document",
    [
        {
            "entity_type": "doc",
            "entity_id": "doc-1",
        },
        {
            "entity_type": "meeting",
            "entity_id": "doc-1",
        },
        {
            "entity_type": "doc",
            "entity_id": "",
        },
    ],
)
def test_company_backfill_rejects_projection_identity_drift(
    document: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SimpleNamespace(
        adapter_id="test.docs",
        entity_types=("doc",),
        load_documents=lambda db,: [document],
    )
    monkeypatch.setattr(
        search_projections,
        "ensure_search_projection_adapters_registered",
        lambda: None,
    )
    monkeypatch.setattr(
        search_projections,
        "get_search_projection_adapters",
        lambda: (adapter,),
    )

    with pytest.raises(SearchProjectionIdentityError):
        search_projections.all_search_documents(
            SimpleNamespace(),
        )


def test_company_backfill_rejects_projection_without_acl_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = SimpleNamespace(
        adapter_id="test.docs",
        entity_types=("doc",),
        load_documents=lambda db,: [
            {
                "entity_type": "doc",
                "entity_id": "doc-1",
            }
        ],
    )
    monkeypatch.setattr(
        search_projections,
        "ensure_search_projection_adapters_registered",
        lambda: None,
    )
    monkeypatch.setattr(
        search_projections,
        "get_search_projection_adapters",
        lambda: (adapter,),
    )

    with pytest.raises(SearchProjectionIdentityError, match="ACL shape mismatch"):
        search_projections.all_search_documents(
            SimpleNamespace(),
        )


def test_company_keyword_search_rejects_workspace_without_active_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_service, "resolve_company_enabled_app_ids", lambda db: [])
    monkeypatch.setattr(
        search_service,
        "_search_client",
        lambda: pytest.fail("search backend must not be called"),
    )

    with pytest.raises(HTTPException) as error:
        search_service.query_keyword_search(
            SimpleNamespace(),
            user=_user(),
            request=_request(),
        )

    assert error.value.status_code == 403
    assert error.value.headers["X-Open-Work-Hub-Error-Code"] == ("search.keyword_search_disabled")


def test_company_keyword_search_returns_empty_for_disallowed_requested_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_service,
        "resolve_company_enabled_app_ids",
        lambda db: ["docs"],
    )
    monkeypatch.setattr(
        search_service,
        "_search_client",
        lambda: pytest.fail("search backend must not be called"),
    )

    response = search_service.query_keyword_search(
        SimpleNamespace(),
        user=_user(),
        request=_request(entity_types=["meeting", "unknown"]),
    )

    assert response.total == 0
    assert response.hits == []
    assert response.facets.entity_types == []


def test_company_keyword_search_accepts_empty_company_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_queries: list[KeywordSearchQuery] = []

    class FakeSearchClient:
        def index_exists(self) -> bool:
            return True

        def count_company_documents(
            self,
        ) -> int:
            raise AssertionError("workspace document count must not gate search")

        def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
            captured_queries.append(query)
            return KeywordSearchResult(hits=())

    class FakePolicy:
        def build_keyword_acl_filter(self) -> KeywordAclFilter:
            return KeywordAclFilter()

    monkeypatch.setattr(
        search_service,
        "resolve_company_enabled_app_ids",
        lambda db: ["docs"],
    )
    monkeypatch.setattr(
        search_service.SourceAclPolicy,
        "for_user",
        staticmethod(lambda db, *, user: FakePolicy()),
    )
    monkeypatch.setattr(search_service, "_search_client", lambda: FakeSearchClient())

    response = search_service.query_keyword_search(
        SimpleNamespace(),
        user=_user(),
        request=_request(),
        backend_candidate_size=80,
    )

    assert response.total == 0
    assert captured_queries[0].entity_types == ("doc",)
    assert captured_queries[0].size == 80


def test_keyword_query_uses_injected_staging_client_without_default_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class StagingClient:
        def index_exists(self) -> bool:
            calls.append("exists")
            return True

        def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
            calls.append(f"search:{query.text}")
            return KeywordSearchResult(hits=())

    class FakePolicy:
        def build_keyword_acl_filter(self) -> KeywordAclFilter:
            return KeywordAclFilter()

    monkeypatch.setattr(
        search_service,
        "resolve_company_enabled_app_ids",
        lambda db: ["docs"],
    )
    monkeypatch.setattr(
        search_service.SourceAclPolicy,
        "for_user",
        staticmethod(lambda db, *, user: FakePolicy()),
    )
    monkeypatch.setattr(
        search_service,
        "_search_client",
        lambda: pytest.fail("active alias client must not be resolved"),
    )

    response = search_service.query_keyword_search(
        SimpleNamespace(),
        user=_user(),
        request=_request(),
        client=StagingClient(),
    )

    assert response.total == 0
    assert calls == ["exists", "search:budget"]


def test_partitioned_keyword_query_uses_partition_then_source_acl_and_hydration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    partition_id = "11111111-1111-1111-1111-111111111111"
    stale_row = {
        "retrieval_partition_id": partition_id,
        "entity_type": "file",
        "entity_id": "file-1",
        "title": "Company handbook",
        "summary": "Published handbook",
        "body": "company handbook",
        "keywords": "handbook",
        "source_updated_at": "2026-07-20T00:00:00Z",
        "created_at": "2026-07-20T00:00:00Z",
        "deep_link": "/apps/files?file=stale-id",
        "visibility": "private",
        "metadata": {},
    }

    class StagingClient:
        def index_exists(self) -> bool:
            return True

        def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
            assert query.retrieval_partition_ids == (partition_id,)
            assert query.acl_filter is None
            return KeywordSearchResult(hits=(KeywordSearchHit(document=stale_row, score=1.0),))

    class FakePolicy:
        def build_keyword_acl_filter(self):
            raise AssertionError("legacy backend ACL must not run for a partitioned generation")

        def authorize_many_resources(self, resources):
            return set(resources)

    monkeypatch.setattr(
        search_service,
        "resolve_company_enabled_app_ids",
        lambda db: ["files"],
    )
    monkeypatch.setattr(
        search_service.SourceAclPolicy,
        "for_user",
        staticmethod(lambda db, *, user: FakePolicy()),
    )
    monkeypatch.setattr(
        search_service,
        "_resolve_keyword_partition_ids",
        lambda *args, **kwargs: (partition_id,),
    )
    monkeypatch.setattr(
        search_service,
        "hydrate_file_search_rows_from_source",
        lambda db, *, rows: [
            {
                **rows[0],
                "deep_link": ("/apps/files?file=file-1"),
                "visibility": "company",
                "metadata": {
                    "access_scope_kind": "company",
                },
            }
        ],
    )

    response = search_service.query_keyword_search(
        SimpleNamespace(),
        user=_user(),
        request=_request(entity_types=["file"]),
        client=StagingClient(),
        evaluation_entity_types=("file",),
        partitioned_generation=True,
    )

    assert response.total == 1
    assert not hasattr(response.hits[0], "workspace_id")
    assert response.hits[0].visibility == "company"
    assert response.hits[0].deep_link == "/apps/files?file=file-1"
    assert response.hits[0].metadata["access_scope_kind"] == "company"


def test_company_keyword_search_reports_missing_global_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSearchClient:
        def index_exists(self) -> bool:
            return False

    class FakePolicy:
        def build_keyword_acl_filter(self) -> KeywordAclFilter:
            return KeywordAclFilter()

    monkeypatch.setattr(
        search_service,
        "resolve_company_enabled_app_ids",
        lambda db: ["docs"],
    )
    monkeypatch.setattr(
        search_service.SourceAclPolicy,
        "for_user",
        staticmethod(lambda db, *, user: FakePolicy()),
    )
    monkeypatch.setattr(search_service, "_search_client", lambda: FakeSearchClient())

    with pytest.raises(HTTPException) as error:
        search_service.query_keyword_search(
            SimpleNamespace(),
            user=_user(),
            request=_request(),
        )

    assert error.value.status_code == 503
    assert error.value.headers["X-Open-Work-Hub-Error-Code"] == "search.keyword_backend_unavailable"


def test_disabled_source_retains_indexed_documents_for_reenable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enabled_app_ids = ["docs"]
    indexed_document = {
        "entity_type": "doc",
        "entity_id": "doc-1",
        "title": "Budget",
        "summary": "Budget review",
        "source_updated_at": "2026-07-20T00:00:00Z",
        "created_at": "2026-07-20T00:00:00Z",
        "deep_link": "/apps/docs/documents/doc-1",
        "doc_pages": [],
    }

    class FakeSearchClient:
        def __init__(self) -> None:
            self.documents = [indexed_document]
            self.search_calls = 0

        def index_exists(self) -> bool:
            return True

        def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
            assert query.entity_types == ("doc",)
            self.search_calls += 1
            return KeywordSearchResult(
                hits=(KeywordSearchHit(document=self.documents[0], score=1.0),)
            )

    class FakePolicy:
        def build_keyword_acl_filter(self) -> KeywordAclFilter:
            return KeywordAclFilter()

        def can_read_resource(self, resource_type: str, resource_id: str) -> bool:
            return bool(resource_type) and resource_id == "doc-1"

    client = FakeSearchClient()
    monkeypatch.setattr(
        search_service,
        "resolve_company_enabled_app_ids",
        lambda db: enabled_app_ids,
    )
    monkeypatch.setattr(
        search_service.SourceAclPolicy,
        "for_user",
        staticmethod(lambda db, *, user: FakePolicy()),
    )
    monkeypatch.setattr(search_service, "_search_client", lambda: client)

    first_response = search_service.query_keyword_search(
        SimpleNamespace(),
        user=_user(),
        request=_request(),
    )
    assert first_response.total == 1

    enabled_app_ids.clear()
    with pytest.raises(HTTPException) as error:
        search_service.query_keyword_search(
            SimpleNamespace(),
            user=_user(),
            request=_request(),
        )
    assert error.value.status_code == 403
    assert client.documents == [indexed_document]
    assert client.search_calls == 1

    enabled_app_ids.append("docs")
    reenabled_response = search_service.query_keyword_search(
        SimpleNamespace(),
        user=_user(),
        request=_request(),
    )
    assert reenabled_response.total == 1
    assert client.search_calls == 2
