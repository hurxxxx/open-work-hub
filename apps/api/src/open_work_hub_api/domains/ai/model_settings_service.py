from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import ipaddress
import json
import socket
from typing import Any, Literal
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pydantic import SecretStr

from open_work_hub_api.core.llm_pool_config_registry import resolve_llm_pool_config_values
from open_work_hub_api.core.llm_provider_registry import (
    external_llm_provider_ids,
    llm_provider_descriptor,
    llm_provider_ids,
)
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.ai.model_credentials import (
    AiModelCredentialError,
    decrypt_api_key,
    encrypt_api_key,
)
from open_work_hub_api.domains.ai.model_discovery import (
    ProviderModelDiscoveryError,
    discover_provider_models,
)
from open_work_hub_api.domains.ai.model_settings_models import (
    AiModelCatalogEntry,
    AiModelProviderConfig,
    AiModelRouteOverride,
)
from open_work_hub_api.domains.ai.model_settings_schemas import (
    AiModelCatalogCreateRequest,
    AiModelCatalogEntryResponse,
    AiModelCatalogUpdateRequest,
    AiModelOrphanedOverrideResponse,
    AiModelProviderResponse,
    AiModelProviderUpdateRequest,
    AiModelResolvedRouteResponse,
    AiModelRouteOverrideResponse,
    AiModelRouteOverrideUpdateRequest,
    AiModelSettingsResponse,
    AiModelWorkloadResponse,
)
from open_work_hub_api.domains.ai.registry import (
    RegisteredLlmWorkload,
    get_ai_capability_registry,
)
from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.auth.security import new_id


@dataclass(frozen=True)
class ResolvedLlmWorkloadRoute:
    workload: RegisteredLlmWorkload
    route: Literal["local", "external"]
    provider_id: str
    adapter_provider: str
    model_role: str
    model_key: str
    endpoint_url: str
    api_key: SecretStr | None = field(repr=False)
    route_source: Literal["default", "override"]
    config_source: Literal["database", "legacy_env", "database_with_legacy_env"]
    local_max_output_tokens: int
    external_max_output_tokens: int
    max_output_tokens: int
    model_entry_id: str | None = None

    @property
    def source(self) -> Literal["default", "override"]:
        return self.route_source


class AiModelSettingsError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.context = context or {}


def ai_model_registry_digest() -> str:
    workloads = get_ai_capability_registry().llm_workloads.values()
    payload = [asdict(item) for item in sorted(workloads, key=lambda item: item.workload_id)]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assert_registry_digest(expected: str) -> str:
    actual = ai_model_registry_digest()
    if expected != actual:
        raise AiModelSettingsError(
            status_code=409,
            code="admin.ai_model_registry_changed",
            context={"registry_digest": actual},
        )
    return actual


