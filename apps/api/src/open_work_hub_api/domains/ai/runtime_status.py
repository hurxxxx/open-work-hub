from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from open_work_hub_api.core.llm import (
    LlmDualHealth,
    LlmEffectiveReadiness,
    LlmPoolConfig,
    LlmPoolHealth,
    LlmTaskReadiness,
    check_resolved_pool_health,
)
from open_work_hub_api.core.llm_provider_registry import parse_external_llm_provider_allowlist
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    ResolvedLlmWorkloadRoute,
    resolve_ai_model_workload_route,
)
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry

RuntimeProbe = Literal["configured", "live"]
_ConfigKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class RegisteredLlmRuntimeStatus:
    pools: LlmDualHealth
    workloads: LlmEffectiveReadiness


def build_resolved_llm_pool_config(
    route: ResolvedLlmWorkloadRoute,
    *,
    settings: Settings | None = None,
) -> LlmPoolConfig:
    """Project a DB-resolved workload route into transport configuration."""

    resolved_settings = settings or get_settings()
    api_key = route.api_key.get_secret_value() if route.api_key is not None else ""
    return LlmPoolConfig(
        pool=route.route,
        provider=route.adapter_provider,
        base_url=route.endpoint_url,
        api_key=api_key,
        default_model=route.model_key,
        canonical_model=route.model_key,
        healthcheck_timeout_seconds=resolved_settings.llm_request_timeout_seconds,
        long_generation_timeout_seconds=(
            resolved_settings.llm_local_long_generation_timeout_seconds
            if route.route == "local"
            else resolved_settings.llm_external_long_generation_timeout_seconds
        ),
        enabled=True,
        requires_credentials=route.route == "external",
    )


def inspect_registered_llm_runtime(
    db: Session,
    *,
    settings: Settings | None = None,
    probe: RuntimeProbe = "configured",
) -> RegisteredLlmRuntimeStatus:
    """Inspect registered workloads through the same route resolver as execution.

    ``configured`` never calls a model provider. ``live`` probes each distinct
    resolved provider/endpoint/model combination through its execution Adapter.
    External environment variables are not read by this Module.
    """

    resolved_settings = settings or get_settings()
    registry = get_ai_capability_registry()
    allowed_external_providers = parse_external_llm_provider_allowlist(
        resolved_settings.llm_external_allowed_providers
    )
    resolved_items: list[tuple[str, str, str, _ConfigKey]] = []
    failed_items: list[LlmTaskReadiness] = []
    failed_pool_health: dict[tuple[str, str], LlmPoolHealth] = {}
    configs: dict[_ConfigKey, LlmPoolConfig] = {}

    for workload in sorted(registry.llm_workloads.values(), key=lambda item: item.workload_id):
        for model_role in workload.model_roles:
            readiness_id = (
                workload.workload_id
                if model_role == "default"
                else f"{workload.workload_id}:{model_role}"
            )
            try:
                route = resolve_ai_model_workload_route(
                    db,
                    workload_id=workload.workload_id,
                    model_role=model_role,
                    settings=resolved_settings,
                )
                if (
                    route.route == "external"
                    and route.provider_id not in allowed_external_providers
                ):
                    raise AiModelSettingsError(
                        status_code=503,
                        code="admin.ai_model_provider_not_allowed",
                        context={"provider_id": route.provider_id},
                    )
            except AiModelSettingsError as exc:
                chosen_pool = workload.default_route
                provider_id = str(exc.context.get("provider_id") or "unresolved")
                failed_items.append(
                    LlmTaskReadiness(
                        task_kind=readiness_id,
                        description=workload.description,
                        policy=workload.default_policy,
                        chosen_pool=chosen_pool,
                        ready=False,
                        detail=exc.code,
                    )
                )
                failed_pool_health.setdefault(
                    (chosen_pool, provider_id),
                    LlmPoolHealth(
                        pool=chosen_pool,
                        provider=provider_id,
                        base_url="",
                        model="",
                        canonical_model="",
                        status="not_configured",
                        detail=exc.code,
                    ),
                )
                continue

            config = build_resolved_llm_pool_config(route, settings=resolved_settings)
            key = _config_key(config)
            configs.setdefault(key, config)
            resolved_items.append(
                (readiness_id, workload.description, workload.default_policy, key)
            )

    health_by_config = {
        key: check_resolved_pool_health(config, live=probe == "live")
        for key, config in configs.items()
    }
    ready_items = [
        LlmTaskReadiness(
            task_kind=readiness_id,
            description=description,
            policy=policy,  # type: ignore[arg-type]
            chosen_pool=configs[key].pool,
            ready=health_by_config[key].ready,
            detail=(
                None
                if health_by_config[key].ready
                else health_by_config[key].detail or health_by_config[key].status
            ),
        )
        for readiness_id, description, policy, key in resolved_items
    ]

    local_health = next(
        (health for health in health_by_config.values() if health.pool == "local"),
        failed_pool_health.get(("local", "local")) or _unused_local_health(),
    )
    external_health_items = _external_health_items(
        health_by_config=health_by_config,
        failed_pool_health=failed_pool_health,
    )
    return RegisteredLlmRuntimeStatus(
        pools=LlmDualHealth(
            local=local_health,
            external=external_health_items[0] if external_health_items else None,
            external_providers=external_health_items,
        ),
        workloads=LlmEffectiveReadiness(
            tasks=tuple(sorted((*ready_items, *failed_items), key=lambda item: item.task_kind))
        ),
    )


def _config_key(config: LlmPoolConfig) -> _ConfigKey:
    return (config.pool, config.provider, config.base_url, config.default_model)


def _external_health_items(
    *,
    health_by_config: dict[_ConfigKey, LlmPoolHealth],
    failed_pool_health: dict[tuple[str, str], LlmPoolHealth],
) -> tuple[LlmPoolHealth, ...]:
    by_provider: dict[str, LlmPoolHealth] = {}
    for health in health_by_config.values():
        if health.pool == "external":
            by_provider.setdefault(health.provider, health)
    for (pool, provider_id), health in failed_pool_health.items():
        if pool == "external":
            by_provider.setdefault(provider_id, health)
    return tuple(by_provider[key] for key in sorted(by_provider))


def _unused_local_health() -> LlmPoolHealth:
    return LlmPoolHealth(
        pool="local",
        provider="local",
        base_url="",
        model="",
        canonical_model="",
        status="disabled",
        detail="no_registered_local_workload",
    )


__all__ = [
    "RegisteredLlmRuntimeStatus",
    "RuntimeProbe",
    "build_resolved_llm_pool_config",
    "inspect_registered_llm_runtime",
]
