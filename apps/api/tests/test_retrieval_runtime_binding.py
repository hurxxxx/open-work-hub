from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from open_work_hub_api.domains.rag.contracts import RagQueryRequest
from open_work_hub_api.domains.rag.providers import RagProviderBundle
from open_work_hub_api.domains.rag.providers.base import RagProviderConfigurationError
from open_work_hub_api.domains.rag.providers.fake import FakeEmbeddingClient
from open_work_hub_api.domains.rag.providers.qdrant import QdrantVectorIndexClient
from open_work_hub_api.domains.rag.runtime import (
    PARTITIONED_RAG_GENERATION_SCHEMA_VERSION,
    build_partitioned_rag_projection_service,
    build_partitioned_retrieval_candidate_query_service,
    resolve_default_collection_name,
    resolve_partitioned_rag_collection_alias,
    resolve_partitioned_rag_collection_name,
)
from open_work_hub_api.domains.retrieval import runtime_binding
from open_work_hub_api.domains.retrieval.models import RetrievalProjectionGeneration
from open_work_hub_api.domains.retrieval.runtime_binding import (
    PartitionedRetrievalRuntimeUnavailable,
    resolve_active_partitioned_generation_pair,
    resolve_partitioned_files_query_runtime,
)
from open_work_hub_api.domains.search.backend_contracts import KeywordSearchQuery
from open_work_hub_api.domains.search.backend_factory import (
    build_partitioned_keyword_search_client,
)
from open_work_hub_api.domains.search.index_gateway import (
    RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
    keyword_search_index_alias,
    keyword_search_partitioned_index_alias,
    keyword_search_partitioned_index_name,
)
from open_work_hub_api.domains.search.opensearch import OpenSearchError


_COHORT = "release_20260723"


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "keyword_search_backend": "opensearch",
        "opensearch_url": "http://search.internal:9200/",
        "opensearch_index_prefix": "open-work-hub-test",
        "rag_vector_index_provider": "qdrant",
        "rag_qdrant_collection_prefix": "open-work-hub-test-rag",
        "rag_embedding_provider": "fake",
        "rag_local_embedding_model": "unused-for-fake",
        "rag_query_timeout_ms": 5_000,
        "rag_rerank_candidate_k": 80,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _generation(
    *,
    backend: str,
    settings: SimpleNamespace,
    cohort: str = _COHORT,
    schema_version: int | None = None,
    validation_state: str = "passed",
    alias_name: str | None = None,
    physical_name: str | None = None,
) -> RetrievalProjectionGeneration:
    if backend == "opensearch":
        resolved_schema_version = (
            RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION if schema_version is None else schema_version
        )
        resolved_alias_name = alias_name or keyword_search_partitioned_index_alias(
            settings.opensearch_index_prefix
        )
        resolved_physical_name = physical_name or keyword_search_partitioned_index_name(
            settings.opensearch_index_prefix,
            generation=cohort,
        )
    else:
        resolved_schema_version = (
            PARTITIONED_RAG_GENERATION_SCHEMA_VERSION if schema_version is None else schema_version
        )
        resolved_alias_name = alias_name or resolve_partitioned_rag_collection_alias(settings)
        resolved_physical_name = physical_name or resolve_partitioned_rag_collection_name(
            settings,
            generation=cohort,
        )
    return RetrievalProjectionGeneration(
        id=f"{backend}-{cohort}-{resolved_schema_version}",
        backend=backend,
        generation_key=cohort,
        physical_name=resolved_physical_name,
        alias_name=resolved_alias_name,
        schema_version=resolved_schema_version,
        state="active",
        baseline_event_sequence=7,
        replay_event_sequence=7,
        validation_state=validation_state,
        validation_details={
            "release_cohort": cohort,
            "included_resource_types": ["file_manager_file"],
        },
        validated_at=datetime(2026, 7, 23, 1, 0, 0),
    )


class _ScalarRows:
    def __init__(self, rows: list[RetrievalProjectionGeneration]) -> None:
        self._rows = rows

    def all(self) -> list[RetrievalProjectionGeneration]:
        return list(self._rows)


