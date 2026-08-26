from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import (
    get_settings,
    is_production_environment,
    is_production_like_environment,
)
from open_work_hub_api.domains.auth.access import (
    SYSTEM_PLATFORM_ADMIN,
    ensure_dev_login_seed_data,
    ensure_seed_data,
    ensure_workspace_default_pms_space,
    get_dev_login_user,
    list_dev_login_account_catalog,
    list_dev_login_accounts,
    load_active_workspace_by_id,
    load_user_graph,
    normalize_locale,
    normalize_time_zone,
    record_audit_log,
    resolve_workspace_role,
    replace_user_system_roles,
    serialize_auth_user,
)
from open_work_hub_api.domains.auth.date_format_preferences import (
    default_date_format_value,
    normalize_date_format_payload,
    validate_date_format_value,
)
from open_work_hub_api.domains.auth.app_bar_preferences import (
    normalize_app_bar_pinned_app_ids,
)
from open_work_hub_api.domains.auth.dependencies import (
    AuthContext,
    require_auth_context,
    require_permission,
)
from open_work_hub_api.domains.auth.models import (
    AuthSession,
    DesktopSessionLink,
    User,
    Workspace,
    WorkspaceUserBinding,
)
from open_work_hub_api.domains.auth.security import (
    derive_login_id_from_email,
    hash_token,
    hash_password,
    issue_session_token,
    is_valid_login_id,
    new_id,
    normalize_email,
    normalize_login_id,
    verify_password,
)
from open_work_hub_api.domains.organization.schemas import OrganizationUnitSummaryResponse

DESKTOP_SESSION_LINK_TTL_SECONDS = 5 * 60


def _valid_email_required_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.valid_email_required",
        "A valid email address is required.",
        {},
    )


def _valid_login_id_required_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.valid_login_id_required",
        "A valid ID is required.",
        {},
    )


def _invalid_locale_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.invalid_locale",
        "Invalid locale.",
        {},
    )


def _invalid_time_zone_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.invalid_time_zone",
        "Invalid time zone.",
        {},
    )


def _invalid_app_bar_layout_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.invalid_app_bar_layout",
        "Invalid app bar layout.",
        {},
    )


