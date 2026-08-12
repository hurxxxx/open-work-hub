from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from open_work_hub_api.core.llm_provider_registry import external_llm_provider_descriptor


LOCAL_DEFAULT_REASONING_EFFORT = "none"
EXTERNAL_DEFAULT_REASONING_EFFORT = "medium"


class LlmProfileConfig(Protocol):
    pool: str
    provider: str


class LlmPayloadExecution(Protocol):
    config: LlmProfileConfig
    chosen_model: str
    resolved_max_tokens: int
    resolved_reasoning_effort: str


ExtraBodyBuilder = Callable[[str | None], dict[str, Any]]


@dataclass(frozen=True)
class LlmGenerationProfile:
    profile_id: str
    pool: str
    provider: str | None
    default_reasoning_effort: str
    extra_body_builder: ExtraBodyBuilder

    def extra_body(self, reasoning_effort: str | None) -> dict[str, Any]:
        return self.extra_body_builder(reasoning_effort)


_profiles_by_key: dict[tuple[str, str | None], LlmGenerationProfile] = {}


def register_llm_generation_profile(profile: LlmGenerationProfile) -> None:
    key = (_normalize_key(profile.pool), _normalize_optional_key(profile.provider))
    if key in _profiles_by_key:
        raise ValueError(f"LLM generation profile already registered for {key}")
    _profiles_by_key[key] = profile


def select_llm_generation_profile(pool: str, provider: str | None) -> LlmGenerationProfile:
    ensure_default_llm_generation_profiles_registered()
    normalized_pool = _normalize_key(pool)
    normalized_provider = _normalize_optional_key(provider)
    profile = _profiles_by_key.get((normalized_pool, normalized_provider))
    if profile is not None:
        return profile
    if _can_use_pool_fallback(normalized_pool, normalized_provider):
        profile = _profiles_by_key.get((normalized_pool, None))
        if profile is not None:
            return profile
    raise ValueError(
        f"no LLM generation profile registered for {normalized_pool}/{normalized_provider}"
    )


def resolve_reasoning_effort(
    pool: str,
    provider: str | None,
    *,
    reasoning_effort: str | None,
) -> str:
    profile = select_llm_generation_profile(pool, provider)
    return reasoning_effort or profile.default_reasoning_effort


def build_chat_payload(
    execution: LlmPayloadExecution,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None,
    extra_body: Mapping[str, Any] | None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    stream_reasoning: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": execution.chosen_model,
        "messages": messages,
        "max_tokens": execution.resolved_max_tokens,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    effective_reasoning_effort = execution.resolved_reasoning_effort if stream_reasoning else "none"
    profile = select_llm_generation_profile(
        execution.config.pool,
        execution.config.provider,
    )
    merged_extra_body = _merge_extra_body(
        profile.extra_body(effective_reasoning_effort), extra_body
    )
    if merged_extra_body:
        payload["extra_body"] = merged_extra_body
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if parallel_tool_calls is not None:
        payload["parallel_tool_calls"] = parallel_tool_calls
    return payload


def llm_generation_profile_keys() -> tuple[str, ...]:
    ensure_default_llm_generation_profiles_registered()
    return tuple(sorted(f"{pool}:{provider or '*'}" for pool, provider in _profiles_by_key))


def reset_llm_generation_profiles() -> None:
    _profiles_by_key.clear()


def ensure_default_llm_generation_profiles_registered() -> None:
    _register_default_profile(
        LlmGenerationProfile(
            profile_id="local_openai_compatible",
            pool="local",
            provider=None,
            default_reasoning_effort=LOCAL_DEFAULT_REASONING_EFFORT,
            extra_body_builder=_local_extra_body,
        )
    )
    for provider in ("vllm", "vllm-openai"):
        _register_default_profile(
            LlmGenerationProfile(
                profile_id=f"local_{provider}",
                pool="local",
                provider=provider,
                default_reasoning_effort=LOCAL_DEFAULT_REASONING_EFFORT,
                extra_body_builder=_vllm_extra_body,
            )
        )
    _register_default_profile(
        LlmGenerationProfile(
            profile_id="local_docker_model_runner",
            pool="local",
            provider="docker-model-runner",
            default_reasoning_effort=LOCAL_DEFAULT_REASONING_EFFORT,
            # Docker Model Runner forwards Qwen chat-template kwargs. Without
            # this, Qwen can spend the full output budget on hidden reasoning
            # and return an empty presentation body.
            extra_body_builder=_vllm_extra_body,
        )
    )
    _register_default_profile(
        LlmGenerationProfile(
            profile_id="external_openai_compatible",
            pool="external",
            provider=None,
            default_reasoning_effort=EXTERNAL_DEFAULT_REASONING_EFFORT,
            extra_body_builder=_no_extra_body,
        )
    )
    _register_default_profile(
        LlmGenerationProfile(
            profile_id="external_openai",
            pool="external",
            provider="openai",
            default_reasoning_effort=EXTERNAL_DEFAULT_REASONING_EFFORT,
            extra_body_builder=_openai_extra_body,
        )
    )
    for provider in ("anthropic", "gemini"):
        _register_default_profile(
            LlmGenerationProfile(
                profile_id=f"external_{provider}",
                pool="external",
                provider=provider,
                default_reasoning_effort=EXTERNAL_DEFAULT_REASONING_EFFORT,
                extra_body_builder=_no_extra_body,
            )
        )


def _register_default_profile(profile: LlmGenerationProfile) -> None:
    key = (_normalize_key(profile.pool), _normalize_optional_key(profile.provider))
    existing = _profiles_by_key.get(key)
    if existing is not None and existing.profile_id != profile.profile_id:
        return
    _profiles_by_key[key] = profile


def _local_extra_body(reasoning_effort: str | None) -> dict[str, Any]:
    if reasoning_effort == "none":
        return {"think": False}
    if reasoning_effort is None:
        return {}
    return {"reasoning_effort": reasoning_effort}


def _vllm_extra_body(reasoning_effort: str | None) -> dict[str, Any]:
    if reasoning_effort is None:
        return {}
    return {
        "chat_template_kwargs": {
            "enable_thinking": reasoning_effort != "none",
        }
    }


def _openai_extra_body(reasoning_effort: str | None) -> dict[str, Any]:
    if reasoning_effort in (None, "none"):
        return {}
    return {"reasoning_effort": reasoning_effort}


def _no_extra_body(reasoning_effort: str | None) -> dict[str, Any]:
    del reasoning_effort
    return {}


def _merge_extra_body(
    base: Mapping[str, Any], extra: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    if not base and not extra:
        return None
    merged = dict(base)
    if extra:
        merged.update(dict(extra))
    return merged


def _normalize_key(value: str) -> str:
    return (value or "").strip().lower()


def _normalize_optional_key(value: str | None) -> str | None:
    normalized = _normalize_key(value or "")
    return normalized or None


def _can_use_pool_fallback(pool: str, provider: str | None) -> bool:
    if provider is None or pool != "external":
        return True
    descriptor = external_llm_provider_descriptor(provider)
    return bool(descriptor and descriptor.openai_compatible)


__all__ = [
    "LlmGenerationProfile",
    "build_chat_payload",
    "ensure_default_llm_generation_profiles_registered",
    "llm_generation_profile_keys",
    "register_llm_generation_profile",
    "reset_llm_generation_profiles",
    "resolve_reasoning_effort",
    "select_llm_generation_profile",
]
