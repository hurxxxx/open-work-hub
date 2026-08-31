from __future__ import annotations

from collections.abc import Callable, Iterable

from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.core.workspace_app_registry import app_is_available_to_system_roles
from open_work_hub_api.domains.auth.access import resolve_system_roles
from open_work_hub_api.domains.auth.app_availability import (
    is_app_enabled,
    is_company_app_enabled,
    is_platform_app_enabled,
    is_workspace_app_enabled,
    load_app_availability_snapshot,
    resolve_workspace_runtime_enabled_app_ids,
)
from open_work_hub_api.domains.auth.dependencies import require_current_workspace
from open_work_hub_api.domains.auth.models import (
    User,
    Workspace,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.workspace_apps import get_workspace_app_catalog_item
from open_work_hub_api.domains.auth.workspace_apps import iter_workspace_app_catalog


def is_app_enabled_for_principal(
    db: Session,
    principal: CallerPrincipal,
    app_id: str,
) -> bool:
    catalog_item = get_workspace_app_catalog_item(app_id)
    if catalog_item is None:
        return False
    if principal.kind != "user" or principal.user_id is None:
        return False
    return is_app_enabled_for_user_context(
        db,
        app_id=app_id,
        user_id=principal.user_id,
        workspace_id=principal.workspace_id,
    )


def is_app_enabled_for_user_context(
    db: Session,
    *,
    app_id: str,
    user_id: str,
    workspace_id: str | None,
) -> bool:
    """Fail-closed execution gate for queued and non-router user work."""

    app = get_workspace_app_catalog_item(app_id)
    user = db.scalar(
        select(User)
        .options(selectinload(User.system_role_links))
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )
    if app is None or user is None or user.status != "active" or user.login_blocked:
        return False
    if not app_is_available_to_system_roles(app, set(resolve_system_roles(db, user))):
        return False
    if app.availability_scope == "platform":
        return is_app_enabled(db, app_id)
    if workspace_id is None:
        return False
    membership_exists = db.scalar(
        select(WorkspaceUserBinding.id)
        .join(Workspace, Workspace.id == WorkspaceUserBinding.workspace_id)
        .where(
            WorkspaceUserBinding.workspace_id == workspace_id,
            WorkspaceUserBinding.user_id == user_id,
            Workspace.active.is_(True),
        )
        .limit(1)
    )
    return bool(membership_exists) and is_app_enabled(
        db,
        app_id,
        workspace_id=workspace_id,
    )


def is_company_app_enabled_for_user_context(
    db: Session,
    *,
    app_id: str,
    user_id: str,
) -> bool:
    """Check the company master and current system-role eligibility.

    Company-scoped resources are intentionally independent of workspace
    membership, even when their owning app normally executes in a workspace.
    """

    app = get_workspace_app_catalog_item(app_id)
    user = db.scalar(
        select(User)
        .options(selectinload(User.system_role_links))
        .where(User.id == user_id)
        .execution_options(populate_existing=True)
    )
    if app is None or user is None or user.status != "active" or user.login_blocked:
        return False
    return app_is_available_to_system_roles(
        app,
        set(resolve_system_roles(db, user)),
    ) and is_company_app_enabled(db, app_id)


def resolve_enabled_app_ids_for_user_context(
    db: Session,
    *,
    user: User,
    workspace_id: str,
) -> frozenset[str]:
    """Bulk visibility projection for rows carrying an owning app id."""

    fresh_user = db.scalar(
        select(User)
        .options(selectinload(User.system_role_links))
        .where(User.id == user.id)
        .execution_options(populate_existing=True)
    )
    if fresh_user is None or fresh_user.status != "active" or fresh_user.login_blocked:
        return frozenset()
    membership_exists = db.scalar(
        select(WorkspaceUserBinding.id)
        .join(Workspace, Workspace.id == WorkspaceUserBinding.workspace_id)
        .where(
            WorkspaceUserBinding.workspace_id == workspace_id,
            WorkspaceUserBinding.user_id == user.id,
            Workspace.active.is_(True),
        )
        .limit(1)
    )
    if not membership_exists:
        return frozenset()
    roles = set(resolve_system_roles(db, fresh_user))
    runtime_enabled = set(resolve_workspace_runtime_enabled_app_ids(db, workspace_id))
    return frozenset(
        app.app_id
        for app in iter_workspace_app_catalog()
        if app.app_id in runtime_enabled and app_is_available_to_system_roles(app, roles)
    )


def resolve_enabled_app_contexts_for_user(
    db: Session,
    *,
    user: User,
    contexts: Iterable[tuple[str, str | None]],
) -> frozenset[tuple[str, str | None]]:
    """Resolve many app/workspace execution gates from one immutable snapshot."""

    normalized_contexts = tuple(dict.fromkeys(contexts))
    if not normalized_contexts:
        return frozenset()
    fresh_user = db.scalar(
        select(User)
        .options(selectinload(User.system_role_links))
        .where(User.id == user.id)
        .execution_options(populate_existing=True)
    )
    if fresh_user is None or fresh_user.status != "active" or fresh_user.login_blocked:
        return frozenset()
    workspace_ids = {
        workspace_id for _, workspace_id in normalized_contexts if workspace_id is not None
    }
    member_workspace_ids = set(
        db.scalars(
            select(WorkspaceUserBinding.workspace_id)
            .join(Workspace, Workspace.id == WorkspaceUserBinding.workspace_id)
            .where(
                WorkspaceUserBinding.workspace_id.in_(workspace_ids),
                WorkspaceUserBinding.user_id == fresh_user.id,
                Workspace.active.is_(True),
            )
        )
    )
    snapshot = load_app_availability_snapshot(db, workspace_ids=workspace_ids)
    roles = set(resolve_system_roles(db, fresh_user))
    enabled: set[tuple[str, str | None]] = set()
    for app_id, workspace_id in normalized_contexts:
        app = get_workspace_app_catalog_item(app_id)
        if app is None or not app_is_available_to_system_roles(app, roles):
            continue
        if app.availability_scope == "platform":
            if snapshot.platform_enabled(app):
                enabled.add((app_id, workspace_id))
        elif workspace_id in member_workspace_ids and snapshot.workspace_enabled(
            app,
            workspace_id,
        ):
            enabled.add((app_id, workspace_id))
    return frozenset(enabled)


def require_workspace_app_enabled(
    app_id: str,
    *,
    error_code: str,
) -> Callable[..., None]:
    def dependency(
        db: Session = Depends(get_db_session),
        current_workspace: Workspace = Depends(require_current_workspace),
    ) -> None:
        if not is_workspace_app_enabled(db, current_workspace.id, app_id):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code=error_code,
            )

    return dependency


def require_company_app_enabled(
    app_id: str,
    *,
    error_code: str = "platform.app_disabled",
) -> Callable[..., None]:
    """Require the company hard-master without inferring workspace context."""

    def dependency(
        db: Session = Depends(get_db_session),
    ) -> None:
        if not is_company_app_enabled(db, app_id):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code=error_code,
            )

    return dependency


def require_platform_app_enabled(
    app_id: str,
    *,
    error_code: str = "platform.app_disabled",
) -> Callable[..., None]:
    def dependency(
        db: Session = Depends(get_db_session),
    ) -> None:
        if not is_platform_app_enabled(db, app_id):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code=error_code,
            )

    return dependency


__all__ = [
    "is_app_enabled_for_principal",
    "is_app_enabled_for_user_context",
    "is_company_app_enabled_for_user_context",
    "is_company_app_enabled",
    "is_platform_app_enabled",
    "is_workspace_app_enabled",
    "require_company_app_enabled",
    "require_platform_app_enabled",
    "require_workspace_app_enabled",
    "resolve_enabled_app_contexts_for_user",
    "resolve_enabled_app_ids_for_user_context",
]
