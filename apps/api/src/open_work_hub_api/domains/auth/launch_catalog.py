from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.principal import personal_user_principal
from open_work_hub_api.core.workspace_app_registry import (
    WorkspaceAppCatalogItem,
    app_is_available_to_system_roles,
)
from open_work_hub_api.domains.auth.access import (
    project_platform_app_bar_categories,
    resolve_system_roles,
    resolve_workspaces,
)
from open_work_hub_api.domains.auth.app_availability import (
    AppAvailabilitySnapshot,
    load_app_availability_snapshot,
)
from open_work_hub_api.domains.auth.models import (
    User,
    UserAppWorkspacePreference,
    Workspace,
    WorkspaceAppOverride,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.workspace_apps import (
    get_workspace_app_catalog_item,
    iter_workspace_app_catalog,
)


def _workspace_summary(workspace: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(workspace["id"]),
        "slug": str(workspace["slug"]),
        "name": str(workspace["name"]),
    }


def _eligible_workspaces(
    app: WorkspaceAppCatalogItem,
    *,
    workspaces: Iterable[dict[str, Any]],
    snapshot: AppAvailabilitySnapshot,
) -> list[dict[str, Any]]:
    if app.availability_scope != "workspace":
        return []
    return [
        workspace
        for workspace in workspaces
        if snapshot.workspace_enabled(app, str(workspace["id"]))
    ]


def query_eligible_workspaces_for_app(
    db: Session,
    *,
    user: User,
    app_id: str,
    query: str = "",
    slug: str = "",
    page: int,
    page_size: int,
) -> tuple[WorkspaceAppCatalogItem | None, list[dict[str, Any]], int]:
    app = get_workspace_app_catalog_item(app_id)
    if app is None or app.availability_scope != "workspace":
        return app, [], 0
    system_roles = set(resolve_system_roles(db, user))
    if not app_is_available_to_system_roles(app, system_roles):
        return app, [], 0
    snapshot = load_app_availability_snapshot(db)
    if not snapshot.company_enabled(app):
        return app, [], 0

    effective_enabled = func.coalesce(
        WorkspaceAppOverride.enabled,
        bool(snapshot.workspace_default_by_app_id.get(app_id, False)),
    )
    statement = (
        select(Workspace.id, Workspace.key, Workspace.name)
        .join(
            WorkspaceUserBinding,
            WorkspaceUserBinding.workspace_id == Workspace.id,
        )
        .outerjoin(
            WorkspaceAppOverride,
            and_(
                WorkspaceAppOverride.workspace_id == Workspace.id,
                WorkspaceAppOverride.app_id == app_id,
            ),
        )
        .where(
            WorkspaceUserBinding.user_id == user.id,
            Workspace.active.is_(True),
            effective_enabled.is_(True),
        )
    )
    normalized_slug = slug.strip().lower()
    if normalized_slug:
        statement = statement.where(func.lower(Workspace.key) == normalized_slug)
    normalized_query = query.strip().lower()
    if normalized_query:
        statement = statement.where(
            or_(
                func.lower(Workspace.name).contains(normalized_query, autoescape=True),
                func.lower(Workspace.key).contains(normalized_query, autoescape=True),
            )
        )
    total = int(
        db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    )
    rows = db.execute(
        statement.order_by(Workspace.name.asc(), Workspace.key.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return (
        app,
        [
            {"id": workspace_id, "slug": workspace_slug, "name": workspace_name}
            for workspace_id, workspace_slug, workspace_name in rows
        ],
        total,
    )


def build_launch_catalog(
    db: Session,
    *,
    user: User,
    source: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    catalog = tuple(iter_workspace_app_catalog())
    workspaces = resolve_workspaces(db, user)
    workspace_by_id = {str(workspace["id"]): workspace for workspace in workspaces}
    snapshot = load_app_availability_snapshot(
        db,
        workspace_ids=workspace_by_id,
    )
    system_roles = set(resolve_system_roles(db, user))
    preferences = {
        row.app_id: row.workspace_id
        for row in db.scalars(
            select(UserAppWorkspacePreference).where(
                UserAppWorkspacePreference.user_id == user.id
            )
        ).all()
    }

    apps: list[dict[str, Any]] = []
    executable_app_ids: set[str] = set()
    global_route_app_ids: list[str] = []
    for app in catalog:
        if not app_is_available_to_system_roles(app, system_roles):
            continue
        # Global and shared routes do not require membership in any workspace.
        # They are available while the company-level app control (and static
        # feature flag) permits the app for this principal.
        if snapshot.company_enabled(app):
            global_route_app_ids.append(app.app_id)
        eligible: list[dict[str, Any]] = []
        if app.availability_scope == "platform":
            if not snapshot.platform_enabled(app):
                continue
        else:
            eligible = _eligible_workspaces(
                app,
                workspaces=workspaces,
                snapshot=snapshot,
            )
            if not eligible:
                continue

        eligible_by_id = {str(workspace["id"]): workspace for workspace in eligible}
        preferred_workspace = eligible_by_id.get(preferences.get(app.app_id, ""))
        single_workspace = eligible[0] if len(eligible) == 1 else None
        apps.append(
            {
                "app_id": app.app_id,
                "title": app.title,
                "route_base": app.route_base,
                "entry_route_id": app.entry_route_id,
                "icon_key": app.icon_key,
                "availability_scope": app.availability_scope,
                "execution_context_kind": app.execution_context_kind,
                "resource_scope": app.resource_scope,
                "coming_soon": app.coming_soon,
                "eligible_workspace_count": len(eligible),
                "preferred_workspace": (
                    _workspace_summary(preferred_workspace)
                    if preferred_workspace is not None
                    else None
                ),
                "single_eligible_workspace": (
                    _workspace_summary(single_workspace)
                    if single_workspace is not None
                    else None
                ),
            }
        )
        executable_app_ids.add(app.app_id)

    catalog_by_app_id = {app.app_id: app for app in catalog}
    return {
        "apps": apps,
        "global_route_app_ids": global_route_app_ids,
        "app_bar_categories": project_platform_app_bar_categories(
            db,
            enabled_app_ids=executable_app_ids,
            settings=snapshot.settings,
        ),
        "personal_tool_app_ids": [
            app["app_id"]
            for app in apps
            if catalog_by_app_id[app["app_id"]].launcher_personal_tools
        ],
        "principal": personal_user_principal(
            user_id=user.id,
            source=source,
            session_id=session_id,
        ).as_payload(),
    }


__all__ = ["build_launch_catalog", "query_eligible_workspaces_for_app"]
