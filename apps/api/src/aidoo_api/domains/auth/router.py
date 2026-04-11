from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.access import (
    SYSTEM_PLATFORM_ADMIN,
    ensure_dev_login_seed_data,
    ensure_seed_data,
    get_dev_login_user,
    list_dev_login_accounts,
    load_user_graph,
    record_audit_log,
    resolve_group_slugs,
    replace_user_system_roles,
    serialize_auth_user,
)
from aidoo_api.domains.auth.dependencies import AuthContext, require_auth_context
from aidoo_api.domains.auth.models import AuthSession, OrgUnit, User
from aidoo_api.domains.auth.security import (
    hash_password,
    issue_session_token,
    new_id,
    normalize_email,
    verify_password,
)


class BootstrapStatusResponse(BaseModel):
    requires_setup: bool
    dev_admin_login_available: bool = False
    dev_login_accounts: list["DevLoginAccountResponse"] = Field(default_factory=list)


class DevLoginAccountResponse(BaseModel):
    account_key: str
    label: str
    email: str
    description: str
    category: str


class OrgUnitSummaryResponse(BaseModel):
    id: str
    name: str
    slug: str
    parent_id: str | None


class WorkspaceSummaryResponse(BaseModel):
    id: str
    slug: str
    name: str
    role: str
    enabled_apps: list[str]


class AuthUserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    display_name: str
    job_title: str | None
    status: str
    theme_preference: str
    primary_org_unit: OrgUnitSummaryResponse | None
    system_roles: list[str]
    workspaces: list[WorkspaceSummaryResponse]
    group_ids: list[str]
    group_slugs: list[str]
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class AuthSessionResponse(BaseModel):
    token: str
    user: AuthUserResponse


class SessionListItemResponse(BaseModel):
    id: str
    is_current: bool
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_seen_at: datetime | None
    user_agent: str | None
    ip_address: str | None


class SessionListResponse(BaseModel):
    items: list[SessionListItemResponse]


class SetupFirstUserRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized:
            raise ValueError("A valid email address is required.")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized:
            raise ValueError("A valid email address is required.")
        return normalized


class DevLoginRequest(BaseModel):
    account_key: str = Field(..., min_length=2, max_length=80)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class UpdatePreferencesRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    theme_preference: Literal["system", "light", "dark"] | None = None


router = APIRouter(prefix="/auth", tags=["auth"])


def _serialize_user(db: Session, user: User) -> AuthUserResponse:
    loaded_user = load_user_graph(db, user.id)
    if loaded_user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return AuthUserResponse.model_validate(serialize_auth_user(db, loaded_user))


def _request_ip(request: Request) -> str | None:
    client = request.client
    return client.host if client else None


def _request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _issue_auth_response(db: Session, user: User, request: Request) -> AuthSessionResponse:
    settings = get_settings()
    issued = issue_session_token(settings.session_ttl_hours)
    now = datetime.now(UTC).replace(tzinfo=None)
    session = AuthSession(
        id=new_id(),
        user_id=user.id,
        token_hash=issued.token_hash,
        expires_at=issued.expires_at,
        last_seen_at=now,
        user_agent=_request_user_agent(request),
        ip_address=_request_ip(request),
    )
    user.last_login_at = now
    db.add(user)
    db.add(session)
    db.commit()
    return AuthSessionResponse(token=issued.plain_text, user=_serialize_user(db, user))


def _ensure_active_user(user: User) -> None:
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )


def _ensure_development_environment() -> None:
    settings = get_settings()
    if settings.environment.lower() == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )


def _is_local_dev_admin_login_available(request: Request) -> bool:
    settings = get_settings()
    if settings.environment.lower() == "production" or not settings.allow_dev_admin_login:
        return False

    client_host = request.client.host if request.client else None
    request_host = request.url.hostname
    local_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
    return client_host in local_hosts or request_host in local_hosts


def _ensure_local_dev_admin_login_allowed(request: Request) -> None:
    if not _is_local_dev_admin_login_available(request):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
        )


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def bootstrap_status(
    request: Request,
    db: Session = Depends(get_db_session),
) -> BootstrapStatusResponse:
    has_users = db.scalar(select(func.count()).select_from(User)) > 0
    dev_admin_login_available = _is_local_dev_admin_login_available(request)
    # The dev-login account list is a read-only projection. Previously this
    # endpoint also triggered ``ensure_dev_login_seed_data`` on every call,
    # which turned the routine "open login page" action into an expensive
    # reconcile that historically wiped user-created team memberships. The
    # seed now runs exactly once on an empty DB (init_db or dev-login).
    return BootstrapStatusResponse(
        requires_setup=not has_users,
        dev_admin_login_available=dev_admin_login_available,
        dev_login_accounts=(
            [
                DevLoginAccountResponse.model_validate(item)
                for item in list_dev_login_accounts(db)
            ]
            if dev_admin_login_available
            else []
        ),
    )


