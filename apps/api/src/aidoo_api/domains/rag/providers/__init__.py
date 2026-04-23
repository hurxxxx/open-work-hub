from __future__ import annotations

from typing import TYPE_CHECKING

from aidoo_api.domains.rag.providers.base import (
    AsrClient,
    EmbeddingClient,
    OcrClient,
    RagProviderConfigurationError,
    RagProviderBundle,
    RerankClient,
    VectorIndexClient,
)
from aidoo_api.domains.rag.providers.fake import (
    FakeAsrClient,
    FakeEmbeddingClient,
    FakeOcrClient,
    FakeRerankClient,
    FakeVectorIndexClient,
)
from aidoo_api.domains.rag.providers.openai_compatible import (
    DeepInfraEmbeddingClient,
    DeepInfraRerankClient,
    OpenAICompatibleEmbeddingClient,
    OpenAICompatibleRerankClient,
    RagProviderError,
    RagProviderTimeoutError,
    RagProviderTransientError,
)

if TYPE_CHECKING:
    from aidoo_api.domains.rag.providers.qdrant import QdrantVectorIndexClient

__all__ = [
    "AsrClient",
    "DeepInfraEmbeddingClient",
    "DeepInfraRerankClient",
    "EmbeddingClient",
    "FakeAsrClient",
    "FakeEmbeddingClient",
    "FakeOcrClient",
    "FakeRerankClient",
    "FakeVectorIndexClient",
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
        from aidoo_api.domains.rag.providers.qdrant import QdrantVectorIndexClient

        return QdrantVectorIndexClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