def resolve_ai_model_workload_route(
    db: Session,
    *,
    workload_id: str,
    model_role: str = "default",
    settings: Settings | None = None,
) -> ResolvedLlmWorkloadRoute:
    """Resolve one workload role to an executable provider configuration.

    Persisted provider defaults and workload overrides are authoritative and
    fail closed when missing, corrupt, or not executable. Environment values
    may supply the local transport endpoint during rollout, but never a model
    selection.
    """

    workload = get_ai_capability_registry().get_llm_workload(workload_id)
    if workload is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_workload_not_found",
            context={"workload_id": workload_id},
        )
    normalized_role = model_role.strip().lower()
    if normalized_role not in workload.model_roles:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_role_not_allowed",
            context={"model_role": normalized_role},
        )

    resolved_settings = settings or get_settings()
    override = db.scalar(
        select(AiModelRouteOverride).where(AiModelRouteOverride.workload_id == workload.workload_id)
    )
    route = override.route_mode if override is not None else workload.default_route
    if route not in workload.allowed_routes:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_route_not_allowed",
            context={"workload_id": workload.workload_id},
        )

    provider_id = _runtime_provider_id(
        db,
        workload=workload,
        route=route,
        override=override,
    )
    provider_config = db.get(AiModelProviderConfig, provider_id)
    if route == "external" and (provider_config is None or not provider_config.enabled):
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_ready",
            context={"provider_id": provider_id},
        )

    use_database_provider = bool(provider_config and provider_config.enabled)
    pool_values = (
        _legacy_pool_values(
            route=route,
            provider_id=provider_id,
            settings=resolved_settings,
        )
        if route == "local"
        else None
    )
    selected_model_id = None
    if override is not None:
        selected_model_id = override.model_ids.get(normalized_role)
    if selected_model_id is None and use_database_provider and provider_config is not None:
        selected_model_id = provider_config.default_model_id

    model_key: str
    if selected_model_id is not None:
        model = _require_provider_model(
            db,
            provider_id=provider_id,
            model_id=selected_model_id,
            require_enabled=True,
        )
        _require_model_capabilities(model, workload=workload)
        model_key = model.model_key
    else:
        model_key = ""
    if not model_key:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_selection_required",
        )

    endpoint_url = (
        (provider_config.endpoint_url or "").strip()
        if use_database_provider and provider_config is not None
        else ""
    ) or (pool_values.base_url.strip() if pool_values is not None else "")
    if not endpoint_url:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_ready",
            context={"provider_id": provider_id},
        )

    api_key: SecretStr | None = None
    used_database_secret = False
    if use_database_provider and provider_config and provider_config.api_key_ciphertext:
        try:
            api_key = decrypt_api_key(provider_config.api_key_ciphertext)
            used_database_secret = True
        except AiModelCredentialError as exc:
            raise AiModelSettingsError(
                status_code=503,
                code="admin.ai_model_credential_encryption_unavailable",
            ) from exc
    elif route == "external":
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_key_required",
            context={"provider_id": provider_id},
        )
    elif pool_values is not None and pool_values.api_key.strip():
        api_key = SecretStr(pool_values.api_key.strip())
    if route == "external" and api_key is None:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_key_required",
            context={"provider_id": provider_id},
        )

    used_database_model = selected_model_id is not None
    used_database_endpoint = bool(
        use_database_provider and provider_config and provider_config.endpoint_url
    )
    database_parts = used_database_model or used_database_endpoint or used_database_secret
    legacy_parts = route == "local" and (
        not used_database_model or not used_database_endpoint
    )
    config_source: Literal["database", "legacy_env", "database_with_legacy_env"]
    if database_parts and legacy_parts:
        config_source = "database_with_legacy_env"
    elif database_parts:
        config_source = "database"
    else:
        config_source = "legacy_env"

    local_max_output_tokens = _effective_max_output_tokens(
        workload,
        override,
        route="local",
    )
    external_max_output_tokens = _effective_max_output_tokens(
        workload,
        override,
        route="external",
    )
    max_output_tokens = local_max_output_tokens if route == "local" else external_max_output_tokens

    return ResolvedLlmWorkloadRoute(
        workload=workload,
        route=route,  # type: ignore[arg-type]
        provider_id=provider_id,
        adapter_provider=(
            pool_values.provider if route == "local" and pool_values is not None else provider_id
        ),
        model_role=normalized_role,
        model_key=model_key,
        endpoint_url=endpoint_url,
        api_key=api_key,
        route_source="override" if override is not None else "default",
        config_source=config_source,
        local_max_output_tokens=local_max_output_tokens,
        external_max_output_tokens=external_max_output_tokens,
        max_output_tokens=max_output_tokens,
        model_entry_id=selected_model_id,
    )


