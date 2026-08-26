from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from open_work_hub_api.core import llm as llm_core
from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai import gateway as gateway_module
from open_work_hub_api.domains.ai.gateway import LlmWorkloadContext, build_llm_workload_request
from open_work_hub_api.domains.ai.model_credentials import encrypt_api_key
from open_work_hub_api.domains.ai.model_settings_models import (
    AiModelCatalogEntry,
    AiModelProviderConfig,
)
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    get_ai_model_settings_snapshot,
    resolve_ai_model_workload_route,
)


_WORKLOAD_ID = "web_search.answer"
_DB_ENDPOINT = "https://db-anthropic.example.test"
_DB_MODEL_ID = "anthropic-database-selected-model"
_DB_MODEL_KEY = "database-selected-model"
_DB_SECRET = "test-db-anthropic-secret"


def _configure_conflicting_external_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_ANTHROPIC_API_KEY", "test-env-anthropic-secret")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_ANTHROPIC_BASE_URL", "https://env.example.test")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_ANTHROPIC_DEFAULT_MODEL", "env-only-model")
    monkeypatch.setenv("OPEN_WORK_HUB_LLM_ANTHROPIC_CANONICAL_MODEL", "env-only-model")
    get_settings.cache_clear()


def _enable_database_anthropic_provider(db) -> str:
    provider = db.get(AiModelProviderConfig, "anthropic")
    if provider is None:
        provider = AiModelProviderConfig(
            provider_id="anthropic",
            enabled=False,
            version=1,
        )
        db.add(provider)
        db.flush()
    model = db.get(AiModelCatalogEntry, _DB_MODEL_ID)
    if model is None:
        model = AiModelCatalogEntry(
            id=_DB_MODEL_ID,
            provider_id="anthropic",
            model_key=_DB_MODEL_KEY,
            display_name="Database selected model",
            capabilities_json=["chat", "tool_calling", "vision"],
            source="manual",
            discovery_status="active",
            enabled=True,
            version=1,
        )
        db.add(model)

    ciphertext = encrypt_api_key(_DB_SECRET)
    provider.enabled = True
    provider.endpoint_url = _DB_ENDPOINT
    provider.api_key_ciphertext = ciphertext
    provider.default_model_id = model.id
    db.commit()
    return ciphertext


@pytest.mark.parametrize("provider_state", ["missing", "disabled"])
def test_external_workload_fails_closed_without_enabled_database_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    provider_state: str,
) -> None:
    del client
    _configure_conflicting_external_env(monkeypatch)

    with get_session_factory()() as db:
        provider = db.get(AiModelProviderConfig, "anthropic")
        if provider is None:
            provider = AiModelProviderConfig(
                provider_id="anthropic",
                enabled=False,
                version=1,
            )
            db.add(provider)
            db.flush()
        provider.enabled = False
        if provider_state == "missing":
            db.execute(
                delete(AiModelCatalogEntry).where(
                    AiModelCatalogEntry.provider_id == "anthropic"
                )
            )
            db.delete(provider)
        db.commit()

        with pytest.raises(AiModelSettingsError) as caught:
            resolve_ai_model_workload_route(db, workload_id=_WORKLOAD_ID)

    assert caught.value.code == "admin.ai_model_provider_not_ready"
    assert "test-env-anthropic-secret" not in repr(caught.value)
    assert "env-only-model" not in repr(caught.value)


def test_enabled_database_provider_is_the_redacted_external_route_source(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del client
    _configure_conflicting_external_env(monkeypatch)

    with get_session_factory()() as db:
        ciphertext = _enable_database_anthropic_provider(db)

        resolved = resolve_ai_model_workload_route(db, workload_id=_WORKLOAD_ID)
        snapshot = get_ai_model_settings_snapshot(db)

    assert resolved.route == "external"
    assert resolved.provider_id == "anthropic"
    assert resolved.endpoint_url == _DB_ENDPOINT
    assert resolved.model_key == _DB_MODEL_KEY
    assert resolved.model_entry_id == _DB_MODEL_ID
    assert resolved.config_source == "database"
    assert resolved.api_key is not None
    assert resolved.api_key.get_secret_value() == _DB_SECRET
    assert _DB_SECRET not in repr(resolved)
    assert "test-env-anthropic-secret" not in repr(resolved)
    assert "env-only-model" not in repr(resolved)

    serialized = snapshot.model_dump()
    anthropic = next(
        item for item in serialized["providers"] if item["provider_id"] == "anthropic"
    )
    assert anthropic["has_api_key"] is True
    assert set(anthropic).isdisjoint({"api_key", "api_key_ciphertext"})
    serialized_json = snapshot.model_dump_json()
    assert _DB_SECRET not in serialized_json
    assert ciphertext not in serialized_json


def test_build_workload_request_does_not_read_legacy_pool_config_for_database_route(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del client
    _configure_conflicting_external_env(monkeypatch)

    def fail_if_legacy_pool_config_is_read(*_args, **_kwargs):
        pytest.fail("DB-resolved workload routes must not read legacy LLM pool config")

    monkeypatch.setattr(llm_core, "get_pool_config", fail_if_legacy_pool_config_is_read)
    monkeypatch.setattr(
        gateway_module,
        "get_pool_config",
        fail_if_legacy_pool_config_is_read,
        raising=False,
    )

    with get_session_factory()() as db:
        _enable_database_anthropic_provider(db)

        request = build_llm_workload_request(
            _WORKLOAD_ID,
            LlmWorkloadContext(
                source="tests.llm_db_control_plane",
                workspace_id="workspace-1",
                app_id="web-search",
            ),
            db,
            messages=[{"role": "user", "content": "hello"}],
        )

    assert request.workload_route == "external"
    assert request.requested_provider == "anthropic"
    assert request.requested_model == _DB_MODEL_KEY
    assert request.workload_config is not None
    assert request.workload_config.base_url == _DB_ENDPOINT
    assert request.workload_config.api_key == _DB_SECRET
    assert request.workload_config.default_model == _DB_MODEL_KEY
