from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import (
    bind_current_workspace,
    get_current_workspace,
    load_active_workspace_by_key,
    load_user_graph,
    resolve_system_roles,
    resolve_team_role,
    resolve_workspaces,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from open_alm_api.domains.auth.models import AuthSession, Team, User, Workspace
from open_alm_api.domains.auth.security import hash_token


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession
    system_roles: frozenset[str]
    impersonator_user_id: str | None = None


@dataclass(frozen=True)
class WorkspaceAccessContext:
    auth: AuthContext
    workspace: Workspace
    role: str | None


@dataclass(frozen=True)
class TeamAccessContext:
    auth: AuthContext
    team: Team
    role: str


def resolve_auth_context_from_token(
    db: Session,
    token: str,
    *,
    update_last_seen: bool = True,
) -> AuthContext:
    now = datetime.now(UTC).replace(tzinfo=None)
    token_hash = hash_token(token)
    auth_session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if auth_session is None:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.session_invalid_or_expired",
        )

    user = load_user_graph(db, auth_session.user_id)
    if user is None:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.user_not_found",
        )
    if user.status != "active" or user.login_blocked:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="auth.user_inactive",
        )

    if update_last_seen:
        auth_session.last_seen_at = now
        db.add(auth_session)
        db.commit()
        db.refresh(auth_session)

    if auth_session.impersonator_user_id:
        db.info["impersonator_user_id"] = auth_session.impersonator_user_id
        db.info["impersonated_user_id"] = auth_session.user_id
        db.info["impersonation_session_id"] = auth_session.id
    else:
        db.info.pop("impersonator_user_id", None)
        db.info.pop("impersonated_user_id", None)
        db.info.pop("impersonation_session_id", None)

    return AuthContext(
        user=user,
        session=auth_session,
        system_roles=frozenset(resolve_system_roles(db, user)),
        impersonator_user_id=auth_session.impersonator_user_id,
    )


def require_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.required",
        )
    context = resolve_auth_context_from_token(
        db,
        credentials.credentials,
    )
    request.state.auth_context = context
    return context


def require_current_user(context: AuthContext = Depends(require_auth_context)) -> User:
    return context.user


def require_any_system_role(*roles: str):
    def dependency(context: AuthContext = Depends(require_auth_context)) -> AuthContext:
        role_set = set(context.system_roles)
        if not any(role in role_set for role in roles):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="auth.system_role_required",
                roles=", ".join(roles),
            )
        return context

    return dependency


PERMISSION_COMPAT_ROLE_MAP = {
    "admin.access": (("platform_admin",)),
    "user.read": (("platform_admin",)),
    "user.write": (("platform_admin",)),
    "org_unit.read": (("platform_admin",)),
    "org_unit.write": (("platform_admin",)),
    "workspace.read": (("platform_admin",)),
    "workspace.write": (("platform_admin",)),
    "team.read": (("platform_admin",)),
    "team.write": (("platform_admin",)),
    "audit.read": (("platform_admin",)),
    "session.revoke": (("platform_admin",)),
    "user.impersonate": (("platform_admin",)),
}


def require_permission(permission: str):
    roles = PERMISSION_COMPAT_ROLE_MAP.get(permission)
    if roles is None:
        raise ValueError(f"Unsupported compatibility permission: {permission}")
    return require_any_system_role(*roles)


def require_admin_context(
    context: AuthContext = Depends(require_any_system_role("platform_admin")),
) -> AuthContext:
    return context


def _resolve_workspace_role_for_request(
    db: Session,
    auth: AuthContext,
    workspace: Workspace,
) -> str | None:
    return resolve_workspace_role(db, auth.user, workspace.id)


def _select_legacy_workspace_for_request(
    db: Session,
    auth: AuthContext,
    min_role: str,
    preferred_workspace_key: str | None = None,
) -> tuple[Workspace, str]:
    if preferred_workspace_key:
        explicit_workspace = load_active_workspace_by_key(db, preferred_workspace_key)
        if explicit_workspace is not None:
            explicit_role = _resolve_workspace_role_for_request(db, auth, explicit_workspace)
            if explicit_role is not None and workspace_role_allows(explicit_role, min_role):
                return explicit_workspace, explicit_role

    for summary in resolve_workspaces(db, auth.user):
        if not workspace_role_allows(summary["role"], min_role):
            continue
        workspace = db.scalar(
            select(Workspace).where(Workspace.id == summary["id"], Workspace.active.is_(True))
        )
        if workspace is not None:
            return workspace, summary["role"]

    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="workspace.access_required",
    )


