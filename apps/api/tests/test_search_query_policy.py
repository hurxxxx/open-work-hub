from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_work_hub_api.domains.search.backend_contracts import (
    KeywordAclBranch,
    KeywordAclFilter,
    KeywordSearchHit,
    KeywordSearchResult,
    keyword_acl_clause,
)
from open_work_hub_api.domains.search.backend_factory import (
    build_keyword_search_client,
    register_keyword_search_backend,
    reset_keyword_search_backends,
)
from open_work_hub_api.domains.search.opensearch import (
    build_keyword_search_opensearch_body,
    parse_keyword_search_opensearch_response,
)
from open_work_hub_api.domains.search.query_policy import (
    KEYWORD_SEARCH_TEXT_FIELDS,
    build_keyword_search_query,
    filter_and_sort_keyword_search_rows,
    keyword_search_row_matches_request,
    sort_keyword_search_rows,
)
from open_work_hub_api.domains.search.result_projection import build_search_facets
from open_work_hub_api.domains.search.schemas import KeywordSearchRequest
from open_work_hub_api.domains.search.service import (
    _filter_accessible_search_rows,
    _load_authorized_ranked_candidates,
)


def test_keyword_search_backend_factory_uses_settings_interface() -> None:
    client = build_keyword_search_client(
        SimpleNamespace(
            opensearch_url="http://search.internal:9200/",
            opensearch_index_prefix="tenant-main",
        )
    )

    assert client.base_url == "http://search.internal:9200"
    assert client.index_name == "tenant-main_keyword_search_documents"


def test_keyword_search_backend_factory_selects_registered_backend() -> None:
    class _FakeKeywordSearchClient:
        def __init__(self, marker: str) -> None:
            self.marker = marker

    reset_keyword_search_backends()
    try:
        register_keyword_search_backend(
            "fake",
            lambda settings: _FakeKeywordSearchClient(settings.marker),
        )

        client = build_keyword_search_client(
            SimpleNamespace(keyword_search_backend="fake", marker="selected")
        )

        assert isinstance(client, _FakeKeywordSearchClient)
        assert client.marker == "selected"
    finally:
        reset_keyword_search_backends()


def _request(**overrides: object) -> KeywordSearchRequest:
    return KeywordSearchRequest.model_validate(overrides)


def _acl_filter(*branches: KeywordAclBranch) -> KeywordAclFilter:
    return KeywordAclFilter(branches=branches)


def test_keyword_search_request_constrains_extension_filter_tokens() -> None:
    _request(
        entity_types=["plugin_record"],
        status_by_type={"plugin_record": ["ready_for_review"]},
        people={"role": "reviewer", "user_ids": ["user_1"]},
        target_refs=[{"type": "plugin_target", "id": "target_1"}],
    )

    with pytest.raises(ValueError):
        _request(entity_types=["bad/type"])
    with pytest.raises(ValueError):
        _request(entity_types=["plugin_record"] * 51)
    with pytest.raises(ValueError):
        _request(status_by_type={"plugin_record": ["bad*status"]})


def test_query_policy_builds_text_opensearch_body_with_scope_acl_and_entity_filters() -> None:
    acl_filter = _acl_filter(
        KeywordAclBranch(
            entity_type="doc",
            clauses=(keyword_acl_clause("visibility", "company"),),
        )
    )
    request = _request(query="  예산 리스크  ", entity_types=["doc", "pms_task"])

    query = build_keyword_search_query(
        acl_filter=acl_filter,
        request=request,
        size=50,
        request_timeout_seconds=5.0,
    )
    body = build_keyword_search_opensearch_body(query)

    assert query.text == "예산 리스크"
    assert query.entity_types == ("doc", "pms_task")
    assert query.request_timeout_seconds == 5.0

    assert body == {
        "track_total_hits": True,
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"entity_type": ["doc", "pms_task"]}},
                    {
                        "bool": {
                            "should": [
                                {
                                    "bool": {
                                        "filter": [{"term": {"entity_type": "doc"}}],
                                        "should": [
                                            {
                                                "term": {
                                                    "visibility": "company",
                                                }
                                            }
                                        ],
                                        "minimum_should_match": 1,
                                    }
                                }
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                ],
                "must": [
                    {
                        "multi_match": {
                            "query": "예산 리스크",
                            "fields": list(KEYWORD_SEARCH_TEXT_FIELDS),
                            "operator": "and",
                            "type": "best_fields",
                        }
                    }
                ],
            }
        },
        "sort": [
            {"_score": {"order": "desc"}},
            {"source_updated_at": {"order": "desc", "unmapped_type": "date"}},
        ],
        "size": 50,
    }


