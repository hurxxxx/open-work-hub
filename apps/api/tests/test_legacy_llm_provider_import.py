from __future__ import annotations

from collections.abc import Iterator
import os

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.legacy_provider_import import (
    LegacyProviderImportError,
    import_legacy_external_llm_providers,
)
from open_work_hub_api.domains.ai.model_credentials import decrypt_api_key, encrypt_api_key
from open_work_hub_api.domains.ai.model_settings_models import (
    AiModelCatalogEntry,
    AiModelProviderConfig,
)


_LEGACY_FIELDS = (
    "OPEN_WORK_HUB_LLM_OPENAI_API_KEY",
    "OPEN_WORK_HUB_LLM_OPENAI_BASE_URL",
    "OPEN_WORK_HUB_LLM_OPENAI_DEFAULT_MODEL",
    "OPEN_WORK_HUB_LLM_ANTHROPIC_API_KEY",
    "OPEN_WORK_HUB_LLM_ANTHROPIC_BASE_URL",
    "OPEN_WORK_HUB_LLM_ANTHROPIC_DEFAULT_MODEL",
    "OPEN_WORK_HUB_LLM_GEMINI_API_KEY",
    "OPEN_WORK_HUB_LLM_GEMINI_BASE_URL",
    "OPEN_WORK_HUB_LLM_GEMINI_DEFAULT_MODEL",
)


def _legacy_environment() -> dict[str, str]:
    return {field: os.environ[field] for field in _LEGACY_FIELDS if field in os.environ}


@pytest.fixture
def db_factory(
    application_postgres_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sessionmaker[Session]]:
    for field in _LEGACY_FIELDS:
        monkeypatch.delenv(field, raising=False)
    engine = create_engine(application_postgres_dsn)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def _remove_provider(factory: sessionmaker[Session], provider_id: str) -> None:
    with factory.begin() as db:
        db.execute(
            delete(AiModelCatalogEntry).where(AiModelCatalogEntry.provider_id == provider_id)
        )
        db.execute(
            delete(AiModelProviderConfig).where(
                AiModelProviderConfig.provider_id == provider_id
            )
        )


def test_preview_reports_changes_without_writing(
    db_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _remove_provider(db_factory, "openai")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_OPENAI_API_KEY", "preview-secret")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_OPENAI_DEFAULT_MODEL", "preview-model")

    with db_factory() as db:
        result = import_legacy_external_llm_providers(
            db,
            environment=_legacy_environment(),
        )

    assert result.mode == "preview"
    assert result.providers_created == 1
    assert result.endpoints_imported == 1
    assert result.credentials_imported == 1
    assert result.defaults_imported == 1
    assert result.catalog_entries_created == 1
    assert "preview-secret" not in result.status_line()
    assert "API_KEY" not in result.status_line()
    with db_factory() as db:
        assert db.get(AiModelProviderConfig, "openai") is None


def test_apply_uses_descriptor_endpoint_and_is_idempotent(
    db_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _remove_provider(db_factory, "openai")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_OPENAI_API_KEY", "apply-secret")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_OPENAI_DEFAULT_MODEL", "imported-chat-model")

    with db_factory() as db:
        first = import_legacy_external_llm_providers(
            db,
            environment=_legacy_environment(),
            apply=True,
        )
    assert first.providers_created == 1
    assert first.catalog_entries_created == 1

    with db_factory() as db:
        provider = db.get(AiModelProviderConfig, "openai")
        assert provider is not None
        assert provider.enabled is True
        assert provider.endpoint_url == "https://api.openai.com/v1"
        assert provider.api_key_ciphertext is not None
        original_ciphertext = provider.api_key_ciphertext
        assert decrypt_api_key(original_ciphertext).get_secret_value() == "apply-secret"
        catalog = db.scalar(
            select(AiModelCatalogEntry).where(
                AiModelCatalogEntry.id == provider.default_model_id
            )
        )
        assert catalog is not None
        assert catalog.model_key == "imported-chat-model"
        assert catalog.capabilities == ("chat",)
        assert catalog.source == "manual"
        assert catalog.discovery_status == "active"
        assert catalog.enabled is True

    with db_factory() as db:
        second = import_legacy_external_llm_providers(
            db,
            environment=_legacy_environment(),
            apply=True,
        )
    assert second.providers_unchanged == 1
    assert second.providers_created == 0
    assert second.providers_updated == 0
    assert second.catalog_entries_created == 0
    with db_factory() as db:
        provider = db.get(AiModelProviderConfig, "openai")
        assert provider is not None
        assert provider.api_key_ciphertext == original_ciphertext


def test_apply_never_overwrites_existing_database_values(
    db_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_ciphertext = encrypt_api_key("database-secret")
    with db_factory.begin() as db:
        provider = db.get(AiModelProviderConfig, "anthropic")
        assert provider is not None
        model = AiModelCatalogEntry(
            id="anthropic-existing-database-model",
            provider_id="anthropic",
            model_key="existing-database-model",
            display_name="Existing database model",
            capabilities_json=["chat"],
            source="manual",
            discovery_status="active",
            enabled=True,
            version=1,
        )
        db.add(model)
        provider.endpoint_url = "https://database.example.test"
        provider.api_key_ciphertext = existing_ciphertext
        provider.default_model_id = model.id
        provider.enabled = False
        original_default_model_id = provider.default_model_id

    monkeypatch.setenv("OPEN_WORK_HUB_LLM_ANTHROPIC_API_KEY", "environment-secret")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_ANTHROPIC_BASE_URL", "https://environment.example.test")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_ANTHROPIC_DEFAULT_MODEL", "environment-model")

    with db_factory() as db:
        result = import_legacy_external_llm_providers(
            db,
            environment=_legacy_environment(),
            apply=True,
        )
    assert result.providers_unchanged == 1

    with db_factory() as db:
        provider = db.get(AiModelProviderConfig, "anthropic")
        assert provider is not None
        assert provider.endpoint_url == "https://database.example.test"
        assert provider.api_key_ciphertext == existing_ciphertext
        assert provider.default_model_id == original_default_model_id
        assert provider.enabled is False


def test_missing_encryption_root_rolls_back_the_transaction(
    db_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _remove_provider(db_factory, "openai")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_OPENAI_API_KEY", "rollback-secret")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_OPENAI_DEFAULT_MODEL", "rollback-model")
    monkeypatch.setenv("OPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        with db_factory() as db:
            with pytest.raises(LegacyProviderImportError) as exc_info:
                import_legacy_external_llm_providers(
                    db,
                    environment=_legacy_environment(),
                    apply=True,
                )
        assert exc_info.value.code == "encryption_unavailable"
    finally:
        get_settings.cache_clear()

    with db_factory() as db:
        assert db.get(AiModelProviderConfig, "openai") is None
        assert db.scalar(
            select(AiModelCatalogEntry).where(
                AiModelCatalogEntry.provider_id == "openai",
                AiModelCatalogEntry.model_key == "rollback-model",
            )
        ) is None
