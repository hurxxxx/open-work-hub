from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from open_alm_api.domains.search.backend_contracts import KeywordSearchQuery
from open_alm_api.domains.search.opensearch import (
    OpenSearchError,
    OpenSearchKeywordClient,
    _bulk_document_chunks,
)
from open_alm_api.domains.search.index_gateway import (
    build_partitioned_bulk_index_ndjson,
    keyword_acl_query_field_names,
    keyword_acl_query_properties,
    keyword_existing_index_mapping_properties,
    keyword_index_definition,
    keyword_partitioned_index_definition,
    keyword_search_index_alias,
    keyword_search_legacy_index_name,
    keyword_search_partitioned_index_alias,
    keyword_search_partitioned_index_name,
    keyword_search_versioned_index_name,
)
from open_alm_api.domains.retrieval.projection_identity import canonical_search_document_id


class _Response:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        status_code: int = 200,
    ) -> None:
        self._payload = payload or {}
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


class RecordingKeywordClient(OpenSearchKeywordClient):
    def __init__(self) -> None:
        super().__init__(base_url="http://opensearch", index_prefix="test")
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> _Response:
        self.calls.append((method, path, kwargs))
        if method == "HEAD":
            return _Response({})
        return _Response({"errors": False})

    def _bulk_index_documents(self, documents: list[dict[str, Any]]) -> None:
        self.calls.append(("BULK", self.index_name, {"documents": documents}))


class ScriptedKeywordClient(OpenSearchKeywordClient):
    def __init__(
        self,
        *,
        existing_indices: set[str],
        target_index_name: str | None = None,
        alias_payload: dict[str, Any] | None = None,
        document_count: int = 0,
        schema_version: int = 2,
    ) -> None:
        super().__init__(
            base_url="http://opensearch",
            index_prefix="test",
            target_index_name=target_index_name,
        )
        self.existing_indices = existing_indices
        self.alias_payload = alias_payload or {}
        self.document_count = document_count
        self.schema_version = schema_version
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> _Response:
        self.calls.append((method, path, kwargs))
        if method == "HEAD":
            index_name = path.removeprefix("/")
            return _Response(status_code=200 if index_name in self.existing_indices else 404)
        if method == "GET" and path.startswith("/_alias/"):
            return _Response(
                self.alias_payload,
                status_code=200 if self.alias_payload else 404,
            )
        if method == "GET" and path.endswith("/_mapping"):
            return _Response(
                {self.index_name: {"mappings": {"_meta": {"schema_version": self.schema_version}}}}
            )
        if method == "GET" and path.endswith("/_count"):
            return _Response({"count": self.document_count})
        if method == "GET" and path == f"/{self.index_name}":
            return _Response(
                {
                    self.index_name: {
                        "settings": {
                            "index": {
                                "uuid": "uuid-1",
                                "creation_date": "1",
                                "provided_name": self.index_name,
                                "number_of_shards": "1",
                            }
                        },
                        "mappings": {"_meta": {"schema_version": self.schema_version}},
                    }
                }
            )
        return _Response({"errors": False})


def _document(entity_id: str, body: str) -> dict:
    return {
        "workspace_id": "workspace-1",
        "entity_type": "plugin_chunk",
        "entity_id": entity_id,
        "title": entity_id,
        "summary": "",
        "body": body,
    }


def _partitioned_document(
    entity_id: str,
    *,
    workspace_id: str = "workspace-1",
    partition_id: str = "a3b6638a-7547-45f8-81f2-973bfa6080d6",
    projection_version: int = 7,
) -> dict[str, Any]:
    return {
        **_document(entity_id, "heater"),
        "workspace_id": workspace_id,
        "resource_type": "file_manager_file",
        "retrieval_partition_id": partition_id,
        "projection_version": projection_version,
    }


