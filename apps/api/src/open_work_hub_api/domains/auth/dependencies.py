from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.access import load_user_graph, resolve_system_roles
from open_work_hub_api.domains.auth.models import AuthSession, User
from open_work_hub_api.domains.auth.security import hash_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession
    system_roles: frozenset[str]
    impersonator_user_id: str | None = None


def resolve_auth_context_from_token(
    db: Session,
    token: str,
    *,
    update_last_seen: bool = True,
    allow_password_change: bool = False,
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

    if user.must_change_password and not allow_password_change:
        raise localized_http_exception(status_code=403, code="auth.password_change_required")

    if auth_session.impersonator_user_id:
        impersonator = load_user_graph(db, auth_session.impersonator_user_id)
        if (
            impersonator is None
            or impersonator.status != "active"
            or impersonator.login_blocked
            or "platform_admin" not in resolve_system_roles(db, impersonator)
        ):
            raise localized_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="auth.session_invalid_or_expired",
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
        allow_password_change=(request.method, request.url.path)
        in {
            ("GET", f"{get_settings().api_prefix}/auth/me"),
            ("POST", f"{get_settings().api_prefix}/auth/change-password"),
            ("POST", f"{get_settings().api_prefix}/auth/logout"),
        },
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


PERMISSION_ROLE_MAP = {
    "admin.access": (("platform_admin",)),
    "user.read": (("platform_admin",)),
    "user.write": (("platform_admin",)),
    "organization.read": (("platform_admin",)),
    "organization.write": (("platform_admin",)),
    "platform_api_key.read": (("platform_admin",)),
    "platform_api_key.write": (("platform_admin",)),
    "platform_api_key.reveal": (("platform_admin",)),
    "audit.read": (("platform_admin",)),
    "session.revoke": (("platform_admin",)),
}


def require_permission(permission: str):
    roles = PERMISSION_ROLE_MAP.get(permission)
    if roles is None:
        raise ValueError(f"Unsupported platform permission: {permission}")
    return require_any_system_role(*roles)


def require_admin_context(
    context: AuthContext = Depends(require_any_system_role("platform_admin")),
) -> AuthContext:
    return context
