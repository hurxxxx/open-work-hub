from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import load_user_graph, resolve_user_permissions
from aidoo_api.domains.auth.models import AuthSession, User
from aidoo_api.domains.auth.security import hash_token


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession
    permissions: frozenset[str]


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
