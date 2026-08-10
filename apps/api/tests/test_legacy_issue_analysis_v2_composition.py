from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine

from open_alm_api.domains.legacy_issues.analysis_v2.composition import (
    AnalysisCompositionDependencies,
    build_analysis_toolset,
    compose_analysis_toolset,
)
from open_alm_api.domains.legacy_issues.analysis_v2.execution import AnalysisSqlScope
from open_alm_api.domains.legacy_issues.analysis_v2.vector_index import (
    GenerationQueryScope,
    PGVectorStoreConfig,
)
from open_alm_api.domains.retrieval.partitioning import (
    RetrievalPartitionId,
    RetrievalReadScope,
    RetrievalSourcePartitions,
)


class _Embedding:
    provider_name = "inference-gateway-embedding"

    def embed_texts(
        self,
        texts: list[str],
        timeout_seconds: float | None = None,
    ) -> list[list[float]]:
        del timeout_seconds
        return [[0.0] * 8 for _ in texts]

    def embed_query(
        self,
        text: str,
        timeout_seconds: float | None = None,
    ) -> list[float]:
        del text, timeout_seconds
        return [0.0] * 8


class _VectorStore:
    def add(self, nodes: list[Any], **kwargs: Any) -> list[str]:
        del kwargs
        return [str(node.node_id) for node in nodes]

    def query(self, query: Any, **kwargs: Any) -> Any:
        del query, kwargs
        return SimpleNamespace(nodes=[], similarities=[])

    def delete_nodes(
        self,
        node_ids: list[str] | None = None,
        filters: Any | None = None,
        **kwargs: Any,
    ) -> None:
        del node_ids, filters, kwargs


class _Resolver:
    def __init__(self, *, escaped_partition: bool = False) -> None:
        self.escaped_partition = escaped_partition
        self.hydrator_kinds: list[str] = []

    def resolve_source_namespaces(self, *_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        return ("legacy_issues",)

    def resolve_sql_scope(self, *_args: Any, **_kwargs: Any) -> AnalysisSqlScope:
        return AnalysisSqlScope(
            workspace_id="workspace-1",
            partition_ids=("partition-1",),
            module_keys=("legacy_issues",),
            revision_ids=("revision-1",),
        )

    def resolve_generation_scope(
        self,
        *_args: Any,
        kind: str,
        **_kwargs: Any,
    ) -> GenerationQueryScope:
        partition = "partition-escaped" if self.escaped_partition else "partition-1"
        source_kind = "analysis_metadata" if kind == "analysis_metadata" else "legacy_issue"
        return GenerationQueryScope(
            workspace_id="workspace-1",
            partition_ids=(partition,),
            module_keys=("legacy_issues",),
            revision_ids=("revision-1",),
            source_kinds=(source_kind,),
            generation=1,
        )

    def resolve_final_acl_hydrator(
        self,
        *_args: Any,
        kind: str,
        **_kwargs: Any,
    ) -> Any:
        self.hydrator_kinds.append(kind)
        return lambda _candidates, _limit: ()

    def resolve_embedding_client(self, *_args: Any, **_kwargs: Any) -> _Embedding:
        return _Embedding()

    def resolve_pgvector_config(
        self,
        *_args: Any,
        **_kwargs: Any,
    ) -> PGVectorStoreConfig:
        return PGVectorStoreConfig(
            connection_string=SecretStr("postgresql+psycopg://localhost/test"),
            async_connection_string=SecretStr(
                "postgresql+asyncpg://localhost/test"
            ),
            embed_dim=8,
        )


def _read_scope(*_args: Any, **_kwargs: Any) -> RetrievalReadScope:
    return RetrievalReadScope(
        sources=(
            RetrievalSourcePartitions(
                source_namespace="legacy_issues",
                partition_ids=(RetrievalPartitionId("partition-1"),),
            ),
        )
    )


def _dependencies(resolver: _Resolver) -> AnalysisCompositionDependencies:
    class _EvidenceRetriever:
        backend_id = "test-native-evidence"

        def retrieve(self, _request):
            return ()

    return AnalysisCompositionDependencies(
        resolver=resolver,
        engine=create_engine("postgresql+psycopg://localhost/test"),
        vector_store=_VectorStore(),
        read_scope_resolver=_read_scope,
        acl_policy_factory=lambda _db, _workspace, _user: SimpleNamespace(),
        evidence_retriever_factory=lambda **_kwargs: _EvidenceRetriever(),
    )


def test_worker_composition_builds_all_four_tools_from_bound_scopes() -> None:
    resolver = _Resolver()
    workspace = SimpleNamespace(id="workspace-1")
    user = SimpleNamespace(id="user-1")
    run = SimpleNamespace(
        run_id="run-1",
        workspace_id="workspace-1",
        requested_by_user_id="user-1",
    )

    composition = compose_analysis_toolset(
        object(),  # type: ignore[arg-type]
        workspace=workspace,  # type: ignore[arg-type]
        user=user,  # type: ignore[arg-type]
        run=run,
        dependencies=_dependencies(resolver),
    )

    assert composition.sql_scope.partition_ids == ("partition-1",)
    assert composition.metadata_scope.generation == 1
    assert composition.embed_dim == 8
    assert resolver.hydrator_kinds == ["analysis_metadata"]
    assert {
        item["name"] for item in composition.toolset.action_schemas()
    } == {
        "run_recipe",
        "run_safe_sql",
        "search_analysis_context",
        "search_legacy_evidence",
    }
    assert (
        build_analysis_toolset(
            object(),  # type: ignore[arg-type]
            workspace=workspace,  # type: ignore[arg-type]
            user=user,  # type: ignore[arg-type]
            run=run,
            dependencies=_dependencies(_Resolver()),
        )
        .catalog.all()
    )


def test_worker_composition_rejects_partition_outside_common_retrieval_scope() -> None:
    with pytest.raises(ValueError, match="unauthorized partitions"):
        compose_analysis_toolset(
            object(),  # type: ignore[arg-type]
            workspace=SimpleNamespace(id="workspace-1"),  # type: ignore[arg-type]
            user=SimpleNamespace(id="user-1"),  # type: ignore[arg-type]
            run=SimpleNamespace(
                run_id="run-1",
                workspace_id="workspace-1",
                requested_by_user_id="user-1",
            ),
            dependencies=_dependencies(_Resolver(escaped_partition=True)),
        )
