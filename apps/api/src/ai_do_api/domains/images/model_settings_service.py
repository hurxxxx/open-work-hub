from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import json
import socket
from typing import Any, Mapping
from urllib.parse import urlsplit

from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ai_do_api.core.settings import Settings, get_settings
from ai_do_api.domains.ai.model_credentials import (
    AiModelCredentialError,
    decrypt_api_key,
    encrypt_api_key,
)
from ai_do_api.domains.auth.models import utcnow_naive
from ai_do_api.domains.images.agent_runtime import (
    ensure_builtin_image_agent_runtime_adapters_registered,
    get_image_agent_runtime_adapter_by_id,
)
from ai_do_api.domains.images.model_settings_models import (
    IMAGE_MODEL_PROFILE_ID,
    ImageModelProfile,
    ImageModelProviderConfig,
)
from ai_do_api.domains.images.model_settings_schemas import (
    ImageModelProfileResponse,
    ImageModelProfileUpdateRequest,
    ImageModelProviderResponse,
    ImageModelProviderUpdateRequest,
    ImageModelSettingsResponse,
)
from ai_do_api.domains.images.provider_registry import (
    ImageProviderDescriptor,
    ensure_builtin_image_providers_registered,
    image_provider_descriptor,
    image_provider_descriptors,
    normalize_image_provider_id,
)


IMAGE_PROVIDER_CREDENTIAL_REF_PREFIX = "image-provider:"
IMAGE_EXECUTION_PROFILE_VERSION = "image_execution_profile.v2"


@dataclass(frozen=True)
class ResolvedImageExecution:
    provider_id: str
    adapter_id: str
    route_mode: str
    endpoint_url: str
    api_key: SecretStr | None
    supervisor_model_id: str
    generation_model_id: str
    brief_web_search_enabled: bool
    generation_web_search_enabled: bool
    max_iterations: int


