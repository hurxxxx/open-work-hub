from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from open_alm_api.domains.legacy_issues.analysis_v2.contracts import (
    RetrievalHit,
    RetrievalResult,
)


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=2_000)
    limit: int = Field(default=8, ge=1, le=50)


class AuthorizedRetriever(Protocol):
    """Scope-bound retrieval backend.

    Implementations are created by the composition root after resolving the
    caller's RetrievalReadScope and SourceAclPolicy. They must use Open ALM's
    inference-gateway embedding provider and return only final-ACL-approved hits.
    This deliberately exposes no workspace, partition, embedding-model, or ACL
    parameters to the model/tool layer.
    """

    backend_id: str

    def retrieve(self, request: RetrievalRequest) -> tuple[RetrievalHit, ...]: ...


class RetrievalBoundaryError(RuntimeError):
    pass


class LlamaIndexRetrieverAdapter:
    """Adapt a trusted Open ALM retriever without letting LlamaIndex own security."""

    def __init__(
        self,
        *,
        backend: AuthorizedRetriever,
        kind: Literal["analysis_metadata", "legacy_evidence"],
    ) -> None:
        self._backend = backend
        self.kind = kind

    @property
    def backend_id(self) -> str:
        return self._backend.backend_id

    def search(self, query: str, *, limit: int = 8) -> RetrievalResult:
        request = RetrievalRequest(query=query, limit=limit)
        hits = self._backend.retrieve(request)
        if len(hits) > request.limit:
            raise RetrievalBoundaryError("authorized retriever exceeded requested limit")
        if len({hit.hit_id for hit in hits}) != len(hits):
            raise RetrievalBoundaryError("authorized retriever returned duplicate hit ids")
        return RetrievalResult(
            query=request.query,
            hits=hits,
            backend_id=self._backend.backend_id,
        )

    def as_llamaindex_retriever(self) -> Any:
        """Return a native BaseRetriever when llama-index-core is installed."""

        try:
            from llama_index.core.retrievers import BaseRetriever
            from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
        except ImportError as exc:
            raise RuntimeError(
                "llama-index-core is required for the native retriever adapter"
            ) from exc

        adapter = self

        class _AiDoAuthorizedRetriever(BaseRetriever):
            def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
                result = adapter.search(query_bundle.query_str)
                return [
                    NodeWithScore(
                        node=TextNode(
                            id_=hit.hit_id,
                            text=hit.text,
                            metadata={
                                **hit.metadata,
                                "resource_type": hit.resource_type,
                                "resource_id": hit.resource_id,
                                "partition_id": hit.partition_id,
                                "retriever_kind": adapter.kind,
                                "backend_id": adapter.backend_id,
                            },
                        ),
                        score=hit.score,
                    )
                    for hit in result.hits
                ]

        return _AiDoAuthorizedRetriever()


__all__ = [
    "AuthorizedRetriever",
    "LlamaIndexRetrieverAdapter",
    "RetrievalBoundaryError",
    "RetrievalRequest",
]
