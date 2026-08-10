from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Literal, Mapping

from sqlalchemy.orm import Session

from ai_do_api.domains.ai.model_credentials import AiModelCredentialError, encrypt_api_key
from ai_do_api.domains.auth.models import utcnow_naive
from ai_do_api.domains.images.model_settings_models import (
    IMAGE_MODEL_PROFILE_ID,
    ImageModelProfile,
    ImageModelProviderConfig,
)
from ai_do_api.domains.images.provider_registry import (
    ensure_builtin_image_providers_registered,
    image_provider_descriptor,
    normalize_image_provider_id,
)


class LegacyImageModelImportError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


LEGACY_IMAGE_ENV_FIELDS = (
    "AI_DO_IMAGE_PROVIDER",
    "AI_DO_IMAGE_API_KEY",
    "AI_DO_IMAGE_OPENAI_API_KEY",
    "AI_DO_IMAGE_PROVIDER_API_KEYS",
    "AI_DO_IMAGE_BASE_URL",
    "AI_DO_IMAGE_MODEL",
    "AI_DO_IMAGE_SUPERVISOR_MODEL",
    "AI_DO_IMAGE_BRIEF_WEB_SEARCH_ENABLED",
    "AI_DO_IMAGE_AGENT_WEB_SEARCH_ENABLED",
    "AI_DO_IMAGE_AGENT_MAX_ITER",
)


@dataclass(frozen=True)
class LegacyImageModelImportResult:
    mode: Literal["preview", "apply"]
    provider_eligible: bool
    provider_created: bool
    provider_updated: bool
    provider_unchanged: bool
    endpoint_imported: bool
    credential_imported: bool
    supervisor_model_imported: bool
    generation_model_imported: bool
    profile_updated: bool

    def status_line(self) -> str:
        fields = (
            ("status", "ok"),
            ("mode", self.mode),
            ("provider_eligible", int(self.provider_eligible)),
            ("provider_created", int(self.provider_created)),
            ("provider_updated", int(self.provider_updated)),
            ("provider_unchanged", int(self.provider_unchanged)),
            ("endpoint_imported", int(self.endpoint_imported)),
            ("credential_imported", int(self.credential_imported)),
            ("supervisor_model_imported", int(self.supervisor_model_imported)),
            ("generation_model_imported", int(self.generation_model_imported)),
            ("profile_updated", int(self.profile_updated)),
        )
        return " ".join(f"{key}={value}" for key, value in fields)


@dataclass(frozen=True)
class _LegacyImageEnvironment:
    provider_id: str
    endpoint_url: str
    supervisor_model_id: str
    generation_model_id: str
    api_key: str = field(repr=False)
    brief_web_search_enabled: bool = True
    generation_web_search_enabled: bool = True
    max_iterations: int = 10


@dataclass(frozen=True)
class _ImageImportPlan:
    provider_id: str
    create_provider: bool
    endpoint_url: str | None
    api_key: str | None = field(repr=False)
    supervisor_model_id: str | None = None
    generation_model_id: str | None = None
    enable_provider: bool = False
    update_profile: bool = False
    brief_web_search_enabled: bool = True
    generation_web_search_enabled: bool = True
    max_iterations: int = 10

    @property
    def changes_provider(self) -> bool:
        return any(
            (
                self.create_provider,
                self.endpoint_url is not None,
                self.api_key is not None,
                self.supervisor_model_id is not None,
                self.generation_model_id is not None,
                self.enable_provider,
            )
        )


