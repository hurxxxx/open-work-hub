from __future__ import annotations

from functools import lru_cache
import logging
import re
from typing import Protocol

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.rag.contracts import RagProviderHealth
from ai_do_api.domains.rag.providers import (
    DeepInfraEmbeddingClient,
    DeepInfraRerankClient,
    FakeEmbeddingClient,
    FakeOcrClient,
    QdrantVectorIndexClient,
    RagProviderBundle,
)
from ai_do_api.domains.rag.providers.base import (
    OcrClient,
    RagProviderConfigurationError,
    RerankClient,
    VectorIndexClient,
)
from ai_do_api.domains.rag.providers.fake import FakeRerankClient, FakeVectorIndexClient
from ai_do_api.domains.rag.query_service import RagGroundedAnswerSynthesizer, RagQueryService
from ai_do_api.domains.rag.service import RagService


logger = logging.getLogger(__name__)


class RagRuntimeSettings(Protocol):
    rag_enabled: bool
    rag_vector_index_provider: str
    rag_embedding_provider: str
    rag_rerank_provider: str
    rag_ocr_provider: str
    rag_query_timeout_ms: int
    rag_grounded_answer_timeout_ms: int
    rag_qdrant_url: str
    rag_qdrant_api_key: str
    rag_qdrant_collection_prefix: str
    rag_deepinfra_api_key: str
    rag_deepinfra_base_url: str
    rag_deepinfra_embedding_model: str
    rag_deepinfra_reranker_model: str
    rag_deepinfra_timeout: float


def build_provider_bundle(settings: RagRuntimeSettings) -> RagProviderBundle:
    if settings.rag_vector_index_provider == "qdrant":
        _warn_collection_migration_once(resolve_default_collection_name(settings))
    vector_index = _build_vector_index(settings)
    embedding = _build_embedding_client(settings)
    rerank = _build_rerank_client(settings)
    ocr = _build_ocr_client(settings)
    return RagProviderBundle(
        vector_index=vector_index,
        embedding=embedding,
        ocr=ocr,
        rerank=rerank,
    )


@lru_cache(maxsize=1)
def get_provider_bundle() -> RagProviderBundle:
    return build_provider_bundle(get_settings())


def build_rag_service(settings: RagRuntimeSettings) -> RagService:
    providers = build_provider_bundle(settings)
    return RagService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        ocr_client=providers.ocr,
        rerank_client=providers.rerank,
        default_collection=resolve_default_collection_name(settings),
    )


@lru_cache(maxsize=1)
def get_rag_service() -> RagService:
    settings = get_settings()
    providers = get_provider_bundle()
    return RagService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        ocr_client=providers.ocr,
        rerank_client=providers.rerank,
        default_collection=resolve_default_collection_name(settings),
    )


def build_rag_query_service(
    settings: RagRuntimeSettings,
    *,
    grounded_answer_synthesizer: RagGroundedAnswerSynthesizer | None = None,
) -> RagQueryService:
    providers = build_provider_bundle(settings)
    return RagQueryService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        rerank_client=providers.rerank,
        grounded_answer_synthesizer=grounded_answer_synthesizer,
        query_timeout_ms=settings.rag_query_timeout_ms,
        grounded_answer_timeout_ms=settings.rag_grounded_answer_timeout_ms,
        legacy_collection_resolver=lambda request: resolve_legacy_collection_names(
            settings,
            source_kinds=request.source_kinds,
        ),
    )


@lru_cache(maxsize=1)
def get_rag_query_service() -> RagQueryService:
    settings = get_settings()
    providers = get_provider_bundle()
    return RagQueryService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        rerank_client=providers.rerank,
        query_timeout_ms=settings.rag_query_timeout_ms,
        grounded_answer_timeout_ms=settings.rag_grounded_answer_timeout_ms,
        legacy_collection_resolver=lambda request: resolve_legacy_collection_names(
            settings,
            source_kinds=request.source_kinds,
        ),
    )


def resolve_default_collection_name(settings: RagRuntimeSettings) -> str:
    model_name = "fake"
    if settings.rag_embedding_provider == "deepinfra":
        model_name = settings.rag_deepinfra_embedding_model or model_name
    normalized_model = re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-") or "default"
    return f"{settings.rag_qdrant_collection_prefix}-{normalized_model}"


