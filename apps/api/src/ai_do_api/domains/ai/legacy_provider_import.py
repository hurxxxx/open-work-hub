from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.core.llm_provider_registry import external_llm_provider_descriptor
from ai_do_api.domains.ai.model_credentials import AiModelCredentialError, encrypt_api_key
from ai_do_api.domains.ai.model_settings_models import (
    AiModelCatalogEntry,
    AiModelProviderConfig,
)
from ai_do_api.domains.auth.models import utcnow_naive
from ai_do_api.domains.auth.security import new_id


_PROVIDER_ENV_FIELDS: dict[str, tuple[str, str, str]] = {
    "openai": (
        "AI_DO_LLM_OPENAI_API_KEY",
        "AI_DO_LLM_OPENAI_BASE_URL",
        "AI_DO_LLM_OPENAI_DEFAULT_MODEL",
    ),
    "anthropic": (
        "AI_DO_LLM_ANTHROPIC_API_KEY",
        "AI_DO_LLM_ANTHROPIC_BASE_URL",
        "AI_DO_LLM_ANTHROPIC_DEFAULT_MODEL",
    ),
    "gemini": (
        "AI_DO_LLM_GEMINI_API_KEY",
        "AI_DO_LLM_GEMINI_BASE_URL",
        "AI_DO_LLM_GEMINI_DEFAULT_MODEL",
    ),
}
LEGACY_EXTERNAL_LLM_ENV_FIELDS = tuple(
    field for fields in _PROVIDER_ENV_FIELDS.values() for field in fields
)


