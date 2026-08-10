from __future__ import annotations

from functools import lru_cache
from typing import cast
from typing import Protocol

from open_alm_api.domains.rag.providers import (
    DoclingOcrClient,
    FakeEmbeddingClient,
    FakeOcrClient,
    InferenceGatewayOcrClient,
    LocalCrossEncoderRerankClient,
    LocalSentenceTransformerEmbeddingClient,
    OpenAICompatibleEmbeddingClient,
    OpenAICompatibleRerankClient,
    QdrantVectorIndexClient,
    RagProviderBundle,
)
from open_alm_api.domains.rag.providers.base import (
    EmbeddingClient,
    OcrClient,
    RagProviderConfigurationError,
    RerankClient,
    VectorIndexClient,
)
from open_alm_api.domains.rag.providers.fake import FakeRerankClient, FakeVectorIndexClient
from open_alm_api.domains.rag.provider_registry import RagProviderDescriptor, RagProviderRegistry


class RagRuntimeSettings(Protocol):
    rag_enabled: bool
    rag_vector_index_provider: str
    rag_embedding_provider: str
    rag_rerank_provider: str
    rag_ocr_provider: str
    rag_rerank_candidate_k: int
    rag_preload_on_startup: bool
    rag_fail_startup_on_preload_error: bool
    rag_query_timeout_ms: int
    rag_qdrant_url: str
    rag_qdrant_api_key: str
    rag_qdrant_collection_prefix: str
    rag_local_embedding_model: str
    rag_local_embedding_revision: str | None
    rag_local_embedding_device: str
    rag_local_embedding_dtype: str
    rag_local_embedding_batch_size: int
    rag_local_embedding_max_seq_length: int
    rag_local_embedding_normalize: bool
    rag_local_embedding_query_prompt_name: str
    rag_local_embedding_query_prefix: str
    rag_local_embedding_trust_remote_code: bool
    rag_local_reranker_model: str
    rag_local_reranker_revision: str | None
    rag_local_reranker_device: str
    rag_local_reranker_dtype: str
    rag_local_reranker_batch_size: int
    rag_local_reranker_max_length: int
    rag_local_reranker_trust_remote_code: bool
    inference_gateway_base_url: str
    inference_gateway_api_key: str
    rag_docling_force_ocr: bool
    rag_docling_ocr_engine: str
    rag_docling_ocr_langs: str
    rag_docling_min_text_chars: int


_LOCAL_EMBEDDING_PROVIDERS = {"local", "local_sentence_transformers", "sentence_transformers"}
_LOCAL_RERANK_PROVIDERS = {"local", "local_cross_encoder", "cross_encoder"}
_DOCLING_OCR_PROVIDERS = {"docling", "local_docling", "docling_easyocr"}
_INFERENCE_GATEWAY_PROVIDER = "inference_gateway"


class RagProviderFactory:
    def __init__(self, settings: RagRuntimeSettings) -> None:
        self._settings = settings

    def build_bundle(self) -> RagProviderBundle:
        return RagProviderBundle(
            vector_index=self.build_vector_index(),
            embedding=self.build_embedding(),
            ocr=self.build_ocr(),
            rerank=self.build_rerank(),
        )

    def build_vector_index(self) -> VectorIndexClient:
        settings = self._settings
        return cast(
            VectorIndexClient,
            get_rag_provider_registry().build_vector_index(
                settings.rag_vector_index_provider,
                settings,
            ),
        )

    def build_embedding(self) -> EmbeddingClient:
        settings = self._settings
        return cast(
            EmbeddingClient,
            get_rag_provider_registry().build_embedding(
                settings.rag_embedding_provider,
                settings,
            ),
        )

    def build_rerank(self) -> RerankClient | None:
        settings = self._settings
        return cast(
            RerankClient | None,
            get_rag_provider_registry().build_rerank(
                settings.rag_rerank_provider,
                settings,
            ),
        )

    def build_ocr(self) -> OcrClient | None:
        settings = self._settings
        return cast(
            OcrClient | None,
            get_rag_provider_registry().build_ocr(
                settings.rag_ocr_provider,
                settings,
            ),
        )


@lru_cache(maxsize=1)
def get_rag_provider_registry() -> RagProviderRegistry[RagRuntimeSettings]:
    registry = RagProviderRegistry[RagRuntimeSettings]()
    _register_builtin_rag_providers(registry)
    return registry


def _register_builtin_rag_providers(registry: RagProviderRegistry[RagRuntimeSettings]) -> None:
    registry.register_vector_index(
        RagProviderDescriptor(names=("fake",), builder=lambda settings: FakeVectorIndexClient())
    )
    registry.register_vector_index(
        RagProviderDescriptor(names=("qdrant",), builder=_build_qdrant_vector_index)
    )
    registry.register_embedding(
        RagProviderDescriptor(
            names=("fake",),
            builder=lambda settings: FakeEmbeddingClient(dimensions=1024),
        )
    )
    registry.register_embedding(
        RagProviderDescriptor(
            names=tuple(sorted(_LOCAL_EMBEDDING_PROVIDERS)),
            builder=_build_local_embedding,
            collection_model_resolver=_configured_embedding_model,
        )
    )
    registry.register_embedding(
        RagProviderDescriptor(
            names=(_INFERENCE_GATEWAY_PROVIDER,),
            builder=_build_inference_gateway_embedding,
            collection_model_resolver=_configured_embedding_model,
        )
    )
    registry.register_rerank(
        RagProviderDescriptor(names=("", "none", "disabled"), builder=lambda settings: None)
    )
    registry.register_rerank(
        RagProviderDescriptor(names=("fake",), builder=lambda settings: FakeRerankClient())
    )
    registry.register_rerank(
        RagProviderDescriptor(
            names=tuple(sorted(_LOCAL_RERANK_PROVIDERS)),
            builder=_build_local_rerank,
        )
    )
    registry.register_rerank(
        RagProviderDescriptor(
            names=(_INFERENCE_GATEWAY_PROVIDER,),
            builder=_build_inference_gateway_rerank,
        )
    )
    registry.register_ocr(
        RagProviderDescriptor(names=("", "none", "disabled"), builder=lambda settings: None)
    )
    registry.register_ocr(
        RagProviderDescriptor(
            names=("fake", "local_stub"), builder=lambda settings: FakeOcrClient()
        )
    )
    registry.register_ocr(
        RagProviderDescriptor(
            names=tuple(sorted(_DOCLING_OCR_PROVIDERS)),
            builder=_build_docling_ocr,
        )
    )
    registry.register_ocr(
        RagProviderDescriptor(
            names=(_INFERENCE_GATEWAY_PROVIDER,),
            builder=_build_inference_gateway_ocr,
        )
    )


