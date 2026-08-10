from __future__ import annotations

from functools import lru_cache
import logging
import re

from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.rag.contracts import RagProviderHealth, RagVectorSearchMode
from open_work_hub_api.domains.rag.provider_factory import (
    RagProviderFactory,
    RagRuntimeSettings,
    embedding_provider_collection_model_name,
    is_qdrant_vector_index,
)
from open_work_hub_api.domains.rag.providers import RagProviderBundle
from open_work_hub_api.domains.rag.providers.base import (
    RagProviderConfigurationError,
)
from open_work_hub_api.domains.rag.providers.qdrant import QdrantVectorIndexClient
from open_work_hub_api.domains.rag.query_service import RagGroundedAnswerSynthesizer, RagQueryService
from open_work_hub_api.domains.rag.queue_health import get_rag_queue_health
from open_work_hub_api.domains.rag.service import RagService
from open_work_hub_api.domains.rag.default_source_adapters import (
    resolve_rag_resource_types_for_source_kinds,
)


logger = logging.getLogger(__name__)
_RETRIEVAL_CANDIDATE_TIMEOUT_MS = 5_000
_PARTITIONED_GENERATION_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PARTITIONED_RAG_GENERATION_SCHEMA_VERSION = 1


def build_provider_bundle(settings: RagRuntimeSettings) -> RagProviderBundle:
    if is_qdrant_vector_index(settings):
        _warn_collection_migration_once(resolve_default_collection_name(settings))
    return RagProviderFactory(settings).build_bundle()


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


def build_partitioned_rag_projection_service(
    settings: RagRuntimeSettings,
    *,
    collection: str,
    providers: RagProviderBundle | None = None,
) -> RagService:
    """Build a projection writer bound to one physical Qdrant generation."""

    if str(settings.rag_vector_index_provider or "").strip().lower() != "qdrant":
        raise RagProviderConfigurationError(
            "Partitioned RAG projection requires the Qdrant vector index provider"
        )
    normalized_collection = str(collection or "").strip()
    if not normalized_collection:
        raise RagProviderConfigurationError(
            "Partitioned RAG projection requires an explicit physical collection"
        )
    resolved_providers = providers if providers is not None else build_provider_bundle(settings)
    if not isinstance(resolved_providers.vector_index, QdrantVectorIndexClient):
        raise RagProviderConfigurationError(
            "Partitioned RAG projection requires a Qdrant vector index client"
        )
    vector_index = resolved_providers.vector_index.for_partitioned_generation(
        collection=normalized_collection
    )
    return RagService(
        vector_index=vector_index,
        embedding_client=resolved_providers.embedding,
        ocr_client=resolved_providers.ocr,
        asr_client=resolved_providers.asr,
        rerank_client=resolved_providers.rerank,
        default_collection=normalized_collection,
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
        rerank_candidate_k=settings.rag_rerank_candidate_k,
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
        rerank_candidate_k=settings.rag_rerank_candidate_k,
        legacy_collection_resolver=lambda request: resolve_legacy_collection_names(
            settings,
            source_kinds=request.source_kinds,
        ),
    )


@lru_cache(maxsize=1)
def get_retrieval_candidate_query_service() -> RagQueryService:
    """Dense-only, search-only candidate retriever for cross-backend fusion."""

    settings = get_settings()
    providers = get_provider_bundle()
    return RagQueryService(
        vector_index=providers.vector_index,
        embedding_client=providers.embedding,
        rerank_client=None,
        query_timeout_ms=min(settings.rag_query_timeout_ms, _RETRIEVAL_CANDIDATE_TIMEOUT_MS),
        rerank_candidate_k=settings.rag_rerank_candidate_k,
        vector_search_mode=RagVectorSearchMode.DENSE,
        legacy_collection_resolver=lambda request: resolve_legacy_collection_names(
            settings,
            source_kinds=request.source_kinds,
        ),
    )