def _password_confirmation_mismatch_error() -> PydanticCustomError:
    return PydanticCustomError(
        "auth.password_confirmation_mismatch",
        "Password confirmation does not match.",
        {},
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


class WorkspaceSummaryResponse(BaseModel):
    id: str
    slug: str
    name: str
    role: str


class AppBarLayoutPreference(BaseModel):
    pinned_app_ids: list[str] = Field(default_factory=list)

    @field_validator("pinned_app_ids")
    @classmethod
    def validate_pinned_app_ids(cls, value: list[str]) -> list[str]:
        try:
            return normalize_app_bar_pinned_app_ids(value, reject_unknown=True)
        except ValueError as exc:
            raise _invalid_app_bar_layout_error() from exc


class AuthUserResponse(BaseModel):
    id: str
    login_id: str
    email: str
    full_name: str
    display_name: str
    employee_code: str | None
    job_title: str | None
    primary_organization_unit: OrganizationUnitSummaryResponse | None
    status: str
    login_blocked: bool
    theme_preference: str
    locale: str
    time_zone: str
    date_format: str
    app_bar_layout: AppBarLayoutPreference
    default_workspace_id: str | None
    system_roles: list[str]
    workspaces: list[WorkspaceSummaryResponse]
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuthSessionResponse(BaseModel):
    token: str
    user: AuthUserResponse


class DesktopSessionLinkResponse(BaseModel):
    code: str
    expires_at: datetime


class DesktopSessionLinkExchangeRequest(BaseModel):
    code: str = Field(..., min_length=16, max_length=256)


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
    login_id: str | None = Field(default=None, min_length=3, max_length=40)
    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("login_id", mode="before")
    @classmethod
    def validate_login_id(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        normalized = normalize_login_id(value)
        if not is_valid_login_id(normalized):
            raise _valid_login_id_required_error()
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized:
            raise _valid_email_required_error()
        return normalized


class SignupRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    login_id: str = Field(..., min_length=3, max_length=40)
    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=8, max_length=128)
    password_confirm: str = Field(..., min_length=8, max_length=128)

    @field_validator("login_id", mode="before")
    @classmethod
    def validate_login_id(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = normalize_login_id(value)
        if not is_valid_login_id(normalized):
            raise _valid_login_id_required_error()
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalize_email(value)
        if "@" not in normalized:
            raise _valid_email_required_error()
        return normalized

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "SignupRequest":
        if self.password != self.password_confirm:
            raise _password_confirmation_mismatch_error()
        return self


class LoginRequest(BaseModel):
    login_id: str = Field(..., min_length=3, max_length=40)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("login_id", mode="before")
    @classmethod
    def validate_login_id(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = normalize_login_id(value)
        if not is_valid_login_id(normalized):
            raise _valid_login_id_required_error()
        return normalized


class DevLoginRequest(BaseModel):
    account_key: str = Field(..., min_length=2, max_length=80)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class UpdatePreferencesRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    theme_preference: Literal["system", "light", "dark"] | None = None
    locale: Literal["ko-KR", "en-US"] | None = None
    time_zone: str | None = Field(default=None, min_length=1, max_length=64)
    date_format: Literal["korean", "iso", "us", "european", "locale"] | None = None
    app_bar_layout: AppBarLayoutPreference | None = None
    default_workspace_id: str | None = Field(default=None, max_length=36)

    @model_validator(mode="before")
    @classmethod
    def validate_locale_before_field_types(cls, data):
        if not isinstance(data, dict) or data.get("locale") is None:
            return data
        value = data.get("locale")
        if not isinstance(value, str):
            raise _invalid_locale_error()
        try:
            normalized = normalize_locale(value)
        except ValueError as exc:
            raise _invalid_locale_error() from exc
        return {**data, "locale": normalized}

    @model_validator(mode="before")
    @classmethod
    def validate_date_format_before_field_types(cls, data):
        return normalize_date_format_payload(data)

    @field_validator("time_zone")
    @classmethod
    def validate_time_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_time_zone(value)
        except ValueError as exc:
            raise _invalid_time_zone_error() from exc

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_locale(value)
        except ValueError as exc:
            raise _invalid_locale_error() from exc

    @field_validator("date_format")
    @classmethod
    def validate_date_format(cls, value: str | None) -> str | None:
        return validate_date_format_value(value)

    @field_validator("default_workspace_id")
    @classmethod
    def validate_default_workspace_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


router = APIRouter(prefix="/auth", tags=["auth"])


def _serialize_user(db: Session, user: User) -> AuthUserResponse:
    loaded_user = load_user_graph(db, user.id)
    if loaded_user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    return AuthUserResponse.model_validate(serialize_auth_user(db, loaded_user))


def _request_ip(request: Request) -> str | None:
    client = request.client
    return client.host if client else None


def _request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def _issue_auth_response(
    db: Session,
    user: User,
    request: Request,
    *,
    impersonator_user_id: str | None = None,
) -> AuthSessionResponse:
    settings = get_settings()
    issued = issue_session_token(settings.session_ttl_hours)
    now = datetime.now(UTC).replace(tzinfo=None)
    session = AuthSession(
        id=new_id(),
        user_id=user.id,
        impersonator_user_id=impersonator_user_id,
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
    if user.status != "active" or user.login_blocked:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="auth.user_inactive",
        )


def _ensure_development_environment() -> None:
    settings = get_settings()
    if is_production_environment(settings.environment):
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="auth.not_found",
        )


def is_local_dev_admin_login_available(request: Request) -> bool:
    settings = get_settings()
    if (
        is_production_like_environment(settings.environment)
        or not settings.allow_dev_admin_login
    ):
        return False

    client_host = request.client.host if request.client else None
    request_host = request.url.hostname
    local_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
    if client_host in local_hosts or request_host in local_hosts:
        return True

    allowed_hosts = {
        host.strip().lower() for host in settings.dev_login_allowed_hosts.split(",") if host.strip()
    }
    if not allowed_hosts:
        return False

    request_hosts = {
        host.lower()
        for host in [
            request_host,
            request.headers.get("host", "").split(":", 1)[0],
            request.headers.get("x-forwarded-host", "").split(",", 1)[0].split(":", 1)[0],
        ]
        if host
    }
    return bool(request_hosts.intersection(allowed_hosts))


def _ensure_local_dev_admin_login_allowed(request: Request) -> None:
    if not is_local_dev_admin_login_available(request):
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="auth.not_found",
        )


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def bootstrap_status(
    request: Request,
    db: Session = Depends(get_db_session),
) -> BootstrapStatusResponse:
    has_users = db.scalar(select(func.count()).select_from(User)) > 0
    dev_admin_login_available = is_local_dev_admin_login_available(request)
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
                for item in (
                    list_dev_login_account_catalog() if has_users else list_dev_login_accounts(db)
                )
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
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="auth.setup_already_complete",
        )

    user = User(
        id=new_id(),
        login_id=payload.login_id or derive_login_id_from_email(payload.email),
        email=payload.email,
        full_name=payload.full_name.strip(),
        display_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        status="active",
        must_change_password=False,
        theme_preference="system",
        locale=normalize_locale(None),
        time_zone=normalize_time_zone(None),
        date_format=default_date_format_value(),
    )
    db.add(user)
    db.flush()
    replace_user_system_roles(db, user.id, [SYSTEM_PLATFORM_ADMIN])
    default_workspaces = db.scalars(
        select(Workspace).where(Workspace.key.in_(["administrator", "general"]))
    ).all()
    for default_workspace in default_workspaces:
        db.add(
            WorkspaceUserBinding(
                id=new_id(),
                workspace_id=default_workspace.id,
                user_id=user.id,
                role="admin",
            )
        )
        ensure_workspace_default_pms_space(db, default_workspace)
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


