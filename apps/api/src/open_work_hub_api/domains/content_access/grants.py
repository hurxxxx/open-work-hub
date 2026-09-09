from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from open_work_hub_api.core.app_contracts_generated import APP_ROUTE_BY_ID
from open_work_hub_api.core.settings import get_settings

ExecutionContextKind = Literal["personal", "company"]
Disposition = Literal["attachment", "inline"]
CONTENT_GRANT_MAX_TTL_SECONDS = 15 * 60


class InvalidContentGrant(ValueError):
    pass


@dataclass(frozen=True)
class ContentGrantIssuer:
    user_id: str
    session_id: str

    def __post_init__(self) -> None:
        if not self.user_id or not self.session_id:
            raise ValueError("content grant issuer requires user and session ids")


@dataclass(frozen=True)
class ContentGrantClaims:
    version: int
    issued_at: int
    resource_kind: str
    resource_id: str
    owner_app_id: str
    issuer_user_id: str
    issuer_session_id: str
    execution_context_kind: ExecutionContextKind
    route_id: str | None
    source_type: str
    source_id: str
    object_identity: str
    resource_version: str
    disposition: Disposition
    expires: int
    extra: dict[str, Any] = field(default_factory=dict)


def build_content_grant_url(
    *,
    resource_kind: str,
    resource_id: str,
    owner_app_id: str,
    issuer: ContentGrantIssuer,
    execution_context_kind: ExecutionContextKind,
    route_id: str | None,
    source_type: str,
    source_id: str,
    object_identity: str,
    resource_version: str,
    disposition: Disposition,
    expires_seconds: int,
    now: float | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    issued_at = int(time.time() if now is None else now)
    if expires_seconds <= 0 or expires_seconds > CONTENT_GRANT_MAX_TTL_SECONDS:
        raise ValueError("content grant TTL is outside the allowed boundary")
    _validate_content_grant_fields(
        resource_kind=resource_kind,
        resource_id=resource_id,
        owner_app_id=owner_app_id,
        issuer_user_id=issuer.user_id,
        issuer_session_id=issuer.session_id,
        execution_context_kind=execution_context_kind,
        route_id=route_id,
        source_type=source_type,
        source_id=source_id,
        object_identity=object_identity,
        resource_version=resource_version,
        disposition=disposition,
        extra=extra or {},
    )
    expires = issued_at + expires_seconds
    claims = ContentGrantClaims(
        version=1,
        issued_at=issued_at,
        resource_kind=resource_kind,
        resource_id=resource_id,
        owner_app_id=owner_app_id,
        issuer_user_id=issuer.user_id,
        issuer_session_id=issuer.session_id,
        execution_context_kind=execution_context_kind,
        route_id=route_id,
        source_type=source_type,
        source_id=source_id,
        object_identity=object_identity,
        resource_version=resource_version,
        disposition=disposition,
        expires=expires,
        extra=extra or {},
    )
    # Fragments are not sent in request targets or referrers. Browser clients
    # forward the capability through the dedicated request header instead.
    return f"{get_settings().api_prefix}/content#grant={_encode(claims)}"


def decode_content_grant(token: str, *, now: float | None = None) -> ContentGrantClaims:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected = hmac.new(
            get_settings().content_grant_signing_key.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual = _base64url_decode(encoded_signature)
        if not hmac.compare_digest(actual, expected):
            raise InvalidContentGrant("signature")
        payload = json.loads(_base64url_decode(encoded_payload))
        if not isinstance(payload, dict):
            raise InvalidContentGrant("shape")
        claims = ContentGrantClaims(**payload)
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, InvalidContentGrant):
            raise
        raise InvalidContentGrant("shape") from error
    current_time = int(time.time() if now is None else now)
    if (
        claims.version != 1
        or claims.issued_at > current_time + 30
        or claims.expires < current_time
        or claims.expires <= claims.issued_at
        or claims.expires - claims.issued_at > CONTENT_GRANT_MAX_TTL_SECONDS
    ):
        raise InvalidContentGrant("expired")
    try:
        _validate_content_grant_fields(
            resource_kind=claims.resource_kind,
            resource_id=claims.resource_id,
            owner_app_id=claims.owner_app_id,
            issuer_user_id=claims.issuer_user_id,
            issuer_session_id=claims.issuer_session_id,
            execution_context_kind=claims.execution_context_kind,
            route_id=claims.route_id,
            source_type=claims.source_type,
            source_id=claims.source_id,
            object_identity=claims.object_identity,
            resource_version=claims.resource_version,
            disposition=claims.disposition,
            extra=claims.extra,
        )
    except ValueError as error:
        raise InvalidContentGrant("claims") from error
    return claims


def _validate_content_grant_fields(
    *,
    resource_kind: object,
    resource_id: object,
    owner_app_id: object,
    issuer_user_id: object,
    issuer_session_id: object,
    execution_context_kind: object,
    route_id: object,
    source_type: object,
    source_id: object,
    object_identity: object,
    resource_version: object,
    disposition: object,
    extra: object,
) -> None:
    required_strings = (
        resource_kind,
        resource_id,
        owner_app_id,
        issuer_user_id,
        issuer_session_id,
        source_type,
        source_id,
        object_identity,
        resource_version,
    )
    if any(not isinstance(value, str) or not value.strip() for value in required_strings):
        raise ValueError("content grant string claims must be non-empty")
    if execution_context_kind not in {"personal", "company"}:
        raise ValueError("invalid execution context")
    if disposition not in {"attachment", "inline"}:
        raise ValueError("invalid content disposition")
    if route_id is not None:
        if not isinstance(route_id, str) or not route_id.strip():
            raise ValueError("invalid route id")
        route = APP_ROUTE_BY_ID.get(route_id)
        if route is None or route.get("app_id") != owner_app_id:
            raise ValueError("content grant route does not belong to owner app")
    if not isinstance(extra, dict):
        raise ValueError("content grant extra claims must be an object")


def require_matching_issuer(
    claims: ContentGrantClaims,
    *,
    current_user_id: str,
    current_session_id: str,
) -> None:
    """Bind a bearer content capability to the exact authenticated session."""

    if not hmac.compare_digest(claims.issuer_user_id, current_user_id) or not hmac.compare_digest(
        claims.issuer_session_id, current_session_id
    ):
        raise InvalidContentGrant("issuer")


def object_identity(*values: object) -> str:
    encoded = json.dumps(values, default=str, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _encode(claims: ContentGrantClaims) -> str:
    payload = json.dumps(
        asdict(claims),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = _base64url_encode(payload)
    signature = hmac.new(
        get_settings().content_grant_signing_key.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_base64url_encode(signature)}"


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    decoded = base64.b64decode(
        value + "=" * (-len(value) % 4),
        altchars=b"-_",
        validate=True,
    )
    if _base64url_encode(decoded) != value:
        raise binascii.Error("non-canonical base64url")
    return decoded


__all__ = [
    "ContentGrantClaims",
    "CONTENT_GRANT_MAX_TTL_SECONDS",
    "InvalidContentGrant",
    "build_content_grant_url",
    "decode_content_grant",
    "object_identity",
    "require_matching_issuer",
]