def build_partitioned_retrieval_candidate_query_service(
    settings: RagRuntimeSettings,
    *,
    collection: str,
    providers: RagProviderBundle | None = None,
) -> RagQueryService:
    """Build a dense-only query Module bound to one physical Qdrant generation."""

    if str(settings.rag_vector_index_provider or "").strip().lower() != "qdrant":
        raise RagProviderConfigurationError(
            "Partitioned RAG retrieval requires the Qdrant vector index provider"
        )
    normalized_collection = str(collection or "").strip()
    if not normalized_collection:
        raise RagProviderConfigurationError(
            "Partitioned RAG retrieval requires an explicit physical collection"
        )
    resolved_providers = providers if providers is not None else build_provider_bundle(settings)
    if not isinstance(resolved_providers.vector_index, QdrantVectorIndexClient):
        raise RagProviderConfigurationError(
            "Partitioned RAG retrieval requires a Qdrant vector index client"
        )
    vector_index = resolved_providers.vector_index.for_partitioned_generation(
        collection=normalized_collection
    )
    return RagQueryService(
        vector_index=vector_index,
        embedding_client=resolved_providers.embedding,
        rerank_client=None,
        query_timeout_ms=min(settings.rag_query_timeout_ms, _RETRIEVAL_CANDIDATE_TIMEOUT_MS),
        rerank_candidate_k=settings.rag_rerank_candidate_k,
        vector_search_mode=RagVectorSearchMode.DENSE,
    )


@lru_cache(maxsize=8)
def get_partitioned_retrieval_candidate_query_service(
    collection: str,
) -> RagQueryService:
    """Reuse the bound query Module and its provider circuit state per generation."""

    settings = get_settings()
    return build_partitioned_retrieval_candidate_query_service(
        settings,
        collection=collection,
        providers=get_provider_bundle(),
    )


def resolve_default_collection_name(settings: RagRuntimeSettings) -> str:
    model_name = embedding_provider_collection_model_name(settings)
    normalized_model = re.sub(r"[^a-z0-9]+", "-", model_name.lower()).strip("-") or "default"
    return f"{settings.rag_qdrant_collection_prefix}-{normalized_model}"


def resolve_partitioned_rag_collection_alias(settings: RagRuntimeSettings) -> str:
    """Return the dedicated alias for partition-aware retrieval collections."""

    return f"{resolve_default_collection_name(settings)}-v{PARTITIONED_RAG_GENERATION_SCHEMA_VERSION}"


def resolve_partitioned_rag_collection_name(
    settings: RagRuntimeSettings,
    *,
    generation: str,
) -> str:
    normalized_generation = str(generation or "").strip().lower()
    if not _PARTITIONED_GENERATION_KEY_PATTERN.fullmatch(normalized_generation):
        raise ValueError(
            "Partitioned RAG generation must contain only lowercase letters, digits, "
            "underscores, or hyphens"
        )
    return (
        f"{resolve_default_collection_name(settings)}"
        f"-v{PARTITIONED_RAG_GENERATION_SCHEMA_VERSION}-{normalized_generation}"
    )


def resolve_legacy_collection_names(
    settings: RagRuntimeSettings,
    *,
    source_kinds: list[str] | None = None,
) -> tuple[str, ...]:
    resource_types = resolve_rag_resource_types_for_source_kinds(source_kinds or [])
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


