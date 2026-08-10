from __future__ import annotations

from typing import TYPE_CHECKING

from ai_do_api.domains.rag.providers.base import (
    AsrClient,
    EmbeddingClient,
    OcrClient,
    RagProviderConfigurationError,
    RagProviderBundle,
    RerankClient,
    VectorIndexClient,
)
from ai_do_api.domains.rag.providers.fake import (
    FakeAsrClient,
    FakeEmbeddingClient,
    FakeOcrClient,
    FakeRerankClient,
    FakeVectorIndexClient,
)
from ai_do_api.domains.rag.providers.local import (
    DoclingOcrClient,
    LocalCrossEncoderRerankClient,
    LocalSentenceTransformerEmbeddingClient,
)
from ai_do_api.domains.rag.providers.openai_compatible import (
    InferenceGatewayOcrClient,
    OpenAICompatibleEmbeddingClient,
    OpenAICompatibleRerankClient,
    RagProviderError,
    RagProviderTimeoutError,
    RagProviderTransientError,
)

if TYPE_CHECKING:
    from ai_do_api.domains.rag.providers.qdrant import QdrantVectorIndexClient

__all__ = [
    "AsrClient",
    "DoclingOcrClient",
    "EmbeddingClient",
    "FakeAsrClient",
    "FakeEmbeddingClient",
    "FakeOcrClient",
    "FakeRerankClient",
    "FakeVectorIndexClient",
    "LocalCrossEncoderRerankClient",
    "InferenceGatewayOcrClient",
    "LocalSentenceTransformerEmbeddingClient",
    "OpenAICompatibleEmbeddingClient",
    "OpenAICompatibleRerankClient",
    "OcrClient",
    "QdrantVectorIndexClient",
    "RagProviderConfigurationError",
    "RagProviderBundle",
    "RagProviderError",
    "RagProviderTimeoutError",
    "RagProviderTransientError",
    "RerankClient",
    "VectorIndexClient",
]


def __getattr__(name: str):
    if name == "QdrantVectorIndexClient":
        from ai_do_api.domains.rag.providers.qdrant import QdrantVectorIndexClient

        return QdrantVectorIndexClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
