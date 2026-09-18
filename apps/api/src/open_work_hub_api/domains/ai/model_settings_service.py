from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from open_work_hub_api.core.llm_provider_registry import (
    llm_provider_descriptor,
    llm_provider_ids,
    parse_external_llm_provider_allowlist,
)
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.ai.agent_runtime import (
    get_agent_runtime_adapter_descriptor,
)
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
    AiModelPolicyDefault,
)
from open_work_hub_api.domains.ai.model_settings_schemas import (
    AiAgentRuntimeAdapterResponse,
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
    AiModelPolicyDefaultResponse,
    AiModelPolicyDefaultUpdateRequest,
    AiModelConnectionCreateRequest,
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
    config_source: Literal["database"]
    local_max_output_tokens: int
    external_max_output_tokens: int
    max_output_tokens: int
    model_entry_id: str | None = None
    runtime_adapter_id: str = "chat_completion"
    app_id: str = ""
    requires_credentials: bool = True
    connection_source: str = "global"
    model_source: str = "connection"
    output_cap_source: str = "global"

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


def _workload_app(workload: RegisteredLlmWorkload, app_id: str | None) -> str:
    if app_id is None and len(workload.app_ids) == 1:
        return workload.app_id
    if app_id not in workload.app_ids:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_workload_app_required",
            context={"workload_id": workload.workload_id},
        )
    return str(app_id)


def _policy_rows(db: Session, app_id: str, route: str):
    return (
        db.get(AiModelPolicyDefault, (app_id, route)),
        db.get(AiModelPolicyDefault, ("", route)),
    )


def _resolved_cap(
    db: Session,
    workload: RegisteredLlmWorkload,
    app_id: str,
    override: AiModelRouteOverride | None,
    route: str,
) -> tuple[int, str]:
    value = getattr(override, f"{route}_max_output_tokens", None)
    if value is not None:
        return value, "workload"
    app, company = _policy_rows(db, app_id, route)
    for row, source in ((app, "app"), (company, "global")):
        if row is not None and row.max_output_tokens is not None:
            return row.max_output_tokens, source
    return getattr(workload, f"{route}_max_output_tokens"), "registry"


