from __future__ import annotations

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.workspace_app_registry import app_is_available_to_system_roles
from open_work_hub_api.domains.auth.access import record_audit_log, resolve_system_roles
from open_work_hub_api.domains.auth.app_availability import load_app_availability_snapshot
from open_work_hub_api.domains.auth.models import (
    User,
    UserAppWorkspacePreference,
    Workspace,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.workspace_apps import get_workspace_app_catalog_item


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _preference_audit_entity_id(*, user_id: str, app_id: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            f"open-work-hub:user-app-workspace-preference:{user_id}:{app_id}",
        )
    )


def set_app_workspace_preference(
    db: Session,
    *,
    user: User,
    app_id: str,
    workspace_id: str,
) -> UserAppWorkspacePreference:
    app = get_workspace_app_catalog_item(app_id)
    if app is None:
        raise localized_http_exception(status_code=404, code="app.not_found")
    if app.availability_scope != "workspace":
        raise localized_http_exception(
            status_code=400,
            code="app.workspace_context_unsupported",
        )
    if not app_is_available_to_system_roles(app, resolve_system_roles(db, user)):
        raise localized_http_exception(status_code=403, code="workspace.app_disabled")

    membership = db.scalar(
        select(WorkspaceUserBinding)
        .join(Workspace, Workspace.id == WorkspaceUserBinding.workspace_id)
        .where(
            WorkspaceUserBinding.workspace_id == workspace_id,
            WorkspaceUserBinding.user_id == user.id,
            Workspace.active.is_(True),
        )
        .with_for_update()
    )
    if membership is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")

    app_snapshot = load_app_availability_snapshot(
        db,
        workspace_ids=(workspace_id,),
    )
    if not app_snapshot.workspace_enabled(app, workspace_id):
        raise localized_http_exception(status_code=403, code="workspace.app_disabled")

    now = _utcnow()
    preference = db.get(UserAppWorkspacePreference, (user.id, app_id))
    if preference is None:
        preference = UserAppWorkspacePreference(
            user_id=user.id,
            app_id=app_id,
            workspace_id=workspace_id,
            created_at=now,
            updated_at=now,
        )
    else:
        preference.workspace_id = workspace_id
        preference.updated_at = now
    db.add(preference)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="apps.workspace_preference.update",
        entity_kind="app_workspace_preference",
        entity_id=_preference_audit_entity_id(user_id=user.id, app_id=app_id),
        summary="Updated app workspace preference",
        payload={"user_id": user.id, "app_id": app_id, "workspace_id": workspace_id},
    )
    db.flush()
    return preference


__all__ = ["set_app_workspace_preference"]
