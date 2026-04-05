from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.dependencies import AuthContext, require_auth_context
from aidoo_api.domains.auth.models import AuthSession, User
from aidoo_api.domains.auth.security import (
    hash_password,
    issue_session_token,
    new_id,
    normalize_email,
    verify_password,
)


class BootstrapStatusResponse(BaseModel):
    requires_setup: bool


class AuthUserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    is_admin: bool


class AuthSessionResponse(BaseModel):
    token: str
    user: AuthUserResponse


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


router = APIRouter(prefix="/auth", tags=["auth"])


def _serialize_user(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
    )


def _issue_auth_response(db: Session, user: User) -> AuthSessionResponse:
    settings = get_settings()
    issued = issue_session_token(settings.session_ttl_hours)
    session = AuthSession(
        id=new_id(),
        user_id=user.id,
        token_hash=issued.token_hash,
        expires_at=issued.expires_at,
    )
    db.add(session)
    db.commit()
    return AuthSessionResponse(token=issued.plain_text, user=_serialize_user(user))


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def bootstrap_status(db: Session = Depends(get_db_session)) -> BootstrapStatusResponse:
    has_users = db.scalar(select(func.count()).select_from(User)) > 0
    return BootstrapStatusResponse(requires_setup=not has_users)


@router.post(
    "/setup",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def setup_first_user(
    payload: SetupFirstUserRequest,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    has_users = db.scalar(select(func.count()).select_from(User)) > 0
    if has_users:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Initial setup is already complete.",
        )

    user = User(
        id=new_id(),
        email=payload.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    return _issue_auth_response(db, user)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db_session),
) -> AuthSessionResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is invalid.",
        )
    return _issue_auth_response(db, user)


@router.get("/me", response_model=AuthUserResponse)
def me(context: AuthContext = Depends(require_auth_context)) -> AuthUserResponse:
    return _serialize_user(context.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    context: AuthContext = Depends(require_auth_context),
    db: Session = Depends(get_db_session),
) -> None:
    context.session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(context.session)
    db.commit()
