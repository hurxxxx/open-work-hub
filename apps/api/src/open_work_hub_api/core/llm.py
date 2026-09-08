"""Provider-neutral LLM transport, generation defaults, and health.

Public surface:

- ``LlmTaskContext`` — identity of an LLM request (source / actor_user_id /
  user_id / task_kind). Mandatory input to ``choose_pool`` and
  ``complete_chat``.
- ``PolicyDecision`` — legacy-compatible execution metadata. Registered
  workloads always record the immutable administrator-selected route here;
  this object does not evaluate AI Security or reroute a request.
- ``get_pool_client(pool)`` / ``get_async_pool_client(pool)`` /
  ``get_pool_config(pool)`` — pool-scoped OpenAI clients + config.
- ``check_pool_health(pool)`` / ``check_all_pools_health()`` — pool-independent
  health. **No cross-pool fallback** in any public function.
- ``check_configured_pools_health()`` — cheap readiness projection for system
  probes. It validates configuration shape without calling model providers.
- ``resolve_registered_chat_execution(...)`` — converts the already-resolved
  workload provider/model/output cap into immutable transport metadata.
- ``complete_chat(context, db, ...)`` / ``complete_chat_stream(...)`` — legacy
  compatibility transports. New domain code enters through the registered
  AI Gateway workload helpers instead of selecting provider/model/pool here.
- ``complete_chat_text(context, db, ...)`` — high-level non-streaming helper for
  domain code that only needs provider-neutral text metadata.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal, Mapping

from openai import (
    AsyncOpenAI,
    OpenAI,
    OpenAIError,
)
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import DEFAULT_LOCALE, LocalizedApiMessage, translate_message
from open_work_hub_api.core.llm_errors import LlmProviderError, LlmRuntimeError
from open_work_hub_api.core.llm_execution_adapters import (
    select_llm_execution_adapter,
)
from open_work_hub_api.core.llm_model_profiles import (
    build_chat_payload,
    resolve_reasoning_effort,
)
from open_work_hub_api.core.llm_pool_config_registry import (
    resolve_llm_pool_config_values,
)
from open_work_hub_api.core.llm_provider_registry import (
    normalize_external_llm_provider_id,
    parse_external_llm_provider_allowlist,
)
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.ai.registry import RegisteredLlmTask, get_ai_capability_registry

logger = logging.getLogger(__name__)


LlmPoolName = Literal["local", "external"]
LlmPoolHint = Literal["local"]
LlmPolicyMode = Literal["local_only", "external"]
ExternalLlmProvider = str
LlmHealthStatus = Literal["ready", "unavailable", "model_missing", "not_configured", "disabled"]
LlmHealthDetail = str | LocalizedApiMessage | None

SupportedLlmTask = RegisteredLlmTask

_FORBIDDEN_LLM_APP_IDS = frozenset({"unknown", "none", "null", "n/a", "na"})


def _normalize_required_llm_app_id(value: object) -> str:
    app_id = str(value or "").strip().lower()
    if not app_id or app_id in _FORBIDDEN_LLM_APP_IDS:
        raise ValueError("LLM app_id is required")
    return app_id


def get_supported_llm_tasks() -> tuple[SupportedLlmTask, ...]:
    registry = get_ai_capability_registry()
    return tuple(
        sorted(
            registry.llm_tasks.values(),
            key=lambda item: item.task_kind,
        )
    )


# ---------------------------------------------------------------------------
# Config + identity types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LlmPoolConfig:
    pool: LlmPoolName
    provider: str
    base_url: str
    api_key: str
    default_model: str
    canonical_model: str
    healthcheck_timeout_seconds: float
    long_generation_timeout_seconds: float
    enabled: bool = True
    default_headers: Mapping[str, str] | None = None
    requires_credentials: bool = True

    @property
    def configured(self) -> bool:
        has_credentials = bool(self.api_key.strip()) or bool(self.default_headers)
        return (
            self.enabled
            and bool(self.base_url.strip())
            and bool(self.default_model.strip())
            and (not self.requires_credentials or has_credentials)
        )


@dataclass(frozen=True)
class LlmTaskContext:
    source: str
    task_kind: str
    app_id: str
    workload_id: str | None = None
    actor_user_id: str | None = None
    principal_kind: Literal["user", "service_account", "system"] = "user"
    principal_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "app_id", _normalize_required_llm_app_id(self.app_id))


@dataclass(frozen=True)
class PolicyDecision:
    policy: LlmPolicyMode
    chosen_pool: LlmPoolName
    pii_hits: list[str] = field(default_factory=list)
    blocked_entity_types: list[str] = field(default_factory=list)
    forced_local: bool = False
    reason: str = ""

    def as_payload(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "chosen_pool": self.chosen_pool,
            "pii_hits": list(self.pii_hits),
            "blocked_entity_types": list(self.blocked_entity_types),
            "forced_local": self.forced_local,
            "decision_reason": self.reason,
        }


@dataclass(frozen=True)
class ResolvedLlmExecution:
    pool: LlmPoolName
    decision: PolicyDecision
    config: LlmPoolConfig
    chosen_model: str
    resolved_max_tokens: int
    resolved_reasoning_effort: str


class LlmModelConfigurationError(LlmRuntimeError):
    def __init__(
        self,
        *,
        requested_model: str,
        pool: LlmPoolName,
        provider: str,
        canonical_model: str,
    ) -> None:
        super().__init__(
            f"requested LLM model is not configured for {pool}/{provider}: {requested_model}"
        )
        self.requested_model = requested_model
        self.pool = pool
        self.provider = provider
        self.canonical_model = canonical_model


@dataclass(frozen=True)
class LlmToolCall:
    id: str | None
    name: str
    arguments: str


@dataclass(frozen=True)
class LlmCompletionResult:
    text: str
    model: str | None
    usage: Mapping[str, int] | None = None
    finish_reason: str | None = None
    tool_calls: tuple[LlmToolCall, ...] = ()


@dataclass(frozen=True)
class LlmPoolHealth:
    pool: LlmPoolName
    provider: str
    base_url: str
    model: str
    canonical_model: str
    status: LlmHealthStatus
    detail: LlmHealthDetail = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def public_dict(
        self,
        *,
        locale: str = DEFAULT_LOCALE,
        include_base_url: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "pool": self.pool,
            "provider": self.provider,
            "model": self.model,
            "canonical_model": self.canonical_model,
            "status": self.status,
            "detail": _render_health_detail(self.detail, locale),
            "ready": self.ready,
        }
        if include_base_url:
            payload["base_url"] = self.base_url
        return payload


@dataclass(frozen=True)
class LlmDualHealth:
    local: LlmPoolHealth
    external: LlmPoolHealth | None
    external_providers: tuple[LlmPoolHealth, ...] = ()

    @property
    def ready(self) -> bool:
        """Overall readiness = local is ready OR external is ready.

        This is a signal for operations dashboards only. It is NOT used to
        decide a route at request time — see ``choose_pool``.
        """
        return (
            self.local.ready
            or bool(self.external and self.external.ready)
            or any(provider.ready for provider in self.external_providers)
        )

    def public_dict(
        self,
        *,
        locale: str = DEFAULT_LOCALE,
        include_base_url: bool = True,
    ) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "local": self.local.public_dict(
                locale=locale,
                include_base_url=include_base_url,
            ),
            "external": (
                self.external.public_dict(
                    locale=locale,
                    include_base_url=include_base_url,
                )
                if self.external
                else None
            ),
            "external_providers": [
                provider.public_dict(
                    locale=locale,
                    include_base_url=include_base_url,
                )
                for provider in self.external_providers
            ],
        }


@dataclass(frozen=True)
class LlmTaskReadiness:
    task_kind: str
    description: str
    policy: LlmPolicyMode
    chosen_pool: LlmPoolName | None
    ready: bool
    detail: LlmHealthDetail = None

    def public_dict(self, *, locale: str = DEFAULT_LOCALE) -> dict[str, Any]:
        return {
            "task_kind": self.task_kind,
            "description": self.description,
            "policy": self.policy,
            "chosen_pool": self.chosen_pool,
            "ready": self.ready,
            "detail": _render_health_detail(self.detail, locale),
        }


@dataclass(frozen=True)
class LlmEffectiveReadiness:
    tasks: tuple[LlmTaskReadiness, ...]

    @property
    def ready(self) -> bool:
        return all(task.ready for task in self.tasks)

    def public_dict(self, *, locale: str = DEFAULT_LOCALE) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "tasks": [task.public_dict(locale=locale) for task in self.tasks],
        }


def _render_health_detail(detail: LlmHealthDetail, locale: str) -> str | None:
    if isinstance(detail, LocalizedApiMessage):
        return translate_message(detail, locale)
    return detail


# ---------------------------------------------------------------------------
# Pool config + client
# ---------------------------------------------------------------------------


def get_pool_config(
    pool: LlmPoolName,
    settings: Settings | None = None,
    *,
    external_provider: str | None = None,
) -> LlmPoolConfig:
    settings = settings or get_settings()
    if pool == "local":
        values = resolve_llm_pool_config_values(
            pool="local",
            provider=None,
            settings=settings,
        )
        return LlmPoolConfig(
            pool="local",
            provider=values.provider,
            base_url=values.base_url,
            api_key=values.api_key,
            default_model=values.default_model,
            canonical_model=values.canonical_model,
            healthcheck_timeout_seconds=settings.llm_request_timeout_seconds,
            long_generation_timeout_seconds=values.long_generation_timeout_seconds,
            enabled=values.enabled,
            default_headers=values.default_headers,
            requires_credentials=values.requires_credentials,
        )

    provider = normalize_external_provider(external_provider, settings=settings)
    values = resolve_llm_pool_config_values(
        pool="external",
        provider=provider,
        settings=settings,
    )
    return LlmPoolConfig(
        pool="external",
        provider=values.provider,
        base_url=values.base_url,
        api_key=values.api_key,
        default_model=values.default_model,
        canonical_model=values.canonical_model,
        healthcheck_timeout_seconds=settings.llm_request_timeout_seconds,
        long_generation_timeout_seconds=values.long_generation_timeout_seconds,
        enabled=values.enabled,
        default_headers=values.default_headers,
        requires_credentials=values.requires_credentials,
    )


def normalize_external_provider(
    provider: str | None = None,
    *,
    settings: Settings | None = None,
) -> ExternalLlmProvider:
    settings = settings or get_settings()
    raw_provider = (provider or "").strip()
    if not raw_provider:
        raise ValueError("external LLM provider must be explicit")
    normalized = normalize_external_llm_provider_id(raw_provider)
    if normalized is None:
        raise ValueError(f"unsupported external LLM provider: {raw_provider}")
    allowed = get_allowed_external_llm_providers(settings)
    if normalized not in allowed:
        raise ValueError(f"external LLM provider is not allowed: {normalized}")
    return normalized


def get_allowed_external_llm_providers(
    settings: Settings | None = None,
) -> tuple[ExternalLlmProvider, ...]:
    settings = settings or get_settings()
    return parse_external_llm_provider_allowlist(settings.llm_external_allowed_providers)


def get_configured_llm_model_names(settings: Settings | None = None) -> tuple[str, ...]:
    settings = settings or get_settings()
    configs = [get_pool_config("local", settings)]
    for provider in get_allowed_external_llm_providers(settings):
        try:
            configs.append(get_pool_config("external", settings, external_provider=provider))
        except ValueError:
            continue
    return tuple(
        sorted(
            {
                model
                for config in configs
                for model in (config.default_model, config.canonical_model)
                if model.strip()
            }
        )
    )


def get_configured_llm_model_names_for_pool(
    pool: LlmPoolName,
    settings: Settings | None = None,
    *,
    external_provider: str | None = None,
) -> tuple[str, ...]:
    settings = settings or get_settings()
    config = get_pool_config(pool, settings, external_provider=external_provider)
    return _configured_model_names_for_config(config)


@lru_cache(maxsize=8)
def get_pool_client(
    pool: LlmPoolName,
    external_provider: str | None = None,
) -> OpenAI:
    config = get_pool_config(pool, external_provider=external_provider)
    return _new_pool_client(config)


def _new_pool_client(config: LlmPoolConfig) -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=config.api_key or "placeholder",
        base_url=config.base_url,
        default_headers=dict(config.default_headers) if config.default_headers else None,
        max_retries=0,
        timeout=settings.llm_request_timeout_seconds,
    )


@lru_cache(maxsize=8)
def get_async_pool_client(
    pool: LlmPoolName,
    external_provider: str | None = None,
) -> AsyncOpenAI:
    config = get_pool_config(pool, external_provider=external_provider)
    return _new_async_pool_client(config)


def _new_async_pool_client(config: LlmPoolConfig) -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=config.api_key or "placeholder",
        base_url=config.base_url,
        default_headers=dict(config.default_headers) if config.default_headers else None,
        max_retries=0,
        timeout=settings.llm_request_timeout_seconds,
    )


def _clear_pool_client_cache() -> None:
    cache_clear = getattr(get_pool_client, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    async_cache_clear = getattr(get_async_pool_client, "cache_clear", None)
    if async_cache_clear is not None:
        async_cache_clear()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def check_pool_health(
    pool: LlmPoolName,
    settings: Settings | None = None,
    *,
    external_provider: str | None = None,
) -> LlmPoolHealth:
    settings = settings or get_settings()
    config = get_pool_config(pool, settings, external_provider=external_provider)

    return check_resolved_pool_health(
        config,
        live=True,
        sync_client_factory=get_pool_client,
    )


def check_resolved_pool_health(
    config: LlmPoolConfig,
    *,
    live: bool,
    sync_client_factory: Any | None = None,
) -> LlmPoolHealth:
    """Inspect an already-resolved runtime config without consulting Settings.

    Registered workload callers use this Interface so configured and live
    health inspect the same immutable provider/model/credential selection as
    execution. Legacy pool health delegates here with its existing client
    factory during the compatibility window.
    """

    if not config.enabled:
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="disabled",
            detail=LocalizedApiMessage(code="llm.pool_disabled", params={"pool": config.pool}),
        )

    if not config.configured:
        missing = _missing_pool_config_settings(config)
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="not_configured",
            detail=LocalizedApiMessage(
                code="llm.missing_settings",
                params={"pool": config.pool, "settings": ", ".join(missing)},
            ),
        )

    if not live:
        return LlmPoolHealth(
            pool=config.pool,
            provider=config.provider,
            base_url=config.base_url,
            model=config.default_model,
            canonical_model=config.canonical_model,
            status="ready",
        )

    adapter = select_llm_execution_adapter(config.pool, config.provider)
    client_factory = sync_client_factory or (
        lambda _pool, _external_provider=None: _new_pool_client(config)
    )
    health = adapter.check_health(config, sync_client_factory=client_factory)
    return LlmPoolHealth(
        pool=config.pool,
        provider=config.provider,
        base_url=config.base_url,
        model=config.default_model,
        canonical_model=config.canonical_model,
        status=health.status,
        detail=health.detail,
    )


def check_all_pools_health(settings: Settings | None = None) -> LlmDualHealth:
    settings = settings or get_settings()
    local = check_pool_health("local", settings)
    external_providers = tuple(
        check_pool_health("external", settings, external_provider=provider)
        for provider in get_allowed_external_llm_providers(settings)
    )
    external = external_providers[0] if len(external_providers) == 1 else None
    return LlmDualHealth(
        local=local,
        external=external,
        external_providers=external_providers,
    )


def check_configured_pools_health(settings: Settings | None = None) -> LlmDualHealth:
    settings = settings or get_settings()
    local = _configured_pool_health("local", settings)
    external_providers = tuple(
        _configured_pool_health("external", settings, external_provider=provider)
        for provider in get_allowed_external_llm_providers(settings)
    )
    external = external_providers[0] if len(external_providers) == 1 else None
    return LlmDualHealth(
        local=local,
        external=external,
        external_providers=external_providers,
    )


def _configured_pool_health(
    pool: LlmPoolName,
    settings: Settings,
    *,
    external_provider: str | None = None,
) -> LlmPoolHealth:
    config = get_pool_config(pool, settings, external_provider=external_provider)
    return check_resolved_pool_health(config, live=False)


def _missing_pool_config_settings(config: LlmPoolConfig) -> list[str]:
    return [
        name
        for name, value in {
            "base_url": config.base_url,
            "api_key": config.api_key if config.requires_credentials else "not_required",
            "default_model": config.default_model,
        }.items()
        if not str(value).strip()
    ]


def check_effective_llm_readiness(
    db: Session,
    settings: Settings | None = None,
    *,
    dual: LlmDualHealth | None = None,
) -> LlmEffectiveReadiness:
    settings = settings or get_settings()
    dual = dual or check_all_pools_health(settings)
    tasks: list[LlmTaskReadiness] = []

    for task in get_supported_llm_tasks():
        policy = task.default_policy
        chosen_pool: LlmPoolName = "external" if policy == "external" else "local"
        pool_health = dual.external if chosen_pool == "external" else dual.local
        if pool_health is None:
            tasks.append(
                LlmTaskReadiness(
                    task_kind=task.task_kind,
                    description=task.description,
                    policy=policy,
                    chosen_pool=chosen_pool,
                    ready=False,
                    detail=LocalizedApiMessage(code="llm.external_pool_disabled"),
                )
            )
            continue

        tasks.append(
            LlmTaskReadiness(
                task_kind=task.task_kind,
                description=task.description,
                policy=policy,
                chosen_pool=chosen_pool,
                ready=pool_health.ready,
                detail=None if pool_health.ready else pool_health.detail or pool_health.status,
            )
        )

    return LlmEffectiveReadiness(tasks=tuple(tasks))


# ---------------------------------------------------------------------------
# Pool selection + chat completion
# ---------------------------------------------------------------------------


def choose_pool(
    context: LlmTaskContext,
    text_inputs: Iterable[str],
    db: Session,
    *,
    pool_hint: LlmPoolHint | None = None,
    policy_override: LlmPolicyMode | None = None,
    external_safety_bypass_reason: str | None = None,
    external_safety_exception_reason: str | None = None,
    external_safety_exception_blockers: Iterable[str] | None = None,
) -> tuple[LlmPoolName, PolicyDecision]:
    """Compatibility pool selector for non-workload callers.

    Registered workloads bypass this function. Payload security is enforced by
    the AI gateway and never changes the selected route in core transport.
    """
    _ = (context, text_inputs, db, external_safety_bypass_reason)
    _ = (external_safety_exception_reason, external_safety_exception_blockers)
    policy = policy_override or "local_only"
    if pool_hint == "local":
        return "local", PolicyDecision(
            policy=policy,
            chosen_pool="local",
            forced_local=True,
            reason="local_hint",
        )

    if policy == "external":
        return "external", PolicyDecision(
            policy="external",
            chosen_pool="external",
            reason=external_safety_bypass_reason or "explicit_external_route",
        )

    return "local", PolicyDecision(
        policy="local_only",
        chosen_pool="local",
        reason="policy_local_only",
    )


def _require_explicit_max_tokens(max_tokens: int | None) -> int:
    if max_tokens is None or max_tokens <= 0:
        raise ValueError("LLM max_tokens must be explicit and positive")
    return max_tokens


def resolve_chat_execution(
    context: LlmTaskContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
    pool_hint: LlmPoolHint | None = None,
    policy_override: LlmPolicyMode | None = None,
    external_provider: str | None = None,
    external_safety_bypass_reason: str | None = None,
    external_safety_exception_reason: str | None = None,
    external_safety_exception_blockers: Iterable[str] | None = None,
    config_override: LlmPoolConfig | None = None,
) -> ResolvedLlmExecution:
    _normalize_required_llm_app_id(context.app_id)
    text_inputs = _collect_text_inputs(messages)
    pool, decision = choose_pool(
        context,
        text_inputs,
        db,
        pool_hint=pool_hint,
        policy_override=policy_override,
        external_safety_bypass_reason=external_safety_bypass_reason,
        external_safety_exception_reason=external_safety_exception_reason,
        external_safety_exception_blockers=external_safety_exception_blockers,
    )
    override_applies = config_override is not None and config_override.pool == pool
    config = (
        config_override
        if override_applies
        else get_pool_config(
            pool,
            external_provider=external_provider if pool == "external" else None,
        )
    )
    effective_model = model if config_override is None or override_applies else None
    _ensure_requested_model_matches_config(effective_model, config)
    chosen_model = effective_model or config.default_model
    resolved_max_tokens = _require_explicit_max_tokens(max_tokens)
    resolved_reasoning_effort = resolve_reasoning_effort(
        pool,
        config.provider,
        reasoning_effort=reasoning_effort,
    )
    return ResolvedLlmExecution(
        pool=pool,
        decision=decision,
        config=config,
        chosen_model=chosen_model,
        resolved_max_tokens=resolved_max_tokens,
        resolved_reasoning_effort=resolved_reasoning_effort,
    )


def resolve_registered_chat_execution(
    context: LlmTaskContext,
    *,
    config: LlmPoolConfig,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    model: str | None = None,
) -> ResolvedLlmExecution:
    """Resolve an execution from the admin-selected workload configuration.

    Registered workloads already have one authoritative route, provider, and
    model.  This path deliberately does not consult task policy or rescan the
    payload to choose another pool; external-transfer enforcement belongs to
    the AI gateway before this immutable execution is built.
    """

    _normalize_required_llm_app_id(context.app_id)
    if not context.workload_id:
        raise ValueError("LLM workload_id is required")
    _ensure_requested_model_matches_config(model, config)
    chosen_model = model or config.default_model
    resolved_max_tokens = _require_explicit_max_tokens(max_tokens)
    resolved_reasoning_effort = resolve_reasoning_effort(
        config.pool,
        config.provider,
        reasoning_effort=reasoning_effort,
    )
    policy: LlmPolicyMode = "external" if config.pool == "external" else "local_only"
    return ResolvedLlmExecution(
        pool=config.pool,
        decision=PolicyDecision(
            policy=policy,
            chosen_pool=config.pool,
            reason="workload_route",
        ),
        config=config,
        chosen_model=chosen_model,
        resolved_max_tokens=resolved_max_tokens,
        resolved_reasoning_effort=resolved_reasoning_effort,
    )


def _configured_model_names_for_config(config: LlmPoolConfig) -> tuple[str, ...]:
    return tuple(
        sorted({model for model in (config.default_model, config.canonical_model) if model.strip()})
    )


def _ensure_requested_model_matches_config(
    requested_model: str | None,
    config: LlmPoolConfig,
) -> None:
    if requested_model is None:
        return
    if requested_model in _configured_model_names_for_config(config):
        return
    raise LlmModelConfigurationError(
        requested_model=requested_model,
        pool=config.pool,
        provider=config.provider,
        canonical_model=config.canonical_model or config.default_model,
    )


def complete_chat(
    context: LlmTaskContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    extra_body: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    model: str | None = None,
    audit_entity_id: str | None = None,
    pool_hint: LlmPoolHint | None = None,
    external_provider: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    resolved_execution: ResolvedLlmExecution | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    audit_context_strategy: str | None = None,
    audit_estimated_input_tokens: int | None = None,
    audit_sensitivity_labels: Iterable[str] | None = None,
    audit_blocked_entity_types: Iterable[str] | None = None,
    audit_content_origin: str | None = None,
    audit_source_kinds: Iterable[str] | None = None,
    audit_ai_security_policy_effect: str | None = None,
    audit_ai_security_policy_rule_id: str | None = None,
    audit_ai_security_policy_reason: str | None = None,
    audit_ai_security_policy_audit_only: bool | None = None,
    audit_custom_block_term_count: int | None = None,
    audit_external_transfer_exception_id: str | None = None,
    audit_external_transfer_exception_name: str | None = None,
    audit_external_transfer_exception_reason: str | None = None,
    audit_external_transfer_exception_blockers: Iterable[str] | None = None,
    audit_ai_security_pipeline_exemption_id: str | None = None,
    audit_ai_security_pipeline_exemption_name: str | None = None,
    audit_ai_security_pipeline_exemption_reason: str | None = None,
    audit_mask_applied: bool | None = None,
    audit_masked_entity_types: Iterable[str] | None = None,
    audit_masked_text_count: int | None = None,
    audit_privacy_filter_status: str | None = None,
    audit_privacy_filter_used: bool | None = None,
    audit_detected_values: list[dict[str, object]] | None = None,
) -> tuple[Any, PolicyDecision, LlmPoolConfig]:
    """Run a chat completion against the pool selected by policy + PII.

    The caller MUST supply an ``LlmTaskContext``. Every invocation — success,
    provider error, or configuration error — produces one ``llm_call`` audit
    log row. Full raw prompt/content is not persisted; audit payloads keep
    identity + decision + token counters + error summary. AI security callers
    may attach detector-specific value/count statistics separately.

    Returns a 3-tuple of the raw completion response, the ``PolicyDecision``
    that was applied, and the ``LlmPoolConfig`` actually used. Pool failure
    surfaces as ``LlmProviderError``; local pool failure does **not**
    transparently re-try on external.
    """
    # Local import keeps core/llm.py free of domain-layer dependencies in the
    # import graph (domains → core, not core → domains).
    from open_work_hub_api.domains.ai.audit import log_llm_call

    _normalize_required_llm_app_id(context.app_id)
    execution = resolved_execution or resolve_chat_execution(
        context,
        db,
        messages=messages,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        model=model,
        pool_hint=pool_hint,
        external_provider=external_provider,
    )
    config = execution.config
    decision = execution.decision
    audit_boundary_kwargs = _audit_boundary_kwargs(
        sensitivity_labels=audit_sensitivity_labels,
        blocked_entity_types=audit_blocked_entity_types or decision.blocked_entity_types,
        content_origin=audit_content_origin,
        source_kinds=audit_source_kinds,
    )
    audit_policy_kwargs = _audit_ai_security_kwargs(
        effect=audit_ai_security_policy_effect,
        rule_id=audit_ai_security_policy_rule_id,
        reason=audit_ai_security_policy_reason,
        audit_only=audit_ai_security_policy_audit_only,
        custom_block_term_count=audit_custom_block_term_count,
        external_transfer_exception_id=audit_external_transfer_exception_id,
        external_transfer_exception_name=audit_external_transfer_exception_name,
        external_transfer_exception_reason=audit_external_transfer_exception_reason,
        external_transfer_exception_blockers=audit_external_transfer_exception_blockers,
        ai_security_pipeline_exemption_id=audit_ai_security_pipeline_exemption_id,
        ai_security_pipeline_exemption_name=audit_ai_security_pipeline_exemption_name,
        ai_security_pipeline_exemption_reason=audit_ai_security_pipeline_exemption_reason,
        mask_applied=audit_mask_applied,
        masked_entity_types=audit_masked_entity_types,
        masked_text_count=audit_masked_text_count,
        privacy_filter_status=audit_privacy_filter_status,
        privacy_filter_used=audit_privacy_filter_used,
    )

    if not config.configured:
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            task_kind=context.task_kind,
            workload_id=context.workload_id,
            app_id=context.app_id,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=0,
            max_tokens=execution.resolved_max_tokens,
            context_strategy=audit_context_strategy,
            estimated_input_tokens=audit_estimated_input_tokens,
            error=f"{execution.pool} pool is not configured",
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            detected_values=audit_detected_values,
            **audit_boundary_kwargs,
            **audit_policy_kwargs,
        )
        raise LlmProviderError(
            f"{execution.pool} pool is not configured",
            pool=execution.pool,
            provider=config.provider,
        )

    payload = build_chat_payload(
        execution,
        messages=messages,
        temperature=temperature,
        extra_body=extra_body,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls,
    )

    started = time.monotonic()
    try:
        adapter = select_llm_execution_adapter(config.pool, config.provider)
        response = adapter.complete(
            config,
            payload,
            timeout_seconds=timeout_seconds or config.long_generation_timeout_seconds,
            sync_client_factory=lambda _pool, _provider: _new_pool_client(config),
        )
    except LlmProviderError as error:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            task_kind=context.task_kind,
            workload_id=context.workload_id,
            app_id=context.app_id,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=elapsed_ms,
            max_tokens=execution.resolved_max_tokens,
            context_strategy=audit_context_strategy,
            estimated_input_tokens=audit_estimated_input_tokens,
            error=str(error),
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            detected_values=audit_detected_values,
            **audit_boundary_kwargs,
            **audit_policy_kwargs,
        )
        raise
    except OpenAIError as error:
        provider_error = LlmProviderError(
            str(error),
            pool=config.pool,
            provider=config.provider,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            task_kind=context.task_kind,
            workload_id=context.workload_id,
            app_id=context.app_id,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=elapsed_ms,
            max_tokens=execution.resolved_max_tokens,
            context_strategy=audit_context_strategy,
            estimated_input_tokens=audit_estimated_input_tokens,
            error=str(provider_error),
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            detected_values=audit_detected_values,
            **audit_boundary_kwargs,
            **audit_policy_kwargs,
        )
        raise provider_error from error
    except Exception as error:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            task_kind=context.task_kind,
            workload_id=context.workload_id,
            app_id=context.app_id,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=elapsed_ms,
            max_tokens=execution.resolved_max_tokens,
            context_strategy=audit_context_strategy,
            estimated_input_tokens=audit_estimated_input_tokens,
            error=str(error),
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            detected_values=audit_detected_values,
            **audit_boundary_kwargs,
            **audit_policy_kwargs,
        )
        raise
    elapsed_ms = int((time.monotonic() - started) * 1000)

    usage = _extract_usage(response)
    finish_reason = _first_choice_finish_reason(response)
    log_llm_call(
        source=context.source,
        actor_user_id=context.actor_user_id,
        principal_kind=context.principal_kind,
        principal_id=context.principal_id,
        task_kind=context.task_kind,
        workload_id=context.workload_id,
        app_id=context.app_id,
        policy=decision.policy,
        chosen_pool=decision.chosen_pool,
        decision_reason=decision.reason,
        forced_local=decision.forced_local,
        pii_hits=decision.pii_hits,
        model=getattr(response, "model", execution.chosen_model),
        status="ok",
        latency_ms=elapsed_ms,
        usage=usage,
        max_tokens=execution.resolved_max_tokens,
        context_strategy=audit_context_strategy,
        estimated_input_tokens=audit_estimated_input_tokens,
        finish_reason=finish_reason,
        entity_id=audit_entity_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
        detected_values=audit_detected_values,
        **audit_boundary_kwargs,
        **audit_policy_kwargs,
    )
    return response, decision, config


def complete_chat_text(
    context: LlmTaskContext,
    db: Session,
    **kwargs: Any,
) -> tuple[LlmCompletionResult, PolicyDecision, LlmPoolConfig]:
    """Run a non-streaming chat completion and return a provider-neutral result."""

    try:
        response, decision, config = complete_chat(context, db, **kwargs)
    except Exception as error:
        raise LlmRuntimeError(str(error)) from error
    return completion_result(response), decision, config


def completion_result(response: Any) -> LlmCompletionResult:
    return LlmCompletionResult(
        text=completion_text(response),
        model=_response_model(response),
        usage=_extract_usage(response),
        finish_reason=_first_choice_finish_reason(response),
        tool_calls=completion_tool_calls(response),
    )


def completion_text(response: Any) -> str:
    choices = (
        response.get("choices")
        if isinstance(response, dict)
        else getattr(response, "choices", None)
    ) or []
    if not choices:
        return ""
    first_choice = choices[0]
    message = (
        first_choice.get("message")
        if isinstance(first_choice, dict)
        else getattr(first_choice, "message", None)
    )
    if message is None:
        return ""
    content = (
        message.get("content") if isinstance(message, dict) else getattr(message, "content", None)
    )
    return _message_content_text(content)


def completion_tool_calls(response: Any) -> tuple[LlmToolCall, ...]:
    choices = (
        response.get("choices")
        if isinstance(response, dict)
        else getattr(response, "choices", None)
    ) or []
    if not choices:
        return ()
    first_choice = choices[0]
    message = (
        first_choice.get("message")
        if isinstance(first_choice, dict)
        else getattr(first_choice, "message", None)
    )
    if message is None:
        return ()
    raw_tool_calls = (
        message.get("tool_calls")
        if isinstance(message, dict)
        else getattr(message, "tool_calls", None)
    ) or []
    normalized: list[LlmToolCall] = []
    for raw_call in raw_tool_calls:
        function = (
            raw_call.get("function")
            if isinstance(raw_call, dict)
            else getattr(raw_call, "function", None)
        )
        if function is None:
            continue
        name = (
            function.get("name") if isinstance(function, dict) else getattr(function, "name", None)
        )
        arguments = (
            function.get("arguments")
            if isinstance(function, dict)
            else getattr(function, "arguments", None)
        )
        if not isinstance(name, str) or not name or not isinstance(arguments, str):
            continue
        call_id = (
            raw_call.get("id") if isinstance(raw_call, dict) else getattr(raw_call, "id", None)
        )
        normalized.append(
            LlmToolCall(
                id=call_id if isinstance(call_id, str) and call_id else None,
                name=name,
                arguments=arguments,
            )
        )
    return tuple(normalized)


def _response_model(response: Any) -> str | None:
    value = (
        response.get("model") if isinstance(response, dict) else getattr(response, "model", None)
    )
    return value if isinstance(value, str) and value else None


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "\n".join(parts)
    return ""


def _extract_usage(response: Any) -> dict[str, int] | None:
    """Normalise OpenAI-compatible usage payloads to the fixed audit shape.

    Missing fields are dropped rather than zero-filled so that the audit log
    does not confuse "unreported" with "zero".
    """
    usage_obj = (
        response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    )
    if usage_obj is None:
        return None
    out: dict[str, int] = {}
    for field_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = (
            usage_obj.get(field_name)
            if isinstance(usage_obj, dict)
            else getattr(usage_obj, field_name, None)
        )
        if isinstance(value, int):
            out[field_name] = value
    return out or None


def _first_choice_finish_reason(response: Any) -> str | None:
    choices = (
        response.get("choices")
        if isinstance(response, dict)
        else getattr(response, "choices", None)
    ) or []
    if not choices:
        return None
    first_choice = choices[0]
    value = (
        first_choice.get("finish_reason")
        if isinstance(first_choice, dict)
        else getattr(first_choice, "finish_reason", None)
    )
    return value if isinstance(value, str) and value else None


def _collect_text_inputs(messages: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            out.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        out.append(text)
    return out


def _audit_boundary_kwargs(
    *,
    sensitivity_labels: Iterable[str] | None,
    blocked_entity_types: Iterable[str] | None,
    content_origin: str | None,
    source_kinds: Iterable[str] | None,
) -> dict[str, Any]:
    return {
        "sensitivity_labels": _string_list(sensitivity_labels),
        "blocked_entity_types": _string_list(blocked_entity_types),
        "content_origin": content_origin,
        "source_kinds": _string_list(source_kinds),
    }


def _audit_ai_security_kwargs(
    *,
    effect: str | None,
    rule_id: str | None,
    reason: str | None,
    audit_only: bool | None,
    custom_block_term_count: int | None,
    external_transfer_exception_id: str | None = None,
    external_transfer_exception_name: str | None = None,
    external_transfer_exception_reason: str | None = None,
    external_transfer_exception_blockers: Iterable[str] | None = None,
    ai_security_pipeline_exemption_id: str | None = None,
    ai_security_pipeline_exemption_name: str | None = None,
    ai_security_pipeline_exemption_reason: str | None = None,
    mask_applied: bool | None = None,
    masked_entity_types: Iterable[str] | None = None,
    masked_text_count: int | None = None,
    privacy_filter_status: str | None = None,
    privacy_filter_used: bool | None = None,
) -> dict[str, Any]:
    return {
        "ai_security_policy_effect": effect,
        "ai_security_policy_rule_id": rule_id,
        "ai_security_policy_reason": reason,
        "ai_security_policy_audit_only": bool(audit_only),
        "custom_block_term_count": int(custom_block_term_count or 0),
        "external_transfer_exception_id": external_transfer_exception_id,
        "external_transfer_exception_name": external_transfer_exception_name,
        "external_transfer_exception_reason": external_transfer_exception_reason,
        "external_transfer_exception_blockers": _string_list(external_transfer_exception_blockers),
        "ai_security_pipeline_exemption_id": ai_security_pipeline_exemption_id,
        "ai_security_pipeline_exemption_name": ai_security_pipeline_exemption_name,
        "ai_security_pipeline_exemption_reason": ai_security_pipeline_exemption_reason,
        "mask_applied": bool(mask_applied),
        "masked_entity_types": _string_list(masked_entity_types),
        "masked_text_count": int(masked_text_count or 0),
        "privacy_filter_status": privacy_filter_status,
        "privacy_filter_used": bool(privacy_filter_used),
    }


def _string_list(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []
    return [str(value) for value in values if value is not None]


async def complete_chat_stream(
    context: LlmTaskContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    extra_body: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    model: str | None = None,
    audit_entity_id: str | None = None,
    pool_hint: LlmPoolHint | None = None,
    external_provider: str | None = None,
    stream_reasoning: bool = True,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    resolved_execution: ResolvedLlmExecution | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    audit_context_strategy: str | None = None,
    audit_estimated_input_tokens: int | None = None,
    audit_sensitivity_labels: Iterable[str] | None = None,
    audit_blocked_entity_types: Iterable[str] | None = None,
    audit_content_origin: str | None = None,
    audit_source_kinds: Iterable[str] | None = None,
    audit_ai_security_policy_effect: str | None = None,
    audit_ai_security_policy_rule_id: str | None = None,
    audit_ai_security_policy_reason: str | None = None,
    audit_ai_security_policy_audit_only: bool | None = None,
    audit_custom_block_term_count: int | None = None,
    audit_external_transfer_exception_id: str | None = None,
    audit_external_transfer_exception_name: str | None = None,
    audit_external_transfer_exception_reason: str | None = None,
    audit_external_transfer_exception_blockers: Iterable[str] | None = None,
    audit_ai_security_pipeline_exemption_id: str | None = None,
    audit_ai_security_pipeline_exemption_name: str | None = None,
    audit_ai_security_pipeline_exemption_reason: str | None = None,
    audit_mask_applied: bool | None = None,
    audit_masked_entity_types: Iterable[str] | None = None,
    audit_masked_text_count: int | None = None,
    audit_privacy_filter_status: str | None = None,
    audit_privacy_filter_used: bool | None = None,
    audit_detected_values: list[dict[str, object]] | None = None,
):
    """Streaming twin of :func:`complete_chat`.

    Yields ``(StreamChunk, PolicyDecision, LlmPoolConfig)`` tuples. The
    caller (route layer) converts each chunk into an agent-event envelope
    and uses ``decision``/``config`` to build the terminal ``done`` meta.

    Exactly one ``llm_call`` audit row is committed per stream:
      - ``status="ok"``        — finish_reason ∈ {stop, length}
      - ``status="error"``     — provider/adapter exception or bad finish
      - ``status="cancelled"`` — consumer closed the stream
        (``asyncio.CancelledError``)

    Full raw prompt/content is not persisted. AI security callers may attach
    detector-specific value/count statistics separately.
    """
    import asyncio

    from open_work_hub_api.domains.ai.audit import log_llm_call

    _normalize_required_llm_app_id(context.app_id)
    execution = resolved_execution or resolve_chat_execution(
        context,
        db,
        messages=messages,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        model=model,
        pool_hint=pool_hint,
        external_provider=external_provider,
    )
    config = execution.config
    decision = execution.decision
    audit_boundary_kwargs = _audit_boundary_kwargs(
        sensitivity_labels=audit_sensitivity_labels,
        blocked_entity_types=audit_blocked_entity_types or decision.blocked_entity_types,
        content_origin=audit_content_origin,
        source_kinds=audit_source_kinds,
    )
    audit_policy_kwargs = _audit_ai_security_kwargs(
        effect=audit_ai_security_policy_effect,
        rule_id=audit_ai_security_policy_rule_id,
        reason=audit_ai_security_policy_reason,
        audit_only=audit_ai_security_policy_audit_only,
        custom_block_term_count=audit_custom_block_term_count,
        external_transfer_exception_id=audit_external_transfer_exception_id,
        external_transfer_exception_name=audit_external_transfer_exception_name,
        external_transfer_exception_reason=audit_external_transfer_exception_reason,
        external_transfer_exception_blockers=audit_external_transfer_exception_blockers,
        ai_security_pipeline_exemption_id=audit_ai_security_pipeline_exemption_id,
        ai_security_pipeline_exemption_name=audit_ai_security_pipeline_exemption_name,
        ai_security_pipeline_exemption_reason=audit_ai_security_pipeline_exemption_reason,
        mask_applied=audit_mask_applied,
        masked_entity_types=audit_masked_entity_types,
        masked_text_count=audit_masked_text_count,
        privacy_filter_status=audit_privacy_filter_status,
        privacy_filter_used=audit_privacy_filter_used,
    )

    if not config.configured:
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            task_kind=context.task_kind,
            workload_id=context.workload_id,
            app_id=context.app_id,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status="error",
            latency_ms=0,
            max_tokens=execution.resolved_max_tokens,
            context_strategy=audit_context_strategy,
            estimated_input_tokens=audit_estimated_input_tokens,
            error=f"{execution.pool} pool is not configured",
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            detected_values=audit_detected_values,
            **audit_boundary_kwargs,
            **audit_policy_kwargs,
        )
        raise LlmProviderError(
            f"{execution.pool} pool is not configured",
            pool=execution.pool,
            provider=config.provider,
        )

    payload = build_chat_payload(
        execution,
        messages=messages,
        temperature=temperature,
        extra_body=extra_body,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls,
        stream_reasoning=stream_reasoning,
    )

    started = time.monotonic()
    status_final: str = "error"
    finish_reason_final: str | None = None
    error_message: str | None = None
    accumulated_usage: dict[str, int] | None = None
    try:
        adapter = select_llm_execution_adapter(config.pool, config.provider)
        async for chunk in adapter.stream(
            config,
            payload,
            timeout_seconds=timeout_seconds or config.long_generation_timeout_seconds,
            sync_client_factory=lambda _pool, _provider: _new_pool_client(config),
            async_client_factory=lambda _pool, _provider: _new_async_pool_client(config),
        ):
            if chunk.kind == "usage" and chunk.usage:
                accumulated_usage = chunk.usage
            if chunk.kind == "done":
                status_final = (
                    "ok" if chunk.finish_reason in ("stop", "length", "tool_calls") else "error"
                )
                finish_reason_final = chunk.finish_reason
            yield chunk, decision, config
    except (asyncio.CancelledError, GeneratorExit):
        status_final = "cancelled"
        raise
    except BaseException as error:  # noqa: BLE001 — we re-raise
        status_final = "error"
        error_message = str(error)
        raise
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_llm_call(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            task_kind=context.task_kind,
            workload_id=context.workload_id,
            app_id=context.app_id,
            policy=decision.policy,
            chosen_pool=decision.chosen_pool,
            decision_reason=decision.reason,
            forced_local=decision.forced_local,
            pii_hits=decision.pii_hits,
            model=execution.chosen_model,
            status=status_final,
            latency_ms=elapsed_ms,
            usage=accumulated_usage,
            max_tokens=execution.resolved_max_tokens,
            context_strategy=audit_context_strategy,
            estimated_input_tokens=audit_estimated_input_tokens,
            finish_reason=finish_reason_final,
            error=error_message,
            entity_id=audit_entity_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            detected_values=audit_detected_values,
            **audit_boundary_kwargs,
            **audit_policy_kwargs,
        )