def resolve_ai_model_workload_route(
    db: Session,
    *,
    workload_id: str,
    app_id: str | None = None,
    model_role: str = "default",
    settings: Settings | None = None,
    require_tool_calling: bool = False,
) -> ResolvedLlmWorkloadRoute:
    """Resolve company -> app -> workload policy once, without env fallback."""
    workload = get_ai_capability_registry().get_llm_workload(workload_id)
    if workload is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_workload_not_found",
            context={"workload_id": workload_id},
        )
    app_id = _workload_app(workload, app_id)
    role = model_role.strip().lower()
    if role not in workload.model_roles:
        raise AiModelSettingsError(
            status_code=422, code="admin.ai_model_role_not_allowed", context={"model_role": role}
        )
    override = db.scalar(
        select(AiModelRouteOverride).where(
            AiModelRouteOverride.workload_id == workload.workload_id,
            AiModelRouteOverride.app_id == app_id,
        )
    )
    route = (override.route_mode if override is not None else None) or workload.default_route
    runtime = (
        override.runtime_adapter_id if override is not None else None
    ) or workload.default_runtime_adapter
    if route not in workload.allowed_routes:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_route_not_allowed",
            context={"workload_id": workload_id},
        )
    if runtime not in workload.allowed_runtime_adapters:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_runtime_adapter_not_allowed",
            context={"workload_id": workload_id},
        )
    app, company = _policy_rows(db, app_id, route)
    connection_id = None
    selected_model_id = None
    connection_source = "global"
    model_source = "connection"
    for row, source in ((override, "workload"), (app, "app"), (company, "global")):
        if row is None:
            continue
        model_id = (
            row.model_ids.get(role) if isinstance(row, AiModelRouteOverride) else row.model_id
        )
        if row.provider_id:
            connection_id = row.provider_id
            connection_source = source
            selected_model_id = model_id
            model_source = source if model_id else "connection"
            break
    if not connection_id:
        raise AiModelSettingsError(status_code=503, code="admin.ai_model_provider_required")
    connection = db.get(AiModelProviderConfig, connection_id)
    if connection is None or not connection.enabled:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_ready",
            context={"provider_id": connection_id},
        )
    if connection.route_mode != route:
        raise AiModelSettingsError(status_code=503, code="admin.ai_model_route_provider_mismatch")
    kind = connection.provider_kind
    if route == "external" and kind not in parse_external_llm_provider_allowlist(
        (settings or get_settings()).llm_external_allowed_providers
    ):
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_allowed",
            context={"provider_id": connection_id},
        )
    if (
        route == "external"
        and workload.allowed_providers
        and kind not in workload.allowed_providers
    ):
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_allowed",
            context={"workload_id": workload_id},
        )
    _require_runtime_route_compatibility(
        workload, runtime_adapter_id=runtime, route=route, provider_id=kind, status_code=503
    )
    selected_model_id = selected_model_id or connection.default_model_id
    if not selected_model_id:
        raise AiModelSettingsError(status_code=503, code="admin.ai_model_selection_required")
    model = _require_provider_model(
        db, provider_id=connection_id, model_id=selected_model_id, require_enabled=True
    )
    _require_model_capabilities(model, workload=workload)
    if require_tool_calling and "tool_calling" not in model.capabilities:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_capability_mismatch",
            context={"model_id": model.id, "workload_id": workload_id},
        )
    endpoint = (connection.endpoint_url or "").strip()
    if not endpoint:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_not_ready",
            context={"provider_id": connection_id},
        )
    if route == "local":
        _validate_endpoint_url(endpoint, provider_id=connection_id, route_mode="local")
    api_key = None
    if connection.api_key_ciphertext:
        try:
            api_key = decrypt_api_key(connection.api_key_ciphertext)
        except AiModelCredentialError as exc:
            raise AiModelSettingsError(
                status_code=503, code="admin.ai_model_credential_encryption_unavailable"
            ) from exc
    if connection.credential_kind == "api_key" and api_key is None:
        raise AiModelSettingsError(
            status_code=503,
            code="admin.ai_model_provider_key_required",
            context={"provider_id": connection_id},
        )
    local_cap, local_source = _resolved_cap(db, workload, app_id, override, "local")
    external_cap, external_source = _resolved_cap(db, workload, app_id, override, "external")
    return ResolvedLlmWorkloadRoute(
        workload=workload,
        app_id=app_id,
        route=route,
        provider_id=connection_id,
        adapter_provider=kind,
        model_role=role,
        model_key=model.model_key,
        endpoint_url=endpoint,
        api_key=api_key,
        route_source="override" if override and override.route_mode else "default",
        config_source="database",
        local_max_output_tokens=local_cap,
        external_max_output_tokens=external_cap,
        max_output_tokens=local_cap if route == "local" else external_cap,
        model_entry_id=model.id,
        runtime_adapter_id=runtime,
        requires_credentials=connection.credential_kind == "api_key",
        connection_source=connection_source,
        model_source=model_source,
        output_cap_source=local_source if route == "local" else external_source,
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
    overrides_by_workload = {(row.app_id, row.workload_id): row for row in override_rows}

    providers = [
        _serialize_provider(
            provider_id,
            providers_by_id.get(provider_id),
            settings=settings,
        )
        for provider_id in dict.fromkeys(
            (*llm_provider_ids(control_plane_only=True), *providers_by_id)
        )
    ]
    # Discovery rows absent from the provider's current inventory are retained
    # for audit/history, but are not part of the selectable admin catalog.
    models = [_serialize_model(row) for row in model_rows if row.discovery_status == "active"]
    workloads = [
        _serialize_workload(
            db,
            descriptor,
            overrides_by_workload.get((app_id, descriptor.workload_id)),
            app_id=app_id,
        )
        for descriptor in sorted(
            registry.llm_workloads.values(),
            key=lambda item: (item.owner_domain, item.workload_id),
        )
        for app_id in descriptor.app_ids
    ]
    orphaned = [
        AiModelOrphanedOverrideResponse(
            app_id=row.app_id,
            workload_id=row.workload_id,
            route_mode=row.route_mode,  # type: ignore[arg-type]
            provider_id=row.provider_id,  # type: ignore[arg-type]
            model_ids=row.model_ids,
            local_max_output_tokens=row.local_max_output_tokens,
            external_max_output_tokens=row.external_max_output_tokens,
            runtime_adapter_id=row.runtime_adapter_id,
            version=row.version,
            updated_at=row.updated_at,
        )
        for row in override_rows
        if row.workload_id not in registry.llm_workloads
        or row.app_id not in registry.llm_workloads[row.workload_id].app_ids
    ]
    return AiModelSettingsResponse(
        registry_digest=ai_model_registry_digest(),
        providers=providers,
        models=models,
        workloads=workloads,
        orphaned_overrides=orphaned,
        defaults=[
            AiModelPolicyDefaultResponse.model_validate(row, from_attributes=True)
            for row in db.scalars(
                select(AiModelPolicyDefault).order_by(
                    AiModelPolicyDefault.app_id, AiModelPolicyDefault.route_mode
                )
            ).all()
        ],
        provider_kinds=list(llm_provider_ids()),
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
    row = db.get(AiModelProviderConfig, normalized_provider_id)
    descriptor = llm_provider_descriptor(row.provider_kind if row else normalized_provider_id)
    if descriptor is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_provider_not_found",
            context={"provider_id": normalized_provider_id},
        )
    route = row.route_mode if row else descriptor.route_mode
    endpoint_url = payload.endpoint_url or descriptor.default_endpoint_url or None
    _validate_endpoint_url(endpoint_url, provider_id=normalized_provider_id, route_mode=route)
    expected_version = payload.expected_version
    if row is None:
        if expected_version not in (None, 0):
            _raise_version_conflict()
        row = AiModelProviderConfig(
            provider_id=normalized_provider_id,
            provider_kind=descriptor.provider_id,
            route_mode=descriptor.route_mode,
            credential_kind=descriptor.credential_kind,
            display_name=descriptor.display_name,
            enabled=False,
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
        try:
            encrypted_api_key = encrypt_api_key(payload.api_key)
        except AiModelCredentialError as exc:
            raise AiModelSettingsError(
                status_code=503,
                code="admin.ai_model_credential_encryption_unavailable",
            ) from exc
    elif payload.clear_api_key:
        encrypted_api_key = None

    credential_kind = payload.credential_kind or row.credential_kind
    if (
        descriptor.provider_id not in {"local", "openai_compatible"}
        and credential_kind != "api_key"
    ):
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_key_required",
            context={"provider_id": normalized_provider_id},
        )
    if credential_kind == "none":
        encrypted_api_key = None
    if (
        credential_kind == "api_key"
        and payload.enabled
        and not encrypted_api_key
        and not payload.clear_api_key
    ):
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_key_required",
            context={"provider_id": normalized_provider_id},
        )

    before = _ready_policies(db) if row.default_model_id != payload.default_model_id else []
    verified = row.verified_version == row.version and (
        row.endpoint_url == endpoint_url
        and row.api_key_ciphertext == encrypted_api_key
        and row.default_model_id == payload.default_model_id
        and row.credential_kind == credential_kind
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
            display_name=payload.display_name or row.display_name or descriptor.display_name,
            credential_kind=credential_kind,
            verified_version=row.version + 1 if verified else None,
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
    if payload.enabled and not payload.clear_api_key:
        _preserve_ready_policies(db, before)


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
    endpoint_url = (provider.endpoint_url or "").strip()
    _validate_endpoint_url(
        endpoint_url or None, provider_id=normalized_provider_id, route_mode=provider.route_mode
    )
    api_key = ""
    if provider.api_key_ciphertext:
        try:
            api_key = decrypt_api_key(provider.api_key_ciphertext).get_secret_value()
        except AiModelCredentialError as exc:
            raise AiModelSettingsError(
                status_code=503, code="admin.ai_model_credential_encryption_unavailable"
            ) from exc
    if provider.credential_kind == "api_key" and not api_key:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_key_required",
            context={"provider_id": normalized_provider_id},
        )
    version = provider.version
    kind = provider.provider_kind
    requires_credentials = provider.credential_kind == "api_key"
    # A saved connection is required. Release its read transaction before network I/O.
    db.rollback()
    try:
        discovered = discover_provider_models(
            kind,
            endpoint_url,
            api_key or None,
            min(30.0, resolved_settings.llm_request_timeout_seconds),
            requires_credentials=requires_credentials,
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

    provider = db.scalar(
        select(AiModelProviderConfig)
        .where(AiModelProviderConfig.provider_id == normalized_provider_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if provider is None or provider.version != version:
        _raise_version_conflict()
    provider.verified_version = None
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
        if row.model_key not in discovered_keys and row.discovery_status != "stale":
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

    before = _ready_policies(db)
    # A model's transport identity can change independently of its connection.
    # Invalidate the saved probe under the same transaction as the catalog edit.
    db.execute(
        update(AiModelProviderConfig)
        .where(AiModelProviderConfig.default_model_id == model_id)
        .values(verified_version=None)
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

    _preserve_ready_policies(db, before)


def upsert_ai_model_route_override(
    db: Session,
    *,
    workload_id: str,
    payload: AiModelRouteOverrideUpdateRequest,
    actor_user_id: str,
    app_id: str | None = None,
) -> None:
    assert_registry_digest(payload.expected_registry_digest)
    workload = get_ai_capability_registry().get_llm_workload(workload_id)
    if workload is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_workload_not_found",
            context={"workload_id": workload_id},
        )
    app_id = _workload_app(workload, app_id)
    _validate_route_override(db, workload=workload, payload=payload)
    row = db.scalar(
        select(AiModelRouteOverride)
        .where(
            AiModelRouteOverride.workload_id == workload.workload_id,
            AiModelRouteOverride.app_id == app_id,
        )
        .with_for_update()
    )
    if payload.expected_version not in ((row.version,) if row else (None, 0)):
        _raise_version_conflict()
    empty = not any(
        (
            payload.route_mode,
            payload.provider_id,
            payload.model_ids,
            payload.local_max_output_tokens,
            payload.external_max_output_tokens,
            payload.runtime_adapter_id,
        )
    )
    if empty:
        before = _ready_policies(db)
        if row:
            db.delete(row)
        db.flush()
        _preserve_ready_policies(db, before)
        return
    if row is None:
        row = AiModelRouteOverride(
            id=new_id(), workload_id=workload.workload_id, app_id=app_id, version=0
        )
        db.add(row)
    row.route_mode = payload.route_mode
    row.provider_id = payload.provider_id
    row.model_ids_json = dict(payload.model_ids)
    row.local_max_output_tokens = payload.local_max_output_tokens
    row.external_max_output_tokens = payload.external_max_output_tokens
    row.runtime_adapter_id = payload.runtime_adapter_id
    row.version += 1
    row.updated_by = actor_user_id
    row.updated_at = utcnow_naive()
    try:
        db.flush()
    except IntegrityError as exc:
        _raise_version_conflict(exc)
    _preserve_ready_policies(db, [(app_id, workload_id, role) for role in workload.model_roles])


def delete_ai_model_route_override(
    db: Session,
    *,
    workload_id: str,
    expected_registry_digest: str,
    expected_version: int,
    app_id: str | None = None,
) -> None:
    assert_registry_digest(expected_registry_digest)
    workload = get_ai_capability_registry().get_llm_workload(workload_id)
    # Explicit stored scope also permits cleanup after a workload or owning app
    # is removed from the registry. Never infer the scope of an orphan.
    if app_id is None:
        if workload is None:
            raise AiModelSettingsError(
                status_code=404,
                code="admin.ai_model_workload_not_found",
                context={"workload_id": workload_id},
            )
        app_id = _workload_app(workload, app_id)
    row = db.scalar(
        select(AiModelRouteOverride)
        .where(
            AiModelRouteOverride.workload_id == workload_id,
            AiModelRouteOverride.app_id == app_id,
        )
        .with_for_update()
    )
    if row is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_route_override_not_found",
            context={"workload_id": workload_id},
        )
    if row.version != expected_version:
        _raise_version_conflict()
    before = _ready_policies(db)
    db.delete(row)
    db.flush()
    _preserve_ready_policies(db, before)


def _serialize_provider(
    provider_id: str,
    row: AiModelProviderConfig | None,
    *,
    settings: Settings,
) -> AiModelProviderResponse:
    descriptor = llm_provider_descriptor(row.provider_kind if row else provider_id)
    if descriptor is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_provider_not_found",
            context={"provider_id": provider_id},
        )
    endpoint = (row.endpoint_url or "") if row else descriptor.default_endpoint_url
    return AiModelProviderResponse(
        provider_id=provider_id,
        provider_kind=descriptor.provider_id,
        display_name=(row.display_name or descriptor.display_name)
        if row
        else descriptor.display_name,
        preset=row.preset if row else "",
        verified=bool(row and row.verified_version == row.version),
        route_mode=row.route_mode if row else descriptor.route_mode,
        credential_kind=row.credential_kind if row else descriptor.credential_kind,
        enabled=row.enabled if row else False,
        endpoint_url=endpoint or None,
        endpoint_source="default" if endpoint == descriptor.default_endpoint_url else "custom",
        has_api_key=bool(row and row.api_key_ciphertext),
        default_model_id=row.default_model_id if row else None,
        version=row.version if row else 0,
        updated_at=row.updated_at if row else None,
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
        runtime_adapter_id=row.runtime_adapter_id,
        version=row.version,
        updated_at=row.updated_at,
    )


def _serialize_workload(
    db: Session,
    descriptor: RegisteredLlmWorkload,
    override: AiModelRouteOverride | None,
    *,
    app_id: str,
) -> AiModelWorkloadResponse:
    serialized_override = _serialize_override(override) if override is not None else None
    resolved_routes: list[AiModelResolvedRouteResponse] = []
    readiness_code: str | None = None
    for model_role in descriptor.model_roles:
        try:
            resolved = resolve_ai_model_workload_route(
                db,
                workload_id=descriptor.workload_id,
                app_id=app_id,
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
                connection_source=resolved.connection_source,
                model_source=resolved.model_source,
                output_cap_source=resolved.output_cap_source,
            )
        )
    return AiModelWorkloadResponse(
        app_id=app_id,
        workload_id=descriptor.workload_id,
        task_kind=descriptor.task_kind,
        owner_domain=descriptor.owner_domain,
        app_ids=[app_id],
        description=descriptor.description,
        label_key=descriptor.label_key,
        description_key=descriptor.description_key,
        execution_kind=descriptor.execution_kind,
        default_runtime_adapter=descriptor.default_runtime_adapter,
        effective_runtime_adapter=(
            serialized_override.runtime_adapter_id
            if serialized_override is not None
            and serialized_override.runtime_adapter_id is not None
            else descriptor.default_runtime_adapter
        ),
        allowed_runtime_adapters=list(descriptor.allowed_runtime_adapters),
        runtime_adapters=[
            AiAgentRuntimeAdapterResponse(
                adapter_id=runtime_descriptor.adapter_id,
                display_name=runtime_descriptor.display_name,
                allowed_routes=list(runtime_descriptor.allowed_routes),  # type: ignore[arg-type]
                allowed_providers=list(runtime_descriptor.allowed_providers),
            )
            for adapter_id in descriptor.allowed_runtime_adapters
            if (runtime_descriptor := get_agent_runtime_adapter_descriptor(adapter_id)) is not None
        ],
        default_route=descriptor.default_route,
        effective_route=(
            serialized_override.route_mode
            if serialized_override is not None and serialized_override.route_mode
            else descriptor.default_route
        ),
        allowed_routes=list(descriptor.allowed_routes),
        allowed_providers=list(descriptor.allowed_providers),
        required_capabilities=list(descriptor.required_capabilities),
        model_roles=list(descriptor.model_roles),
        external_data=descriptor.external_data,
        local_max_output_tokens=_resolved_cap(db, descriptor, app_id, override, "local")[0],
        external_max_output_tokens=_resolved_cap(db, descriptor, app_id, override, "external")[0],
        ready=readiness_code is None,
        readiness_code=readiness_code,
        resolved_routes=resolved_routes,
        override=serialized_override,
        management_surface=descriptor.management_surface,
    )


