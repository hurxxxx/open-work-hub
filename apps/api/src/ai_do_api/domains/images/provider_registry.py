from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ImageProviderRouteMode = Literal["local", "external"]
ImageProviderCredentialKind = Literal["none", "api_key"]


@dataclass(frozen=True)
class ImageProviderDescriptor:
    provider_id: str
    display_name: str
    route_mode: ImageProviderRouteMode
    credential_kind: ImageProviderCredentialKind
    default_endpoint_url: str | None
    adapter_id: str


_descriptors: dict[str, ImageProviderDescriptor] = {}


def normalize_image_provider_id(value: str | None) -> str:
    return str(value or "").strip().lower()


def normalize_image_adapter_id(value: str | None) -> str:
    return str(value or "").strip().lower()


def register_image_provider(descriptor: ImageProviderDescriptor) -> None:
    provider_id = normalize_image_provider_id(descriptor.provider_id)
    adapter_id = normalize_image_adapter_id(descriptor.adapter_id)
    if not provider_id:
        raise ValueError("Image provider id is required")
    if not descriptor.display_name.strip():
        raise ValueError(f"Image provider {provider_id} display name is required")
    if not adapter_id:
        raise ValueError(f"Image provider {provider_id} adapter id is required")
    if descriptor.route_mode not in ("local", "external"):
        raise ValueError(f"Image provider {provider_id} route mode is invalid")
    if descriptor.credential_kind not in ("none", "api_key"):
        raise ValueError(f"Image provider {provider_id} credential kind is invalid")
    if provider_id in _descriptors:
        raise ValueError(f"Image provider already registered: {provider_id}")
    _descriptors[provider_id] = ImageProviderDescriptor(
        provider_id=provider_id,
        display_name=descriptor.display_name.strip(),
        route_mode=descriptor.route_mode,
        credential_kind=descriptor.credential_kind,
        default_endpoint_url=(descriptor.default_endpoint_url or "").strip().rstrip("/") or None,
        adapter_id=adapter_id,
    )


def image_provider_descriptor(provider_id: str) -> ImageProviderDescriptor | None:
    return _descriptors.get(normalize_image_provider_id(provider_id))


def image_provider_descriptors() -> tuple[ImageProviderDescriptor, ...]:
    return tuple(_descriptors[provider_id] for provider_id in sorted(_descriptors))


def image_provider_ids() -> tuple[str, ...]:
    return tuple(descriptor.provider_id for descriptor in image_provider_descriptors())


def ensure_builtin_image_providers_registered() -> None:
    if "openai" not in _descriptors:
        register_image_provider(
            ImageProviderDescriptor(
                provider_id="openai",
                display_name="OpenAI",
                route_mode="external",
                credential_kind="api_key",
                default_endpoint_url="https://api.openai.com/v1",
                adapter_id="openai",
            )
        )


def reset_image_providers() -> None:
    _descriptors.clear()


__all__ = [
    "ImageProviderCredentialKind",
    "ImageProviderDescriptor",
    "ImageProviderRouteMode",
    "ensure_builtin_image_providers_registered",
    "image_provider_descriptor",
    "image_provider_descriptors",
    "image_provider_ids",
    "normalize_image_adapter_id",
    "normalize_image_provider_id",
    "register_image_provider",
    "reset_image_providers",
]