def test_query_policy_allows_recall_oriented_text_matching() -> None:
    query = build_keyword_search_query(
        acl_filter=_acl_filter(
            KeywordAclBranch(
                entity_type="file",
                clauses=(keyword_acl_clause("visibility", "company"),),
            )
        ),
        request=_request(query="국제 특허 출원 조사 절차", entity_types=["file"]),
        text_operator="or",
        text_minimum_should_match="30%",
    )

    body = build_keyword_search_opensearch_body(query)

    assert query.text_operator == "or"
    assert body["query"]["bool"]["must"][0]["multi_match"]["operator"] == "or"
    assert body["query"]["bool"]["must"][0]["multi_match"]["minimum_should_match"] == "30%"


def test_query_policy_uses_match_all_for_empty_query_and_requested_date_sort() -> None:
    acl_filter = _acl_filter(
        KeywordAclBranch(
            entity_type="pms_task",
            clauses=(keyword_acl_clause("team_ids", ["team_1"]),),
        )
    )
    request = _request(query="  ", sort={"field": "updated_at", "direction": "asc"})

    body = build_keyword_search_opensearch_body(
        build_keyword_search_query(
            acl_filter=acl_filter,
            request=request,
        )
    )

    assert body["query"] == {
        "bool": {
            "filter": [
                {
                    "bool": {
                        "should": [
                            {
                                "bool": {
                                    "filter": [{"term": {"entity_type": "pms_task"}}],
                                    "should": [{"term": {"team_ids": "team_1"}}],
                                    "minimum_should_match": 1,
                                }
                            }
                        ],
                        "minimum_should_match": 1,
                    }
                },
            ],
            "must": [{"match_all": {}}],
        }
    }
    assert body["sort"] == [
        {"source_updated_at": {"order": "asc", "unmapped_type": "date"}},
        {"_score": {"order": "desc"}},
    ]
    assert body["size"] == 10000


def test_query_policy_uses_match_none_for_empty_acl_filter() -> None:
    body = build_keyword_search_opensearch_body(
        build_keyword_search_query(
            acl_filter=KeywordAclFilter(),
            request=_request(query="예산"),
        )
    )

    assert body["query"]["bool"]["filter"] == [
        {"match_none": {}},
    ]


def test_partition_query_omits_stale_legacy_acl_hint() -> None:
    partition_id = "11111111-1111-1111-1111-111111111111"
    body = build_keyword_search_opensearch_body(
        build_keyword_search_query(
            retrieval_partition_ids=(partition_id,),
            acl_filter=None,
            request=_request(query="company handbook", entity_types=["file"]),
        )
    )

    assert body["query"]["bool"]["filter"] == [
        {"terms": {"retrieval_partition_id": [partition_id]}},
        {"terms": {"entity_type": ["file"]}},
    ]


def test_query_policy_matches_status_people_target_and_date_filters() -> None:
    request = _request(
        entity_types=["pms_task"],
        people={"role": "assignee", "user_ids": ["user_1"]},
        status_by_type={"pms_task": ["todo"]},
        target_refs=[{"type": "pms_space", "id": "space_1"}],
        date_filters=[
            {
                "field": "due_date",
                "from": "2026-05-01T00:00:00",
                "to": "2026-05-31T00:00:00",
            }
        ],
    )
    row = {
        "entity_type": "pms_task",
        "status": "todo",
        "people": [{"role": "assignee", "user_id": "user_1"}],
        "target_keys": ["pms_space:space_1"],
        "date_markers": {"due_date": "2026-05-10"},
    }

    assert keyword_search_row_matches_request(row, request)
    assert not keyword_search_row_matches_request({**row, "status": "done"}, request)
    assert not keyword_search_row_matches_request(
        {**row, "people": [{"role": "owner", "user_id": "user_1"}]},
        request,
    )
    assert not keyword_search_row_matches_request(
        {**row, "target_keys": ["pms_space:space_2"]},
        request,
    )
    assert not keyword_search_row_matches_request(
        {**row, "date_markers": {"due_date": "2026-06-01"}},
        request,
    )


