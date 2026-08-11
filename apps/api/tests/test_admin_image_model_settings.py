from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.images.cutover import (
    ImageModelCutoverError,
    check_image_model_cutover,
)
from open_work_hub_api.domains.images.model_settings_models import (
    ImageModelProviderConfig,
)
from open_work_hub_api.domains.images.model_settings_service import (
    IMAGE_EXECUTION_PROFILE_VERSION,
    ImageModelSettingsError,
    resolve_profiled_image_execution,
)
from tests.dev_accounts import auth_headers, dev_login


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
    monkeypatch.setenv("OPEN_WORK_HUB_IMAGE_ENABLED", "1")
    monkeypatch.setenv("OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS", "openai")
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
