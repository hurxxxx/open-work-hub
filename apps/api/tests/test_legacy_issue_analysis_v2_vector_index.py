from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from ai_do_api.domains.legacy_issues.analysis_v2.contracts import RetrievalHit
from ai_do_api.domains.legacy_issues.analysis_v2.retrieval import (
    RetrievalBoundaryError,
    RetrievalRequest,
)
from ai_do_api.domains.legacy_issues.analysis_v2.vector_index import (
    GenerationIndexNode,
    GenerationQueryScope,
    PGVectorAuthorizedRetriever,
    PGVectorGenerationIndex,
    VectorIndexError,
    build_legacy_source_retriever,
)


class _Embedding:
    provider_name = "inference-gateway-embedding"

    def embed_texts(
        self,
        texts: list[str],
        timeout_seconds: float | None = None,
    ) -> list[list[float]]:
        del timeout_seconds
        return [[float(index == 0) for index in range(8)] for _text in texts]

    def embed_query(
        self,
        text: str,
        timeout_seconds: float | None = None,
    ) -> list[float]:
        del text, timeout_seconds
        return [float(index == 0) for index in range(8)]


class _WrongEmbedding(_Embedding):
    provider_name = "local-embedding"


class _VectorStore:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.query_result = SimpleNamespace(nodes=[], similarities=[])
        self.queries: list[Any] = []

    def add(self, nodes: list[Any], **kwargs: Any) -> list[str]:
        del kwargs
        self.added.extend(nodes)
        return [node.node_id for node in nodes]

    def query(self, query: Any, **kwargs: Any) -> Any:
        self.queries.append((query, kwargs))
        return self.query_result

    def delete_nodes(
        self,
        node_ids: list[str] | None = None,
        filters: Any | None = None,
        **kwargs: Any,
    ) -> None:
        del node_ids, filters, kwargs


def _node(*, text: str = "결빙 시 소음 발생") -> GenerationIndexNode:
    return GenerationIndexNode.from_text(
        text=text,
        workspace_id="workspace-1",
        partition_id="partition-1",
        module_key="aircon",
        revision_id="revision-1",
        source_kind="legacy_issue_record",
        source_id="record-1",
        generation=3,
    )


def _scope() -> GenerationQueryScope:
    return GenerationQueryScope(
        workspace_id="workspace-1",
        partition_ids=("partition-1",),
        module_keys=("aircon",),
        revision_ids=("revision-1",),
        source_kinds=("legacy_issue_record",),
        generation=3,
    )


def test_generation_node_is_text_only_and_hash_verified() -> None:
    node = _node()

    assert node.metadata.content_hash
    with pytest.raises(ValidationError):
        _node(text="binary\x00payload")
    with pytest.raises(ValidationError, match="content_hash"):
        GenerationIndexNode(
            node_id=node.node_id,
            text="changed",
            metadata=node.metadata,
        )


def test_generation_index_uses_inference_gateway_embeddings_and_llama_nodes() -> None:
    store = _VectorStore()
    index = PGVectorGenerationIndex(
        vector_store=store,
        embedding_client=_Embedding(),
        embed_dim=8,
    )

    stored = index.ingest([_node()])

    assert stored == (_node().node_id,)
    assert store.added[0].metadata["generation"] == 3
    assert store.added[0].embedding == [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    with pytest.raises(VectorIndexError, match="requires_inference_gateway"):
        PGVectorGenerationIndex(
            vector_store=store,
            embedding_client=_WrongEmbedding(),
            embed_dim=8,
        )


def test_pgvector_retriever_requires_final_acl_hydration_and_generation_scope() -> None:
    from llama_index.core.schema import TextNode

    store = _VectorStore()
    node = _node()
    store.query_result = SimpleNamespace(
        nodes=[
            TextNode(
                id_=node.node_id,
                text=node.text,
                metadata=node.metadata.model_dump(mode="json"),
            )
        ],
        similarities=[0.93],
    )
    hydrated_candidates: list[Any] = []

    def _hydrate(candidates: tuple[Any, ...], limit: int) -> tuple[RetrievalHit, ...]:
        hydrated_candidates.extend(candidates)
        assert limit == 5
        candidate = candidates[0]
        return (
            RetrievalHit(
                hit_id="evidence-1",
                text="현재 DB에서 다시 조회한 허가된 근거",
                score=candidate.score,
                resource_type=candidate.metadata.source_kind,
                resource_id=candidate.metadata.source_id,
                partition_id=candidate.metadata.partition_id,
            ),
        )

    retriever = build_legacy_source_retriever(
        vector_store=store,
        embedding_client=_Embedding(),
        scope=_scope(),
        embed_dim=8,
        final_acl_hydrator=_hydrate,
    )
    hits = retriever.retrieve(RetrievalRequest(query="결빙 문제", limit=5))

    assert isinstance(retriever, PGVectorAuthorizedRetriever)
    assert hits[0].text == "현재 DB에서 다시 조회한 허가된 근거"
    assert hydrated_candidates[0].indexed_text == "결빙 시 소음 발생"
    query = store.queries[0][0]
    assert query.similarity_top_k == 25
    assert query.filters is not None


def test_pgvector_retriever_fails_before_hydration_for_out_of_scope_candidate() -> None:
    from llama_index.core.schema import TextNode

    store = _VectorStore()
    node = GenerationIndexNode.from_text(
        text="other workspace",
        workspace_id="workspace-2",
        partition_id="partition-1",
        module_key="aircon",
        revision_id="revision-1",
        source_kind="legacy_issue_record",
        source_id="record-2",
        generation=3,
    )
    store.query_result = SimpleNamespace(
        nodes=[
            TextNode(
                id_=node.node_id,
                text=node.text,
                metadata=node.metadata.model_dump(mode="json"),
            )
        ],
        similarities=[0.5],
    )
    retriever = PGVectorAuthorizedRetriever(
        vector_store=store,
        embedding_client=_Embedding(),
        scope=_scope(),
        embed_dim=8,
        final_acl_hydrator=lambda _candidates, _limit: (),
    )

    with pytest.raises(RetrievalBoundaryError, match="out-of-scope"):
        retriever.retrieve(RetrievalRequest(query="anything", limit=3))
