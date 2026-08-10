from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from open_work_hub_api.core.llm_provider_registry import llm_provider_descriptor
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.admin.model_runtime_status_schemas import (
    AdminModelRuntimeStatusResponse,
    ModelRuntimeModelResponse,
    ModelRuntimeTargetResponse,
)
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    get_ai_model_provider_default_model_key,
)
from open_work_hub_api.domains.ai.model_credentials import AiModelCredentialError, decrypt_api_key
from open_work_hub_api.domains.ai.model_settings_models import AiModelProviderConfig


@dataclass(frozen=True, slots=True)
class RuntimeTargetDescriptor:
    id: str
    display_name: str
    kind: str
    role: str
    endpoint_url: str
    provider_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderRuntimeConfig:
    provider_id: str
    display_name: str
    endpoint_url: str
    api_key: str
    expected_model: str


def _authorization_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key.strip() else {}


def _inference_health_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return f"{root}/health"


def _llm_models_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    return f"{root}/models" if root.endswith("/v1") else f"{root}/v1/models"


def _error_target(
    *,
    target: RuntimeTargetDescriptor,
    error_code: str,
) -> ModelRuntimeTargetResponse:
    return ModelRuntimeTargetResponse.model_validate(
        {
            "id": target.id,
            "display_name": target.display_name,
            "kind": target.kind,
            "role": target.role,
            "provider_id": target.provider_id,
            "status": "offline",
            "error_code": error_code,
        }
    )


async def _get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
) -> tuple[httpx.Response | None, Any | None, str | None]:
    try:
        response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        return None, None, "timeout"
    except httpx.HTTPError:
        return None, None, "connection_failed"

    try:
        payload = response.json()
    except ValueError:
        return response, None, "invalid_response"
    return response, payload, None


async def _probe_inference_gateway(
    client: httpx.AsyncClient,
    target: RuntimeTargetDescriptor,
    *,
    api_key: str,
) -> ModelRuntimeTargetResponse:
    base_url = target.endpoint_url.strip()
    if not base_url:
        return ModelRuntimeTargetResponse(
            id=target.id,
            display_name=target.display_name,
            kind="inference_gateway",
            role=target.role,  # type: ignore[arg-type]
            status="not_configured",
        )

    response, payload, error_code = await _get_json(
        client,
        _inference_health_url(base_url),
        headers=_authorization_headers(api_key),
    )
    if error_code:
        return _error_target(
            target=target,
            error_code=error_code,
        )
    if response is None or not isinstance(payload, dict):
        return _error_target(
            target=target,
            error_code="invalid_response",
        )

    status_payload = payload.get("detail") if isinstance(payload.get("detail"), dict) else payload
    raw_models = status_payload.get("models") if isinstance(status_payload, dict) else None
    if not isinstance(raw_models, dict):
        return _error_target(
            target=target,
            error_code="invalid_response",
        )

    models = [
        ModelRuntimeModelResponse(
            name=str(model.get("model", "")).strip() or task,
            task=str(model.get("task", "")).strip() or task,
            loaded=bool(model.get("loaded", False)),
        )
        for task, model in raw_models.items()
        if isinstance(model, dict)
    ]
    ready = bool(status_payload.get("ready")) and all(model.loaded for model in models)
    return ModelRuntimeTargetResponse(
        id=target.id,
        display_name=target.display_name,
        kind="inference_gateway",
        role=target.role,  # type: ignore[arg-type]
        status="online" if response.is_success and ready else "degraded",
        models=models,
        error_code=None if response.is_success else "http_error",
    )