def resolve_legacy_collection_names(
    settings: RagRuntimeSettings,
    *,
    source_kinds: list[str] | None = None,
) -> tuple[str, ...]:
    resource_types = _resource_types_for_source_kinds(source_kinds or [])
    collection_names: list[str] = []
    for resource_type in resource_types:
        for token in _legacy_collection_tokens(resource_type):
            collection_names.append(f"{settings.rag_qdrant_collection_prefix}-{token}")
    return tuple(dict.fromkeys(collection_names))


def ensure_default_collection_ready(
    settings: RagRuntimeSettings,
    *,
    providers: RagProviderBundle | None = None,
    dense_dimensions: int | None = None,
) -> str:
    resolved_providers = providers or build_provider_bundle(settings)
    collection = resolve_default_collection_name(settings)
    dimensions = dense_dimensions or _resolve_embedding_dimensions(resolved_providers)
    resolved_providers.vector_index.ensure_collection(
        collection=collection,
        dense_dimensions=dimensions,
        sparse_enabled=True,
    )
    return collection


def get_rag_runtime_health() -> dict[str, object]:
    settings = get_settings()
    if not settings.rag_enabled:
        return {
            "enabled": False,
            "ready": True,
            "collection": None,
            "providers": [],
        }

    try:
        providers = build_provider_bundle(settings)
    except Exception as error:
        return {
            "enabled": True,
            "ready": False,
            "collection": resolve_default_collection_name(settings),
            "detail": str(error),
            "providers": [],
        }

    try:
        provider_healths = [
            provider.healthcheck()
            for provider in (
                providers.vector_index,
                providers.embedding,
                providers.rerank,
                providers.ocr,
            )
            if provider is not None
        ]
    except Exception as error:
        _close_provider_bundle(providers)
        return {
            "enabled": True,
            "ready": False,
            "collection": resolve_default_collection_name(settings),
            "detail": str(error),
            "providers": _serialize_provider_healths(provider_healths if "provider_healths" in locals() else []),
        }

    _close_provider_bundle(providers)
    return {
        "enabled": True,
        "ready": all(item.ready for item in provider_healths),
        "collection": resolve_default_collection_name(settings),
        "providers": _serialize_provider_healths(provider_healths),
    }


def _build_vector_index(settings: RagRuntimeSettings) -> VectorIndexClient:
    if settings.rag_vector_index_provider == "fake":
        return FakeVectorIndexClient()
    if settings.rag_vector_index_provider == "qdrant":
        if not settings.rag_qdrant_url:
            raise RagProviderConfigurationError(
                "AI_DO_QDRANT_URL is required when rag_vector_index_provider=qdrant"
            )
        return QdrantVectorIndexClient(
            url=settings.rag_qdrant_url,
            api_key=settings.rag_qdrant_api_key or None,
        )
    raise RagProviderConfigurationError(
        f"Unsupported RAG vector index provider: {settings.rag_vector_index_provider}"
    )


def _build_embedding_client(settings: RagRuntimeSettings):
    if settings.rag_embedding_provider == "fake":
        return FakeEmbeddingClient()
    if settings.rag_embedding_provider == "deepinfra":
        _require_deepinfra_config(
            api_key=settings.rag_deepinfra_api_key,
            model=settings.rag_deepinfra_embedding_model,
            provider_kind="embedding",
        )
        return DeepInfraEmbeddingClient(
            base_url=settings.rag_deepinfra_base_url,
            api_key=settings.rag_deepinfra_api_key,
            model=settings.rag_deepinfra_embedding_model,
            timeout=settings.rag_deepinfra_timeout,
        )
    raise RagProviderConfigurationError(
        f"Unsupported RAG embedding provider: {settings.rag_embedding_provider}"
    )


def _build_rerank_client(settings: RagRuntimeSettings) -> RerankClient | None:
    if settings.rag_rerank_provider in {"", "none", "disabled"}:
        return None
    if settings.rag_rerank_provider == "fake":
        return FakeRerankClient()
    if settings.rag_rerank_provider == "deepinfra":
        _require_deepinfra_config(
            api_key=settings.rag_deepinfra_api_key,
            model=settings.rag_deepinfra_reranker_model,
            provider_kind="rerank",
        )
        return DeepInfraRerankClient(
            base_url=settings.rag_deepinfra_base_url,
            api_key=settings.rag_deepinfra_api_key,
            model=settings.rag_deepinfra_reranker_model,
            timeout=settings.rag_deepinfra_timeout,
        )
    raise RagProviderConfigurationError(
        f"Unsupported RAG rerank provider: {settings.rag_rerank_provider}"
    )