def _store_request_workspace(request: Request, workspace: Workspace | None) -> None:
    request.state.current_workspace = workspace


def require_current_workspace(
    request: Request,
    db: Session = Depends(get_db_session),
) -> Workspace:
    request_workspace = getattr(request.state, "current_workspace", None)
    if isinstance(request_workspace, Workspace):
        return request_workspace
    workspace = get_current_workspace(db)
    if workspace is None:
        raise localized_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="workspace.context_unavailable",
        )
    _store_request_workspace(request, workspace)
    return workspace


async def require_workspace_context(
    request: Request,
    auth: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
):
    workspace_slug = request.path_params.get("workspace_slug")
    if not workspace_slug:
        raise localized_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="workspace.slug_missing",
        )
    workspace = load_active_workspace_by_key(db, workspace_slug)
    if workspace is None:
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="workspace.not_found",
        )

    role = _resolve_workspace_role_for_request(db, auth, workspace)
    bind_current_workspace(db, workspace)
    _store_request_workspace(request, workspace)
    return WorkspaceAccessContext(auth=auth, workspace=workspace, role=role)


def require_workspace_membership(min_role: str = "member"):
    def dependency(
        workspace_context: WorkspaceAccessContext = Depends(require_workspace_context),
    ) -> WorkspaceAccessContext:
        if not workspace_role_allows(workspace_context.role, min_role):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="workspace.membership_required",
                workspace=workspace_context.workspace.key,
            )
        return workspace_context

    return dependency


def require_workspace_access(workspace_key: str, min_role: str = "member"):
    async def dependency(
        request: Request,
        auth: AuthContext = Depends(require_auth_context),
        db: Session = Depends(get_db_session),
    ) -> WorkspaceAccessContext:
        workspace = load_active_workspace_by_key(db, workspace_key)
        if workspace is None:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="workspace.not_found",
            )
        role = _resolve_workspace_role_for_request(db, auth, workspace)
        if not workspace_role_allows(role, min_role):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="workspace.access_required_named",
                workspace=workspace.key,
            )
        bind_current_workspace(db, workspace)
        _store_request_workspace(request, workspace)
        return WorkspaceAccessContext(auth=auth, workspace=workspace, role=role)

    return dependency


def require_legacy_workspace_membership(
    min_role: str = "member",
    preferred_workspace_key: str | None = None,
):
    async def dependency(
        request: Request,
        auth: AuthContext = Depends(require_auth_context),
        db: Session = Depends(get_db_session),
    ) -> WorkspaceAccessContext:
        workspace, role = _select_legacy_workspace_for_request(
            db,
            auth,
            min_role,
            preferred_workspace_key=preferred_workspace_key,
        )
        bind_current_workspace(db, workspace)
        _store_request_workspace(request, workspace)
        return WorkspaceAccessContext(auth=auth, workspace=workspace, role=role)

    return dependency


def require_team_access(min_role: str = "member", team_param: str = "team_id"):
    def dependency(
        request: Request,
        context: AuthContext = Depends(require_auth_context),
        db: Session = Depends(get_db_session),
    ) -> TeamAccessContext:
        team_id = request.path_params.get(team_param)
        if not team_id:
            raise localized_http_exception(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="team.path_parameter_missing",
                team_param=team_param,
            )

        team = db.scalar(
            select(Team)
            .options(joinedload(Team.workspace))
            .where(
                Team.id == team_id,
                Team.trashed_at.is_(None),
                Team.active.is_(True),
                Team.workspace.has(Workspace.active.is_(True)),
            )
        )
        if team is None:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="team.not_found",
            )

        request_workspace = getattr(request.state, "current_workspace", None)
        bound_workspace = (
            request_workspace if isinstance(request_workspace, Workspace) else get_current_workspace(db)
        )
        if bound_workspace is not None and team.workspace_id != bound_workspace.id:
            raise localized_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                code="team.not_found",
            )

        role = resolve_team_role(db, context.user, team)
        if not team_role_allows(role, min_role):
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="team.access_required",
            )
        assert role is not None
        return TeamAccessContext(auth=context, team=team, role=role)

    return dependency
