from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from ai_do_api.core.llm_provider_registry import llm_provider_descriptor


MAX_DISCOVERED_MODELS = 500
MAX_MODEL_KEY_LENGTH = 160
MAX_DISPLAY_NAME_LENGTH = 160


@dataclass(frozen=True, slots=True)
class DiscoveredProviderModel:
    model_key: str
    display_name: str
    capabilities: tuple[str, ...]


class ProviderModelDiscoveryError(RuntimeError):
    """Provider discovery failure that exposes only a stable, non-secret code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


ProviderModelDiscoveryAdapter = Callable[..., Iterable[DiscoveredProviderModel]]
_discovery_adapters: dict[str, ProviderModelDiscoveryAdapter] = {}


def register_provider_model_discovery_adapter(
    adapter_id: str,
    adapter: ProviderModelDiscoveryAdapter,
) -> None:
    normalized = adapter_id.strip().lower()
    if not normalized:
        raise ValueError("Provider model discovery adapter id must not be empty")
    if normalized in _discovery_adapters:
        raise ValueError(f"Provider model discovery adapter already registered: {normalized}")
    _discovery_adapters[normalized] = adapter


def discover_provider_models(
    provider_id: str,
    endpoint_url: str,
    api_key: str | None,
    timeout_seconds: float,
) -> tuple[DiscoveredProviderModel, ...]:
    """List models visible to one configured provider credential."""

    descriptor = llm_provider_descriptor(provider_id)
    if descriptor is None or not descriptor.discovery_adapter_id:
        raise ProviderModelDiscoveryError("provider_not_supported")

    endpoint = endpoint_url.strip().rstrip("/")
    if not endpoint:
        raise ProviderModelDiscoveryError("endpoint_required")

    key = (api_key or "").strip()
    if descriptor.credential_kind == "api_key" and not key:
        raise ProviderModelDiscoveryError("api_key_required")
    if timeout_seconds <= 0:
        raise ProviderModelDiscoveryError("timeout_invalid")

    try:
        _ensure_default_discovery_adapters_registered()
        adapter = _discovery_adapters.get(descriptor.discovery_adapter_id)
        if adapter is None:
            raise ProviderModelDiscoveryError("provider_not_supported")
        candidates = adapter(
            endpoint_url=endpoint,
            api_key=key,
            timeout_seconds=timeout_seconds,
        )
        return _normalize_candidates(candidates)
    except ProviderModelDiscoveryError:
        raise
    except Exception:
        # Provider exceptions can contain request URLs, headers, or response bodies.
        raise ProviderModelDiscoveryError("provider_unavailable") from None


def _discover_openai_compatible_models(
    *,
    endpoint_url: str,
    api_key: str,
    timeout_seconds: float,
) -> Iterable[DiscoveredProviderModel]:
    client = _new_openai_client(
        endpoint_url=endpoint_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    try:
        for model in client.models.list():
            model_key = getattr(model, "id", "")
            yield DiscoveredProviderModel(
                model_key=str(model_key),
                display_name=str(model_key),
                # The OpenAI models response does not advertise modality or tool support.
                capabilities=(),
            )
    finally:
        _close_client(client)


def _discover_anthropic_models(
    *,
    endpoint_url: str,
    api_key: str,
    timeout_seconds: float,
) -> Iterable[DiscoveredProviderModel]:
    client = _new_anthropic_client(
        endpoint_url=endpoint_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    try:
        for model in client.models.list(limit=100):
            model_key = getattr(model, "id", "")
            display_name = getattr(model, "display_name", "")
            yield DiscoveredProviderModel(
                model_key=str(model_key),
                display_name=str(display_name or model_key),
                capabilities=("chat",),
            )
    finally:
        _close_client(client)


def _discover_gemini_models(
    *,
    endpoint_url: str,
    api_key: str,
    timeout_seconds: float,
) -> Iterable[DiscoveredProviderModel]:
    client = _new_gemini_client(
        endpoint_url=endpoint_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    try:
        from google.genai import types

        for model in client.models.list(config=types.ListModelsConfig(page_size=100)):
            model_key = str(getattr(model, "name", ""))
            if model_key.startswith("models/"):
                model_key = model_key.removeprefix("models/")
            display_name = getattr(model, "display_name", "")
            supported_actions = {
                str(action) for action in (getattr(model, "supported_actions", None) or ())
            }
            capabilities = ("chat",) if "generateContent" in supported_actions else ()
            yield DiscoveredProviderModel(
                model_key=model_key,
                display_name=str(display_name or model_key),
                capabilities=capabilities,
            )
    finally:
        _close_client(client)


def _ensure_default_discovery_adapters_registered() -> None:
    for adapter_id, adapter in (
        ("openai_compatible", _discover_openai_compatible_models),
        ("anthropic", _discover_anthropic_models),
        ("gemini", _discover_gemini_models),
    ):
        _discovery_adapters.setdefault(adapter_id, adapter)


def _normalize_candidates(
    candidates: Iterable[DiscoveredProviderModel],
) -> tuple[DiscoveredProviderModel, ...]:
    normalized: list[DiscoveredProviderModel] = []
    seen: set[str] = set()
    for candidate in candidates:
        model_key = candidate.model_key.strip()
        if not model_key or len(model_key) > MAX_MODEL_KEY_LENGTH or model_key in seen:
            continue
        display_name = candidate.display_name.strip() or model_key
        display_name = display_name[:MAX_DISPLAY_NAME_LENGTH]
        capabilities = tuple(
            dict.fromkeys(
                capability.strip() for capability in candidate.capabilities if capability.strip()
            )
        )
        normalized.append(
            DiscoveredProviderModel(
                model_key=model_key,
                display_name=display_name,
                capabilities=capabilities,
            )
        )
        seen.add(model_key)
        if len(normalized) >= MAX_DISCOVERED_MODELS:
            break
    return tuple(normalized)


def _new_openai_client(*, endpoint_url: str, api_key: str, timeout_seconds: float) -> Any:
    from openai import OpenAI

    return OpenAI(
        api_key=api_key or "local-no-key",
        base_url=endpoint_url,
        timeout=timeout_seconds,
    )


def _new_anthropic_client(*, endpoint_url: str, api_key: str, timeout_seconds: float) -> Any:
    from anthropic import Anthropic

    return Anthropic(
        api_key=api_key,
        base_url=endpoint_url,
        timeout=timeout_seconds,
    )


def _new_gemini_client(*, endpoint_url: str, api_key: str, timeout_seconds: float) -> Any:
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            base_url=endpoint_url,
            timeout=max(1, int(timeout_seconds * 1000)),
        ),
    )


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


__all__ = [
    "DiscoveredProviderModel",
    "ProviderModelDiscoveryError",
    "discover_provider_models",
    "register_provider_model_discovery_adapter",
]