def _read_environment(environment: Mapping[str, str]) -> _LegacyImageEnvironment | None:
    if not any(field in environment for field in LEGACY_IMAGE_ENV_FIELDS):
        return None

    provider_id = (
        normalize_image_provider_id(environment.get("AI_DO_IMAGE_PROVIDER")) or "openai"
    )
    provider_keys = _provider_api_keys(environment)
    provider_specific_field = (
        "AI_DO_IMAGE_"
        + "".join(char if char.isalnum() else "_" for char in provider_id.upper())
        + "_API_KEY"
    )
    api_key = (
        environment.get(provider_specific_field, "").strip()
        or provider_keys.get(provider_id, "")
        or environment.get("AI_DO_IMAGE_API_KEY", "").strip()
    )
    return _LegacyImageEnvironment(
        provider_id=provider_id,
        endpoint_url=environment.get("AI_DO_IMAGE_BASE_URL", "").strip().rstrip("/"),
        supervisor_model_id=environment.get("AI_DO_IMAGE_SUPERVISOR_MODEL", "").strip(),
        generation_model_id=environment.get("AI_DO_IMAGE_MODEL", "").strip(),
        api_key=api_key,
        brief_web_search_enabled=_env_bool(
            environment,
            "AI_DO_IMAGE_BRIEF_WEB_SEARCH_ENABLED",
            default=True,
        ),
        generation_web_search_enabled=_env_bool(
            environment,
            "AI_DO_IMAGE_AGENT_WEB_SEARCH_ENABLED",
            default=True,
        ),
        max_iterations=_env_int(
            environment,
            "AI_DO_IMAGE_AGENT_MAX_ITER",
            default=10,
            minimum=1,
            maximum=20,
        ),
    )