def _build_qdrant_vector_index(settings: RagRuntimeSettings) -> VectorIndexClient:
    if not settings.rag_qdrant_url:
        raise RagProviderConfigurationError(
            "OPEN_ALM_RAG_QDRANT_URL is required when rag_vector_index_provider=qdrant"
        )
    return QdrantVectorIndexClient(
        url=settings.rag_qdrant_url,
        api_key=settings.rag_qdrant_api_key or None,
    )


def _build_local_embedding(settings: RagRuntimeSettings) -> EmbeddingClient:
    return LocalSentenceTransformerEmbeddingClient(
        model_name=settings.rag_local_embedding_model,
        revision=settings.rag_local_embedding_revision,
        device=settings.rag_local_embedding_device,
        dtype=settings.rag_local_embedding_dtype,
        batch_size=settings.rag_local_embedding_batch_size,
        max_seq_length=settings.rag_local_embedding_max_seq_length,
        normalize_embeddings=settings.rag_local_embedding_normalize,
        query_prompt_name=settings.rag_local_embedding_query_prompt_name,
        query_prefix=settings.rag_local_embedding_query_prefix,
        trust_remote_code=settings.rag_local_embedding_trust_remote_code,
        keep_loaded=True,
    )


def _build_inference_gateway_embedding(settings: RagRuntimeSettings) -> EmbeddingClient:
    return OpenAICompatibleEmbeddingClient(
        base_url=inference_gateway_v1_base_url(settings),
        api_key=inference_gateway_api_key(settings),
        model=settings.rag_local_embedding_model,
        provider_name="inference-gateway-embedding",
        query_input_type="query",
        query_prompt_name=settings.rag_local_embedding_query_prompt_name,
        max_batch_size=settings.rag_local_embedding_batch_size,
    )


def _build_local_rerank(settings: RagRuntimeSettings) -> RerankClient:
    return LocalCrossEncoderRerankClient(
        model_name=settings.rag_local_reranker_model,
        revision=settings.rag_local_reranker_revision,
        device=settings.rag_local_reranker_device,
        dtype=settings.rag_local_reranker_dtype,
        batch_size=settings.rag_local_reranker_batch_size,
        max_length=settings.rag_local_reranker_max_length,
        trust_remote_code=settings.rag_local_reranker_trust_remote_code,
        keep_loaded=True,
    )


def _build_inference_gateway_rerank(settings: RagRuntimeSettings) -> RerankClient:
    return OpenAICompatibleRerankClient(
        base_url=inference_gateway_v1_base_url(settings),
        api_key=inference_gateway_api_key(settings),
        model=settings.rag_local_reranker_model,
        provider_name="inference-gateway-rerank",
        score_semantics="normalized_relevance",
    )


def _build_docling_ocr(settings: RagRuntimeSettings) -> OcrClient:
    return DoclingOcrClient(
        force_ocr=settings.rag_docling_force_ocr,
        ocr_engine=settings.rag_docling_ocr_engine,
        ocr_langs=split_csv(settings.rag_docling_ocr_langs),
        min_text_chars=settings.rag_docling_min_text_chars,
    )


def _build_inference_gateway_ocr(settings: RagRuntimeSettings) -> OcrClient:
    return InferenceGatewayOcrClient(
        base_url=inference_gateway_v1_base_url(settings),
        api_key=inference_gateway_api_key(settings),
    )


def is_qdrant_vector_index(settings: RagRuntimeSettings) -> bool:
    return settings.rag_vector_index_provider == "qdrant"


def embedding_provider_collection_model_name(settings: RagRuntimeSettings) -> str:
    return get_rag_provider_registry().embedding_collection_model_name(
        settings.rag_embedding_provider,
        settings,
    )


def _configured_embedding_model(settings: RagRuntimeSettings) -> str | None:
    return settings.rag_local_embedding_model


def inference_gateway_v1_base_url(settings: RagRuntimeSettings) -> str:
    base_url = settings.inference_gateway_base_url.rstrip("/")
    if not base_url:
        raise RagProviderConfigurationError(
            "OPEN_ALM_INFERENCE_GATEWAY_BASE_URL is required when using provider=inference_gateway"
        )
    return base_url if base_url.endswith("/v1") else f"{base_url}/v1"


def inference_gateway_api_key(settings: RagRuntimeSettings) -> str:
    return settings.inference_gateway_api_key or "local"


def split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())