@router.post(
    "/signup",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def signup(
    payload: SignupRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    ensure_seed_data(db)
    if not db.scalar(select(func.count()).select_from(User)):
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="auth.setup_required",
        )
    if db.scalar(select(User.id).where(User.login_id == payload.login_id)) is not None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="auth.login_id_already_exists",
        )
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="auth.user_already_exists",
        )

    default_workspace = db.scalar(select(Workspace).where(Workspace.key == "general"))
    if default_workspace is None:
        raise localized_http_exception(
            status_code=500,
            code="auth.default_identity_seed_incomplete",
        )

    user = User(
        id=new_id(),
        login_id=payload.login_id,
        email=payload.email,
        full_name=payload.full_name.strip(),
        display_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        status="active",
        must_change_password=False,
        theme_preference="system",
        locale=normalize_locale(None),
        time_zone=normalize_time_zone(None),
        date_format=default_date_format_value(),
    )
    db.add(user)
    db.flush()
    db.add(
        WorkspaceUserBinding(
            id=new_id(),
            workspace_id=default_workspace.id,
            user_id=user.id,
            role="member",
        )
    )
    ensure_workspace_default_pms_space(db, default_workspace)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.signup",
        entity_kind="user",
        entity_id=user.id,
        summary=f"User signed up: {user.email}",
    )
    db.commit()
    return _issue_auth_response(db, user, request)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    user = db.scalar(select(User).where(User.login_id == payload.login_id))
    if user is None:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.invalid_credentials",
        )
    _ensure_active_user(user)
    password_matches = verify_password(payload.password, user.password_hash)

    if not password_matches:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.invalid_credentials",
        )
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.login",
        entity_kind="session",
        entity_id=user.id,
        summary=f"User logged in: {user.email}",
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
        .order_by((User.email == "admin@open-work-hub.local").desc(), User.created_at.asc())
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
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="auth.no_active_admin",
        )

    _ensure_active_user(user)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.dev_admin_login",
        entity_kind="session",
        entity_id=user.id,
        summary=f"Development admin quick login: {user.email}",
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
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="auth.dev_account_unavailable",
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


@router.post("/impersonations/{user_id}", response_model=AuthSessionResponse)
def impersonate_user(
    user_id: str,
    request: Request,
    context: AuthContext = Depends(require_permission("user.impersonate")),
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    target_user = db.scalar(select(User).where(User.id == user_id))
    if target_user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    _ensure_active_user(target_user)

    impersonator_user_id = context.impersonator_user_id or context.user.id
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="auth.impersonate",
        entity_kind="user",
        entity_id=target_user.id,
        summary=f"User impersonation started: {context.user.email} -> {target_user.email}",
        payload={
            "impersonator_user_id": impersonator_user_id,
            "impersonator_email": context.user.email,
            "target_user_id": target_user.id,
            "target_email": target_user.email,
            "source_session_id": context.session.id,
        },
    )
    return _issue_auth_response(
        db,
        target_user,
        request,
        impersonator_user_id=impersonator_user_id,
    )


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


