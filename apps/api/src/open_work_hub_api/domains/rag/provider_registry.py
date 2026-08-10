from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from open_work_hub_api.domains.rag.providers.base import RagProviderConfigurationError


SettingsT = TypeVar("SettingsT")
ProviderT = TypeVar("ProviderT")


@dataclass(frozen=True)
class RagProviderDescriptor(Generic[SettingsT, ProviderT]):
    names: tuple[str, ...]
    builder: Callable[[SettingsT], ProviderT]
    collection_model_resolver: Callable[[SettingsT], str | None] | None = None


class RagProviderRegistry(Generic[SettingsT]):
    def __init__(self) -> None:
        self._vector_index_builders: dict[str, Callable[[SettingsT], object]] = {}
        self._embedding_builders: dict[str, Callable[[SettingsT], object]] = {}
        self._embedding_collection_model_resolvers: dict[
            str,
            Callable[[SettingsT], str | None],
        ] = {}
        self._rerank_builders: dict[str, Callable[[SettingsT], object | None]] = {}
        self._ocr_builders: dict[str, Callable[[SettingsT], object | None]] = {}

    def register_vector_index(self, descriptor: RagProviderDescriptor[SettingsT, object]) -> None:
        self._register(self._vector_index_builders, "vector index", descriptor)

    def register_embedding(self, descriptor: RagProviderDescriptor[SettingsT, object]) -> None:
        self._register(self._embedding_builders, "embedding", descriptor)
        if descriptor.collection_model_resolver is None:
            return
        for raw_name in descriptor.names:
            name = _normalize_provider_name(raw_name)
            self._embedding_collection_model_resolvers[
                name
            ] = descriptor.collection_model_resolver

    def register_rerank(self, descriptor: RagProviderDescriptor[SettingsT, object | None]) -> None:
        self._register(self._rerank_builders, "rerank", descriptor)

    def register_ocr(self, descriptor: RagProviderDescriptor[SettingsT, object | None]) -> None:
        self._register(self._ocr_builders, "OCR", descriptor)

    def build_vector_index(self, provider_name: str, settings: SettingsT) -> object:
        return self._build(self._vector_index_builders, "vector index", provider_name, settings)

    def build_embedding(self, provider_name: str, settings: SettingsT) -> object:
        return self._build(self._embedding_builders, "embedding", provider_name, settings)

    def build_rerank(self, provider_name: str, settings: SettingsT) -> object | None:
        return self._build(self._rerank_builders, "rerank", provider_name, settings)

    def build_ocr(self, provider_name: str, settings: SettingsT) -> object | None:
        return self._build(self._ocr_builders, "OCR", provider_name, settings)

    def vector_index_provider_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._vector_index_builders))

    def embedding_provider_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._embedding_builders))

    def embedding_collection_model_name(
        self,
        provider_name: str,
        settings: SettingsT,
    ) -> str:
        provider_name = _normalize_provider_name(provider_name)
        if provider_name not in self._embedding_builders:
            raise RagProviderConfigurationError(
                f"Unsupported RAG embedding provider: {provider_name}"
            )
        resolver = self._embedding_collection_model_resolvers.get(provider_name)
        if resolver is None:
            return provider_name
        return resolver(settings) or provider_name

    def rerank_provider_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._rerank_builders))

    def ocr_provider_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._ocr_builders))

    @staticmethod
    def _register(
        builders: dict[str, Callable[[SettingsT], ProviderT]],
        provider_kind: str,
        descriptor: RagProviderDescriptor[SettingsT, ProviderT],
    ) -> None:
        for raw_name in descriptor.names:
            name = _normalize_provider_name(raw_name)
            if name in builders:
                raise RagProviderConfigurationError(
                    f"RAG {provider_kind} provider is already registered: {name}"
                )
            builders[name] = descriptor.builder

    @staticmethod
    def _build(
        builders: dict[str, Callable[[SettingsT], ProviderT]],
        provider_kind: str,
        provider_name: str,
        settings: SettingsT,
    ) -> ProviderT:
        provider_name = _normalize_provider_name(provider_name)
        builder = builders.get(provider_name)
        if builder is None:
            raise RagProviderConfigurationError(f"Unsupported RAG {provider_kind} provider: {provider_name}")
        return builder(settings)


def _normalize_provider_name(value: object) -> str:
    return str(value or "").strip().lower()


__all__ = ["RagProviderDescriptor", "RagProviderRegistry"]