def test_acl_query_mapping_is_identical_for_new_and_existing_indexes() -> None:
    acl_properties = keyword_acl_query_properties()
    new_index_properties = keyword_index_definition()["mappings"]["properties"]
    existing_index_properties = keyword_existing_index_mapping_properties()

    assert keyword_acl_query_field_names() == frozenset(acl_properties)
    assert {
        field: new_index_properties[field] for field in keyword_acl_query_field_names()
    } == acl_properties
    assert {
        field: existing_index_properties[field] for field in keyword_acl_query_field_names()
    } == acl_properties


def test_keyword_index_uses_explicit_bm25_nori_and_lower_boost_subfields() -> None:
    definition = keyword_index_definition()
    settings = definition["settings"]
    mappings = definition["mappings"]

    assert settings["number_of_replicas"] == 0
    assert settings["similarity"]["keyword_bm25"] == {
        "type": "BM25",
        "k1": 1.2,
        "b": 0.75,
    }
    assert settings["analysis"]["tokenizer"]["korean_nori_tokenizer"] == {
        "type": "nori_tokenizer",
        "decompound_mode": "mixed",
        "discard_punctuation": True,
    }
    assert mappings["_meta"]["schema_version"] == 2
    assert mappings["properties"]["body"] == {
        "type": "text",
        "analyzer": "korean_nori",
        "search_analyzer": "korean_nori",
        "similarity": "keyword_bm25",
        "fields": {
            "partial": {
                "type": "text",
                "analyzer": "korean_ngram_partial",
                "search_analyzer": "korean_ngram_partial",
                "similarity": "keyword_bm25",
            },
            "exact": {
                "type": "keyword",
                "normalizer": "normalized_keyword",
                "ignore_above": 2048,
            },
        },
    }


def test_runtime_client_attaches_alias_to_legacy_v1_without_creating_empty_v2() -> None:
    legacy_index = keyword_search_legacy_index_name("test")
    client = ScriptedKeywordClient(existing_indices={legacy_index})

    client.ensure_index()

    assert (
        "POST",
        "/_aliases",
        {
            "json": {
                "actions": [
                    {
                        "add": {
                            "index": legacy_index,
                            "alias": keyword_search_index_alias("test"),
                            "is_write_index": True,
                        }
                    }
                ]
            }
        },
    ) in client.calls
    assert not any(
        method == "PUT" and path == f"/{client.versioned_index_name}"
        for method, path, _ in client.calls
    )


def test_index_exists_attaches_runtime_alias_to_legacy_index() -> None:
    legacy_index = keyword_search_legacy_index_name("test")
    client = ScriptedKeywordClient(existing_indices={legacy_index})

    assert client.index_exists()

    assert any(
        method == "POST"
        and path == "/_aliases"
        and kwargs["json"]["actions"][0]["add"]["index"] == legacy_index
        for method, path, kwargs in client.calls
    )


def test_new_install_creates_v2_bootstrap_with_write_alias() -> None:
    client = ScriptedKeywordClient(existing_indices=set())

    client.ensure_index()

    create_call = next(
        call for call in client.calls if call[:2] == ("PUT", f"/{client.versioned_index_name}")
    )
    assert create_call[2]["json"]["aliases"] == {
        keyword_search_index_alias("test"): {"is_write_index": True}
    }


def test_versioned_index_activation_atomically_moves_alias_and_preserves_old_generation() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    previous = keyword_search_versioned_index_name("test", generation="release_20260720")
    client_alias = keyword_search_index_alias("test")
    client = ScriptedKeywordClient(
        existing_indices={target, previous},
        target_index_name=target,
        alias_payload={previous: {"aliases": {client_alias: {}}}},
    )

    client.activate_versioned_index(writes_quiesced=True)

    alias_call = client.calls[-1]
    assert alias_call == (
        "POST",
        "/_aliases",
        {
            "json": {
                "actions": [
                    {"remove": {"index": previous, "alias": client_alias}},
                    {
                        "add": {
                            "index": target,
                            "alias": client_alias,
                            "is_write_index": True,
                        }
                    },
                ]
            }
        },
    )
    assert not any(method == "DELETE" for method, _, _ in client.calls)