def test_query_policy_includes_exact_midnight_datetime_boundary() -> None:
    request = _request(
        date_filters=[
            {
                "field": "authored_at",
                "from": "2026-08-02T00:00:00Z",
                "to": "2026-08-02T00:00:00Z",
            }
        ]
    )
    row = {"date_markers": {"authored_at": "2026-08-02T00:00:00+00:00"}}

    assert keyword_search_row_matches_request(row, request)
    query = build_keyword_search_query(
        acl_filter=None,
        request=request,
    )
    assert query.date_filters[0].from_value == "2026-08-02T00:00:00+00:00"
    assert query.date_filters[0].to_value == "2026-08-02T00:00:00+00:00"


@pytest.mark.parametrize(
    ("field", "backend_field"),
    [
        ("updated_at", "source_updated_at"),
        ("created_at", "created_at"),
        ("authored_at", "date_markers.authored_at"),
    ],
)
def test_opensearch_date_filter_uses_the_canonical_backend_field(
    field: str,
    backend_field: str,
) -> None:
    body = build_keyword_search_opensearch_body(
        build_keyword_search_query(
            acl_filter=None,
            request=_request(
                date_filters=[
                    {
                        "field": field,
                        "from": "2026-08-01T00:00:00Z",
                        "to": "2026-08-02T00:00:00Z",
                    }
                ]
            ),
        )
    )

    assert {
        "range": {
            backend_field: {
                "gte": "2026-08-01T00:00:00+00:00",
                "lte": "2026-08-02T00:00:00+00:00",
            }
        }
    } in body["query"]["bool"]["filter"]


def test_query_policy_disambiguates_app_aware_target_refs() -> None:
    request = _request(target_refs=[{"app": "pms", "type": "space", "id": "space_1"}])
    legacy_request = _request(target_refs=[{"type": "space", "id": "space_1"}])
    row = {
        "entity_type": "doc",
        "target_keys": ["docs:space:space_1", "space:space_1"],
    }

    assert not keyword_search_row_matches_request(row, request)
    assert keyword_search_row_matches_request(row, legacy_request)
    assert keyword_search_row_matches_request(
        {**row, "target_keys": ["pms:space:space_1", "space:space_1"]},
        request,
    )


def test_all_target_refs_compile_to_independent_backend_filter_groups() -> None:
    request = _request(
        target_refs=[
            {"app": "files", "type": "file_author", "id": "author-hash"},
            {"app": "files", "type": "file_department", "id": "department-hash"},
        ],
        target_ref_match="all",
    )
    query = build_keyword_search_query(
        acl_filter=None,
        request=request,
    )
    body = build_keyword_search_opensearch_body(query)

    assert query.target_keys == ()
    assert query.target_key_groups == (
        ("files:file_author:author-hash",),
        ("files:file_department:department-hash",),
    )
    assert {"terms": {"target_keys": ["files:file_author:author-hash"]}} in body["query"]["bool"][
        "filter"
    ]
    assert {"terms": {"target_keys": ["files:file_department:department-hash"]}} in body["query"][
        "bool"
    ]["filter"]
    assert keyword_search_row_matches_request(
        {
            "target_keys": [
                "files:file_author:author-hash",
                "files:file_department:department-hash",
            ]
        },
        request,
    )
    assert not keyword_search_row_matches_request(
        {"target_keys": ["files:file_author:author-hash"]},
        request,
    )