def _validate_endpoint_url(
    endpoint_url: str | None, *, provider_id: str, route_mode: str | None = None
) -> None:
    if endpoint_url is None:
        return
    parsed = urlsplit(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_endpoint_invalid",
        )
    try:
        port = parsed.port
    except ValueError as exc:
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_endpoint_invalid") from exc
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_endpoint_invalid",
        )
    if (route_mode or ("local" if provider_id == "local" else "external")) == "local":
        allowed_hosts = {
            host.strip().lower()
            for host in get_settings().llm_local_allowed_hosts.split(",")
            if host.strip()
        }
        if not parsed.hostname or parsed.hostname.lower() not in allowed_hosts:
            raise AiModelSettingsError(
                status_code=422, code="admin.ai_model_local_host_not_allowed"
            )
        if parsed.hostname in {"metadata.google.internal", "169.254.169.254"}:
            raise AiModelSettingsError(status_code=422, code="admin.ai_model_endpoint_invalid")
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
        except ValueError:
            address = None
        if address is not None and (
            address.is_link_local or address.is_multicast or address.is_unspecified
        ):
            raise AiModelSettingsError(status_code=422, code="admin.ai_model_endpoint_invalid")
        return
    if parsed.scheme != "https" or port not in {None, 443} or not parsed.hostname:
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
        provider_kind=descriptor.provider_id,
        route_mode=descriptor.route_mode,
        credential_kind=descriptor.credential_kind,
        display_name=descriptor.display_name,
        enabled=False,
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
    db: Session, *, workload: RegisteredLlmWorkload, payload: AiModelRouteOverrideUpdateRequest
) -> None:
    route = payload.route_mode or workload.default_route
    runtime = payload.runtime_adapter_id or workload.default_runtime_adapter
    if route not in workload.allowed_routes:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_route_not_allowed",
            context={"workload_id": workload.workload_id},
        )
    if runtime not in workload.allowed_runtime_adapters:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_runtime_adapter_not_allowed",
            context={"workload_id": workload.workload_id},
        )
    unknown = set(payload.model_ids) - set(workload.model_roles)
    if unknown:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_role_not_allowed",
            context={"model_role": sorted(unknown)[0]},
        )
    if payload.model_ids and not payload.provider_id:
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_provider_required")
    if payload.provider_id:
        provider = db.get(AiModelProviderConfig, payload.provider_id)
        if provider is None or not provider.enabled:
            raise AiModelSettingsError(
                status_code=422,
                code="admin.ai_model_provider_not_ready",
                context={"provider_id": payload.provider_id},
            )
        if provider.route_mode != route:
            raise AiModelSettingsError(
                status_code=422, code="admin.ai_model_route_provider_mismatch"
            )
        _require_runtime_route_compatibility(
            workload,
            runtime_adapter_id=runtime,
            route=route,
            provider_id=provider.provider_kind,
            status_code=422,
        )
        for model_id in payload.model_ids.values():
            model = _require_provider_model(
                db, provider_id=provider.provider_id, model_id=model_id, require_enabled=True
            )
            try:
                _require_model_capabilities(model, workload=workload)
            except AiModelSettingsError as exc:
                raise AiModelSettingsError(
                    status_code=422, code=exc.code, context=exc.context
                ) from exc