class _GenerationSession:
    def __init__(self, rows: list[RetrievalProjectionGeneration]) -> None:
        self._rows = rows
        self.statements: list[object] = []

    def scalars(self, statement: object) -> _ScalarRows:
        self.statements.append(statement)
        return _ScalarRows(self._rows)


def test_partitioned_runtime_resolves_one_validated_shared_cohort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    opensearch = _generation(backend="opensearch", settings=settings)
    qdrant = _generation(backend="qdrant", settings=settings)
    db = _GenerationSession([qdrant, opensearch])
    keyword_client = object()
    rag_query_service = object()
    built: dict[str, Any] = {}

    def _build_keyword(resolved_settings, *, physical_index_name: str):
        built["keyword_settings"] = resolved_settings
        built["physical_index_name"] = physical_index_name
        return keyword_client

    def _build_rag(resolved_settings, *, collection: str, providers=None):
        built["rag_settings"] = resolved_settings
        built["collection"] = collection
        built["providers"] = providers
        return rag_query_service

    monkeypatch.setattr(runtime_binding, "build_partitioned_keyword_search_client", _build_keyword)
    monkeypatch.setattr(
        runtime_binding,
        "build_partitioned_retrieval_candidate_query_service",
        _build_rag,
    )
    provider_bundle = object()

    binding = resolve_partitioned_files_query_runtime(
        db,  # type: ignore[arg-type]
        settings=settings,
        rag_providers=provider_bundle,  # type: ignore[arg-type]
    )

    assert binding.release_cohort == _COHORT
    assert binding.opensearch_generation_id == opensearch.id
    assert binding.qdrant_generation_id == qdrant.id
    assert binding.keyword_search_client is keyword_client
    assert binding.rag_query_service is rag_query_service
    assert binding.rag_collection == qdrant.physical_name
    assert built == {
        "keyword_settings": settings,
        "physical_index_name": opensearch.physical_name,
        "rag_settings": settings,
        "collection": qdrant.physical_name,
        "providers": provider_bundle,
    }
    assert len(db.statements) == 1


def test_partitioned_runtime_rejects_legacy_shared_aliases() -> None:
    settings = _settings()
    rows = [
        _generation(
            backend="opensearch",
            settings=settings,
            alias_name=keyword_search_index_alias(settings.opensearch_index_prefix),
        ),
        _generation(
            backend="qdrant",
            settings=settings,
            alias_name=resolve_default_collection_name(settings),
        ),
    ]

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_active_partitioned_generation_pair(
            _GenerationSession(rows),  # type: ignore[arg-type]
            settings=settings,
        )

    assert caught.value.reason == "alias_identity_mismatch"


def test_generation_pair_descriptor_does_not_construct_query_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    opensearch = _generation(backend="opensearch", settings=settings)
    qdrant = _generation(backend="qdrant", settings=settings)
    monkeypatch.setattr(
        runtime_binding,
        "build_partitioned_keyword_search_client",
        lambda *args, **kwargs: pytest.fail("descriptor built keyword query adapter"),
    )
    monkeypatch.setattr(
        runtime_binding,
        "build_partitioned_retrieval_candidate_query_service",
        lambda *args, **kwargs: pytest.fail("descriptor built RAG query adapter"),
    )

    pair = resolve_active_partitioned_generation_pair(
        _GenerationSession([qdrant, opensearch]),  # type: ignore[arg-type]
        settings=settings,
    )

    assert pair.release_cohort == _COHORT
    assert pair.opensearch_generation_id == opensearch.id
    assert pair.qdrant_generation_id == qdrant.id
    assert pair.opensearch_physical_name == opensearch.physical_name
    assert pair.qdrant_physical_name == qdrant.physical_name
    assert pair.opensearch_replay_event_sequence == 7
    assert pair.qdrant_replay_event_sequence == 7