def test_versioned_index_activation_rejects_missing_generation() -> None:
    target = keyword_search_versioned_index_name("test", generation="missing")
    client = ScriptedKeywordClient(existing_indices=set(), target_index_name=target)

    with pytest.raises(OpenSearchError, match="does not exist"):
        client.activate_versioned_index(writes_quiesced=True)


def test_versioned_index_activation_fails_closed_without_quiesce_confirmation() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    client = ScriptedKeywordClient(existing_indices={target}, target_index_name=target)

    with pytest.raises(OpenSearchError, match="writers are quiesced"):
        client.activate_versioned_index()

    assert client.calls == []


def test_versioned_index_activation_validates_schema_and_document_count() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    client = ScriptedKeywordClient(
        existing_indices={target},
        target_index_name=target,
        document_count=4,
    )

    with pytest.raises(OpenSearchError, match="document count mismatch"):
        client.activate_versioned_index(
            writes_quiesced=True,
            expected_document_count=5,
        )

    assert not any(path == "/_aliases" for _, path, _ in client.calls)


def test_versioned_index_activation_rejects_content_changed_after_evaluation() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    client = ScriptedKeywordClient(existing_indices={target}, target_index_name=target)
    client.content_sha256 = lambda: "a" * 64  # type: ignore[method-assign]

    with pytest.raises(OpenSearchError, match="content changed"):
        client.activate_versioned_index(
            writes_quiesced=True,
            expected_content_sha256="b" * 64,
        )

    assert not any(path == "/_aliases" for _, path, _ in client.calls)


def test_versioned_index_activation_rejects_recreated_physical_index() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    client = ScriptedKeywordClient(existing_indices={target}, target_index_name=target)

    with pytest.raises(OpenSearchError, match="identity changed"):
        client.activate_versioned_index(
            writes_quiesced=True,
            expected_index_uuid="previous-uuid",
        )

    assert not any(path == "/_aliases" for _, path, _ in client.calls)


def test_quality_identity_excludes_transient_index_identity_settings() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    first = ScriptedKeywordClient(existing_indices={target}, target_index_name=target)
    second = ScriptedKeywordClient(existing_indices={target}, target_index_name=target)

    first_uuid, first_digest = first.quality_identity()
    second_uuid, second_digest = second.quality_identity()

    assert first_uuid == second_uuid == "uuid-1"
    assert first_digest == second_digest
    assert len(first_digest) == 64


