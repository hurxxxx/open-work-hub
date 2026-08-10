from __future__ import annotations

import os

from fastapi.testclient import TestClient
import pytest

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.images.cutover import (
    ImageModelCutoverError,
    check_image_model_cutover,
)
from ai_do_api.domains.images.legacy_model_settings_import import (
    import_legacy_image_model_settings,
)
from ai_do_api.domains.images.model_settings_models import (
    IMAGE_MODEL_PROFILE_ID,
    ImageModelProfile,
    ImageModelProviderConfig,
)
from ai_do_api.domains.images.model_settings_service import (
    IMAGE_EXECUTION_PROFILE_VERSION,
    ImageModelSettingsError,
    resolve_profiled_image_execution,
)
from tests.dev_accounts import auth_headers, dev_login


LEGACY_IMAGE_ENV_KEYS = (
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


def _legacy_image_environment() -> dict[str, str]:
    return {
        field: os.environ[field]
        for field in LEGACY_IMAGE_ENV_KEYS
        if field in os.environ
    }


def _execution_profile(**overrides: object) -> dict[str, object]:
    profile: dict[str, object] = {
        "version": IMAGE_EXECUTION_PROFILE_VERSION,
        "provider_id": "openai",
        "adapter_id": "openai",
        "credential_ref": "image-provider:openai",
        "supervisor_model_id": "untrusted-stale-supervisor",
        "generation_model_id": "untrusted-stale-generation",
        "requested_options": {"web_search_enabled": False, "max_iterations": 3},
    }
    profile.update(overrides)
    return profile


def _admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(dev_login(client)["token"])


def test_admin_image_model_settings_are_separate_and_secret_free(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_DO_IMAGE_ENABLED", "1")
    monkeypatch.setenv("AI_DO_AI_ALLOWED_EXTERNAL_PROVIDERS", "openai")
    get_settings.cache_clear()
    headers = _admin_headers(client)

    initial_response = client.get(
        "/api/v1/admin/image-model-settings",
        headers=headers,
    )
    assert initial_response.status_code == 200, initial_response.text
    initial = initial_response.json()
    assert initial["deployment_enabled"] is True
    assert initial["ready"] is False
    assert initial["readiness_code"] == "active_provider_required"
    assert [provider["provider_id"] for provider in initial["providers"]] == ["openai"]
    provider = initial["providers"][0]
    assert provider["supervisor_model_id"] is None
    assert provider["generation_model_id"] is None

    with get_session_factory()() as db:
        jobs_only = check_image_model_cutover(
            db,
            jobs_only=True,
            queue_length=lambda: 0,
        )
        assert jobs_only.ready is False
        with pytest.raises(ImageModelCutoverError) as readiness_error:
            check_image_model_cutover(db, queue_length=lambda: 0)
        assert readiness_error.value.code == "active_provider_required"

    provider_response = client.put(
        "/api/v1/admin/image-model-settings/providers/openai",
        headers=headers,
        json={
            "expected_registry_digest": initial["registry_digest"],
            "expected_version": 0,
            "enabled": True,
            "endpoint_url": None,
            "supervisor_model_id": "supervisor-explicit",
            "generation_model_id": "image-explicit",
            "api_key": "image-secret-value",
        },
    )
    assert provider_response.status_code == 200, provider_response.text
    provider_payload = provider_response.json()
    assert "image-secret-value" not in provider_response.text
    assert "api_key_ciphertext" not in provider_response.text
    configured = provider_payload["providers"][0]
    assert configured["has_api_key"] is True
    assert configured["supervisor_model_id"] == "supervisor-explicit"
    assert configured["generation_model_id"] == "image-explicit"

    profile_response = client.put(
        "/api/v1/admin/image-model-settings/profile",
        headers=headers,
        json={
            "expected_registry_digest": initial["registry_digest"],
            "expected_version": provider_payload["profile"]["version"],
            "active_provider_id": "openai",
            "brief_web_search_enabled": False,
            "generation_web_search_enabled": True,
            "max_iterations": 7,
        },
    )
    assert profile_response.status_code == 200, profile_response.text
    result = profile_response.json()
    assert result["ready"] is True
    assert result["profile"]["active_provider_id"] == "openai"
    assert result["profile"]["brief_web_search_enabled"] is False
    assert result["profile"]["generation_web_search_enabled"] is True
    assert result["profile"]["max_iterations"] == 7

    with get_session_factory()() as db:
        cutover = check_image_model_cutover(db, queue_length=lambda: 0)
        assert cutover.ready is True
        assert cutover.broker_queue_count == 0
        assert cutover.active_job_count == 0
        with pytest.raises(ImageModelCutoverError) as queue_error:
            check_image_model_cutover(db, jobs_only=True, queue_length=lambda: 1)
        assert queue_error.value.code == "broker_queue_not_empty"

        row = db.get(ImageModelProviderConfig, "openai")
        assert row is not None
        assert row.api_key_ciphertext
        assert row.api_key_ciphertext != "image-secret-value"

        resolved = resolve_profiled_image_execution(db, _execution_profile())
        assert resolved.supervisor_model_id == "supervisor-explicit"
        assert resolved.generation_model_id == "image-explicit"
        assert resolved.generation_web_search_enabled is False
        assert resolved.max_iterations == 3

        with pytest.raises(ImageModelSettingsError) as version_error:
            resolve_profiled_image_execution(
                db,
                _execution_profile(version="image_execution_profile.v1"),
            )
        assert version_error.value.code == "admin.image_model_execution_profile_invalid"

        with pytest.raises(ImageModelSettingsError) as credential_error:
            resolve_profiled_image_execution(db, _execution_profile(credential_ref=""))
        assert (
            credential_error.value.code
            == "admin.image_model_credential_reference_invalid"
        )


def test_legacy_image_settings_import_is_preview_first_and_idempotent(
    client: TestClient,
    monkeypatch,
) -> None:
    del client
    for key in LEGACY_IMAGE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_DO_IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("AI_DO_IMAGE_API_KEY", "legacy-image-secret")
    monkeypatch.setenv("AI_DO_IMAGE_MODEL", "legacy-image-model")
    monkeypatch.setenv("AI_DO_IMAGE_SUPERVISOR_MODEL", "legacy-supervisor-model")
    monkeypatch.setenv("AI_DO_IMAGE_AGENT_MAX_ITER", "6")

    with get_session_factory()() as db:
        preview = import_legacy_image_model_settings(
            db,
            environment=_legacy_image_environment(),
        )
        assert preview.mode == "preview"
        assert preview.provider_created is True
        assert db.get(ImageModelProviderConfig, "openai") is None

    with get_session_factory()() as db:
        applied = import_legacy_image_model_settings(
            db,
            environment=_legacy_image_environment(),
            apply=True,
        )
        assert applied.mode == "apply"
        assert applied.credential_imported is True

    with get_session_factory()() as db:
        row = db.get(ImageModelProviderConfig, "openai")
        profile = db.get(ImageModelProfile, IMAGE_MODEL_PROFILE_ID)
        assert row is not None and profile is not None
        ciphertext = row.api_key_ciphertext
        assert ciphertext and ciphertext != "legacy-image-secret"
        assert row.generation_model_id == "legacy-image-model"
        assert row.supervisor_model_id == "legacy-supervisor-model"
        assert profile.active_provider_id == "openai"
        assert profile.max_iterations == 6

    with get_session_factory()() as db:
        repeated = import_legacy_image_model_settings(
            db,
            environment=_legacy_image_environment(),
            apply=True,
        )
        row = db.get(ImageModelProviderConfig, "openai")
        assert repeated.provider_unchanged is True
        assert row is not None and row.api_key_ciphertext == ciphertext


def test_legacy_image_settings_import_enables_existing_provider_before_activation(
    client: TestClient,
    monkeypatch,
) -> None:
    del client
    for key in LEGACY_IMAGE_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_DO_IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("AI_DO_IMAGE_API_KEY", "legacy-image-secret")
    monkeypatch.setenv("AI_DO_IMAGE_MODEL", "legacy-image-model")
    monkeypatch.setenv("AI_DO_IMAGE_SUPERVISOR_MODEL", "legacy-supervisor-model")

    with get_session_factory()() as db:
        db.add(
            ImageModelProviderConfig(
                provider_id="openai",
                enabled=False,
                version=1,
            )
        )
        db.commit()

    with get_session_factory()() as db:
        result = import_legacy_image_model_settings(
            db,
            environment=_legacy_image_environment(),
            apply=True,
        )
        row = db.get(ImageModelProviderConfig, "openai")
        profile = db.get(ImageModelProfile, IMAGE_MODEL_PROFILE_ID)
        assert result.provider_updated is True
        assert result.profile_updated is True
        assert row is not None and row.enabled is True
        assert profile is not None and profile.active_provider_id == "openai"
