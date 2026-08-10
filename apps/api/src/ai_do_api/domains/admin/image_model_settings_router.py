from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import is_platform_admin_user, record_audit_log
from ai_do_api.domains.auth.dependencies import AuthContext, require_permission
from ai_do_api.domains.images.model_settings_schemas import (
    ImageModelProfileUpdateRequest,
    ImageModelProviderUpdateRequest,
    ImageModelSettingsResponse,
    ImageProviderId,
)
from ai_do_api.domains.images.model_settings_service import (
    ImageModelSettingsError,
    get_image_model_settings_snapshot,
    update_image_model_profile,
    update_image_model_provider,
)


router = APIRouter(prefix="/admin/image-model-settings", tags=["admin"])


def _ensure_platform_admin(context: AuthContext, db: Session) -> None:
    if not is_platform_admin_user(context.user, db):
        raise localized_http_exception(
            status_code=403,
            code="admin.platform_admin_required",
        )


def _raise_settings_error(db: Session, exc: ImageModelSettingsError) -> None:
    db.rollback()
    raise localized_http_exception(
        status_code=exc.status_code,
        code=exc.code,
        **exc.context,
    ) from exc


@router.get("", response_model=ImageModelSettingsResponse)
def get_image_model_settings(
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> ImageModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        return get_image_model_settings_snapshot(db)
    except ImageModelSettingsError as exc:
        _raise_settings_error(db, exc)


@router.put("/providers/{provider_id}", response_model=ImageModelSettingsResponse)
def put_image_model_provider(
    provider_id: ImageProviderId,
    payload: ImageModelProviderUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> ImageModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        update_image_model_provider(
            db,
            provider_id=provider_id,
            payload=payload,
            actor_user_id=context.user.id,
        )
    except ImageModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.image_model.provider.update",
        entity_kind="image_model_provider",
        entity_id=provider_id,
        summary=f"Updated image model provider {provider_id}",
        payload={
            "provider_id": provider_id,
            "enabled": payload.enabled,
            "endpoint_configured": payload.endpoint_url is not None,
            "api_key_changed": payload.api_key is not None or payload.clear_api_key,
            "supervisor_model_id": payload.supervisor_model_id,
            "generation_model_id": payload.generation_model_id,
        },
    )
    db.commit()
    return get_image_model_settings_snapshot(db)


@router.put("/profile", response_model=ImageModelSettingsResponse)
def put_image_model_profile(
    payload: ImageModelProfileUpdateRequest,
    context: AuthContext = Depends(require_permission("audit.read")),
    db: Session = Depends(get_db_session),
) -> ImageModelSettingsResponse:
    _ensure_platform_admin(context, db)
    try:
        update_image_model_profile(
            db,
            payload=payload,
            actor_user_id=context.user.id,
        )
    except ImageModelSettingsError as exc:
        _raise_settings_error(db, exc)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="admin.image_model.profile.update",
        entity_kind="image_model_profile",
        entity_id="default",
        summary="Updated image model profile",
        payload={
            "active_provider_id": payload.active_provider_id,
            "brief_web_search_enabled": payload.brief_web_search_enabled,
            "generation_web_search_enabled": payload.generation_web_search_enabled,
            "max_iterations": payload.max_iterations,
        },
    )
    db.commit()
    return get_image_model_settings_snapshot(db)


__all__ = ["router"]