def get_ai_model_settings_snapshot(db: Session) -> AiModelSettingsResponse:
    registry = get_ai_capability_registry()
    settings = get_settings()
    providers_by_id = {
        row.provider_id: row for row in db.scalars(select(AiModelProviderConfig)).all()
    }
    model_rows = list(
        db.scalars(
            select(AiModelCatalogEntry).order_by(
                AiModelCatalogEntry.provider_id,
                AiModelCatalogEntry.display_name,
                AiModelCatalogEntry.id,
            )
        ).all()
    )
    override_rows = list(
        db.scalars(select(AiModelRouteOverride).order_by(AiModelRouteOverride.workload_id)).all()
    )
    overrides_by_workload = {row.workload_id: row for row in override_rows}

    providers = [
        _serialize_provider(
            provider_id,
            providers_by_id.get(provider_id),
            settings=settings,
        )
        for provider_id in llm_provider_ids(control_plane_only=True)
    ]
    # Discovery rows absent from the provider's current inventory are retained
    # for audit/history, but are not part of the selectable admin catalog.
    models = [
        _serialize_model(row)
        for row in model_rows
        if row.discovery_status == "active"
    ]
    workloads = [
        _serialize_workload(
            db,
            descriptor,
            overrides_by_workload.get(descriptor.workload_id),
        )
        for descriptor in sorted(
            registry.llm_workloads.values(),
            key=lambda item: (item.owner_domain, item.workload_id),
        )
    ]
    orphaned = [
        AiModelOrphanedOverrideResponse(
            workload_id=row.workload_id,
            route_mode=row.route_mode,  # type: ignore[arg-type]
            provider_id=row.provider_id,  # type: ignore[arg-type]
            model_ids=row.model_ids,
            local_max_output_tokens=row.local_max_output_tokens,
            external_max_output_tokens=row.external_max_output_tokens,
            version=row.version,
            updated_at=row.updated_at,
        )
        for row in override_rows
        if row.workload_id not in registry.llm_workloads
    ]
    return AiModelSettingsResponse(
        registry_digest=ai_model_registry_digest(),
        providers=providers,
        models=models,
        workloads=workloads,
        orphaned_overrides=orphaned,
    )


def get_ai_model_provider_default_model_key(
    db: Session,
    *,
    provider_id: str,
) -> str | None:
    """Return an explicit provider default as its executable model key."""

    normalized_provider_id = provider_id.strip().lower()
    provider = db.get(AiModelProviderConfig, normalized_provider_id)
    if provider is None or provider.default_model_id is None:
        return None
    model = _require_provider_model(
        db,
        provider_id=normalized_provider_id,
        model_id=provider.default_model_id,
        require_enabled=True,
    )
    return model.model_key