@router.post(
    "/setup",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def setup_first_user(
    payload: SetupFirstUserRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    ensure_seed_data(db)
    has_users = db.scalar(select(func.count()).select_from(User)) > 0
    if has_users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial setup is already complete.",
        )

    root_org_unit = db.scalar(select(OrgUnit).where(OrgUnit.slug == "hq"))
    if root_org_unit is None:
        raise HTTPException(status_code=500, detail="Default identity seed is incomplete.")

    user = User(
        id=new_id(),
        email=payload.email,
        full_name=payload.full_name.strip(),
        display_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        status="active",
        primary_org_unit_id=root_org_unit.id,
        must_change_password=False,
        theme_preference="system",
    )
    db.add(user)
    db.flush()
    replace_user_system_roles(db, user.id, [SYSTEM_PLATFORM_ADMIN])
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.setup",
        entity_kind="user",
        entity_id=user.id,
        summary=f"Initial administrator created: {user.email}",
        payload={"system_roles": [SYSTEM_PLATFORM_ADMIN]},
    )
    db.commit()
    return _issue_auth_response(db, user, request)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is invalid.",
        )
    _ensure_active_user(user)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.login",
        entity_kind="session",
        entity_id=user.id,
        summary=f"User logged in: {user.email}",
        payload={"group_slugs": resolve_group_slugs(load_user_graph(db, user.id) or user)},
    )
    db.commit()
    return _issue_auth_response(db, user, request)


@router.post("/dev-admin-login", response_model=AuthSessionResponse)
def dev_admin_login(
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    _ensure_local_dev_admin_login_allowed(request)
    has_users = db.scalar(select(func.count()).select_from(User)) > 0
    if has_users:
        ensure_dev_login_seed_data(db)

    candidates = db.scalars(
        select(User)
        .where(User.status == "active")
        .order_by((User.email == "admin@aidoo.local").desc(), User.created_at.asc())
    ).all()
    user = next(
        (
            candidate
            for candidate in candidates
            if SYSTEM_PLATFORM_ADMIN in _serialize_user(db, candidate).system_roles
        ),
        None,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active administrator account is available.",
        )

    _ensure_active_user(user)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.dev_admin_login",
        entity_kind="session",
        entity_id=user.id,
        summary=f"Development admin quick login: {user.email}",
        payload={"group_slugs": resolve_group_slugs(load_user_graph(db, user.id) or user)},
    )
    db.commit()
    return _issue_auth_response(db, user, request)


@router.post("/dev-login", response_model=AuthSessionResponse)
def dev_login(
    payload: DevLoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    _ensure_local_dev_admin_login_allowed(request)
    has_users = db.scalar(select(func.count()).select_from(User)) > 0
    if has_users:
        ensure_dev_login_seed_data(db)

    user = get_dev_login_user(db, payload.account_key)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requested development account is not available.",
        )

    _ensure_active_user(user)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.dev_login",
        entity_kind="session",
        entity_id=user.id,
        summary=f"Development account quick login: {user.email}",
        payload={"account_key": payload.account_key},
    )
    db.commit()
    return _issue_auth_response(db, user, request)


@router.get("/me", response_model=AuthUserResponse)
def me(
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> AuthUserResponse:
    return _serialize_user(db, context.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> None:
    context.session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(context.session)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="auth.logout",
        entity_kind="session",
        entity_id=context.session.id,
        summary=f"User logged out: {context.user.email}",
    )
    db.commit()


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> None:
    if not verify_password(payload.current_password, context.user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is invalid.",
        )

    context.user.password_hash = hash_password(payload.new_password)
    context.user.must_change_password = False
    db.add(context.user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="auth.change-password",
        entity_kind="user",
        entity_id=context.user.id,
        summary=f"Password changed for {context.user.email}",
    )
    db.commit()


@router.patch("/preferences", response_model=AuthUserResponse)
def update_preferences(
    payload: UpdatePreferencesRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> AuthUserResponse:
    if payload.display_name is not None:
        context.user.display_name = payload.display_name.strip()
    if payload.full_name is not None:
        context.user.full_name = payload.full_name.strip()
    if payload.job_title is not None:
        context.user.job_title = payload.job_title.strip()
    if payload.theme_preference is not None:
        context.user.theme_preference = payload.theme_preference

    db.add(context.user)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="auth.update-preferences",
        entity_kind="user",
        entity_id=context.user.id,
        summary=f"Preferences updated for {context.user.email}",
        payload={
            "theme_preference": payload.theme_preference,
            "display_name": payload.display_name,
            "job_title": payload.job_title,
        },
    )
    db.commit()
    return _serialize_user(db, context.user)


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> SessionListResponse:
    sessions = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == context.user.id)
        .order_by(AuthSession.created_at.desc())
    ).all()
    return SessionListResponse(
        items=[
            SessionListItemResponse(
                id=session.id,
                is_current=session.id == context.session.id,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                last_seen_at=session.last_seen_at,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
            )
            for session in sessions
        ]
    )


@router.post("/sessions/{session_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: str,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> None:
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == context.user.id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(session)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="auth.revoke-session",
        entity_kind="session",
        entity_id=session.id,
        summary=f"Session revoked for {context.user.email}",
    )
    db.commit()
