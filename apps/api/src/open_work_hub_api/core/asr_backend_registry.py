from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from open_work_hub_api.core.asr_contracts import ASRBackend


ASRBackendBuilder = Callable[[Any], ASRBackend]


@dataclass(frozen=True)
class ASRBackendDescriptor:
    backend: str
    builder: ASRBackendBuilder
    label: str = ""


_backends_by_name: dict[str, ASRBackendDescriptor] = {}


def normalize_asr_backend_name(value: object) -> str:
    return str(value or "").strip().lower()


def register_asr_backend(descriptor: ASRBackendDescriptor) -> None:
    normalized = _normalize_descriptor(descriptor)
    existing = _backends_by_name.get(normalized.backend)
    if existing is not None and existing != normalized:
        raise ValueError(f"ASR backend already registered: {normalized.backend}")
    _backends_by_name[normalized.backend] = normalized


def get_asr_backend_descriptor(backend: object) -> ASRBackendDescriptor | None:
    return _backends_by_name.get(normalize_asr_backend_name(backend))


def has_asr_backend(backend: object) -> bool:
    return get_asr_backend_descriptor(backend) is not None


def asr_backend_names() -> tuple[str, ...]:
    return tuple(sorted(_backends_by_name))


def build_registered_asr_backend(backend: object, settings: Any) -> ASRBackend:
    normalized = normalize_asr_backend_name(backend)
    descriptor = _backends_by_name.get(normalized)
    if descriptor is None:
        raise LookupError(f"ASR backend is not registered: {normalized}")
    return descriptor.builder(settings)


def reset_asr_backends() -> None:
    _backends_by_name.clear()


def _normalize_descriptor(descriptor: ASRBackendDescriptor) -> ASRBackendDescriptor:
    backend = normalize_asr_backend_name(descriptor.backend)
    if not backend:
        raise ValueError("ASR backend name must not be empty")
    label = descriptor.label.strip() or backend
    return ASRBackendDescriptor(
        backend=backend,
        builder=descriptor.builder,
        label=label,
    )


__all__ = [
    "ASRBackendDescriptor",
    "asr_backend_names",
    "build_registered_asr_backend",
    "get_asr_backend_descriptor",
    "has_asr_backend",
    "normalize_asr_backend_name",
    "register_asr_backend",
    "reset_asr_backends",
]
