from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import re
import secrets
import unicodedata
from typing import Annotated

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.core.settings import get_settings
from open_alm_api.domains.auth.models import PlatformApiKey, utcnow_naive
from open_alm_api.domains.auth.security import new_id


PLATFORM_API_KEY_TOKEN_PREFIX = "aido_pk_"
PLATFORM_API_KEY_STATUS_ACTIVE = "active"
PLATFORM_API_KEY_STATUS_REVOKED = "revoked"
PLATFORM_API_KEY_SCOPE_REGISTRY = ("hr:read",)
_PLATFORM_API_KEY_DISPLAY_PREFIX_LENGTH = 18
_PLATFORM_API_KEY_FERNET_PURPOSE = b"open-alm:platform-api-key:v1"
_PLATFORM_API_KEY_TOKEN_PATTERN = re.compile(r"^aido_pk_[A-Za-z0-9_-]{43}$")
_SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_PLATFORM_API_KEY_AUTH_ERROR_HEADERS = {
    "WWW-Authenticate": "Bearer",
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
}


class PlatformApiKeyServiceError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PlatformApiPrincipal:
    key_id: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class IssuedPlatformApiKey:
    row: PlatformApiKey
    secret: SecretStr


def normalize_platform_api_key_scopes(scopes: list[str] | tuple[str, ...]) -> list[str]:
    normalized = sorted({str(scope).strip().lower() for scope in scopes})
    registered_scopes = frozenset(PLATFORM_API_KEY_SCOPE_REGISTRY)
    if (
        not normalized
        or any(not _SCOPE_PATTERN.fullmatch(scope) for scope in normalized)
        or not set(normalized).issubset(registered_scopes)
    ):
        raise PlatformApiKeyServiceError("admin.platform_api_key_scope_invalid")
    return normalized


def hash_platform_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _is_platform_api_key_token(secret: str) -> bool:
    return _PLATFORM_API_KEY_TOKEN_PATTERN.fullmatch(secret) is not None


def _platform_api_key_fernet() -> Fernet:
    configured_root = get_settings().ai_model_credential_encryption_key.strip()
    if not configured_root:
        raise PlatformApiKeyServiceError("admin.platform_api_key_encryption_unavailable")

    try:
        encoded_root = configured_root.encode("ascii")
        Fernet(encoded_root)
        root_material = base64.urlsafe_b64decode(encoded_root)
    except (UnicodeEncodeError, ValueError):
        root_material = hashlib.sha256(configured_root.encode("utf-8")).digest()
    purpose_key = hmac.new(
        root_material,
        _PLATFORM_API_KEY_FERNET_PURPOSE,
        hashlib.sha256,
    ).digest()
    return Fernet(base64.urlsafe_b64encode(purpose_key))


def encrypt_platform_api_key(secret: SecretStr | str) -> str:
    raw_secret = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    if not _is_platform_api_key_token(raw_secret):
        raise PlatformApiKeyServiceError("platform_api_key.invalid")
    return _platform_api_key_fernet().encrypt(raw_secret.encode("utf-8")).decode("ascii")


def decrypt_platform_api_key(ciphertext: str) -> SecretStr:
    try:
        secret = _platform_api_key_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise PlatformApiKeyServiceError("admin.platform_api_key_encryption_unavailable") from exc
    if not _is_platform_api_key_token(secret):
        raise PlatformApiKeyServiceError("admin.platform_api_key_encryption_unavailable")
    return SecretStr(secret)


def issue_platform_api_key(
    db: Session,
    *,
    name: str,
    scopes: list[str] | tuple[str, ...],
    actor_user_id: str,
    issued_at: datetime | None = None,
) -> IssuedPlatformApiKey:
    normalized_name = name.strip()
    if not normalized_name:
        raise PlatformApiKeyServiceError("admin.platform_api_key_name_required")
    if any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in normalized_name):
        raise PlatformApiKeyServiceError("admin.platform_api_key_name_invalid")
    normalized_scopes = normalize_platform_api_key_scopes(scopes)
    now = issued_at or utcnow_naive()

    for _ in range(5):
        secret = f"{PLATFORM_API_KEY_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        token_hash = hash_platform_api_key(secret)
        key_prefix = secret[:_PLATFORM_API_KEY_DISPLAY_PREFIX_LENGTH]
        collision = db.scalar(
            select(PlatformApiKey.id).where(
                (PlatformApiKey.token_hash == token_hash)
                | (PlatformApiKey.key_prefix == key_prefix)
            )
        )
        if collision is None:
            break
    else:  # pragma: no cover - cryptographically implausible
        raise PlatformApiKeyServiceError("admin.platform_api_key_issue_failed")

    row = PlatformApiKey(
        id=new_id(),
        token_hash=token_hash,
        secret_ciphertext=encrypt_platform_api_key(secret),
        key_prefix=key_prefix,
        name=normalized_name,
        scopes=normalized_scopes,
        status=PLATFORM_API_KEY_STATUS_ACTIVE,
        created_by_user_id=actor_user_id,
        created_at=now,
    )
    db.add(row)
    db.flush()
    return IssuedPlatformApiKey(row=row, secret=SecretStr(secret))