def update_ai_model_provider(
    db: Session,
    *,
    provider_id: str,
    payload: AiModelProviderUpdateRequest,
    actor_user_id: str,
) -> None:
    assert_registry_digest(payload.expected_registry_digest)
    normalized_provider_id = provider_id.strip().lower()
    descriptor = llm_provider_descriptor(normalized_provider_id)
    if descriptor is None or not descriptor.control_plane_visible:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_provider_not_found",
            context={"provider_id": normalized_provider_id},
        )
    endpoint_url = payload.endpoint_url
    if descriptor.route_mode == "external" and endpoint_url is None:
        endpoint_url = descriptor.default_endpoint_url or None
    _validate_endpoint_url(endpoint_url, provider_id=normalized_provider_id)

    row = db.get(AiModelProviderConfig, normalized_provider_id)
    expected_version = payload.expected_version
    if row is None:
        if expected_version not in (None, 0):
            _raise_version_conflict()
        row = AiModelProviderConfig(
            provider_id=normalized_provider_id,
            enabled=normalized_provider_id == "local",
            version=1,
            updated_by=actor_user_id,
        )
        db.add(row)
        db.flush()
    elif expected_version != row.version:
        _raise_version_conflict()

    if payload.default_model_id is not None:
        _require_provider_model(
            db,
            provider_id=normalized_provider_id,
            model_id=payload.default_model_id,
            require_enabled=True,
        )

    encrypted_api_key = row.api_key_ciphertext
    if payload.api_key is not None:
        if normalized_provider_id == "local":
            raise AiModelSettingsError(
                status_code=422,
                code="admin.ai_model_local_key_not_allowed",
            )
        try:
            encrypted_api_key = encrypt_api_key(payload.api_key)
        except AiModelCredentialError as exc:
            raise AiModelSettingsError(
                status_code=503,
                code="admin.ai_model_credential_encryption_unavailable",
            ) from exc
    elif payload.clear_api_key:
        encrypted_api_key = None

    if normalized_provider_id != "local" and payload.enabled and not encrypted_api_key:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_key_required",
            context={"provider_id": normalized_provider_id},
        )

    now = utcnow_naive()
    result = db.execute(
        update(AiModelProviderConfig)
        .where(
            AiModelProviderConfig.provider_id == normalized_provider_id,
            AiModelProviderConfig.version == row.version,
        )
        .values(
            enabled=payload.enabled,
            endpoint_url=endpoint_url,
            default_model_id=payload.default_model_id,
            api_key_ciphertext=encrypted_api_key,
            version=row.version + 1,
            updated_by=actor_user_id,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        _raise_version_conflict()


def discover_ai_model_provider_catalog(
    db: Session,
    *,
    provider_id: str,
    expected_registry_digest: str,
    actor_user_id: str,
    settings: Settings | None = None,
) -> int:
    """Refresh one provider inventory without automatically approving models."""

    assert_registry_digest(expected_registry_digest)
    normalized_provider_id = provider_id.strip().lower()
    provider = _ensure_provider_row(
        db,
        normalized_provider_id,
        actor_user_id=actor_user_id,
    )
    resolved_settings = settings or get_settings()
    pool_values = (
        _legacy_pool_values(
            route="local",
            provider_id=normalized_provider_id,
            settings=resolved_settings,
        )
        if normalized_provider_id == "local"
        else None
    )
    endpoint_url = (provider.endpoint_url or "").strip() or (
        pool_values.base_url.strip() if pool_values is not None else ""
    )
    _validate_endpoint_url(endpoint_url or None, provider_id=normalized_provider_id)

    api_key = (
        pool_values.api_key.strip()
        if normalized_provider_id == "local" and pool_values is not None
        else ""
    )
    if normalized_provider_id != "local":
        if not provider.api_key_ciphertext:
            raise AiModelSettingsError(
                status_code=422,
                code="admin.ai_model_provider_key_required",
                context={"provider_id": normalized_provider_id},
            )
        try:
            api_key = decrypt_api_key(provider.api_key_ciphertext).get_secret_value()
        except AiModelCredentialError as exc:
            raise AiModelSettingsError(
                status_code=503,
                code="admin.ai_model_credential_encryption_unavailable",
            ) from exc

    try:
        discovered = discover_provider_models(
            normalized_provider_id,
            endpoint_url,
            api_key or None,
            min(
                30.0,
                (
                    pool_values.long_generation_timeout_seconds
                    if pool_values is not None
                    else resolved_settings.llm_external_long_generation_timeout_seconds
                ),
            ),
        )
    except ProviderModelDiscoveryError as exc:
        if exc.code == "api_key_required":
            raise AiModelSettingsError(
                status_code=422,
                code="admin.ai_model_provider_key_required",
                context={"provider_id": normalized_provider_id},
            ) from exc
        raise AiModelSettingsError(
            status_code=502,
            code="admin.ai_model_discovery_failed",
            context={"provider_id": normalized_provider_id},
        ) from exc

    now = utcnow_naive()
    rows = list(
        db.scalars(
            select(AiModelCatalogEntry).where(
                AiModelCatalogEntry.provider_id == normalized_provider_id
            )
        ).all()
    )
    rows_by_key = {row.model_key: row for row in rows}
    discovered_keys = {item.model_key for item in discovered}

    for item in discovered:
        row = rows_by_key.get(item.model_key)
        if row is None:
            db.add(
                AiModelCatalogEntry(
                    id=new_id(),
                    provider_id=normalized_provider_id,
                    model_key=item.model_key,
                    display_name=item.display_name,
                    capabilities_json=list(item.capabilities),
                    source="discovered",
                    discovery_status="active",
                    last_seen_at=now,
                    enabled=False,
                    version=1,
                    created_by=actor_user_id,
                    updated_by=actor_user_id,
                )
            )
            continue

        changed = row.discovery_status != "active" or row.last_seen_at != now
        row.discovery_status = "active"
        row.last_seen_at = now
        if row.source == "discovered":
            if row.display_name != item.display_name:
                row.display_name = item.display_name
                changed = True
            if not row.capabilities and item.capabilities:
                row.capabilities_json = list(item.capabilities)
                changed = True
        if changed:
            row.version += 1
            row.updated_by = actor_user_id
            row.updated_at = now

    for row in rows:
        if (
            row.model_key not in discovered_keys
            and row.discovery_status != "stale"
        ):
            row.discovery_status = "stale"
            row.version += 1
            row.updated_by = actor_user_id
            row.updated_at = now

    db.flush()
    return len(discovered)


def create_ai_model_catalog_entry(
    db: Session,
    *,
    payload: AiModelCatalogCreateRequest,
    actor_user_id: str,
) -> None:
    assert_registry_digest(payload.expected_registry_digest)
    _ensure_provider_row(db, payload.provider_id, actor_user_id=actor_user_id)
    row = AiModelCatalogEntry(
        id=new_id(),
        provider_id=payload.provider_id,
        model_key=payload.model_key,
        display_name=payload.display_name,
        capabilities_json=list(payload.capabilities),
        enabled=payload.enabled,
        version=1,
        created_by=actor_user_id,
        updated_by=actor_user_id,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AiModelSettingsError(
            status_code=409,
            code="admin.ai_model_catalog_duplicate",
        ) from exc


def update_ai_model_catalog_entry(
    db: Session,
    *,
    model_id: str,
    payload: AiModelCatalogUpdateRequest,
    actor_user_id: str,
) -> None:
    assert_registry_digest(payload.expected_registry_digest)
    row = db.get(AiModelCatalogEntry, model_id)
    if row is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_catalog_not_found",
            context={"model_id": model_id},
        )
    if row.version != payload.expected_version:
        _raise_version_conflict()
    if row.source == "discovered" and payload.model_key != row.model_key:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_discovered_key_read_only",
            context={"model_id": model_id},
        )
    if not payload.enabled and _model_is_referenced(db, model_id=model_id):
        raise AiModelSettingsError(
            status_code=409,
            code="admin.ai_model_catalog_in_use",
            context={"model_id": model_id},
        )

    result = db.execute(
        update(AiModelCatalogEntry)
        .where(
            AiModelCatalogEntry.id == model_id,
            AiModelCatalogEntry.version == payload.expected_version,
        )
        .values(
            model_key=payload.model_key,
            display_name=payload.display_name,
            capabilities_json=list(payload.capabilities),
            enabled=payload.enabled,
            version=payload.expected_version + 1,
            updated_by=actor_user_id,
            updated_at=utcnow_naive(),
        )
    )
    if result.rowcount != 1:
        _raise_version_conflict()


def upsert_ai_model_route_override(
    db: Session,
    *,
    workload_id: str,
    payload: AiModelRouteOverrideUpdateRequest,
    actor_user_id: str,
) -> None:
    assert_registry_digest(payload.expected_registry_digest)
    workload = get_ai_capability_registry().get_llm_workload(workload_id)
    if workload is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_workload_not_found",
            context={"workload_id": workload_id},
        )
    provider_id = _validate_route_override(db, workload=workload, payload=payload)

    row = db.scalar(
        select(AiModelRouteOverride).where(AiModelRouteOverride.workload_id == workload.workload_id)
    )
    if row is None:
        if payload.expected_version not in (None, 0):
            _raise_version_conflict()
        db.add(
            AiModelRouteOverride(
                id=new_id(),
                workload_id=workload.workload_id,
                route_mode=payload.route_mode,
                provider_id=provider_id,
                model_ids_json=dict(payload.model_ids),
                local_max_output_tokens=payload.local_max_output_tokens,
                external_max_output_tokens=payload.external_max_output_tokens,
                version=1,
                updated_by=actor_user_id,
            )
        )
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            _raise_version_conflict(exc)
        return
    if payload.expected_version != row.version:
        _raise_version_conflict()

    result = db.execute(
        update(AiModelRouteOverride)
        .where(
            AiModelRouteOverride.id == row.id,
            AiModelRouteOverride.version == row.version,
        )
        .values(
            route_mode=payload.route_mode,
            provider_id=provider_id,
            model_ids_json=dict(payload.model_ids),
            local_max_output_tokens=payload.local_max_output_tokens,
            external_max_output_tokens=payload.external_max_output_tokens,
            version=row.version + 1,
            updated_by=actor_user_id,
            updated_at=utcnow_naive(),
        )
    )
    if result.rowcount != 1:
        _raise_version_conflict()