@router.post("/desktop-session-links", response_model=DesktopSessionLinkResponse)
def create_desktop_session_link(
    request: Request,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> DesktopSessionLinkResponse:
    code = secrets.token_urlsafe(32)
    now = datetime.now(UTC).replace(tzinfo=None)
    expires_at = now + timedelta(seconds=DESKTOP_SESSION_LINK_TTL_SECONDS)
    link = DesktopSessionLink(
        id=new_id(),
        user_id=context.user.id,
        source_session_id=context.session.id,
        code_hash=hash_token(code),
        created_at=now,
        expires_at=expires_at,
        user_agent=_request_user_agent(request),
        ip_address=_request_ip(request),
    )
    db.add(link)
    record_audit_log(
        db,
        actor_user_id=context.user.id,
        action="auth.desktop-session-link.create",
        entity_kind="session",
        entity_id=link.id,
        summary=f"Desktop session link created for {context.user.email}",
        payload={"expires_at": expires_at.isoformat()},
    )
    db.commit()
    return DesktopSessionLinkResponse(code=code, expires_at=expires_at)


@router.post("/desktop-session-links/exchange", response_model=AuthSessionResponse)
def exchange_desktop_session_link(
    payload: DesktopSessionLinkExchangeRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    now = datetime.now(UTC).replace(tzinfo=None)
    link = db.scalar(
        select(DesktopSessionLink)
        .where(
            DesktopSessionLink.code_hash == hash_token(payload.code),
            DesktopSessionLink.consumed_at.is_(None),
            DesktopSessionLink.expires_at > now,
        )
        .with_for_update()
    )
    if link is None:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.desktop_session_link_invalid",
        )

    source_session = db.scalar(
        select(AuthSession).where(
            AuthSession.id == link.source_session_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    user = load_user_graph(db, link.user_id)
    if source_session is None or user is None:
        link.consumed_at = now
        db.add(link)
        db.commit()
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="auth.desktop_session_link_invalid",
        )
    _ensure_active_user(user)

    link.consumed_at = now
    db.add(link)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.desktop-session-link.exchange",
        entity_kind="session",
        entity_id=link.id,
        summary=f"Desktop session link exchanged for {user.email}",
    )
    db.commit()
    return _issue_auth_response(db, user, request)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> None:
    if not verify_password(payload.current_password, context.user.password_hash):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="auth.current_password_invalid",
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
    if payload.theme_preference is not None:
        context.user.theme_preference = payload.theme_preference
    if payload.locale is not None:
        context.user.locale = payload.locale
    if payload.time_zone is not None:
        context.user.time_zone = payload.time_zone
    if payload.date_format is not None:
        context.user.date_format = payload.date_format
    if "app_bar_layout" in payload.model_fields_set:
        context.user.app_bar_layout = (
            payload.app_bar_layout.model_dump()
            if payload.app_bar_layout is not None
            else None
        )
    if "default_workspace_id" in payload.model_fields_set:
        if payload.default_workspace_id is None:
            context.user.default_workspace_id = None
        else:
            workspace = load_active_workspace_by_id(db, payload.default_workspace_id)
            if workspace is None:
                raise localized_http_exception(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="workspace.not_found",
                )
            if resolve_workspace_role(db, context.user, workspace.id) is None:
                raise localized_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="workspace.membership_required",
                    workspace=workspace.key,
                )
            context.user.default_workspace_id = workspace.id

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
            "locale": payload.locale,
            "time_zone": payload.time_zone,
            "date_format": payload.date_format,
            "app_bar_layout": (
                payload.app_bar_layout.model_dump()
                if payload.app_bar_layout is not None
                else None
            ),
            "default_workspace_id": (
                payload.default_workspace_id
                if "default_workspace_id" in payload.model_fields_set
                else None
            ),
            "display_name": payload.display_name,
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
        raise localized_http_exception(status_code=404, code="auth.session_not_found")

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