def test_generation_pair_descriptor_rejects_divergent_files_validation_evidence() -> None:
    settings = _settings()
    opensearch = _generation(backend="opensearch", settings=settings)
    qdrant = _generation(backend="qdrant", settings=settings)
    qdrant.validation_details = {
        **dict(qdrant.validation_details or {}),
        "source": {"resource_count": 1},
    }

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_active_partitioned_generation_pair(
            _GenerationSession([opensearch, qdrant]),  # type: ignore[arg-type]
            settings=settings,
        )

    assert caught.value.reason == "validation_evidence_mismatch"


def test_generation_pair_descriptor_rejects_invalid_replay_checkpoint() -> None:
    settings = _settings()
    opensearch = _generation(backend="opensearch", settings=settings)
    qdrant = _generation(backend="qdrant", settings=settings)
    qdrant.replay_event_sequence = None  # type: ignore[assignment]

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_active_partitioned_generation_pair(
            _GenerationSession([opensearch, qdrant]),  # type: ignore[arg-type]
            settings=settings,
        )

    assert caught.value.reason == "generation_checkpoint_invalid"


def test_partitioned_runtime_reuses_the_cached_query_module_in_default_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    opensearch = _generation(backend="opensearch", settings=settings)
    qdrant = _generation(backend="qdrant", settings=settings)
    keyword_client = object()
    rag_query_service = object()
    requested_collections: list[str] = []
    monkeypatch.setattr(runtime_binding, "get_settings", lambda: settings)
    monkeypatch.setattr(
        runtime_binding,
        "build_partitioned_keyword_search_client",
        lambda *args, **kwargs: keyword_client,
    )

    def _get_cached_query_service(collection: str):
        requested_collections.append(collection)
        return rag_query_service

    monkeypatch.setattr(
        runtime_binding,
        "get_partitioned_retrieval_candidate_query_service",
        _get_cached_query_service,
    )

    binding = resolve_partitioned_files_query_runtime(
        _GenerationSession([opensearch, qdrant]),  # type: ignore[arg-type]
    )

    assert binding.keyword_search_client is keyword_client
    assert binding.rag_query_service is rag_query_service
    assert requested_collections == [qdrant.physical_name]


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ([], "missing_active_generation"),
        (["opensearch"], "missing_active_generation"),
        (["opensearch", "opensearch", "qdrant"], "multiple_active_generations"),
    ],
)
def test_partitioned_runtime_requires_exactly_one_active_generation_per_backend(
    rows: list[str],
    reason: str,
) -> None:
    settings = _settings()
    generations = [_generation(backend=backend, settings=settings) for backend in rows]

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_partitioned_files_query_runtime(
            _GenerationSession(generations),  # type: ignore[arg-type]
            settings=settings,
            rag_providers=object(),  # type: ignore[arg-type]
        )

    assert caught.value.reason == reason


@pytest.mark.parametrize(
    ("opensearch_overrides", "qdrant_overrides", "reason"),
    [
        ({"validation_state": "pending"}, {}, "generation_not_validated"),
        ({"schema_version": 2}, {}, "schema_version_mismatch"),
        ({}, {"schema_version": 2}, "schema_version_mismatch"),
        ({}, {"cohort": "release_other"}, "release_cohort_mismatch"),
        ({"alias_name": "wrong-keyword-alias"}, {}, "alias_identity_mismatch"),
        ({}, {"alias_name": "wrong-vector-alias"}, "alias_identity_mismatch"),
        (
            {"physical_name": "open-work-hub-test_keyword_search_documents_v3_release_other"},
            {},
            "physical_identity_mismatch",
        ),
    ],
)
def test_partitioned_runtime_fails_closed_on_validation_schema_or_identity_drift(
    opensearch_overrides: dict[str, object],
    qdrant_overrides: dict[str, object],
    reason: str,
) -> None:
    settings = _settings()
    rows = [
        _generation(backend="opensearch", settings=settings, **opensearch_overrides),
        _generation(backend="qdrant", settings=settings, **qdrant_overrides),
    ]

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_partitioned_files_query_runtime(
            _GenerationSession(rows),  # type: ignore[arg-type]
            settings=settings,
            rag_providers=object(),  # type: ignore[arg-type]
        )

    assert caught.value.reason == reason