def _build_ocr_client(settings: RagRuntimeSettings) -> OcrClient | None:
    if settings.rag_ocr_provider in {"", "none", "disabled"}:
        return None
    if settings.rag_ocr_provider in {"fake", "local_stub"}:
        return FakeOcrClient()
    raise RagProviderConfigurationError(
        f"Unsupported RAG OCR provider: {settings.rag_ocr_provider}"
    )


def _require_deepinfra_config(
    *,
    api_key: str,
    model: str,
    provider_kind: str,
) -> None:
    if not api_key.strip():
        raise RagProviderConfigurationError(
            f"DeepInfra API key is required for RAG {provider_kind} provider."
        )
    if not model.strip():
        raise RagProviderConfigurationError(
            f"DeepInfra model is required for RAG {provider_kind} provider."
        )


def close_rag_runtime_resources() -> None:
    cache_info = getattr(get_provider_bundle, "cache_info", None)
    if callable(cache_info) and cache_info().currsize > 0:
        _close_provider_bundle(get_provider_bundle())
    reset_rag_runtime_caches()


def reset_rag_runtime_caches() -> None:
    get_provider_bundle.cache_clear()
    get_default_embedding_dimensions.cache_clear()
    get_rag_service.cache_clear()
    get_rag_query_service.cache_clear()


def _close_provider_bundle(bundle: RagProviderBundle) -> None:
    for provider in (
        bundle.vector_index,
        bundle.embedding,
        bundle.ocr,
        bundle.asr,
        bundle.rerank,
    ):
        close = getattr(provider, "close", None)
        if callable(close):
            close()


@lru_cache(maxsize=8)
def _warn_collection_migration_once(collection_name: str) -> None:
    logger.warning(
        "RAG now uses model-scoped Qdrant collections. Current collection=%s. "
        "Legacy per-resource collections are not read automatically; run a full reindex after upgrading.",
        collection_name,
    )


@lru_cache(maxsize=1)
def get_default_embedding_dimensions() -> int:
    return _resolve_embedding_dimensions(get_provider_bundle())


_DOCS_RESOURCE_TYPE = "docs_native_doc"
_MEETING_RESOURCE_TYPE = "meeting"
_PMS_RESOURCE_TYPE = "pms_issue"
_PLANNER_RESOURCE_TYPE = "planner_event"
_DOCS_SOURCE_KINDS = {"manual", "meeting_notes", "app_generated"}
_SOURCE_KIND_RESOURCE_TYPES = {
    "meeting": _MEETING_RESOURCE_TYPE,
    "pms_issue": _PMS_RESOURCE_TYPE,
    "planner_event": _PLANNER_RESOURCE_TYPE,
    **{source_kind: _DOCS_RESOURCE_TYPE for source_kind in _DOCS_SOURCE_KINDS},
}


def _resource_types_for_source_kinds(source_kinds: list[str]) -> tuple[str, ...]:
    if not source_kinds:
        return (
            _DOCS_RESOURCE_TYPE,
            _MEETING_RESOURCE_TYPE,
            _PMS_RESOURCE_TYPE,
            _PLANNER_RESOURCE_TYPE,
        )
    resource_types = [
        _SOURCE_KIND_RESOURCE_TYPES[source_kind]
        for source_kind in source_kinds
        if source_kind in _SOURCE_KIND_RESOURCE_TYPES
    ]
    return tuple(dict.fromkeys(resource_types)) or (
        _DOCS_RESOURCE_TYPE,
        _MEETING_RESOURCE_TYPE,
        _PMS_RESOURCE_TYPE,
        _PLANNER_RESOURCE_TYPE,
    )


def _legacy_collection_tokens(resource_type: str) -> tuple[str, ...]:
    tokens = {
        resource_type,
        re.sub(r"[^a-z0-9]+", "-", resource_type.lower()).strip("-"),
    }
    if "_" in resource_type:
        suffix = resource_type.split("_", 1)[1]
        tokens.add(suffix)
        tokens.add(re.sub(r"[^a-z0-9]+", "-", suffix.lower()).strip("-"))
    return tuple(sorted(token for token in tokens if token))


def _resolve_embedding_dimensions(bundle: RagProviderBundle) -> int:
    embedding = bundle.embedding.embed_query("__rag_collection_bootstrap__")
    dimensions = len(embedding)
    if dimensions <= 0:
        raise RagProviderConfigurationError(
            "RAG embedding provider returned an empty vector during collection bootstrap."
        )
    return dimensions


def _serialize_provider_healths(healths: list[RagProviderHealth]) -> list[dict[str, object]]:
    return [health.model_dump(mode="json") for health in healths]
