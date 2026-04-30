from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from aidoo_api.core.settings import Settings, get_settings


AI_MANAGER_ADAPTER_ID = "openai_agents_ai_manager.v1"

AiManagerDisabledReason = Literal[
    "feature_disabled",
    "unsupported_provider",
    "model_not_configured",
]


@dataclass(frozen=True, slots=True)
class AiManagerConfig:
    adapter_id: str
    enabled: bool
    ready: bool
    disabled_reason: AiManagerDisabledReason | None
    provider: str
    model: str
    max_loops: int
    trace_sensitive_data: bool
    store_response: bool
    hosted_tools_enabled: bool

    @property
    def safety_defaults_enabled(self) -> bool:
        return (
            not self.trace_sensitive_data
            and not self.store_response
            and not self.hosted_tools_enabled
        )

    def public_summary(self) -> dict[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "enabled": self.enabled,
            "ready": self.ready,
            "disabled_reason": self.disabled_reason,
            "provider": self.provider,
            "model_configured": bool(self.model),
            "max_loops": self.max_loops,
            "trace_sensitive_data": self.trace_sensitive_data,
            "store_response": self.store_response,
            "hosted_tools_enabled": self.hosted_tools_enabled,
        }


def build_ai_manager_config(settings: Settings | None = None) -> AiManagerConfig:
    resolved_settings = settings or get_settings()
    enabled = bool(resolved_settings.ai_manager_enabled)
    provider = resolved_settings.ai_manager_provider.strip().lower()
    model = resolved_settings.ai_manager_model.strip()
    disabled_reason = _disabled_reason(
        enabled=enabled,
        provider=provider,
        model=model,
    )

    return AiManagerConfig(
        adapter_id=AI_MANAGER_ADAPTER_ID,
        enabled=enabled,
        ready=disabled_reason is None,
        disabled_reason=disabled_reason,
        provider=provider,
        model=model,
        max_loops=resolved_settings.ai_manager_max_loops,
        trace_sensitive_data=resolved_settings.ai_manager_trace_sensitive_data,
        store_response=resolved_settings.ai_manager_store_response,
        hosted_tools_enabled=resolved_settings.ai_manager_hosted_tools_enabled,
    )


def _disabled_reason(
    *,
    enabled: bool,
    provider: str,
    model: str,
) -> AiManagerDisabledReason | None:
    if not enabled:
        return "feature_disabled"
    if provider != "openai":
        return "unsupported_provider"
    if not model:
        return "model_not_configured"
    return None