def get_rag_runtime_health(db: Session | None = None) -> dict[str, object]:
    settings = get_settings()
    if not settings.rag_enabled:
        return _attach_queue_health(
            {
                "enabled": False,
                "ready": True,
                "collection": None,
                "providers": [],
            },
            db=db,
            lease_seconds=settings.rag_job_processing_lease_seconds,
        )

    try:
        providers = build_provider_bundle(settings)
    except Exception as error:
        return _attach_queue_health(
            {
                "enabled": True,
                "ready": False,
                "collection": resolve_default_collection_name(settings),
                "detail": str(error),
                "providers": [],
            },
            db=db,
            lease_seconds=settings.rag_job_processing_lease_seconds,
        )

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
        return _attach_queue_health(
            {
                "enabled": True,
                "ready": False,
                "collection": resolve_default_collection_name(settings),
                "detail": str(error),
                "providers": _serialize_provider_healths(
                    provider_healths if "provider_healths" in locals() else []
                ),
            },
            db=db,
            lease_seconds=settings.rag_job_processing_lease_seconds,
        )

    _close_provider_bundle(providers)
    return _attach_queue_health(
        {
            "enabled": True,
            "ready": all(item.ready for item in provider_healths),
            "collection": resolve_default_collection_name(settings),
            "providers": _serialize_provider_healths(provider_healths),
        },
        db=db,
        lease_seconds=settings.rag_job_processing_lease_seconds,
    )


def attach_rag_queue_health(
    health: dict[str, object],
    *,
    db: Session,
) -> dict[str, object]:
    """Attach queue readiness while holding a DB session only for queue SQL."""

    return _attach_queue_health(
        health,
        db=db,
        lease_seconds=get_settings().rag_job_processing_lease_seconds,
    )


def _attach_queue_health(
    health: dict[str, object],
    *,
    db: Session | None,
    lease_seconds: int,
) -> dict[str, object]:
    if db is None or not health["enabled"]:
        health["queues"] = {
            "observed": db is not None,
            "ready": True,
            "processing_lease_seconds": lease_seconds,
            "lanes": [],
        }
        return health
    try:
        queues = get_rag_queue_health(
            db,
            processing_lease_seconds=lease_seconds,
        )
    except Exception:
        logger.exception("RAG queue readiness query failed")
        queues = {
            "observed": True,
            "ready": False,
            "processing_lease_seconds": lease_seconds,
            "lanes": [],
            "detail": "RAG queue health is unavailable.",
        }
    health["queues"] = queues
    health["ready"] = bool(health["ready"]) and bool(queues["ready"])
    return health


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
    get_retrieval_candidate_query_service.cache_clear()
    get_partitioned_retrieval_candidate_query_service.cache_clear()


def preload_rag_runtime(
    settings: RagRuntimeSettings | None = None,
    *,
    providers: RagProviderBundle | None = None,
) -> dict[str, object]:
    resolved_settings = settings or get_settings()
    if not resolved_settings.rag_enabled:
        return {
            "enabled": False,
            "ready": True,
            "collection": None,
            "providers": [],
        }
    if not resolved_settings.rag_preload_on_startup:
        return {
            "enabled": True,
            "ready": True,
            "collection": resolve_default_collection_name(resolved_settings),
            "providers": [],
            "detail": "RAG preload disabled.",
        }

    resolved_providers = providers or get_provider_bundle()
    try:
        for provider in (
            resolved_providers.embedding,
            resolved_providers.rerank,
            resolved_providers.ocr,
            resolved_providers.asr,
        ):
            preload = getattr(provider, "preload", None)
            if callable(preload):
                preload()
        collection = ensure_default_collection_ready(
            resolved_settings,
            providers=resolved_providers,
        )
        provider_healths = [
            provider.healthcheck()
            for provider in (
                resolved_providers.vector_index,
                resolved_providers.embedding,
                resolved_providers.rerank,
                resolved_providers.ocr,
            )
            if provider is not None
        ]
    except Exception as error:
        if resolved_settings.rag_fail_startup_on_preload_error:
            raise
        logger.warning("RAG runtime preload failed: %s", error)
        return {
            "enabled": True,
            "ready": False,
            "collection": resolve_default_collection_name(resolved_settings),
            "detail": str(error),
            "providers": [],
        }

    return {
        "enabled": True,
        "ready": all(item.ready for item in provider_healths),
        "collection": collection,
        "providers": _serialize_provider_healths(provider_healths),
    }


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