def test_partitioned_runtime_wraps_adapter_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    rows = [
        _generation(backend="opensearch", settings=settings),
        _generation(backend="qdrant", settings=settings),
    ]
    monkeypatch.setattr(
        runtime_binding,
        "build_partitioned_keyword_search_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("wrong backend")),
    )

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_partitioned_files_query_runtime(
            _GenerationSession(rows),  # type: ignore[arg-type]
            settings=settings,
            rag_providers=object(),  # type: ignore[arg-type]
        )

    assert caught.value.reason == "backend_binding_failed"


def test_partitioned_runtime_wraps_runtime_identity_configuration_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    rows = [
        _generation(backend="opensearch", settings=settings),
        _generation(backend="qdrant", settings=settings),
    ]
    monkeypatch.setattr(
        runtime_binding,
        "resolve_partitioned_rag_collection_alias",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("unknown embedding provider")),
    )

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_partitioned_files_query_runtime(
            _GenerationSession(rows),  # type: ignore[arg-type]
            settings=settings,
            rag_providers=object(),  # type: ignore[arg-type]
        )

    assert caught.value.reason == "runtime_configuration_invalid"


def test_partitioned_runtime_requires_validation_to_name_its_release_cohort() -> None:
    settings = _settings()
    opensearch = _generation(backend="opensearch", settings=settings)
    qdrant = _generation(backend="qdrant", settings=settings)
    qdrant.validation_details = {}

    with pytest.raises(PartitionedRetrievalRuntimeUnavailable) as caught:
        resolve_partitioned_files_query_runtime(
            _GenerationSession([opensearch, qdrant]),  # type: ignore[arg-type]
            settings=settings,
            rag_providers=object(),  # type: ignore[arg-type]
        )

    assert caught.value.reason == "release_cohort_mismatch"


def test_partitioned_keyword_client_is_bound_to_the_v3_physical_index() -> None:
    settings = _settings()
    physical_index = keyword_search_partitioned_index_name(
        settings.opensearch_index_prefix,
        generation=_COHORT,
    )

    client = build_partitioned_keyword_search_client(
        settings,
        physical_index_name=physical_index,
    )

    assert client.index_name == physical_index
    with pytest.raises(OpenSearchError, match="require retrieval_partition_ids"):
        client.search(KeywordSearchQuery(workspace_id="workspace-1"))


def test_partitioned_rag_query_service_is_bound_to_one_physical_collection() -> None:
    settings = _settings()
    providers = RagProviderBundle(
        vector_index=QdrantVectorIndexClient(client=object()),  # type: ignore[arg-type]
        embedding=FakeEmbeddingClient(dimensions=4),
    )
    collection = "open-work-hub-test-rag-v1-release_20260723"
    query_service = build_partitioned_retrieval_candidate_query_service(
        settings,
        collection=collection,
        providers=providers,
    )

    with pytest.raises(RagProviderConfigurationError, match="bound to collection"):
        query_service.query(
            RagQueryRequest(
                collection="other-collection",
                workspace_id="workspace-1",
                retrieval_partition_ids=["partition-1"],
                query="test",
                source_kinds=["files"],
                top_k=1,
            )
        )

    with pytest.raises(RagProviderConfigurationError, match="require retrieval_partition_ids"):
        query_service.query(
            RagQueryRequest(
                collection=collection,
                workspace_id="workspace-1",
                query="test",
                source_kinds=["files"],
                top_k=1,
            )
        )


def test_partitioned_rag_projection_service_is_bound_to_one_physical_collection() -> None:
    settings = _settings()
    providers = RagProviderBundle(
        vector_index=QdrantVectorIndexClient(client=object()),  # type: ignore[arg-type]
        embedding=FakeEmbeddingClient(dimensions=4),
    )
    collection = "open-work-hub-test-rag-v1-release_20260723"
    service = build_partitioned_rag_projection_service(
        settings,
        collection=collection,
        providers=providers,
    )

    with pytest.raises(RagProviderConfigurationError, match="bound to collection"):
        service.delete_projection(
            collection="other-collection",
            retrieval_partition_id="partition-1",
            workspace_id="workspace-1",
            resource_type="file_manager_file",
            resource_id="file-1",
        )