async def _probe_llm(
    client: httpx.AsyncClient,
    *,
    target: RuntimeTargetDescriptor,
    api_key: str,
    expected_model: str,
) -> ModelRuntimeTargetResponse:
    base_url = target.endpoint_url.strip()
    if not base_url:
        return ModelRuntimeTargetResponse(
            id=target.id,
            display_name=target.display_name,
            kind="llm",
            role=target.role,  # type: ignore[arg-type]
            provider_id=target.provider_id,
            status="not_configured",
        )

    response, payload, error_code = await _get_json(
        client,
        _llm_models_url(base_url),
        headers=_authorization_headers(api_key),
    )
    if error_code:
        return _error_target(target=target, error_code=error_code)
    if response is None or not response.is_success:
        return _error_target(target=target, error_code="http_error")
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return _error_target(
            target=target,
            error_code="invalid_response",
        )

    models = [
        ModelRuntimeModelResponse(name=str(item["id"]), loaded=True)
        for item in payload["data"]
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    ]
    expected_model = expected_model.strip()
    model_missing = bool(expected_model) and all(model.name != expected_model for model in models)
    return ModelRuntimeTargetResponse(
        id=target.id,
        display_name=target.display_name,
        kind="llm",
        role=target.role,  # type: ignore[arg-type]
        provider_id=target.provider_id,
        status="degraded" if model_missing or not models else "online",
        models=models,
        error_code="model_missing" if model_missing else None,
    )


