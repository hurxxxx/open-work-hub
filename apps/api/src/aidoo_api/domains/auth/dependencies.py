from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import (
    is_platform_admin_user,
    load_active_workspace_by_key,
    load_user_graph,
    resolve_team_role,
    resolve_user_permissions,
    resolve_visible_features,
    resolve_workspace_role,
    team_role_allows,
    workspace_role_allows,
)
from aidoo_api.domains.auth.models import AuthSession, Team, User, Workspace
from aidoo_api.domains.auth.security import hash_token


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession
    permissions: frozenset[str]


@dataclass(frozen=True)
class WorkspaceAccessContext:
    auth: AuthContext
    workspace: Workspace
    role: str


@dataclass(frozen=True)
class TeamAccessContext:
    auth: AuthContext
    team: Team
    role: str


def require_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    now = datetime.now(UTC).replace(tzinfo=None)
    token_hash = hash_token(credentials.credentials)
    auth_session = db.scalar(
        select(AuthSession)
        .where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired.",
        )

    user = load_user_graph(db, auth_session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    auth_session.last_seen_at = now
    db.add(auth_session)
    db.commit()
    db.refresh(auth_session)

    return AuthContext(
        user=user,
        session=auth_session,
        permissions=frozenset(resolve_user_permissions(user)),
    )


def require_current_user(context: AuthContext = Depends(require_auth_context)) -> User:
    return context.user


def require_permission(permission: str):
    def dependency(context: AuthContext = Depends(require_auth_context)) -> AuthContext:
        if permission not in context.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return context

    return dependency


def require_admin_context(
    context: AuthContext = Depends(require_permission("admin.access")),
) -> AuthContext:
    return context


def require_feature_access(feature_code: str):
    def dependency(
        context: AuthContext = Depends(require_auth_context),
        db: Session = Depends(get_db_session),
    ) -> AuthContext:
        if feature_code not in resolve_visible_features(db, context.user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature access required: {feature_code}",
            )
        return context

    return dependency


def require_workspace_access(workspace_key: str, min_role: str = "member"):
    def dependency(
        context: AuthContext = Depends(require_auth_context),
        db: Session = Depends(get_db_session),
    ) -> WorkspaceAccessContext:
        workspace = load_active_workspace_by_key(db, workspace_key)
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found.",
            )

        if is_platform_admin_user(context.user):
            return WorkspaceAccessContext(auth=context, workspace=workspace, role="workspace_admin")

        role = resolve_workspace_role(db, context.user, workspace.id)
        if not workspace_role_allows(role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Workspace access required: {workspace.key}",
            )
        assert role is not None
        return WorkspaceAccessContext(auth=context, workspace=workspace, role=role)

    return dependency


def require_workspace_feature_access(
    workspace_key: str,
    feature_code: str,
    min_role: str = "member",
):
    def dependency(
        workspace_context: WorkspaceAccessContext = Depends(require_workspace_access(workspace_key, min_role)),
        _feature_context: AuthContext = Depends(require_feature_access(feature_code)),
    ) -> WorkspaceAccessContext:
        return workspace_context

    return dependency


def require_team_access(min_role: str = "member", team_param: str = "team_id"):
    def dependency(
        request: Request,
        context: AuthContext = Depends(require_auth_context),
        db: Session = Depends(get_db_session),
    ) -> TeamAccessContext:
        team_id = request.path_params.get(team_param)
        if not team_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Missing team path parameter: {team_param}",
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found.")

        role = resolve_team_role(db, context.user, team)
        if not team_role_allows(role, min_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Team access required.")
        assert role is not None
        return TeamAccessContext(auth=context, team=team, role=role)

    return dependency
