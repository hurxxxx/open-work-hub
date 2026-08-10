from __future__ import annotations

from typing import Any, Protocol

from open_work_hub_api.domains.images.model_settings_service import (
    IMAGE_EXECUTION_PROFILE_VERSION,
    image_provider_credential_ref,
)


class ResolvedImageExecutionSettings(Protocol):
    provider_id: str
    adapter_id: str
    supervisor_model_id: str
    generation_model_id: str
    generation_web_search_enabled: bool
    max_iterations: int


def build_image_execution_profile(
    record: Any,
    resolved: ResolvedImageExecutionSettings,
    *,
    max_reference_uploads: int,
) -> dict[str, Any]:
    style = _mapping(getattr(record, "style", None))
    layout = _mapping(getattr(record, "layout", None))
    return {
        "version": IMAGE_EXECUTION_PROFILE_VERSION,
        "provider_id": resolved.provider_id,
        "adapter_id": resolved.adapter_id,
        "credential_ref": image_provider_credential_ref(resolved.provider_id),
        "supervisor_model_id": resolved.supervisor_model_id,
        "generation_model_id": resolved.generation_model_id,
        "requested_options": {
            "background": str(style.get("background") or ""),
            "quality": str(style.get("quality") or ""),
            "aspect": str(layout.get("aspect") or ""),
            "web_search_enabled": resolved.generation_web_search_enabled,
            "max_iterations": resolved.max_iterations,
            "max_reference_uploads": max(1, int(max_reference_uploads)),
        },
    }


def image_execution_requested_options(
    execution_profile: dict[str, Any] | None,
    *,
    max_reference_uploads: int,
) -> dict[str, Any]:
    profile = _mapping(execution_profile)
    options = _mapping(profile.get("requested_options"))
    return {
        "background": str(options.get("background") or ""),
        "quality": str(options.get("quality") or ""),
        "aspect": str(options.get("aspect") or ""),
        "web_search_enabled": _profile_bool(
            options.get("web_search_enabled"),
            default=False,
        ),
        "max_iterations": _profile_int(
            options.get("max_iterations"),
            default=1,
            minimum=1,
            maximum=20,
        ),
        "max_reference_uploads": _profile_int(
            options.get("max_reference_uploads"),
            default=max_reference_uploads,
            minimum=1,
            maximum=max_reference_uploads,
        ),
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _profile_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _profile_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return min(maximum, max(minimum, parsed))


__all__ = [
    "IMAGE_EXECUTION_PROFILE_VERSION",
    "build_image_execution_profile",
    "image_execution_requested_options",
]
