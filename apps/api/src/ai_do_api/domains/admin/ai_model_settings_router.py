from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.ai.model_settings_schemas import (
    AiModelCatalogCreateRequest,
    AiModelCatalogUpdateRequest,
    AiModelDiscoveryRequest,
    AiModelProviderId,
    AiModelProviderUpdateRequest,
    AiModelRouteOverrideUpdateRequest,
    AiModelSettingsResponse,
)
from ai_do_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    create_ai_model_catalog_entry,
    delete_ai_model_route_override,
    discover_ai_model_provider_catalog,
    get_ai_model_settings_snapshot,
    update_ai_model_catalog_entry,
    update_ai_model_provider,
    upsert_ai_model_route_override,
)
from ai_do_api.domains.auth.access import is_platform_admin_user, record_audit_log
from ai_do_api.domains.auth.dependencies import AuthContext, require_permission


router = APIRouter(prefix="/admin/ai-model-settings", tags=["admin"])


def _ensure_platform_admin(context: AuthContext, db: Session) -> None:
    if not is_platform_admin_user(context.user, db):
        raise localized_http_exception(
            status_code=403,
            code="admin.platform_admin_required",
        )


def _raise_settings_error(db: Session, exc: AiModelSettingsError) -> None:
    db.rollback()
    raise localized_http_exception(
        status_code=exc.status_code,
        code=exc.code,
        **exc.context,
    ) from exc


@router.get("", response_model=AiModelSettingsResponse)
def get_ai_model_settings(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiModelSettingsResponse:
    _ensure_platform_admin(context, db)
    return get_ai_model_settings_snapshot(db)


@router.put("/providers/{provider_id}", response_model=AiModelSettingsResponse)
def put_ai_model_provider(
    provider_id: AiModelProviderId,
    payload: AiModelProviderUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        update_ai_model_provider(
            db,
            provider_id=provider_id,
            payload=payload,
            actor_user_id=context.user.id,
        )
    except AiModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_model.provider.update",
        entity_kind="ai_model_provider",
        entity_id=provider_id,
        summary=f"Updated AI model provider {provider_id}",
        payload={
            "provider_id": provider_id,
            "enabled": payload.enabled,
            "endpoint_configured": payload.endpoint_url is not None,
            "api_key_changed": payload.api_key is not None or payload.clear_api_key,
            "default_model_id": payload.default_model_id,
        },
    )
    db.commit()
    return get_ai_model_settings_snapshot(db)


@router.post(
    "/providers/{provider_id}/discover-models",
    response_model=AiModelSettingsResponse,
)
def post_ai_model_provider_discovery(
    provider_id: AiModelProviderId,
    payload: AiModelDiscoveryRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        discovered_count = discover_ai_model_provider_catalog(
            db,
            provider_id=provider_id,
            expected_registry_digest=payload.expected_registry_digest,
            actor_user_id=context.user.id,
        )
    except AiModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_model.provider.models.discover",
        entity_kind="ai_model_provider",
        entity_id=provider_id,
        summary=f"Discovered models for AI provider {provider_id}",
        payload={
            "provider_id": provider_id,
            "discovered_count": discovered_count,
        },
    )
    db.commit()
    return get_ai_model_settings_snapshot(db)


@router.post("/models", response_model=AiModelSettingsResponse, status_code=201)
def post_ai_model_catalog_entry(
    payload: AiModelCatalogCreateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        create_ai_model_catalog_entry(
            db,
            payload=payload,
            actor_user_id=context.user.id,
        )
    except AiModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_model.catalog.create",
        entity_kind="ai_model_catalog",
        entity_id=None,
        summary=f"Registered AI model {payload.provider_id}/{payload.model_key}",
        payload={
            "provider_id": payload.provider_id,
            "model_key": payload.model_key,
            "capabilities": list(payload.capabilities),
            "enabled": payload.enabled,
        },
    )
    db.commit()
    return get_ai_model_settings_snapshot(db)


@router.put("/models/{model_id}", response_model=AiModelSettingsResponse)
def put_ai_model_catalog_entry(
    model_id: str,
    payload: AiModelCatalogUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        update_ai_model_catalog_entry(
            db,
            model_id=model_id,
            payload=payload,
            actor_user_id=context.user.id,
        )
    except AiModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_model.catalog.update",
        entity_kind="ai_model_catalog",
        entity_id=model_id,
        summary=f"Updated AI model {model_id}",
        payload={
            "model_id": model_id,
            "model_key": payload.model_key,
            "capabilities": list(payload.capabilities),
            "enabled": payload.enabled,
        },
    )
    db.commit()
    return get_ai_model_settings_snapshot(db)


@router.put(
    "/workloads/{workload_id}/route",
    response_model=AiModelSettingsResponse,
)
def put_ai_model_route_override(
    workload_id: str,
    payload: AiModelRouteOverrideUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        upsert_ai_model_route_override(
            db,
            workload_id=workload_id,
            payload=payload,
            actor_user_id=context.user.id,
        )
    except AiModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_model.route_override.update",
        entity_kind="ai_model_workload",
        entity_id=workload_id,
        summary=f"Updated AI model route for {workload_id}",
        payload={
            "workload_id": workload_id,
            "route_mode": payload.route_mode,
            "provider_id": payload.provider_id,
            "model_roles": sorted(payload.model_ids),
            "local_max_output_tokens": payload.local_max_output_tokens,
            "external_max_output_tokens": payload.external_max_output_tokens,
        },
    )
    db.commit()
    return get_ai_model_settings_snapshot(db)


@router.delete(
    "/workloads/{workload_id}/route",
    response_model=AiModelSettingsResponse,
)
def reset_ai_model_route_override(
    workload_id: str,
    expected_registry_digest: str = Query(min_length=64, max_length=64),
    expected_version: int = Query(ge=1),
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> AiModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        delete_ai_model_route_override(
            db,
            workload_id=workload_id,
            expected_registry_digest=expected_registry_digest,
            expected_version=expected_version,
        )
    except AiModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.ai_model.route_override.reset",
        entity_kind="ai_model_workload",
        entity_id=workload_id,
        summary=f"Reset AI model route for {workload_id}",
        payload={"workload_id": workload_id},
    )
    db.commit()
    return get_ai_model_settings_snapshot(db)


__all__ = ["router"]
