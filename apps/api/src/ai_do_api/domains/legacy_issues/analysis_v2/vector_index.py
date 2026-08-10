from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from ai_do_api.domains.legacy_issues.analysis_v2.contracts import RetrievalHit
from ai_do_api.domains.legacy_issues.analysis_v2.retrieval import (
    AuthorizedRetriever,
    RetrievalBoundaryError,
    RetrievalRequest,
)


PGVECTOR_SCHEMA = "legacy_issue_analysis"
PGVECTOR_INDEX_NAME = "analysis_nodes_v1"
PGVECTOR_PHYSICAL_TABLE = f"{PGVECTOR_SCHEMA}.data_{PGVECTOR_INDEX_NAME}"
INFERENCE_GATEWAY_EMBEDDING_PROVIDER = "inference-gateway-embedding"
MAX_INDEX_TEXT_CHARS = 50_000
MAX_INGEST_BATCH = 200
MAX_VECTOR_PREFETCH = 200

_SAFE_METADATA_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$"


class GenerationNodeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(pattern=_SAFE_METADATA_PATTERN)
    partition_id: str = Field(pattern=_SAFE_METADATA_PATTERN)
    module_key: str = Field(pattern=_SAFE_METADATA_PATTERN)
    revision_id: str = Field(pattern=_SAFE_METADATA_PATTERN)
    source_kind: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,79}$")
    source_id: str = Field(pattern=_SAFE_METADATA_PATTERN)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    generation: int = Field(ge=1)