class ImageModelSettingsError(RuntimeError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.context = context or {}


def image_model_registry_digest() -> str:
    ensure_builtin_image_providers_registered()
    payload = [asdict(item) for item in image_provider_descriptors()]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assert_image_model_registry_digest(expected: str) -> str:
    actual = image_model_registry_digest()
    if expected != actual:
        raise ImageModelSettingsError(
            status_code=409,
            code="admin.image_model_registry_changed",
            context={"registry_digest": actual},
        )
    return actual


def get_image_model_settings_snapshot(
    db: Session,
    *,
    settings: Settings | None = None,
) -> ImageModelSettingsResponse:
    ensure_builtin_image_agent_runtime_adapters_registered()
    resolved_settings = settings or get_settings()
    profile = _require_profile(db)
    rows = {
        row.provider_id: row
        for row in db.scalars(select(ImageModelProviderConfig)).all()
    }
    providers = [
        _serialize_provider(descriptor, rows.get(descriptor.provider_id), resolved_settings)
        for descriptor in image_provider_descriptors()
    ]
    profile_response = _serialize_profile(profile)
    readiness_code = _overall_readiness_code(
        providers,
        active_provider_id=profile.active_provider_id,
        deployment_enabled=resolved_settings.image_enabled,
    )
    return ImageModelSettingsResponse(
        registry_digest=image_model_registry_digest(),
        deployment_enabled=resolved_settings.image_enabled,
        ready=readiness_code is None,
        readiness_code=readiness_code,
        providers=providers,
        profile=profile_response,
    )


def update_image_model_provider(
    db: Session,
    *,
    provider_id: str,
    payload: ImageModelProviderUpdateRequest,
    actor_user_id: str,
    settings: Settings | None = None,
) -> None:
    assert_image_model_registry_digest(payload.expected_registry_digest)
    ensure_builtin_image_agent_runtime_adapters_registered()
    normalized_provider_id = normalize_image_provider_id(provider_id)
    descriptor = image_provider_descriptor(normalized_provider_id)
    if descriptor is None:
        raise ImageModelSettingsError(
            status_code=404,
            code="admin.image_model_provider_not_found",
            context={"provider_id": normalized_provider_id},
        )

    if payload.endpoint_url is not None:
        _validate_endpoint_url(payload.endpoint_url, descriptor=descriptor)

    row = db.get(ImageModelProviderConfig, normalized_provider_id)
    if row is None:
        if payload.expected_version != 0:
            _raise_version_conflict()
        current_ciphertext = None
        current_version = 0
    else:
        if payload.expected_version != row.version:
            _raise_version_conflict()
        current_ciphertext = row.api_key_ciphertext
        current_version = row.version

    encrypted_api_key = current_ciphertext
    if payload.api_key is not None:
        if descriptor.credential_kind == "none":
            raise ImageModelSettingsError(
                status_code=422,
                code="admin.image_model_key_not_allowed",
                context={"provider_id": normalized_provider_id},
            )
        try:
            encrypted_api_key = encrypt_api_key(payload.api_key)
        except AiModelCredentialError as exc:
            raise ImageModelSettingsError(
                status_code=503,
                code="admin.image_model_credential_encryption_unavailable",
            ) from exc
    elif payload.clear_api_key:
        encrypted_api_key = None

    candidate = ImageModelProviderConfig(
        provider_id=normalized_provider_id,
        endpoint_url=payload.endpoint_url,
        api_key_ciphertext=encrypted_api_key,
        supervisor_model_id=payload.supervisor_model_id,
        generation_model_id=payload.generation_model_id,
        enabled=payload.enabled,
        version=max(1, current_version + 1),
        updated_by=actor_user_id,
    )
    if payload.enabled:
        readiness_code = _provider_readiness_code(
            descriptor,
            candidate,
            settings or get_settings(),
        )
        if readiness_code is not None:
            raise ImageModelSettingsError(
                status_code=422,
                code=f"admin.image_model_{readiness_code}",
                context={"provider_id": normalized_provider_id},
            )

    now = utcnow_naive()
    if row is None:
        candidate.created_at = now
        candidate.updated_at = now
        db.add(candidate)
        db.flush()
        return

    result = db.execute(
        update(ImageModelProviderConfig)
        .where(
            ImageModelProviderConfig.provider_id == normalized_provider_id,
            ImageModelProviderConfig.version == current_version,
        )
        .values(
            endpoint_url=payload.endpoint_url,
            api_key_ciphertext=encrypted_api_key,
            supervisor_model_id=payload.supervisor_model_id,
            generation_model_id=payload.generation_model_id,
            enabled=payload.enabled,
            version=current_version + 1,
            updated_by=actor_user_id,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        _raise_version_conflict()


def update_image_model_profile(
    db: Session,
    *,
    payload: ImageModelProfileUpdateRequest,
    actor_user_id: str,
) -> None:
    assert_image_model_registry_digest(payload.expected_registry_digest)
    profile = _require_profile(db)
    if payload.expected_version != profile.version:
        _raise_version_conflict()
    if payload.active_provider_id is not None:
        provider_id = normalize_image_provider_id(payload.active_provider_id)
        if image_provider_descriptor(provider_id) is None:
            raise ImageModelSettingsError(
                status_code=404,
                code="admin.image_model_provider_not_found",
                context={"provider_id": provider_id},
            )
        if db.get(ImageModelProviderConfig, provider_id) is None:
            raise ImageModelSettingsError(
                status_code=422,
                code="admin.image_model_provider_not_configured",
                context={"provider_id": provider_id},
            )

    now = utcnow_naive()
    result = db.execute(
        update(ImageModelProfile)
        .where(
            ImageModelProfile.profile_id == IMAGE_MODEL_PROFILE_ID,
            ImageModelProfile.version == profile.version,
        )
        .values(
            active_provider_id=payload.active_provider_id,
            brief_web_search_enabled=payload.brief_web_search_enabled,
            generation_web_search_enabled=payload.generation_web_search_enabled,
            max_iterations=payload.max_iterations,
            version=profile.version + 1,
            updated_by=actor_user_id,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        _raise_version_conflict()


def resolve_active_image_execution(
    db: Session,
    *,
    settings: Settings | None = None,
) -> ResolvedImageExecution:
    profile = _require_profile(db)
    if not profile.active_provider_id:
        raise ImageModelSettingsError(
            status_code=503,
            code="admin.image_model_active_provider_required",
        )
    return _resolve_provider_execution(
        db,
        provider_id=profile.active_provider_id,
        profile=profile,
        settings=settings or get_settings(),
    )


def resolve_profiled_image_execution(
    db: Session,
    execution_profile: Mapping[str, Any] | None,
    *,
    settings: Settings | None = None,
) -> ResolvedImageExecution:
    raw_profile = dict(execution_profile) if isinstance(execution_profile, Mapping) else {}
    if raw_profile.get("version") != IMAGE_EXECUTION_PROFILE_VERSION:
        _raise_execution_profile_invalid()

    current_profile = _require_profile(db)
    active_provider_id = normalize_image_provider_id(current_profile.active_provider_id)
    if not active_provider_id:
        raise ImageModelSettingsError(
            status_code=503,
            code="admin.image_model_active_provider_required",
        )
    provider_id = normalize_image_provider_id(str(raw_profile.get("provider_id") or ""))
    if provider_id != active_provider_id:
        _raise_execution_profile_invalid()

    resolved = _resolve_provider_execution(
        db,
        provider_id=provider_id,
        profile=current_profile,
        settings=settings or get_settings(),
    )

    credential_ref = str(raw_profile.get("credential_ref") or "").strip()
    expected_ref = image_provider_credential_ref(provider_id)
    if credential_ref != expected_ref:
        raise ImageModelSettingsError(
            status_code=503,
            code="admin.image_model_credential_reference_invalid",
        )

    adapter_id = str(raw_profile.get("adapter_id") or "").strip().lower()
    if adapter_id != resolved.adapter_id:
        _raise_execution_profile_invalid()
    adapter = get_image_agent_runtime_adapter_by_id(adapter_id)
    if adapter is None or normalize_image_provider_id(adapter.provider_id) != provider_id:
        raise ImageModelSettingsError(
            status_code=503,
            code="admin.image_model_adapter_not_registered",
            context={"provider_id": provider_id},
        )
    requested_options = raw_profile.get("requested_options")
    options = dict(requested_options) if isinstance(requested_options, Mapping) else {}
    return ResolvedImageExecution(
        provider_id=resolved.provider_id,
        adapter_id=adapter_id,
        route_mode=resolved.route_mode,
        endpoint_url=resolved.endpoint_url,
        api_key=resolved.api_key,
        supervisor_model_id=resolved.supervisor_model_id,
        generation_model_id=resolved.generation_model_id,
        brief_web_search_enabled=resolved.brief_web_search_enabled,
        generation_web_search_enabled=_profile_bool(
            options.get("web_search_enabled"),
            default=resolved.generation_web_search_enabled,
        ),
        max_iterations=_profile_int(
            options.get("max_iterations"),
            default=resolved.max_iterations,
            minimum=1,
            maximum=20,
        ),
    )


def image_provider_credential_ref(provider_id: str) -> str:
    return f"{IMAGE_PROVIDER_CREDENTIAL_REF_PREFIX}{normalize_image_provider_id(provider_id)}"


def _resolve_provider_execution(
    db: Session,
    *,
    provider_id: str,
    profile: ImageModelProfile,
    settings: Settings,
) -> ResolvedImageExecution:
    ensure_builtin_image_agent_runtime_adapters_registered()
    descriptor = image_provider_descriptor(provider_id)
    row = db.get(ImageModelProviderConfig, provider_id)
    readiness_code = (
        "provider_not_registered"
        if descriptor is None
        else _provider_readiness_code(descriptor, row, settings)
    )
    if readiness_code is not None or descriptor is None or row is None:
        raise ImageModelSettingsError(
            status_code=503,
            code=f"admin.image_model_{readiness_code or 'provider_not_configured'}",
            context={"provider_id": provider_id},
        )
    endpoint_url = _effective_endpoint_url(descriptor, row)
    api_key: SecretStr | None = None
    if descriptor.credential_kind == "api_key":
        try:
            api_key = decrypt_api_key(row.api_key_ciphertext or "")
        except AiModelCredentialError as exc:
            raise ImageModelSettingsError(
                status_code=503,
                code="admin.image_model_credential_encryption_unavailable",
            ) from exc
    return ResolvedImageExecution(
        provider_id=provider_id,
        adapter_id=descriptor.adapter_id,
        route_mode=descriptor.route_mode,
        endpoint_url=endpoint_url,
        api_key=api_key,
        supervisor_model_id=(row.supervisor_model_id or "").strip(),
        generation_model_id=(row.generation_model_id or "").strip(),
        brief_web_search_enabled=profile.brief_web_search_enabled,
        generation_web_search_enabled=profile.generation_web_search_enabled,
        max_iterations=profile.max_iterations,
    )


def _serialize_provider(
    descriptor: ImageProviderDescriptor,
    row: ImageModelProviderConfig | None,
    settings: Settings,
) -> ImageModelProviderResponse:
    endpoint_url = _effective_endpoint_url(descriptor, row)
    readiness_code = _provider_readiness_code(descriptor, row, settings)
    return ImageModelProviderResponse(
        provider_id=descriptor.provider_id,
        display_name=descriptor.display_name,
        route_mode=descriptor.route_mode,
        credential_kind=descriptor.credential_kind,
        enabled=bool(row and row.enabled),
        endpoint_url=endpoint_url or None,
        endpoint_source="custom" if row and row.endpoint_url else "default",
        has_api_key=bool(row and row.api_key_ciphertext),
        supervisor_model_id=row.supervisor_model_id if row else None,
        generation_model_id=row.generation_model_id if row else None,
        ready=readiness_code is None,
        readiness_code=readiness_code,
        version=row.version if row else 0,
        updated_at=row.updated_at if row else None,
    )


def _serialize_profile(profile: ImageModelProfile) -> ImageModelProfileResponse:
    return ImageModelProfileResponse(
        active_provider_id=profile.active_provider_id,
        brief_web_search_enabled=profile.brief_web_search_enabled,
        generation_web_search_enabled=profile.generation_web_search_enabled,
        max_iterations=profile.max_iterations,
        version=profile.version,
        updated_at=profile.updated_at,
    )


def _provider_readiness_code(
    descriptor: ImageProviderDescriptor,
    row: ImageModelProviderConfig | None,
    settings: Settings,
) -> str | None:
    if row is None:
        return "provider_not_configured"
    if not row.enabled:
        return "provider_disabled"
    adapter = get_image_agent_runtime_adapter_by_id(descriptor.adapter_id)
    if adapter is None or normalize_image_provider_id(adapter.provider_id) != descriptor.provider_id:
        return "adapter_not_registered"
    endpoint_url = _effective_endpoint_url(descriptor, row)
    if descriptor.route_mode == "external" and not endpoint_url:
        return "endpoint_required"
    if descriptor.credential_kind == "api_key" and not row.api_key_ciphertext:
        return "credential_required"
    if not (row.supervisor_model_id or "").strip():
        return "supervisor_model_required"
    if not (row.generation_model_id or "").strip():
        return "generation_model_required"
    if (
        descriptor.route_mode == "external"
        and descriptor.provider_id not in _allowed_external_provider_ids(settings)
    ):
        return "provider_not_allowed"
    return None


def _overall_readiness_code(
    providers: list[ImageModelProviderResponse],
    *,
    active_provider_id: str | None,
    deployment_enabled: bool,
) -> str | None:
    if not deployment_enabled:
        return "feature_disabled"
    if not active_provider_id:
        return "active_provider_required"
    active = next(
        (provider for provider in providers if provider.provider_id == active_provider_id),
        None,
    )
    if active is None:
        return "provider_not_registered"
    return active.readiness_code


def _require_profile(db: Session) -> ImageModelProfile:
    profile = db.get(ImageModelProfile, IMAGE_MODEL_PROFILE_ID)
    if profile is None:
        raise ImageModelSettingsError(
            status_code=503,
            code="admin.image_model_profile_unavailable",
        )
    return profile


def _effective_endpoint_url(
    descriptor: ImageProviderDescriptor,
    row: ImageModelProviderConfig | None,
) -> str:
    return str((row.endpoint_url if row else None) or descriptor.default_endpoint_url or "").strip()


def _allowed_external_provider_ids(settings: Settings) -> set[str]:
    return {
        normalize_image_provider_id(provider)
        for provider in str(settings.ai_allowed_external_providers or "").split(",")
        if normalize_image_provider_id(provider)
    }


def _validate_endpoint_url(
    endpoint_url: str,
    *,
    descriptor: ImageProviderDescriptor,
) -> None:
    parsed = urlsplit(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ImageModelSettingsError(
            status_code=422,
            code="admin.image_model_endpoint_invalid",
        )
    if parsed.username or parsed.password:
        raise ImageModelSettingsError(
            status_code=422,
            code="admin.image_model_endpoint_invalid",
        )
    if descriptor.route_mode == "local":
        return
    if parsed.scheme != "https" or parsed.port not in {None, 443} or not parsed.hostname:
        raise ImageModelSettingsError(
            status_code=422,
            code="admin.image_model_endpoint_public_https_required",
        )
    try:
        addresses = {
            ipaddress.ip_address(sockaddr[0])
            for _family, _type, _proto, _canonname, sockaddr in socket.getaddrinfo(
                parsed.hostname,
                443,
                type=socket.SOCK_STREAM,
            )
        }
    except (socket.gaierror, ValueError) as exc:
        raise ImageModelSettingsError(
            status_code=422,
            code="admin.image_model_endpoint_unresolvable",
        ) from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ImageModelSettingsError(
            status_code=422,
            code="admin.image_model_endpoint_public_https_required",
        )


def _raise_version_conflict() -> None:
    raise ImageModelSettingsError(
        status_code=409,
        code="admin.image_model_version_conflict",
    )


def _raise_execution_profile_invalid() -> None:
    raise ImageModelSettingsError(
        status_code=503,
        code="admin.image_model_execution_profile_invalid",
    )


def _profile_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _profile_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


__all__ = [
    "IMAGE_EXECUTION_PROFILE_VERSION",
    "IMAGE_PROVIDER_CREDENTIAL_REF_PREFIX",
    "ImageModelSettingsError",
    "ResolvedImageExecution",
    "assert_image_model_registry_digest",
    "get_image_model_settings_snapshot",
    "image_model_registry_digest",
    "image_provider_credential_ref",
    "resolve_active_image_execution",
    "resolve_profiled_image_execution",
    "update_image_model_profile",
    "update_image_model_provider",
]