def delete_ai_model_route_override(
    db: Session,
    *,
    workload_id: str,
    expected_registry_digest: str,
    expected_version: int,
) -> None:
    assert_registry_digest(expected_registry_digest)
    row = db.scalar(
        select(AiModelRouteOverride).where(
            AiModelRouteOverride.workload_id == workload_id.strip().lower()
        )
    )
    if row is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_route_override_not_found",
            context={"workload_id": workload_id},
        )
    if row.version != expected_version:
        _raise_version_conflict()
    db.delete(row)
    db.flush()


def _serialize_provider(
    provider_id: str,
    row: AiModelProviderConfig | None,
    *,
    settings: Settings,
) -> AiModelProviderResponse:
    descriptor = llm_provider_descriptor(provider_id)
    if descriptor is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_provider_not_found",
            context={"provider_id": provider_id},
        )
    pool_values = (
        _legacy_pool_values(route="local", provider_id=provider_id, settings=settings)
        if descriptor.route_mode == "local"
        else None
    )
    stored_endpoint_url = (row.endpoint_url or "").strip() if row is not None else ""
    default_endpoint_url = (
        pool_values.base_url.strip()
        if pool_values is not None
        else descriptor.default_endpoint_url
    )
    return AiModelProviderResponse(
        provider_id=provider_id,
        display_name=descriptor.display_name,
        route_mode=descriptor.route_mode,
        credential_kind=descriptor.credential_kind,
        enabled=row.enabled if row is not None else descriptor.route_mode == "local",
        endpoint_url=stored_endpoint_url or default_endpoint_url or None,
        endpoint_source=(
            "custom"
            if stored_endpoint_url and stored_endpoint_url != default_endpoint_url
            else "default"
        ),
        has_api_key=bool(row and row.api_key_ciphertext),
        default_model_id=row.default_model_id if row is not None else None,
        version=row.version if row is not None else 0,
        updated_at=row.updated_at if row is not None else None,
    )