def test_search_facets_sort_mixed_legacy_and_app_aware_targets() -> None:
    facets = build_search_facets(
        [
            {
                "entity_type": "pms_task",
                "targets": [
                    {"type": "list", "id": "list_1", "label": "Backlog"},
                    {"app": "pms", "type": "space", "id": "space_1", "label": "Product"},
                    {"app": "docs", "type": "", "id": "ignored", "label": "Ignored"},
                ],
            }
        ]
    )

    assert [item.model_dump() for item in facets.targets] == [
        {"app": None, "type": "list", "id": "list_1", "label": "Backlog", "count": 1},
        {"app": "pms", "type": "space", "id": "space_1", "label": "Product", "count": 1},
    ]


def test_query_policy_filters_before_relevance_sorting() -> None:
    request = _request(entity_types=["doc"])
    rows = [
        {
            "entity_id": "low",
            "entity_type": "doc",
            "_search_score": 1.0,
            "source_updated_at": "2026-05-20T00:00:00",
        },
        {
            "entity_id": "high_old",
            "entity_type": "doc",
            "_search_score": 5.0,
            "source_updated_at": "2026-05-10T00:00:00",
        },
        {
            "entity_id": "high_new",
            "entity_type": "doc",
            "_search_score": 5.0,
            "source_updated_at": "2026-05-21T00:00:00",
        },
        {
            "entity_id": "filtered",
            "entity_type": "meeting",
            "_search_score": 9.0,
            "source_updated_at": "2026-05-22T00:00:00",
        },
    ]

    result = filter_and_sort_keyword_search_rows(rows, request)

    assert [row["entity_id"] for row in result] == ["high_new", "high_old", "low"]


def test_query_policy_sorts_by_requested_timestamp_field() -> None:
    rows = [
        {
            "entity_id": "new_low_score",
            "created_at": "2026-05-20T00:00:00",
            "source_updated_at": "2026-05-20T00:00:00",
            "_search_score": 1.0,
        },
        {
            "entity_id": "old_high_score",
            "created_at": "2026-05-10T00:00:00",
            "source_updated_at": "2026-05-10T00:00:00",
            "_search_score": 9.0,
        },
    ]

    updated_asc = sort_keyword_search_rows(
        rows,
        _request(sort={"field": "updated_at", "direction": "asc"}),
    )
    created_desc = sort_keyword_search_rows(
        rows,
        _request(sort={"field": "created_at", "direction": "desc"}),
    )

    assert [row["entity_id"] for row in updated_asc] == ["old_high_score", "new_low_score"]
    assert [row["entity_id"] for row in created_desc] == ["new_low_score", "old_high_score"]


def test_query_policy_accepts_extension_filter_and_sort_vocabulary() -> None:
    request = _request(
        entity_types=["plugin_record"],
        people={"role": "reviewer", "user_ids": ["user_1"]},
        date_filters=[
            {
                "field": "reviewed_at",
                "from": "2026-05-01T00:00:00",
                "to": "2026-05-31T00:00:00",
            }
        ],
        sort={"field": "reviewed_at", "direction": "asc"},
    )
    rows = [
        {
            "entity_id": "later",
            "entity_type": "plugin_record",
            "people": [{"role": "reviewer", "user_id": "user_1"}],
            "date_markers": {"reviewed_at": "2026-05-20T00:00:00"},
            "_search_score": 1.0,
        },
        {
            "entity_id": "earlier",
            "entity_type": "plugin_record",
            "people": [{"role": "reviewer", "user_id": "user_1"}],
            "date_markers": {"reviewed_at": "2026-05-10T00:00:00"},
            "_search_score": 1.0,
        },
        {
            "entity_id": "wrong_role",
            "entity_type": "plugin_record",
            "people": [{"role": "owner", "user_id": "user_1"}],
            "date_markers": {"reviewed_at": "2026-05-11T00:00:00"},
            "_search_score": 10.0,
        },
    ]

    body = build_keyword_search_opensearch_body(
        build_keyword_search_query(
            acl_filter=_acl_filter(
                KeywordAclBranch(
                    entity_type="plugin_record",
                    clauses=(keyword_acl_clause("visibility", "company"),),
                )
            ),
            request=request,
        )
    )
    result = filter_and_sort_keyword_search_rows(rows, request)

    assert body["sort"] == [
        {"date_markers.reviewed_at": {"order": "asc", "unmapped_type": "date"}},
        {"_score": {"order": "desc"}},
    ]
    assert [row["entity_id"] for row in result] == ["earlier", "later"]


