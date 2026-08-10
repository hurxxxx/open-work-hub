from __future__ import annotations

from collections.abc import Callable

from open_alm_api.domains.search.backend_contracts import (
    KeywordSearchBackendSettings,
    KeywordSearchClient,
)

KeywordSearchClientFactory = Callable[[KeywordSearchBackendSettings], KeywordSearchClient]

_backend_factories: dict[str, KeywordSearchClientFactory] = {}
_defaults_registered = False


def build_keyword_search_client(
    settings: KeywordSearchBackendSettings,
) -> KeywordSearchClient:
    ensure_default_keyword_search_backends_registered()
    backend_name = normalize_keyword_search_backend_name(
        getattr(settings, "keyword_search_backend", "opensearch")
    )
    factory = _backend_factories.get(backend_name)
    if factory is None:
        raise ValueError(f"Keyword search backend is not registered: {backend_name}")
    return factory(settings)


def build_partitioned_keyword_search_client(
    settings: KeywordSearchBackendSettings,
    *,
    physical_index_name: str,
) -> KeywordSearchClient:
    """Bind query traffic to one explicit partition-aware OpenSearch generation."""

    backend_name = normalize_keyword_search_backend_name(
        getattr(settings, "keyword_search_backend", "opensearch")
    )
    if backend_name != "opensearch":
        raise ValueError("Partitioned keyword retrieval requires the OpenSearch backend")
    from open_alm_api.domains.search.index_gateway import (
        RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
    )
    from open_alm_api.domains.search.opensearch import OpenSearchKeywordClient

    return OpenSearchKeywordClient(
        base_url=settings.opensearch_url,
        index_prefix=settings.opensearch_index_prefix,
        target_index_name=physical_index_name,
        target_schema_version=RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
        partitioned_generation_index=physical_index_name,
    )


def register_keyword_search_backend(
    backend_name: str,
    factory: KeywordSearchClientFactory,
) -> None:
    normalized = normalize_keyword_search_backend_name(backend_name)
    if normalized in _backend_factories:
        raise ValueError(f"Keyword search backend already registered: {normalized}")
    _backend_factories[normalized] = factory


def keyword_search_backend_names() -> tuple[str, ...]:
    ensure_default_keyword_search_backends_registered()
    return tuple(sorted(_backend_factories))


def ensure_default_keyword_search_backends_registered() -> None:
    global _defaults_registered
    if _defaults_registered:
        return
    register_keyword_search_backend("opensearch", _build_opensearch_keyword_search_client)
    _defaults_registered = True


def reset_keyword_search_backends() -> None:
    global _defaults_registered
    _backend_factories.clear()
    _defaults_registered = False


def normalize_keyword_search_backend_name(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "opensearch"


def _build_opensearch_keyword_search_client(
    settings: KeywordSearchBackendSettings,
) -> KeywordSearchClient:
    from open_alm_api.domains.search.opensearch import OpenSearchKeywordClient

    return OpenSearchKeywordClient(
        base_url=settings.opensearch_url,
        index_prefix=settings.opensearch_index_prefix,
    )


__all__ = [
    "KeywordSearchBackendSettings",
    "KeywordSearchClient",
    "build_keyword_search_client",
    "build_partitioned_keyword_search_client",
    "ensure_default_keyword_search_backends_registered",
    "keyword_search_backend_names",
    "normalize_keyword_search_backend_name",
    "register_keyword_search_backend",
    "reset_keyword_search_backends",
]