def _serialize_model(row: AiModelCatalogEntry) -> AiModelCatalogEntryResponse:
    return AiModelCatalogEntryResponse(
        id=row.id,
        provider_id=row.provider_id,  # type: ignore[arg-type]
        model_key=row.model_key,
        display_name=row.display_name,
        capabilities=list(row.capabilities),  # type: ignore[arg-type]
        enabled=row.enabled,
        source=row.source,  # type: ignore[arg-type]
        discovery_status=row.discovery_status,  # type: ignore[arg-type]
        last_seen_at=row.last_seen_at,
        version=row.version,
        updated_at=row.updated_at,
    )


def _serialize_override(row: AiModelRouteOverride) -> AiModelRouteOverrideResponse:
    return AiModelRouteOverrideResponse(
        route_mode=row.route_mode,  # type: ignore[arg-type]
        provider_id=row.provider_id,  # type: ignore[arg-type]
        model_ids=row.model_ids,
        local_max_output_tokens=row.local_max_output_tokens,
        external_max_output_tokens=row.external_max_output_tokens,
        version=row.version,
        updated_at=row.updated_at,
    )


def _serialize_workload(
    db: Session,
    descriptor: RegisteredLlmWorkload,
    override: AiModelRouteOverride | None,
) -> AiModelWorkloadResponse:
    serialized_override = _serialize_override(override) if override is not None else None
    resolved_routes: list[AiModelResolvedRouteResponse] = []
    readiness_code: str | None = None
    for model_role in descriptor.model_roles:
        try:
            resolved = resolve_ai_model_workload_route(
                db,
                workload_id=descriptor.workload_id,
                model_role=model_role,
            )
        except AiModelSettingsError as exc:
            readiness_code = exc.code
            break
        resolved_routes.append(
            AiModelResolvedRouteResponse(
                model_role=model_role,
                provider_id=resolved.provider_id,  # type: ignore[arg-type]
                model_key=resolved.model_key,
                route_source=resolved.route_source,
                config_source=resolved.config_source,
                max_output_tokens=resolved.max_output_tokens,
            )
        )
    return AiModelWorkloadResponse(
        workload_id=descriptor.workload_id,
        task_kind=descriptor.task_kind,
        owner_domain=descriptor.owner_domain,
        app_ids=list(descriptor.app_ids),
        description=descriptor.description,
        label_key=descriptor.label_key,
        description_key=descriptor.description_key,
        execution_kind=descriptor.execution_kind,
        default_route=descriptor.default_route,
        effective_route=(
            serialized_override.route_mode
            if serialized_override is not None
            else descriptor.default_route
        ),
        allowed_routes=list(descriptor.allowed_routes),
        allowed_providers=list(descriptor.allowed_providers),
        required_capabilities=list(descriptor.required_capabilities),
        model_roles=list(descriptor.model_roles),
        external_data=descriptor.external_data,
        local_max_output_tokens=_effective_max_output_tokens(
            descriptor,
            override,
            route="local",
        ),
        external_max_output_tokens=_effective_max_output_tokens(
            descriptor,
            override,
            route="external",
        ),
        ready=readiness_code is None,
        readiness_code=readiness_code,
        resolved_routes=resolved_routes,
        override=serialized_override,
        management_surface=descriptor.management_surface,
    )


