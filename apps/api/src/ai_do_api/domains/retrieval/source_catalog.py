from __future__ import annotations

from dataclasses import dataclass

from ai_do_api.domains.retrieval.contracts import RetrievalSourceDescriptor, RetrievalStrategy


@dataclass(frozen=True, slots=True)
class RetrievalSourceCatalogItem:
    source: str
    label: str
    scope: str
    backend: str
    description: str
    required_app_ids: tuple[str, ...] = ()
    active: bool = True


_SOURCE_CATALOG: tuple[RetrievalSourceCatalogItem, ...] = (
    RetrievalSourceCatalogItem(
        source="generic_rag",
        label="Workspace RAG",
        scope="workspace",
        backend="qdrant",
        description="Official workspace RAG over registered source adapters.",
        required_app_ids=("docs",),
    ),
    RetrievalSourceCatalogItem(
        source="keyword",
        label="Workspace keyword search",
        scope="workspace",
        backend="keyword_search",
        description="BM25/full-text style keyword search over workspace projections.",
    ),
    RetrievalSourceCatalogItem(
        source="qna",
        label="Company Q&A",
        scope="company",
        backend="qdrant",
        description="Company-scope Q&A and notice RAG source.",
        required_app_ids=("qa-assistant",),
    ),
    RetrievalSourceCatalogItem(
        source="legacy_issues",
        label="Legacy issue AI search",
        scope="workspace",
        backend="postgres_pgvector",
        description="Legacy issue exact, term, full-text, trigram, pgvector, and rerank search.",
        required_app_ids=("legacy-issues",),
    ),
    RetrievalSourceCatalogItem(
        source="documents_demo",
        label="Documents demo",
        scope="workspace",
        backend="fixture",
        description="Prototype fixture source retained for audit visibility; not RAG.",
        active=False,
    ),
    RetrievalSourceCatalogItem(
        source="learning_notes_personal",
        label="Learning notes personal embeddings",
        scope="user",
        backend="native_doc_embedding",
        description="Personal learning-note vector logic retained outside the unified surface.",
        active=False,
    ),
)

_DEFAULT_SOURCES_BY_STRATEGY: dict[RetrievalStrategy, tuple[str, ...]] = {
    RetrievalStrategy.SEMANTIC: ("generic_rag",),
    RetrievalStrategy.KEYWORD: ("keyword",),
    RetrievalStrategy.HYBRID: ("keyword", "generic_rag"),
    RetrievalStrategy.GRAPH_HYBRID: ("keyword", "generic_rag"),
}


def iter_retrieval_source_catalog() -> tuple[RetrievalSourceCatalogItem, ...]:
    return _SOURCE_CATALOG


def registered_retrieval_source_app_ids() -> frozenset[str]:
    return frozenset(
        app_id for item in _SOURCE_CATALOG if item.active for app_id in item.required_app_ids
    )


def source_catalog_item(source: str) -> RetrievalSourceCatalogItem | None:
    normalized = source.strip()
    for item in _SOURCE_CATALOG:
        if item.source == normalized:
            return item
    return None


def default_sources_for_strategy(strategy: RetrievalStrategy) -> tuple[str, ...]:
    return _DEFAULT_SOURCES_BY_STRATEGY.get(
        strategy,
        _DEFAULT_SOURCES_BY_STRATEGY[RetrievalStrategy.HYBRID],
    )


def source_descriptor(
    item: RetrievalSourceCatalogItem,
    *,
    available: bool,
) -> RetrievalSourceDescriptor:
    return RetrievalSourceDescriptor(
        source=item.source,
        label=item.label,
        scope=item.scope,
        backend=item.backend,
        required_app_ids=list(item.required_app_ids),
        active=item.active,
        available=available,
        description=item.description,
    )