def list_platform_api_keys(db: Session) -> list[PlatformApiKey]:
    return list(
        db.scalars(
            select(PlatformApiKey).order_by(
                PlatformApiKey.created_at.desc(),
                PlatformApiKey.id.desc(),
            )
        ).all()
    )


def load_platform_api_key(
    db: Session,
    key_id: str,
    *,
    for_update: bool = False,
) -> PlatformApiKey:
    statement = select(PlatformApiKey).where(PlatformApiKey.id == key_id)
    if for_update:
        statement = statement.with_for_update()
    row = db.scalar(statement)
    if row is None:
        raise PlatformApiKeyServiceError("admin.platform_api_key_not_found")
    return row


def reveal_platform_api_key(db: Session, key_id: str) -> SecretStr:
    row = load_platform_api_key(db, key_id, for_update=True)
    if row.status != PLATFORM_API_KEY_STATUS_ACTIVE:
        raise PlatformApiKeyServiceError("admin.platform_api_key_inactive")
    return decrypt_platform_api_key(row.secret_ciphertext)


def revoke_platform_api_key(
    db: Session,
    *,
    key_id: str,
    actor_user_id: str,
    revoked_at: datetime | None = None,
) -> PlatformApiKey:
    row = load_platform_api_key(db, key_id, for_update=True)
    if row.status != PLATFORM_API_KEY_STATUS_ACTIVE:
        raise PlatformApiKeyServiceError("admin.platform_api_key_inactive")
    row.status = PLATFORM_API_KEY_STATUS_REVOKED
    row.secret_ciphertext = ""
    row.revoked_by_user_id = actor_user_id
    row.revoked_at = revoked_at or utcnow_naive()
    db.add(row)
    db.flush()
    return row


def authenticate_platform_api_key(
    db: Session,
    secret: str,
    *,
    used_at: datetime | None = None,
) -> PlatformApiPrincipal | None:
    if not _is_platform_api_key_token(secret):
        return None
    token_hash = hash_platform_api_key(secret)
    row = db.scalar(select(PlatformApiKey).where(PlatformApiKey.token_hash == token_hash))
    if (
        row is None
        or row.status != PLATFORM_API_KEY_STATUS_ACTIVE
        or not hmac.compare_digest(row.token_hash, token_hash)
    ):
        return None
    try:
        scopes = frozenset(normalize_platform_api_key_scopes(row.scopes))
    except PlatformApiKeyServiceError:
        return None
    row.last_used_at = used_at or utcnow_naive()
    db.add(row)
    db.commit()
    return PlatformApiPrincipal(key_id=row.id, scopes=scopes)


class PlatformApiKeyBearer(HTTPBearer):
    """Bearer extractor that deliberately accepts only platform API key tokens."""

    def __init__(self) -> None:
        super().__init__(
            auto_error=False,
            scheme_name="PlatformApiKey",
            description="Platform API key using the aido_pk_ token format.",
        )

    async def __call__(self, request: Request) -> str:
        credentials: HTTPAuthorizationCredentials | None = await super().__call__(request)
        if credentials is None:
            raise localized_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="platform_api_key.required",
                headers=_PLATFORM_API_KEY_AUTH_ERROR_HEADERS,
            )
        if credentials.scheme.lower() != "bearer" or not _is_platform_api_key_token(
            credentials.credentials
        ):
            raise localized_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="platform_api_key.invalid",
                headers=_PLATFORM_API_KEY_AUTH_ERROR_HEADERS,
            )
        return credentials.credentials


platform_api_key_bearer = PlatformApiKeyBearer()


def require_platform_api_key(
    secret: Annotated[str, Depends(platform_api_key_bearer)],
    db: Session = Depends(get_db_session),
) -> PlatformApiPrincipal:
    principal = authenticate_platform_api_key(db, secret)
    if principal is None:
        raise localized_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="platform_api_key.invalid",
            headers=_PLATFORM_API_KEY_AUTH_ERROR_HEADERS,
        )
    return principal


def require_platform_api_scope(scope: str):
    normalized_scope = normalize_platform_api_key_scopes([scope])[0]

    def dependency(
        principal: PlatformApiPrincipal = Depends(require_platform_api_key),
    ) -> PlatformApiPrincipal:
        if normalized_scope not in principal.scopes:
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="platform_api_key.scope_required",
                headers={
                    "Cache-Control": "private, no-store",
                    "Pragma": "no-cache",
                },
                scope=normalized_scope,
            )
        return principal

    return dependency


__all__ = [
    "IssuedPlatformApiKey",
    "PLATFORM_API_KEY_STATUS_ACTIVE",
    "PLATFORM_API_KEY_STATUS_REVOKED",
    "PLATFORM_API_KEY_SCOPE_REGISTRY",
    "PLATFORM_API_KEY_TOKEN_PREFIX",
    "PlatformApiKeyBearer",
    "PlatformApiKeyServiceError",
    "PlatformApiPrincipal",
    "authenticate_platform_api_key",
    "decrypt_platform_api_key",
    "encrypt_platform_api_key",
    "hash_platform_api_key",
    "issue_platform_api_key",
    "list_platform_api_keys",
    "load_platform_api_key",
    "normalize_platform_api_key_scopes",
    "platform_api_key_bearer",
    "require_platform_api_key",
    "require_platform_api_scope",
    "reveal_platform_api_key",
    "revoke_platform_api_key",
]