def _effective_max_output_tokens(
    workload: RegisteredLlmWorkload,
    override: AiModelRouteOverride | None,
    *,
    route: Literal["local", "external"] | str,
) -> int:
    if route == "local":
        if override is not None and override.local_max_output_tokens is not None:
            return override.local_max_output_tokens
        return workload.local_max_output_tokens
    if override is not None and override.external_max_output_tokens is not None:
        return override.external_max_output_tokens
    return workload.external_max_output_tokens


def _validate_endpoint_url(endpoint_url: str | None, *, provider_id: str) -> None:
    if endpoint_url is None:
        return
    parsed = urlsplit(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_endpoint_invalid",
        )
    if parsed.username or parsed.password:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_endpoint_invalid",
        )
    if provider_id == "local":
        return
    if parsed.scheme != "https" or parsed.port not in {None, 443} or not parsed.hostname:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_endpoint_public_https_required",
        )
    try:
        addresses = {
            ipaddress.ip_address(sockaddr[0])
            for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
                parsed.hostname,
                443,
                type=socket.SOCK_STREAM,
            )
        }
    except (socket.gaierror, ValueError) as exc:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_endpoint_unresolvable",
        ) from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_endpoint_public_https_required",
        )


def _runtime_provider_id(
    db: Session,
    *,
    workload: RegisteredLlmWorkload,
    route: str,
    override: AiModelRouteOverride | None,
) -> str:
    if override is not None:
        provider_id = (override.provider_id or ("local" if route == "local" else "")).strip()
        if not provider_id:
            raise AiModelSettingsError(
                status_code=503,
                code="admin.ai_model_provider_required",
            )
        descriptor = llm_provider_descriptor(provider_id)
        if descriptor is None or descriptor.route_mode != route:
            raise AiModelSettingsError(
                status_code=503,
                code="admin.ai_model_route_provider_mismatch",
            )
        if (
            route == "external"
            and workload.allowed_providers
            and provider_id not in workload.allowed_providers
        ):
            raise AiModelSettingsError(
                status_code=503,
                code="admin.ai_model_provider_not_allowed",
                context={"workload_id": workload.workload_id},
            )
        return provider_id

    if route == "local":
        return "local"

    allowed = tuple(
        provider_id
        for provider_id in (workload.allowed_providers or external_llm_provider_ids())
        if (
            (descriptor := llm_provider_descriptor(provider_id)) is not None
            and descriptor.route_mode == "external"
        )
    )
    if not allowed:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_required",
        )
    enabled = tuple(
        provider_id
        for provider_id in allowed
        if (
            (row := db.get(AiModelProviderConfig, provider_id)) is not None
            and row.enabled
        )
    )
    if len(enabled) == 1:
        return enabled[0]
    if not enabled:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_ready",
        )
    raise AiModelSettingsError(
        status_code=503,
        code="admin.ai_model_provider_required",
    )


def _legacy_pool_values(
    *,
    route: str,
    provider_id: str,
    settings: Settings,
):
    try:
        return resolve_llm_pool_config_values(
            pool=route,
            provider=None if route == "local" else provider_id,
            settings=settings,
        )
    except ValueError as exc:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_ready",
            context={"provider_id": provider_id},
        ) from exc


def _require_model_capabilities(
    model: AiModelCatalogEntry,
    *,
    workload: RegisteredLlmWorkload,
) -> None:
    if not set(workload.required_capabilities).issubset(model.capabilities):
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_capability_mismatch",
            context={"model_id": model.id, "workload_id": workload.workload_id},
        )