class LegacyProviderImportError(RuntimeError):
    """Stable, non-secret failure raised by the temporary rollout Adapter."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LegacyProviderImportResult:
    mode: Literal["preview", "apply"]
    providers_scanned: int
    providers_eligible: int
    providers_skipped: int
    providers_created: int
    providers_updated: int
    providers_unchanged: int
    endpoints_imported: int
    credentials_imported: int
    defaults_imported: int
    catalog_entries_created: int

    def status_line(self) -> str:
        fields = (
            ("status", "ok"),
            ("mode", self.mode),
            ("providers_scanned", self.providers_scanned),
            ("providers_eligible", self.providers_eligible),
            ("providers_skipped", self.providers_skipped),
            ("providers_created", self.providers_created),
            ("providers_updated", self.providers_updated),
            ("providers_unchanged", self.providers_unchanged),
            ("endpoints_imported", self.endpoints_imported),
            ("credentials_imported", self.credentials_imported),
            ("defaults_imported", self.defaults_imported),
            ("catalog_entries_created", self.catalog_entries_created),
        )
        return " ".join(f"{key}={value}" for key, value in fields)


@dataclass(frozen=True)
class _LegacyProviderEnvironment:
    endpoint_url: str
    default_model: str
    api_key: str = field(repr=False)


@dataclass(frozen=True)
class _ProviderImportPlan:
    provider_id: str
    create_provider: bool
    endpoint_url: str | None
    api_key: str | None = field(repr=False)
    default_model: str | None = None
    existing_catalog_id: str | None = None
    create_catalog: bool = False
    enable_provider: bool = False

    @property
    def changes_provider(self) -> bool:
        return any(
            (
                self.create_provider,
                self.endpoint_url is not None,
                self.api_key is not None,
                self.default_model is not None,
                self.enable_provider,
            )
        )


def _read_provider_environment(
    provider_id: str,
    environment: Mapping[str, str],
) -> _LegacyProviderEnvironment:
    api_key_field, endpoint_field, model_field = _PROVIDER_ENV_FIELDS[provider_id]
    return _LegacyProviderEnvironment(
        api_key=environment.get(api_key_field, "").strip(),
        endpoint_url=environment.get(endpoint_field, "").strip().rstrip("/"),
        default_model=environment.get(model_field, "").strip(),
    )


def _catalog_entry_for_key(
    db: Session,
    *,
    provider_id: str,
    model_key: str,
) -> AiModelCatalogEntry | None:
    return db.scalar(
        select(AiModelCatalogEntry).where(
            AiModelCatalogEntry.provider_id == provider_id,
            AiModelCatalogEntry.model_key == model_key,
        )
    )


def _build_provider_plan(
    db: Session,
    *,
    provider_id: str,
    environment: Mapping[str, str],
) -> _ProviderImportPlan | None:
    provider_environment = _read_provider_environment(provider_id, environment)
    provider = db.get(AiModelProviderConfig, provider_id)
    has_database_credential = bool(provider and provider.api_key_ciphertext)
    if not provider_environment.api_key and not has_database_credential:
        return None

    descriptor = external_llm_provider_descriptor(provider_id)
    if descriptor is None or not descriptor.default_endpoint_url:
        raise LegacyProviderImportError("provider_descriptor_unavailable")

    endpoint_url: str | None = None
    if provider is None or not (provider.endpoint_url or "").strip():
        endpoint_url = provider_environment.endpoint_url or descriptor.default_endpoint_url

    api_key: str | None = None
    if (provider is None or not provider.api_key_ciphertext) and provider_environment.api_key:
        api_key = provider_environment.api_key

    default_model: str | None = None
    existing_catalog_id: str | None = None
    create_catalog = False
    if provider is None or provider.default_model_id is None:
        if provider_environment.default_model:
            catalog = _catalog_entry_for_key(
                db,
                provider_id=provider_id,
                model_key=provider_environment.default_model,
            )
            if catalog is not None and not catalog.enabled:
                raise LegacyProviderImportError("default_model_not_enabled")
            default_model = provider_environment.default_model
            existing_catalog_id = catalog.id if catalog is not None else None
            create_catalog = catalog is None
        elif api_key is not None:
            raise LegacyProviderImportError("default_model_required")

    has_effective_endpoint = bool(
        endpoint_url or (provider is not None and (provider.endpoint_url or "").strip())
    )
    has_effective_credential = bool(api_key or has_database_credential)
    has_effective_default = bool(
        default_model or (provider is not None and provider.default_model_id)
    )
    has_migration_change = any(
        (
            provider is None,
            endpoint_url is not None,
            api_key is not None,
            default_model is not None,
        )
    )
    enable_provider = bool(
        has_migration_change
        and has_effective_endpoint
        and has_effective_credential
        and has_effective_default
        and (provider is None or not provider.enabled)
    )
    return _ProviderImportPlan(
        provider_id=provider_id,
        create_provider=provider is None,
        endpoint_url=endpoint_url,
        api_key=api_key,
        default_model=default_model,
        existing_catalog_id=existing_catalog_id,
        create_catalog=create_catalog,
        enable_provider=enable_provider,
    )


def _apply_provider_plan(db: Session, plan: _ProviderImportPlan) -> None:
    provider = db.get(AiModelProviderConfig, plan.provider_id)
    now = utcnow_naive()
    if provider is None:
        provider = AiModelProviderConfig(
            provider_id=plan.provider_id,
            enabled=False,
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(provider)
        db.flush()

    if plan.endpoint_url is not None:
        provider.endpoint_url = plan.endpoint_url
    if plan.api_key is not None:
        provider.api_key_ciphertext = encrypt_api_key(plan.api_key)
    if plan.default_model is not None:
        catalog_id = plan.existing_catalog_id
        if plan.create_catalog:
            catalog_id = new_id()
            db.add(
                AiModelCatalogEntry(
                    id=catalog_id,
                    provider_id=plan.provider_id,
                    model_key=plan.default_model,
                    display_name=plan.default_model,
                    capabilities_json=["chat"],
                    source="manual",
                    discovery_status="active",
                    enabled=True,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
        provider.default_model_id = catalog_id
    if plan.enable_provider:
        provider.enabled = True
    if not plan.create_provider and plan.changes_provider:
        provider.version += 1
        provider.updated_at = now


def _summarize_plans(
    plans: list[_ProviderImportPlan],
    *,
    apply: bool,
) -> LegacyProviderImportResult:
    changed = [plan for plan in plans if plan.changes_provider]
    return LegacyProviderImportResult(
        mode="apply" if apply else "preview",
        providers_scanned=len(_PROVIDER_ENV_FIELDS),
        providers_eligible=len(plans),
        providers_skipped=len(_PROVIDER_ENV_FIELDS) - len(plans),
        providers_created=sum(plan.create_provider for plan in changed),
        providers_updated=sum(not plan.create_provider for plan in changed),
        providers_unchanged=len(plans) - len(changed),
        endpoints_imported=sum(plan.endpoint_url is not None for plan in plans),
        credentials_imported=sum(plan.api_key is not None for plan in plans),
        defaults_imported=sum(plan.default_model is not None for plan in plans),
        catalog_entries_created=sum(plan.create_catalog for plan in plans),
    )


def import_legacy_external_llm_providers(
    db: Session,
    *,
    environment: Mapping[str, str],
    apply: bool = False,
) -> LegacyProviderImportResult:
    """Preview or atomically import legacy external LLM settings into the DB.

    This temporary Adapter is the only migration path allowed to read the old
    provider environment fields. Preview is the default and never mutates the
    session. Apply is all-or-nothing and never overwrites populated DB fields.
    """

    try:
        with db.begin():
            plans = [
                plan
                for provider_id in _PROVIDER_ENV_FIELDS
                if (
                    plan := _build_provider_plan(
                        db,
                        provider_id=provider_id,
                        environment=environment,
                    )
                )
                is not None
            ]
            result = _summarize_plans(plans, apply=apply)
            if apply:
                for plan in plans:
                    if plan.changes_provider:
                        _apply_provider_plan(db, plan)
                db.flush()
            return result
    except AiModelCredentialError as exc:
        raise LegacyProviderImportError("encryption_unavailable") from exc


__all__ = [
    "LEGACY_EXTERNAL_LLM_ENV_FIELDS",
    "LegacyProviderImportError",
    "LegacyProviderImportResult",
    "import_legacy_external_llm_providers",
]