def _require_runtime_route_compatibility(
    workload: RegisteredLlmWorkload,
    *,
    runtime_adapter_id: str,
    route: str,
    provider_id: str | None,
    status_code: int,
) -> None:
    if workload.execution_kind != "agent":
        return
    descriptor = get_agent_runtime_adapter_descriptor(runtime_adapter_id)
    if descriptor is None:
        raise AiModelSettingsError(
            status_code=status_code,
            code="admin.ai_model_runtime_adapter_not_allowed",
            context={"workload_id": workload.workload_id},
        )
    if route not in descriptor.allowed_routes or (
        descriptor.allowed_providers and (provider_id or "") not in descriptor.allowed_providers
    ):
        raise AiModelSettingsError(
            status_code=status_code,
            code="admin.ai_model_runtime_route_mismatch",
        )


def _model_is_referenced(db: Session, *, model_id: str) -> bool:
    provider_default = db.scalar(
        select(AiModelProviderConfig.provider_id).where(
            AiModelProviderConfig.default_model_id == model_id
        )
    )
    if (
        provider_default is not None
        or db.scalar(
            select(AiModelPolicyDefault.app_id).where(AiModelPolicyDefault.model_id == model_id)
        )
        is not None
    ):
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


def create_ai_model_connection(
    db: Session, *, payload: AiModelConnectionCreateRequest, actor_user_id: str
) -> str:
    assert_registry_digest(payload.expected_registry_digest)
    descriptor = llm_provider_descriptor(payload.provider_kind)
    if descriptor is None:
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_not_found",
            context={"provider_id": payload.provider_kind},
        )
    if (
        payload.provider_kind not in {"local", "openai_compatible"}
        and payload.route_mode != "external"
    ):
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_route_provider_mismatch")
    if payload.provider_kind == "local" and payload.route_mode != "local":
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_route_provider_mismatch")
    if payload.preset and payload.provider_kind != "openai_compatible":
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_route_provider_mismatch")
    identifier = "conn_" + new_id().replace("-", "")[:24]
    row = AiModelProviderConfig(
        provider_id=identifier,
        provider_kind=descriptor.provider_id,
        display_name=payload.display_name,
        route_mode=payload.route_mode,
        credential_kind=payload.credential_kind or descriptor.credential_kind,
        preset=payload.preset,
        enabled=False,
        version=1,
        updated_by=actor_user_id,
    )
    db.add(row)
    db.flush()
    update_ai_model_provider(
        db,
        provider_id=identifier,
        payload=AiModelProviderUpdateRequest(
            **payload.model_dump(
                exclude={"provider_kind", "route_mode", "preset", "expected_version", "enabled"}
            ),
            expected_version=1,
            enabled=False,
        ),
        actor_user_id=actor_user_id,
    )
    return identifier