def _ensure_provider_row(
    db: Session,
    provider_id: str,
    *,
    actor_user_id: str,
) -> AiModelProviderConfig:
    row = db.get(AiModelProviderConfig, provider_id)
    if row is not None:
        return row
    descriptor = llm_provider_descriptor(provider_id)
    if descriptor is None or not descriptor.control_plane_visible:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_provider_not_found",
            context={"provider_id": provider_id},
        )
    row = AiModelProviderConfig(
        provider_id=provider_id,
        enabled=descriptor.route_mode == "local",
        version=1,
        updated_by=actor_user_id,
    )
    db.add(row)
    db.flush()
    return row


def _require_provider_model(
    db: Session,
    *,
    provider_id: str,
    model_id: str,
    require_enabled: bool,
) -> AiModelCatalogEntry:
    row = db.get(AiModelCatalogEntry, model_id)
    if row is None or row.provider_id != provider_id or (require_enabled and not row.enabled):
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_catalog_invalid_for_provider",
            context={"model_id": model_id, "provider_id": provider_id},
        )
    if require_enabled and row.discovery_status != "active":
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_selected_model_not_served",
            context={"model_id": model_id, "provider_id": provider_id},
        )
    return row


def _validate_route_override(
    db: Session,
    *,
    workload: RegisteredLlmWorkload,
    payload: AiModelRouteOverrideUpdateRequest,
) -> str:
    if payload.route_mode not in workload.allowed_routes:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_route_not_allowed",
            context={"workload_id": workload.workload_id},
        )
    provider_id = payload.provider_id or ("local" if payload.route_mode == "local" else "")
    if not provider_id:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_required",
        )
    if payload.route_mode == "local" and provider_id != "local":
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_route_provider_mismatch",
        )
    if payload.route_mode == "external" and provider_id == "local":
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_route_provider_mismatch",
        )
    if (
        payload.route_mode == "external"
        and workload.allowed_providers
        and provider_id not in workload.allowed_providers
    ):
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_not_allowed",
            context={"workload_id": workload.workload_id},
        )
    provider = db.get(AiModelProviderConfig, provider_id)
    if provider is None or not provider.enabled:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_not_ready",
            context={"provider_id": provider_id},
        )

    unknown_roles = sorted(set(payload.model_ids) - set(workload.model_roles))
    if unknown_roles:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_role_not_allowed",
            context={"model_role": unknown_roles[0]},
        )
    selected_models = [
        _require_provider_model(
            db,
            provider_id=provider_id,
            model_id=model_id,
            require_enabled=True,
        )
        for model_id in payload.model_ids.values()
    ]
    if not selected_models and provider.default_model_id:
        selected_models.append(
            _require_provider_model(
                db,
                provider_id=provider_id,
                model_id=provider.default_model_id,
                require_enabled=True,
            )
        )
    if payload.route_mode == "external" and not selected_models:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_selection_required",
        )
    required_capabilities = set(workload.required_capabilities)
    for model in selected_models:
        if not required_capabilities.issubset(model.capabilities):
            raise AiModelSettingsError(
                status_code=422,
                code="admin.ai_model_capability_mismatch",
                context={"model_id": model.id, "workload_id": workload.workload_id},
            )
    return provider_id


def _model_is_referenced(db: Session, *, model_id: str) -> bool:
    provider_default = db.scalar(
        select(AiModelProviderConfig.provider_id).where(
            AiModelProviderConfig.default_model_id == model_id
        )
    )
    if provider_default is not None:
        return True
    return any(
        model_id in row.model_ids.values() for row in db.scalars(select(AiModelRouteOverride)).all()
    )


def _raise_version_conflict(exc: Exception | None = None) -> None:
    error = AiModelSettingsError(
        status_code=409,
        code="admin.ai_model_version_conflict",
    )
    if exc is not None:
        raise error from exc
    raise error


__all__ = [
    "AiModelSettingsError",
    "ResolvedLlmWorkloadRoute",
    "ai_model_registry_digest",
    "assert_registry_digest",
    "create_ai_model_catalog_entry",
    "delete_ai_model_route_override",
    "discover_ai_model_provider_catalog",
    "get_ai_model_provider_default_model_key",
    "get_ai_model_settings_snapshot",
    "resolve_ai_model_workload_route",
    "update_ai_model_catalog_entry",
    "update_ai_model_provider",
    "upsert_ai_model_route_override",
]