async def collect_model_runtime_status(
    settings: Settings | None = None,
    *,
    db: Session | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AdminModelRuntimeStatusResponse:
    settings = settings or get_settings()
    timeout = httpx.Timeout(settings.model_status_request_timeout_seconds)
    inference_target = RuntimeTargetDescriptor(
        id="inference-gateway",
        display_name="Inference gateway",
        kind="inference_gateway",
        role="diagnostic",
        endpoint_url=settings.inference_gateway_base_url,
    )
    local_runtime = _resolve_provider_runtime(
        db,
        provider_id="local",
        settings=settings,
    )
    diagnostic_targets, invalid_targets = _diagnostic_targets(settings)
    llm_targets = [
        RuntimeTargetDescriptor(
            id="local-llm",
            display_name=local_runtime.display_name,
            kind="llm",
            role="serving",
            endpoint_url=local_runtime.endpoint_url,
            provider_id=local_runtime.provider_id,
        ),
        *diagnostic_targets,
    ]
    async with httpx.AsyncClient(
        timeout=timeout,
        transport=transport,
        follow_redirects=False,
    ) as client:
        probe_tasks = [
            _probe_inference_gateway(
                client,
                inference_target,
                api_key=settings.inference_gateway_api_key,
            )
        ]
        for target in llm_targets:
            runtime = (
                local_runtime
                if target.provider_id == "local"
                else _resolve_provider_runtime(
                    db,
                    provider_id=target.provider_id or "",
                    settings=settings,
                )
            )
            probe_tasks.append(
                _probe_llm(
                    client,
                    target=target,
                    api_key=runtime.api_key,
                    expected_model=runtime.expected_model,
                )
            )
        targets = [*await asyncio.gather(*probe_tasks), *invalid_targets]

    relevant_targets = [target for target in targets if target.role != "diagnostic"]
    online_count = sum(target.status == "online" for target in relevant_targets)
    reachable_count = sum(
        target.status in {"online", "degraded"} for target in relevant_targets
    )
    overall_status = (
        "online"
        if relevant_targets and online_count == len(relevant_targets)
        else "degraded"
        if reachable_count > 0
        else "offline"
    )
    if any(target.error_code == "configuration_invalid" for target in targets):
        overall_status = "degraded"
    return AdminModelRuntimeStatusResponse(
        checked_at=datetime.now(timezone.utc),
        status=overall_status,
        targets=list(targets),
    )


def _resolve_provider_runtime(
    db: Session | None,
    *,
    provider_id: str,
    settings: Settings,
) -> ProviderRuntimeConfig:
    descriptor = llm_provider_descriptor(provider_id)
    if descriptor is None:
        raise ValueError(f"Unknown runtime provider: {provider_id}")
    row = db.get(AiModelProviderConfig, provider_id) if db is not None else None
    if row is not None and not row.enabled:
        return ProviderRuntimeConfig(
            provider_id=provider_id,
            display_name=descriptor.display_name,
            endpoint_url="",
            api_key="",
            expected_model="",
        )
    endpoint_url = ((row.endpoint_url or "").strip() if row is not None else "")
    if not endpoint_url:
        endpoint_url = (
            settings.llm_local_base_url.strip()
            if provider_id == "local"
            else descriptor.default_endpoint_url.strip()
        )
    configured_model: str | None = None
    selection_invalid = False
    if db is not None:
        try:
            configured_model = get_ai_model_provider_default_model_key(
                db,
                provider_id=provider_id,
            )
        except AiModelSettingsError:
            selection_invalid = bool(row and row.default_model_id)
    expected_model = "" if selection_invalid else configured_model or ""
    if selection_invalid:
        endpoint_url = ""
    api_key = settings.llm_local_api_key if provider_id == "local" else ""
    if row is not None and row.api_key_ciphertext:
        try:
            api_key = decrypt_api_key(row.api_key_ciphertext).get_secret_value()
        except AiModelCredentialError:
            api_key = ""
    return ProviderRuntimeConfig(
        provider_id=provider_id,
        display_name=descriptor.display_name,
        endpoint_url=endpoint_url,
        api_key=api_key,
        expected_model=expected_model,
    )


def _diagnostic_targets(
    settings: Settings,
) -> tuple[list[RuntimeTargetDescriptor], list[ModelRuntimeTargetResponse]]:
    raw_json = settings.model_status_diagnostic_targets_json
    if len(raw_json.encode("utf-8")) > 65_536:
        return [], [_invalid_diagnostic_target("diagnostic-config")]
    try:
        raw = json.loads(raw_json)
    except (TypeError, ValueError):
        raw = None
    if not isinstance(raw, list):
        return [], [_invalid_diagnostic_target("diagnostic-config")]
    if len(raw) > 20:
        return [], [_invalid_diagnostic_target("diagnostic-config")]

    targets: list[RuntimeTargetDescriptor] = []
    invalid: list[ModelRuntimeTargetResponse] = []
    seen = {"inference-gateway", "local-llm"}
    for index, item in enumerate(raw):
        target_id = str(item.get("id", "")).strip().lower() if isinstance(item, dict) else ""
        display_name = str(item.get("display_name", "")).strip() if isinstance(item, dict) else ""
        endpoint_url = str(item.get("endpoint_url", "")).strip() if isinstance(item, dict) else ""
        provider_id = str(item.get("provider_id", "local")).strip().lower() if isinstance(item, dict) else ""
        role = str(item.get("role", "diagnostic")).strip().lower() if isinstance(item, dict) else ""
        provider_descriptor = llm_provider_descriptor(provider_id)
        valid_keys = {"id", "display_name", "endpoint_url", "provider_id", "role"}
        if (
            not isinstance(item, dict)
            or set(item) - valid_keys
            or not target_id
            or target_id in seen
            or not display_name
            or not endpoint_url
            or role not in {"redundancy", "diagnostic"}
            or provider_descriptor is None
            or provider_descriptor.discovery_adapter_id != "openai_compatible"
        ):
            invalid.append(_invalid_diagnostic_target(f"diagnostic-config-{index + 1}"))
            continue
        provider_id = provider_descriptor.provider_id
        try:
            ModelRuntimeTargetResponse(
                id=target_id,
                display_name=display_name,
                kind="llm",
                role=role,  # type: ignore[arg-type]
                provider_id=provider_id,
                status="not_configured",
            )
        except ValueError:
            invalid.append(_invalid_diagnostic_target(f"diagnostic-config-{index + 1}"))
            continue
        seen.add(target_id)
        targets.append(
            RuntimeTargetDescriptor(
                id=target_id,
                display_name=display_name,
                kind="llm",
                role=role,
                endpoint_url=endpoint_url,
                provider_id=provider_id,
            )
        )
    return targets, invalid


def _invalid_diagnostic_target(target_id: str) -> ModelRuntimeTargetResponse:
    return ModelRuntimeTargetResponse(
        id=target_id,
        display_name="Invalid runtime diagnostic target",
        kind="llm",
        role="diagnostic",
        status="not_configured",
        error_code="configuration_invalid",
    )


__all__ = ["collect_model_runtime_status"]