def test_opensearch_response_projection_returns_backend_neutral_hits() -> None:
    result = parse_keyword_search_opensearch_response(
        {
            "hits": {
                "hits": [
                    {
                        "_score": 1.5,
                        "_source": {"entity_id": "doc-1"},
                        "sort": [1.5, "2026-05-20T00:00:00"],
                    }
                ]
            }
        }
    )

    assert isinstance(result, KeywordSearchResult)
    assert result.hits[0].document == {"entity_id": "doc-1"}
    assert result.hits[0].score == 1.5
    assert result.hits[0].sort_values == (1.5, "2026-05-20T00:00:00")


def test_search_access_filter_skips_unregistered_entity_rows() -> None:
    class _Policy:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def can_read_resource(self, resource_type: str, resource_id: str) -> bool:
            self.calls.append((resource_type, resource_id))
            return resource_id == "doc-1"

    policy = _Policy()
    rows = [
        {"entity_type": "plugin_typo", "entity_id": "record-1"},
        {"entity_type": "doc", "entity_id": "doc-2"},
        {"entity_type": "doc", "entity_id": "doc-1"},
    ]

    result = _filter_accessible_search_rows(
        rows,
        policy,
        allowed_entity_types=frozenset({"doc"}),
    )

    assert result == [{"entity_type": "doc", "entity_id": "doc-1"}]
    assert policy.calls == [("docs_native_doc", "doc-2"), ("docs_native_doc", "doc-1")]


def test_partition_authorized_search_ignores_stale_workspace_payload() -> None:
    partition_id = "11111111-1111-1111-1111-111111111111"

    class _Policy:
        def authorize_many_resources(self, resources):
            return set(resources)

    stale_workspace_row = {
        "retrieval_partition_id": partition_id,
        "entity_type": "doc",
        "entity_id": "doc-1",
    }
    wrong_partition_row = {
        **stale_workspace_row,
        "retrieval_partition_id": "22222222-2222-2222-2222-222222222222",
        "entity_id": "doc-2",
    }

    result = _filter_accessible_search_rows(
        [stale_workspace_row, wrong_partition_row],
        _Policy(),
        allowed_entity_types=frozenset({"doc"}),
        authorized_partition_ids=(partition_id,),
    )

    assert result == [stale_workspace_row]


def test_keyword_acl_refill_uses_pit_and_search_after_until_authorized_hit() -> None:
    class _Client:
        def __init__(self) -> None:
            self.queries = []
            self.closed: list[str] = []

        def open_point_in_time(self, *, keep_alive: str = "1m") -> str:
            assert keep_alive == "1m"
            return "pit-1"

        def close_point_in_time(self, point_in_time_id: str) -> None:
            self.closed.append(point_in_time_id)

        def search(self, query):
            self.queries.append(query)
            resource_id = "denied" if not query.search_after else "allowed"
            cursor = (1,) if not query.search_after else (2,)
            return KeywordSearchResult(
                hits=(
                    KeywordSearchHit(
                        document={
                            "entity_type": "doc",
                            "entity_id": resource_id,
                        },
                        score=1.0,
                        sort_values=cursor,
                    ),
                )
            )

    class _Policy:
        def authorize_many_resources(self, resources):
            return {
                (resource_type, resource_id)
                for resource_type, resource_id in resources
                if resource_id == "allowed"
            }

    client = _Client()
    rows = _load_authorized_ranked_candidates(
        acl_filter=KeywordAclFilter(),
        policy=_Policy(),
        allowed_entity_types=frozenset({"doc"}),
        request=_request(limit=1),
        backend_timeout_seconds=5.0,
        client=client,
        text_operator="and",
        text_minimum_should_match=None,
        size=1,
    )

    assert [row["entity_id"] for row in rows] == ["allowed"]
    assert len(client.queries) == 2
    assert client.queries[0].point_in_time_id == "pit-1"
    assert client.queries[1].search_after == (1,)
    assert client.closed == ["pit-1"]