class GenerationIndexNode(BaseModel):
    """Text-only node; binary/file payloads cannot cross this contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(pattern=_SAFE_METADATA_PATTERN)
    text: str = Field(min_length=1, max_length=MAX_INDEX_TEXT_CHARS)
    metadata: GenerationNodeMetadata

    @field_validator("text")
    @classmethod
    def _reject_binary_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("index text cannot contain NUL/binary data")
        return value

    @model_validator(mode="after")
    def _validate_content_hash(self) -> GenerationIndexNode:
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if digest != self.metadata.content_hash:
            raise ValueError("content_hash does not match UTF-8 text")
        return self

    @classmethod
    def from_text(
        cls,
        *,
        text: str,
        workspace_id: str,
        partition_id: str,
        module_key: str,
        revision_id: str,
        source_kind: str,
        source_id: str,
        generation: int,
    ) -> GenerationIndexNode:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        node_id = f"{source_kind}:{source_id}:{digest[:16]}:g{generation}"
        return cls(
            node_id=node_id,
            text=text,
            metadata=GenerationNodeMetadata(
                workspace_id=workspace_id,
                partition_id=partition_id,
                module_key=module_key,
                revision_id=revision_id,
                source_kind=source_kind,
                source_id=source_id,
                content_hash=digest,
                generation=generation,
            ),
        )


class GenerationQueryScope(BaseModel):
    """Server-resolved vector candidate scope; never populated by the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str = Field(pattern=_SAFE_METADATA_PATTERN)
    partition_ids: tuple[str, ...] = Field(min_length=1, max_length=500)
    module_keys: tuple[str, ...] = Field(min_length=1, max_length=100)
    revision_ids: tuple[str, ...] = Field(min_length=1, max_length=500)
    source_kinds: tuple[str, ...] = Field(min_length=1, max_length=20)
    generation: int = Field(ge=1)

    @field_validator("partition_ids", "module_keys", "revision_ids")
    @classmethod
    def _validate_safe_filter_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        import re

        if any(re.fullmatch(_SAFE_METADATA_PATTERN, value) is None for value in values):
            raise ValueError("vector metadata filter contains unsafe value")
        return tuple(dict.fromkeys(values))

    @field_validator("source_kinds")
    @classmethod
    def _validate_source_kinds(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        import re

        pattern = r"^[a-z][a-z0-9_.-]{1,79}$"
        if any(re.fullmatch(pattern, value) is None for value in values):
            raise ValueError("vector source kind contains unsafe value")
        return tuple(dict.fromkeys(values))


class PGVectorStoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connection_string: SecretStr
    async_connection_string: SecretStr
    embed_dim: int = Field(ge=8, le=65_535)


class InferenceGatewayEmbeddingClient(Protocol):
    provider_name: str

    def embed_texts(
        self,
        texts: list[str],
        timeout_seconds: float | None = None,
    ) -> list[list[float]]: ...

    def embed_query(
        self,
        text: str,
        timeout_seconds: float | None = None,
    ) -> list[float]: ...


class VectorStoreProtocol(Protocol):
    def add(self, nodes: list[Any], **kwargs: Any) -> list[str]: ...

    def query(self, query: Any, **kwargs: Any) -> Any: ...

    def delete_nodes(
        self,
        node_ids: list[str] | None = None,
        filters: Any | None = None,
        **kwargs: Any,
    ) -> None: ...


class VectorIndexError(RuntimeError):
    pass


class VectorCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    indexed_text: str = Field(max_length=MAX_INDEX_TEXT_CHARS)
    score: float
    metadata: GenerationNodeMetadata


FinalAclHydrator = Callable[
    [tuple[VectorCandidate, ...], int],
    tuple[RetrievalHit, ...],
]


def build_pgvector_store(config: PGVectorStoreConfig) -> Any:
    """Build the real LlamaIndex PGVectorStore; schema setup stays in Alembic."""

    try:
        from llama_index.vector_stores.postgres import PGVectorStore
    except ImportError as exc:
        raise RuntimeError(
            "llama-index-vector-stores-postgres is required for analysis_v2"
        ) from exc
    return PGVectorStore.from_params(
        connection_string=config.connection_string.get_secret_value(),
        async_connection_string=config.async_connection_string.get_secret_value(),
        table_name=PGVECTOR_INDEX_NAME,
        schema_name=PGVECTOR_SCHEMA,
        hybrid_search=True,
        text_search_config="simple",
        embed_dim=config.embed_dim,
        cache_ok=True,
        perform_setup=False,
        use_jsonb=True,
        indexed_metadata_keys={
            ("workspace_id", "text"),
            ("partition_id", "text"),
            ("module_key", "text"),
            ("revision_id", "text"),
            ("source_kind", "text"),
            ("source_id", "text"),
            ("content_hash", "text"),
            ("generation", "integer"),
        },
    )


class PGVectorGenerationIndex:
    def __init__(
        self,
        *,
        vector_store: VectorStoreProtocol,
        embedding_client: InferenceGatewayEmbeddingClient,
        embed_dim: int,
    ) -> None:
        _require_inference_gateway(embedding_client)
        self._vector_store = vector_store
        self._embedding = embedding_client
        self._embed_dim = embed_dim

    def ingest(self, nodes: Sequence[GenerationIndexNode]) -> tuple[str, ...]:
        if not nodes:
            return ()
        if len(nodes) > MAX_INGEST_BATCH:
            raise VectorIndexError("analysis_v2_vector_ingest_batch_limit")
        node_ids = [node.node_id for node in nodes]
        if len(set(node_ids)) != len(node_ids):
            raise VectorIndexError("analysis_v2_vector_duplicate_node_id")
        embeddings = self._embedding.embed_texts(
            [node.text for node in nodes],
            timeout_seconds=5.0,
        )
        if len(embeddings) != len(nodes):
            raise VectorIndexError("analysis_v2_vector_embedding_count_mismatch")
        try:
            from llama_index.core.schema import TextNode
        except ImportError as exc:
            raise RuntimeError("llama-index-core is required for analysis_v2") from exc
        llama_nodes = []
        for node, embedding in zip(nodes, embeddings, strict=True):
            _validate_embedding(embedding, embed_dim=self._embed_dim)
            llama_nodes.append(
                TextNode(
                    id_=node.node_id,
                    text=node.text,
                    metadata=node.metadata.model_dump(mode="json"),
                    embedding=embedding,
                    excluded_llm_metadata_keys=[
                        "workspace_id",
                        "partition_id",
                        "generation",
                    ],
                )
            )
        # A generation is not promoted until ingestion completes, so replacing
        # deterministic node IDs makes worker retries idempotent without exposing
        # a partially rebuilt generation to query traffic.
        self._vector_store.delete_nodes(node_ids=node_ids)
        stored_ids = tuple(self._vector_store.add(llama_nodes))
        if set(stored_ids) != set(node_ids):
            raise VectorIndexError("analysis_v2_vector_store_id_mismatch")
        return stored_ids

    def delete_generation(self, scope: GenerationQueryScope) -> None:
        """Delete one exact server-resolved generation after retention approval."""

        self._vector_store.delete_nodes(filters=_metadata_filters(scope))


class PGVectorAuthorizedRetriever(AuthorizedRetriever):
    """Generation-aware candidate retrieval followed by mandatory final ACL hydrate."""

    backend_id = "legacy-issues-llamaindex-pgvector-v1"

    def __init__(
        self,
        *,
        vector_store: VectorStoreProtocol,
        embedding_client: InferenceGatewayEmbeddingClient,
        scope: GenerationQueryScope,
        embed_dim: int,
        final_acl_hydrator: FinalAclHydrator,
    ) -> None:
        if final_acl_hydrator is None:
            raise ValueError("final_acl_hydrator is required")
        _require_inference_gateway(embedding_client)
        self._vector_store = vector_store
        self._embedding = embedding_client
        self._scope = scope
        self._embed_dim = embed_dim
        self._final_acl_hydrator = final_acl_hydrator

    def retrieve(self, request: RetrievalRequest) -> tuple[RetrievalHit, ...]:
        query_embedding = self._embedding.embed_query(
            request.query,
            timeout_seconds=5.0,
        )
        _validate_embedding(query_embedding, embed_dim=self._embed_dim)
        try:
            from llama_index.core.vector_stores import VectorStoreQuery
            from llama_index.core.vector_stores.types import VectorStoreQueryMode
        except ImportError as exc:
            raise RuntimeError("llama-index-core is required for analysis_v2") from exc
        prefetch = min(max(request.limit * 5, 20), MAX_VECTOR_PREFETCH)
        result = self._vector_store.query(
            VectorStoreQuery(
                query_embedding=query_embedding,
                query_str=request.query,
                similarity_top_k=prefetch,
                sparse_top_k=prefetch,
                hybrid_top_k=prefetch,
                mode=VectorStoreQueryMode.HYBRID,
                filters=_metadata_filters(self._scope),
            )
        )
        candidates = self._validated_candidates(result)
        hydrated = self._final_acl_hydrator(candidates, request.limit)
        self._validate_hydrated(hydrated, candidates=candidates, limit=request.limit)
        return hydrated

    def _validated_candidates(self, result: Any) -> tuple[VectorCandidate, ...]:
        nodes = tuple(result.nodes or ())
        scores = tuple(result.similarities or ())
        if len(nodes) != len(scores):
            raise RetrievalBoundaryError("vector result nodes/scores mismatch")
        candidates: list[VectorCandidate] = []
        for node, score in zip(nodes, scores, strict=True):
            metadata = GenerationNodeMetadata.model_validate(dict(node.metadata))
            if not self._metadata_in_scope(metadata):
                raise RetrievalBoundaryError("vector store returned out-of-scope metadata")
            candidates.append(
                VectorCandidate(
                    node_id=str(node.node_id),
                    indexed_text=str(node.get_content()),
                    score=max(float(score or 0), 0),
                    metadata=metadata,
                )
            )
        return tuple(candidates)

    def _metadata_in_scope(self, metadata: GenerationNodeMetadata) -> bool:
        return (
            metadata.workspace_id == self._scope.workspace_id
            and metadata.partition_id in self._scope.partition_ids
            and metadata.module_key in self._scope.module_keys
            and metadata.revision_id in self._scope.revision_ids
            and metadata.source_kind in self._scope.source_kinds
            and metadata.generation == self._scope.generation
        )

    def _validate_hydrated(
        self,
        hits: tuple[RetrievalHit, ...],
        *,
        candidates: tuple[VectorCandidate, ...],
        limit: int,
    ) -> None:
        if len(hits) > limit:
            raise RetrievalBoundaryError("final ACL hydrator exceeded result limit")
        candidates_by_source = {
            (item.metadata.source_kind, item.metadata.source_id): item
            for item in candidates
        }
        seen: set[str] = set()
        for hit in hits:
            if hit.hit_id in seen:
                raise RetrievalBoundaryError("final ACL hydrator returned duplicate hits")
            seen.add(hit.hit_id)
            candidate = candidates_by_source.get((hit.resource_type, hit.resource_id))
            if candidate is None:
                raise RetrievalBoundaryError("final ACL hydrator introduced a new resource")
            if hit.partition_id != candidate.metadata.partition_id:
                raise RetrievalBoundaryError("final ACL hydrator changed partition identity")


def build_legacy_source_retriever(
    *,
    vector_store: VectorStoreProtocol,
    embedding_client: InferenceGatewayEmbeddingClient,
    scope: GenerationQueryScope,
    embed_dim: int,
    final_acl_hydrator: FinalAclHydrator,
) -> AuthorizedRetriever:
    """Public seam shared by analysis tools and the common Retrieval service."""

    return PGVectorAuthorizedRetriever(
        vector_store=vector_store,
        embedding_client=embedding_client,
        scope=scope,
        embed_dim=embed_dim,
        final_acl_hydrator=final_acl_hydrator,
    )


def _metadata_filters(scope: GenerationQueryScope) -> Any:
    try:
        from llama_index.core.vector_stores import (
            FilterCondition,
            FilterOperator,
            MetadataFilter,
            MetadataFilters,
        )
    except ImportError as exc:
        raise RuntimeError("llama-index-core is required for analysis_v2") from exc
    return MetadataFilters(
        condition=FilterCondition.AND,
        filters=[
            MetadataFilter(
                key="workspace_id",
                value=scope.workspace_id,
                operator=FilterOperator.EQ,
            ),
            MetadataFilter(
                key="partition_id",
                value=list(scope.partition_ids),
                operator=FilterOperator.IN,
            ),
            MetadataFilter(
                key="module_key",
                value=list(scope.module_keys),
                operator=FilterOperator.IN,
            ),
            MetadataFilter(
                key="revision_id",
                value=list(scope.revision_ids),
                operator=FilterOperator.IN,
            ),
            MetadataFilter(
                key="source_kind",
                value=list(scope.source_kinds),
                operator=FilterOperator.IN,
            ),
            MetadataFilter(
                key="generation",
                value=scope.generation,
                operator=FilterOperator.EQ,
            ),
        ],
    )


def _require_inference_gateway(client: InferenceGatewayEmbeddingClient) -> None:
    if getattr(client, "provider_name", None) != INFERENCE_GATEWAY_EMBEDDING_PROVIDER:
        raise VectorIndexError("analysis_v2_requires_inference_gateway_embedding")


def _validate_embedding(embedding: Sequence[float], *, embed_dim: int) -> None:
    if len(embedding) != embed_dim:
        raise VectorIndexError("analysis_v2_vector_embedding_dimension_mismatch")
    if any(not math.isfinite(float(value)) for value in embedding):
        raise VectorIndexError("analysis_v2_vector_embedding_non_finite")


__all__ = [
    "INFERENCE_GATEWAY_EMBEDDING_PROVIDER",
    "MAX_INDEX_TEXT_CHARS",
    "PGVECTOR_INDEX_NAME",
    "PGVECTOR_PHYSICAL_TABLE",
    "PGVECTOR_SCHEMA",
    "FinalAclHydrator",
    "GenerationIndexNode",
    "GenerationNodeMetadata",
    "GenerationQueryScope",
    "InferenceGatewayEmbeddingClient",
    "PGVectorAuthorizedRetriever",
    "PGVectorGenerationIndex",
    "PGVectorStoreConfig",
    "VectorCandidate",
    "VectorIndexError",
    "build_legacy_source_retriever",
    "build_pgvector_store",
]