def test_content_sha256_hashes_canonical_documents_in_stable_order() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    client = ScriptedKeywordClient(existing_indices={target}, target_index_name=target)
    hits = [
        {
            "_id": "workspace-1:file:file-1",
            "_source": {
                "workspace_id": "workspace-1",
                "entity_type": "file",
                "entity_id": "file-1",
                "title": "히터 사양",
            },
            "sort": ["workspace-1", "file", "file-1"],
        }
    ]
    original_request = client._request

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        if method == "POST" and path.endswith("/_search"):
            return _Response({"hits": {"hits": hits}})
        return original_request(method, path, **kwargs)

    client._request = request  # type: ignore[method-assign]
    canonical = json.dumps(
        {"_id": hits[0]["_id"], "_source": hits[0]["_source"]},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()

    assert client.content_sha256() == hashlib.sha256(canonical + b"\n").hexdigest()


def test_versioned_index_activation_rejects_incompatible_schema() -> None:
    target = keyword_search_versioned_index_name("test", generation="release_20260721")
    client = ScriptedKeywordClient(
        existing_indices={target},
        target_index_name=target,
        schema_version=1,
    )

    with pytest.raises(OpenSearchError, match="incompatible schema"):
        client.activate_versioned_index(writes_quiesced=True)

    assert not any(path == "/_aliases" for _, path, _ in client.calls)


def test_legacy_v1_rollback_atomically_moves_alias_after_count_check() -> None:
    legacy = keyword_search_legacy_index_name("test")
    current = keyword_search_versioned_index_name("test", generation="release_20260721")
    alias = keyword_search_index_alias("test")
    client = ScriptedKeywordClient(
        existing_indices={legacy, current},
        alias_payload={current: {"aliases": {alias: {}}}},
        document_count=4,
    )

    client.rollback_to_legacy_index(
        writes_quiesced=True,
        expected_document_count=4,
    )

    assert client.calls[-1] == (
        "POST",
        "/_aliases",
        {
            "json": {
                "actions": [
                    {"remove": {"index": current, "alias": alias}},
                    {
                        "add": {
                            "index": legacy,
                            "alias": alias,
                            "is_write_index": True,
                        }
                    },
                ]
            }
        },
    )


def test_legacy_v1_rollback_rejects_document_count_mismatch() -> None:
    legacy = keyword_search_legacy_index_name("test")
    client = ScriptedKeywordClient(
        existing_indices={legacy},
        document_count=3,
    )

    with pytest.raises(OpenSearchError, match="document count mismatch"):
        client.rollback_to_legacy_index(
            writes_quiesced=True,
            expected_document_count=4,
        )

    assert not any(path == "/_aliases" for _, path, _ in client.calls)


def test_versioned_rebuild_search_targets_named_generation_not_alias() -> None:
    client = RecordingKeywordClient().for_versioned_rebuild(generation="release_20260721")
    calls: list[tuple[str, str]] = []
    client._request = lambda method, path, **kwargs: (  # type: ignore[method-assign]
        calls.append((method, path)) or _Response({"hits": {"hits": []}})
    )

    client.search(KeywordSearchQuery(workspace_id="workspace-1", text="heater"))

    assert calls == [
        (
            "POST",
            "/test_keyword_search_documents_v2_release_20260721/_search",
        )
    ]


def test_existing_index_mapping_update_includes_every_acl_query_field() -> None:
    client = RecordingKeywordClient()

    client.ensure_index()

    mapping_call = next(
        call for call in client.calls if call[:2] == ("PUT", f"/{client.index_name}/_mapping")
    )
    assert keyword_acl_query_field_names() <= mapping_call[2]["json"]["properties"].keys()


def test_workspace_document_count_can_be_scoped_to_entity_types() -> None:
    client = RecordingKeywordClient()

    assert (
        client.count_workspace_documents(
            workspace_id="workspace-1",
            entity_types=("doc", "pms_task"),
        )
        == 0
    )

    count_call = client.calls[-1]
    assert count_call[:2] == ("POST", f"/{client.index_name}/_count")
    assert count_call[2]["json"] == {
        "query": {
            "bool": {
                "filter": [
                    {"term": {"workspace_id": "workspace-1"}},
                    {"terms": {"entity_type": ["doc", "pms_task"]}},
                ]
            }
        }
    }


def test_candidate_search_forwards_request_timeout() -> None:
    client = RecordingKeywordClient()

    client.search(
        KeywordSearchQuery(
            workspace_id="workspace-1",
            request_timeout_seconds=5.0,
        )
    )

    assert client.calls[-1][2]["request_timeout_seconds"] == 5.0


def test_partitioned_candidate_search_requires_explicit_partition_terms() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    calls: list[tuple[str, str, dict[str, Any]]] = []
    client._request = lambda method, path, **kwargs: (  # type: ignore[method-assign]
        calls.append((method, path, kwargs)) or _Response({"hits": {"hits": []}})
    )

    client.search(
        KeywordSearchQuery(
            workspace_id="diagnostic-workspace",
            retrieval_partition_ids=("a3b6638a-7547-45f8-81f2-973bfa6080d6",),
            text="heater",
        )
    )

    filters = calls[-1][2]["json"]["query"]["bool"]["filter"]
    assert filters[0] == {
        "terms": {"retrieval_partition_id": ["a3b6638a-7547-45f8-81f2-973bfa6080d6"]}
    }
    assert not any("workspace_id" in str(item) for item in filters)


def test_partitioned_candidate_search_rejects_missing_partition_terms() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    client._request = lambda *args, **kwargs: pytest.fail(  # type: ignore[method-assign]
        "partition validation must happen before an OpenSearch request"
    )

    with pytest.raises(OpenSearchError, match="require retrieval_partition_ids"):
        client.search(KeywordSearchQuery(workspace_id="diagnostic-workspace", text="heater"))


def test_legacy_candidate_search_rejects_partition_terms() -> None:
    client = RecordingKeywordClient()

    with pytest.raises(OpenSearchError, match="partitioned v3 generation"):
        client.search(
            KeywordSearchQuery(
                workspace_id="diagnostic-workspace",
                retrieval_partition_ids=("a3b6638a-7547-45f8-81f2-973bfa6080d6",),
                text="heater",
            )
        )

    assert client.calls == []


def test_partitioned_candidate_search_rejects_empty_partition_scope() -> None:
    with pytest.raises(ValueError, match="retrieval_partition_ids"):
        KeywordSearchQuery(workspace_id="diagnostic-workspace", retrieval_partition_ids=())


def test_opensearch_pit_search_uses_global_endpoint_and_stable_tiebreaker() -> None:
    client = RecordingKeywordClient()
    client.search(
        KeywordSearchQuery(
            workspace_id="workspace-1",
            text="heater",
            point_in_time_id="pit-1",
            search_after=(1.5, "2026-07-22", 42),
        )
    )

    method, path, kwargs = client.calls[-1]
    assert (method, path) == ("POST", "/_search")
    assert kwargs["json"]["pit"] == {"id": "pit-1", "keep_alive": "1m"}
    assert kwargs["json"]["sort"][-1] == {"_shard_doc": {"order": "asc"}}
    assert kwargs["json"]["search_after"] == [1.5, "2026-07-22", 42]


def test_opensearch_opens_and_closes_point_in_time() -> None:
    client = RecordingKeywordClient()

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        client.calls.append((method, path, kwargs))
        if path.endswith("/point_in_time") and method == "POST":
            return _Response({"pit_id": "pit-1"})
        return _Response({"succeeded": True})

    client._request = request  # type: ignore[method-assign]

    assert client.open_point_in_time(keep_alive="2m") == "pit-1"
    client.close_point_in_time("pit-1")

    assert client.calls == [
        (
            "POST",
            f"/{client.index_name}/_search/point_in_time",
            {"params": {"keep_alive": "2m"}},
        ),
        (
            "DELETE",
            "/_search/point_in_time",
            {"json": {"pit_id": ["pit-1"]}},
        ),
    ]


def test_bulk_document_chunks_split_by_payload_size() -> None:
    chunks = _bulk_document_chunks(
        [
            _document("one", "x" * 100),
            _document("two", "x" * 100),
            _document("three", "x" * 100),
        ],
        max_bytes=360,
        max_documents=100,
    )

    assert [[item["entity_id"] for item in chunk] for chunk in chunks] == [
        ["one"],
        ["two"],
        ["three"],
    ]


def test_bulk_document_chunks_split_by_document_count() -> None:
    chunks = _bulk_document_chunks(
        [
            _document("one", "x"),
            _document("two", "x"),
            _document("three", "x"),
        ],
        max_bytes=100_000,
        max_documents=2,
    )

    assert [[item["entity_id"] for item in chunk] for chunk in chunks] == [
        ["one", "two"],
        ["three"],
    ]


def test_rebuild_workspace_indexes_documents_before_deleting_stale_documents() -> None:
    client = RecordingKeywordClient()

    client.rebuild_workspace(
        workspace_id="workspace-1",
        documents=[_document("one", "body")],
    )

    call_names = [(method, path) for method, path, _ in client.calls]
    bulk_index = call_names.index(("BULK", client.index_name))
    stale_delete = call_names.index(("POST", f"/{client.index_name}/_delete_by_query"))
    assert bulk_index < stale_delete

    delete_payload = client.calls[stale_delete][2]["json"]
    assert delete_payload["query"]["bool"]["filter"] == [{"term": {"workspace_id": "workspace-1"}}]
    assert delete_payload["query"]["bool"]["must_not"] == [
        {"ids": {"values": ["workspace-1:plugin_chunk:one"]}}
    ]


def test_legacy_live_write_keeps_scope_bound_id_without_external_version() -> None:
    client = RecordingKeywordClient()
    document = _document("one", "body")

    client.upsert_document(document)

    method, path, kwargs = client.calls[-1]
    assert (method, path) == (
        "PUT",
        f"/{client.index_name}/_doc/workspace-1:plugin_chunk:one",
    )
    assert kwargs["params"] == {"refresh": "true"}


def test_partitioned_v3_requires_explicit_generated_physical_index_binding() -> None:
    physical_index = keyword_search_partitioned_index_name(
        "test",
        generation="partition_20260722",
    )

    with pytest.raises(OpenSearchError, match="explicit physical index binding"):
        OpenSearchKeywordClient(
            base_url="http://opensearch",
            index_prefix="test",
            target_index_name=physical_index,
            target_schema_version=3,
        )

    live_alias = keyword_search_index_alias("test")
    with pytest.raises(OpenSearchError, match="generated physical v3 index"):
        OpenSearchKeywordClient(
            base_url="http://opensearch",
            index_prefix="test",
            target_index_name=live_alias,
            target_schema_version=3,
            partitioned_generation_index=live_alias,
        )

    with pytest.raises(OpenSearchError, match="must match its physical index binding"):
        OpenSearchKeywordClient(
            base_url="http://opensearch",
            index_prefix="test",
            target_index_name=keyword_search_legacy_index_name("test"),
            target_schema_version=3,
            partitioned_generation_index=physical_index,
        )


def test_partitioned_v3_operations_reject_a_changed_live_index_target() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    document = _partitioned_document("file-1")
    client.index_name = client.index_alias
    client._request = lambda *args, **kwargs: pytest.fail(  # type: ignore[method-assign]
        "index binding validation must happen before an OpenSearch request"
    )

    operations = (
        client.ensure_index,
        lambda: client.upsert_partitioned_document(document),
        lambda: client.delete_partitioned_document(
            resource_type="file_manager_file",
            resource_id="file-1",
            projection_version=8,
        ),
        lambda: client.bulk_index_partitioned_documents([document]),
        lambda: client.search(
            KeywordSearchQuery(
                workspace_id="workspace-1",
                retrieval_partition_ids=("a3b6638a-7547-45f8-81f2-973bfa6080d6",),
            )
        ),
        client.index_exists,
        client.open_point_in_time,
    )

    for operation in operations:
        with pytest.raises(OpenSearchError, match="bound to physical index"):
            operation()


def test_partitioned_v3_rejects_legacy_mutation_apis() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    client._request = lambda *args, **kwargs: pytest.fail(  # type: ignore[method-assign]
        "mutation API validation must happen before an OpenSearch request"
    )

    operations = (
        lambda: client.rebuild_workspace(
            workspace_id="workspace-1",
            documents=[_document("one", "body")],
        ),
        lambda: client.upsert_document(_document("one", "body")),
        lambda: client.delete_document(
            workspace_id="workspace-1",
            entity_type="plugin_chunk",
            entity_id="one",
        ),
        lambda: client.count_workspace_documents(workspace_id="workspace-1"),
    )

    for operation in operations:
        with pytest.raises(OpenSearchError, match="Legacy keyword mutation APIs"):
            operation()


@pytest.mark.parametrize(
    "missing_field",
    [
        "resource_type",
        "entity_id",
        "retrieval_partition_id",
        "projection_version",
    ],
)
def test_partitioned_writes_reject_missing_projection_fence_before_index_access(
    missing_field: str,
) -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    document = _partitioned_document("file-1")
    document.pop(missing_field)
    client.ensure_index = lambda: pytest.fail(  # type: ignore[method-assign]
        "projection validation must happen before index access"
    )

    with pytest.raises(ValueError, match="Partitioned keyword"):
        client.upsert_partitioned_document(document)

    with pytest.raises(ValueError, match="Partitioned keyword"):
        client.bulk_index_partitioned_documents([document])


def test_partitioned_delete_rejects_missing_projection_version_before_index_access() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    client.ensure_index = lambda: pytest.fail(  # type: ignore[method-assign]
        "projection validation must happen before index access"
    )

    with pytest.raises(ValueError, match="integer projection_version"):
        client.delete_partitioned_document(
            resource_type="file_manager_file",
            resource_id="file-1",
            projection_version=None,  # type: ignore[arg-type]
        )


def test_existing_partitioned_physical_index_must_have_v3_schema_before_write() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        calls.append((method, path, kwargs))
        if method == "HEAD":
            return _Response(status_code=200)
        if method == "GET" and path.endswith("/_mapping"):
            return _Response({client.index_name: {"mappings": {"_meta": {"schema_version": 2}}}})
        return _Response({"count": 0})

    client._request = request  # type: ignore[method-assign]

    with pytest.raises(OpenSearchError, match="incompatible schema"):
        client.upsert_partitioned_document(_partitioned_document("file-1"))

    assert not any("/_doc/" in path for _, path, _ in calls)


def test_partitioned_v3_generation_is_isolated_and_has_required_fields() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        calls.append((method, path, kwargs))
        return _Response({}, status_code=404 if method == "HEAD" else 200)

    client._request = request  # type: ignore[method-assign]

    client.ensure_index()

    expected_name = keyword_search_partitioned_index_name("test", generation="partition_20260722")
    assert client.index_name == expected_name
    assert client.index_alias == keyword_search_partitioned_index_alias("test")
    assert client.index_alias != keyword_search_index_alias("test")
    create = next(call for call in calls if call[:2] == ("PUT", f"/{expected_name}"))
    definition = create[2]["json"]
    assert definition == keyword_partitioned_index_definition()
    assert definition["mappings"]["_meta"]["schema_version"] == 3
    assert {
        "resource_type",
        "retrieval_partition_id",
        "projection_version",
    } <= set(definition["mappings"]["properties"])


def test_partitioned_v3_activation_never_moves_the_legacy_shared_alias() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        calls.append((method, path, kwargs))
        if method == "HEAD":
            return _Response(status_code=200)
        if method == "GET" and path.endswith("/_mapping"):
            return _Response({client.index_name: {"mappings": {"_meta": {"schema_version": 3}}}})
        if method == "GET" and path.endswith("/_count"):
            return _Response({"count": 0})
        if method == "GET" and path.startswith("/_alias/"):
            return _Response(status_code=404)
        return _Response({"errors": False})

    client._request = request  # type: ignore[method-assign]

    client.activate_partitioned_index(
        writes_quiesced=True,
        expected_document_count=0,
    )

    dedicated_alias = keyword_search_partitioned_index_alias("test")
    assert ("GET", f"/_alias/{dedicated_alias}") in [(method, path) for method, path, _ in calls]
    assert not any(path == f"/_alias/{keyword_search_index_alias('test')}" for _, path, _ in calls)
    alias_call = next(call for call in calls if call[:2] == ("POST", "/_aliases"))
    assert alias_call[2]["json"]["actions"] == [
        {
            "add": {
                "index": client.index_name,
                "alias": dedicated_alias,
                "is_write_index": True,
            }
        }
    ]


def test_partitioned_physical_index_exposes_validated_document_count() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        calls.append((method, path, kwargs))
        if method == "HEAD":
            return _Response(status_code=200)
        return _Response({"count": 17})

    client._request = request  # type: ignore[method-assign]

    assert client.count_documents() == 17
    assert [call[:2] for call in calls] == [
        ("HEAD", f"/{client.index_name}"),
        ("GET", f"/{client.index_name}/_count"),
    ]


def test_partitioned_physical_index_supports_explicit_validation_refresh() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    calls: list[tuple[str, str, dict[str, Any]]] = []
    client._request = lambda method, path, **kwargs: (  # type: ignore[method-assign]
        calls.append((method, path, kwargs)) or _Response({})
    )

    client.refresh_partitioned_index()

    assert [call[:2] for call in calls] == [("POST", f"/{client.index_name}/_refresh")]


def test_partitioned_write_uses_scope_neutral_id_and_strict_external_version() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    calls: list[tuple[str, str, dict[str, Any]]] = []
    client.ensure_index = lambda: None  # type: ignore[method-assign]
    client._request = lambda method, path, **kwargs: (  # type: ignore[method-assign]
        calls.append((method, path, kwargs)) or _Response({})
    )

    first = _partitioned_document("file-1")
    moved = _partitioned_document(
        "file-1",
        workspace_id="workspace-2",
        partition_id="98d869c5-370a-40ab-8eca-56e9ce2bb810",
        projection_version=8,
    )

    assert client.upsert_partitioned_document(first) == "upserted"
    assert client.upsert_partitioned_document(moved) == "upserted"

    expected_id = canonical_search_document_id(
        resource_type="file_manager_file",
        resource_id="file-1",
    )
    writes = [call for call in calls if call[0] == "PUT"]
    assert [path for _, path, _ in writes] == [
        f"/{client.index_name}/_doc/{expected_id}",
        f"/{client.index_name}/_doc/{expected_id}",
    ]
    assert writes[0][2]["params"] == {
        "refresh": "false",
        "version": 7,
        "version_type": "external",
    }
    assert writes[1][2]["params"]["version"] == 8


def test_partitioned_bulk_actions_use_canonical_id_and_external_version() -> None:
    document = _partitioned_document("file-1")

    payload = build_partitioned_bulk_index_ndjson(
        index_name="partitioned-v3",
        documents=[document],
    )

    action, source, empty = payload.split("\n")
    assert empty == ""
    decoded_action = json.loads(action)["index"]
    assert decoded_action == {
        "_index": "partitioned-v3",
        "_id": canonical_search_document_id(
            resource_type="file_manager_file",
            resource_id="file-1",
        ),
        "version": 7,
        "version_type": "external",
    }
    assert json.loads(source) == document


def test_partitioned_external_version_retry_is_idempotent() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    client.ensure_index = lambda: None  # type: ignore[method-assign]

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        del path, kwargs
        if method == "PUT":
            return _Response({}, status_code=409)
        assert method == "GET"
        return _Response({"_version": 7})

    client._request = request  # type: ignore[method-assign]

    assert client.upsert_partitioned_document(_partitioned_document("file-1")) == "unchanged"


def test_partitioned_upsert_after_newer_tombstone_is_superseded() -> None:
    client = RecordingKeywordClient().for_partitioned_rebuild(generation="partition_20260722")
    client.ensure_index = lambda: None  # type: ignore[method-assign]

    def request(method: str, path: str, **kwargs: Any) -> _Response:
        del path, kwargs
        if method == "PUT":
            return _Response({}, status_code=409)
        assert method == "GET"
        # OpenSearch retains the higher external version in its delete
        # tombstone, but a realtime GET only reports that the document is gone.
        return _Response({"found": False}, status_code=404)

    client._request = request  # type: ignore[method-assign]

    assert client.upsert_partitioned_document(_partitioned_document("file-1")) == "superseded"