def _provider_api_keys(environment: Mapping[str, str]) -> dict[str, str]:
    raw = environment.get("AI_DO_IMAGE_PROVIDER_API_KEYS", "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LegacyImageModelImportError("provider_api_keys_invalid") from exc
    if not isinstance(value, dict):
        raise LegacyImageModelImportError("provider_api_keys_invalid")
    return {
        normalize_image_provider_id(str(provider)): str(api_key or "").strip()
        for provider, api_key in value.items()
        if normalize_image_provider_id(str(provider)) and str(api_key or "").strip()
    }


def _build_plan(
    db: Session,
    environment_values: Mapping[str, str],
) -> _ImageImportPlan | None:
    environment = _read_environment(environment_values)
    if environment is None:
        return None
    ensure_builtin_image_providers_registered()
    descriptor = image_provider_descriptor(environment.provider_id)
    if descriptor is None:
        raise LegacyImageModelImportError("provider_descriptor_unavailable")

    row = db.get(ImageModelProviderConfig, environment.provider_id)
    endpoint_url = None
    if row is None or not (row.endpoint_url or "").strip():
        endpoint_url = environment.endpoint_url or descriptor.default_endpoint_url
    api_key = None
    if descriptor.credential_kind == "api_key" and (
        row is None or not row.api_key_ciphertext
    ):
        api_key = environment.api_key or None
    supervisor_model_id = None
    if row is None or not (row.supervisor_model_id or "").strip():
        supervisor_model_id = environment.supervisor_model_id or None
    generation_model_id = None
    if row is None or not (row.generation_model_id or "").strip():
        generation_model_id = environment.generation_model_id or None

    effective_credential = descriptor.credential_kind == "none" or bool(
        api_key or (row and row.api_key_ciphertext)
    )
    effective_endpoint = descriptor.route_mode == "local" or bool(
        endpoint_url or (row and row.endpoint_url) or descriptor.default_endpoint_url
    )
    effective_supervisor = bool(supervisor_model_id or (row and row.supervisor_model_id))
    effective_generation = bool(generation_model_id or (row and row.generation_model_id))
    if not effective_credential:
        raise LegacyImageModelImportError("credential_required")
    if not effective_endpoint:
        raise LegacyImageModelImportError("endpoint_required")
    if not effective_supervisor:
        raise LegacyImageModelImportError("supervisor_model_required")
    if not effective_generation:
        raise LegacyImageModelImportError("generation_model_required")

    profile = db.get(ImageModelProfile, IMAGE_MODEL_PROFILE_ID)
    if profile is None:
        raise LegacyImageModelImportError("profile_unavailable")
    update_profile = profile.active_provider_id is None
    return _ImageImportPlan(
        provider_id=environment.provider_id,
        create_provider=row is None,
        endpoint_url=endpoint_url,
        api_key=api_key,
        supervisor_model_id=supervisor_model_id,
        generation_model_id=generation_model_id,
        enable_provider=row is None or not row.enabled,
        update_profile=update_profile,
        brief_web_search_enabled=environment.brief_web_search_enabled,
        generation_web_search_enabled=environment.generation_web_search_enabled,
        max_iterations=environment.max_iterations,
    )


def _apply_plan(db: Session, plan: _ImageImportPlan) -> None:
    now = utcnow_naive()
    row = db.get(ImageModelProviderConfig, plan.provider_id)
    if row is None:
        row = ImageModelProviderConfig(
            provider_id=plan.provider_id,
            enabled=False,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
    if plan.endpoint_url is not None:
        row.endpoint_url = plan.endpoint_url
    if plan.api_key is not None:
        row.api_key_ciphertext = encrypt_api_key(plan.api_key)
    if plan.supervisor_model_id is not None:
        row.supervisor_model_id = plan.supervisor_model_id
    if plan.generation_model_id is not None:
        row.generation_model_id = plan.generation_model_id
    if plan.enable_provider:
        row.enabled = True
    if not plan.create_provider and plan.changes_provider:
        row.version += 1
        row.updated_at = now

    if plan.update_profile:
        profile = db.get(ImageModelProfile, IMAGE_MODEL_PROFILE_ID)
        if profile is None:
            raise LegacyImageModelImportError("profile_unavailable")
        profile.active_provider_id = plan.provider_id
        profile.brief_web_search_enabled = plan.brief_web_search_enabled
        profile.generation_web_search_enabled = plan.generation_web_search_enabled
        profile.max_iterations = plan.max_iterations
        profile.version += 1
        profile.updated_at = now


def import_legacy_image_model_settings(
    db: Session,
    *,
    environment: Mapping[str, str],
    apply: bool = False,
) -> LegacyImageModelImportResult:
    """Preview or atomically import legacy image provider environment settings."""

    try:
        with db.begin():
            plan = _build_plan(db, environment)
            if plan is None:
                return LegacyImageModelImportResult(
                    mode="apply" if apply else "preview",
                    provider_eligible=False,
                    provider_created=False,
                    provider_updated=False,
                    provider_unchanged=False,
                    endpoint_imported=False,
                    credential_imported=False,
                    supervisor_model_imported=False,
                    generation_model_imported=False,
                    profile_updated=False,
                )
            if apply and (plan.changes_provider or plan.update_profile):
                _apply_plan(db, plan)
                db.flush()
            return LegacyImageModelImportResult(
                mode="apply" if apply else "preview",
                provider_eligible=True,
                provider_created=plan.create_provider and plan.changes_provider,
                provider_updated=not plan.create_provider and plan.changes_provider,
                provider_unchanged=not plan.changes_provider,
                endpoint_imported=plan.endpoint_url is not None,
                credential_imported=plan.api_key is not None,
                supervisor_model_imported=plan.supervisor_model_id is not None,
                generation_model_imported=plan.generation_model_id is not None,
                profile_updated=plan.update_profile,
            )
    except AiModelCredentialError as exc:
        raise LegacyImageModelImportError("encryption_unavailable") from exc


def _env_bool(
    environment: Mapping[str, str],
    field: str,
    *,
    default: bool,
) -> bool:
    raw = environment.get(field)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise LegacyImageModelImportError("boolean_value_invalid")


def _env_int(
    environment: Mapping[str, str],
    field: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = environment.get(field)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise LegacyImageModelImportError("integer_value_invalid") from exc
    if not minimum <= value <= maximum:
        raise LegacyImageModelImportError("integer_value_invalid")
    return value


__all__ = [
    "LEGACY_IMAGE_ENV_FIELDS",
    "LegacyImageModelImportError",
    "LegacyImageModelImportResult",
    "import_legacy_image_model_settings",
]