def _ready_policies(db: Session) -> list[tuple[str, str, str]]:
    ready = []
    for workload in get_ai_capability_registry().llm_workloads.values():
        for app_id in workload.app_ids:
            for role in workload.model_roles:
                try:
                    resolve_ai_model_workload_route(
                        db, workload_id=workload.workload_id, app_id=app_id, model_role=role
                    )
                except AiModelSettingsError:
                    continue
                ready.append((app_id, workload.workload_id, role))
    return ready


def _preserve_ready_policies(db: Session, policies: list[tuple[str, str, str]]) -> None:
    for app_id, workload_id, role in policies:
        try:
            resolve_ai_model_workload_route(
                db, workload_id=workload_id, app_id=app_id, model_role=role
            )
        except AiModelSettingsError as exc:
            raise AiModelSettingsError(
                status_code=422,
                code="admin.ai_model_default_breaks_workload",
                context={"workload_id": workload_id, "app_id": app_id},
            ) from exc


def update_ai_model_policy_default(
    db: Session,
    *,
    app_id: str,
    route: str,
    payload: AiModelPolicyDefaultUpdateRequest,
    actor_user_id: str,
) -> None:
    from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item

    assert_registry_digest(payload.expected_registry_digest)
    if route not in {"local", "external"}:
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_route_provider_mismatch")
    if app_id and get_app_catalog_item(app_id) is None:
        raise AiModelSettingsError(status_code=404, code="admin.ai_model_app_not_found")
    before = _ready_policies(db)
    row = db.scalar(
        select(AiModelPolicyDefault)
        .where(AiModelPolicyDefault.app_id == app_id, AiModelPolicyDefault.route_mode == route)
        .with_for_update()
    )
    if payload.expected_version != (row.version if row else 0):
        _raise_version_conflict()
    provider = (
        db.scalar(
            select(AiModelProviderConfig)
            .where(AiModelProviderConfig.provider_id == payload.provider_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if payload.provider_id
        else None
    )
    if payload.model_id and not provider:
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_provider_required")
    if payload.provider_id and (provider is None or not provider.enabled):
        raise AiModelSettingsError(
            status_code=422,
            code="admin.ai_model_provider_not_ready",
            context={"provider_id": payload.provider_id},
        )
    if provider is not None and provider.route_mode != route:
        raise AiModelSettingsError(status_code=422, code="admin.ai_model_route_provider_mismatch")
    if payload.model_id and provider is not None:
        _require_provider_model(
            db, provider_id=provider.provider_id, model_id=payload.model_id, require_enabled=True
        )
        if not app_id:
            if payload.expected_provider_version != provider.version:
                _raise_version_conflict()
            provider.default_model_id = payload.model_id
            provider.version += 1
            provider.updated_by = actor_user_id
    if app_id and not any((payload.provider_id, payload.model_id, payload.max_output_tokens)):
        if row is not None:
            db.delete(row)
            db.flush()
            _preserve_ready_policies(db, before)
        return
    if row is None:
        row = AiModelPolicyDefault(app_id=app_id, route_mode=route, version=0)
        db.add(row)
    row.provider_id = payload.provider_id
    row.model_id = payload.model_id if app_id else None
    row.max_output_tokens = payload.max_output_tokens
    row.version += 1
    row.updated_by = actor_user_id
    row.updated_at = utcnow_naive()
    try:
        db.flush()
    except IntegrityError as exc:
        _raise_version_conflict(exc)
    _preserve_ready_policies(db, before)


def probe_ai_model_connection(
    db: Session, *, provider_id: str, expected_version: int, expected_registry_digest: str
) -> bool:
    """Check a saved model inventory without holding a DB connection during I/O."""
    assert_registry_digest(expected_registry_digest)
    row = db.get(AiModelProviderConfig, provider_id)
    if row is None:
        raise AiModelSettingsError(
            status_code=404,
            code="admin.ai_model_provider_not_found",
            context={"provider_id": provider_id},
        )
    if row.version != expected_version:
        _raise_version_conflict()
    _validate_endpoint_url(row.endpoint_url, provider_id=provider_id, route_mode=row.route_mode)
    model = _require_provider_model(
        db, provider_id=provider_id, model_id=row.default_model_id or "", require_enabled=True
    )
    try:
        key = (
            decrypt_api_key(row.api_key_ciphertext).get_secret_value()
            if row.api_key_ciphertext
            else ""
        )
    except AiModelCredentialError as exc:
        raise AiModelSettingsError(
            status_code=503, code="admin.ai_model_credential_encryption_unavailable"
        ) from exc
    kind, endpoint, requires_key, model_key = (
        row.provider_kind,
        row.endpoint_url or "",
        row.credential_kind == "api_key",
        model.model_key,
    )
    model_id, model_version = model.id, model.version
    timeout = min(10.0, get_settings().llm_request_timeout_seconds)
    db.rollback()
    try:
        inventory = discover_provider_models(
            kind, endpoint, key or None, timeout, requires_credentials=requires_key
        )
        ready = any(item.model_key == model_key for item in inventory)
    except ProviderModelDiscoveryError:
        ready = False
    current_connection = db.scalar(
        select(AiModelProviderConfig)
        .where(AiModelProviderConfig.provider_id == provider_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current_connection is None or current_connection.version != expected_version:
        _raise_version_conflict()
    current_model = db.scalar(
        select(AiModelCatalogEntry)
        .where(AiModelCatalogEntry.id == model_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current_model is None or current_model.version != model_version:
        _raise_version_conflict()
    current_connection.verified_version = expected_version if ready else None
    db.flush()
    return ready
