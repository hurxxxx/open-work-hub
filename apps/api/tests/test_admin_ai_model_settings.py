from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.llm_provider_registry import (
    ExternalLlmProviderDescriptor,
    ensure_default_external_llm_providers_registered,
    register_external_llm_provider,
    reset_external_llm_providers,
)
from ai_do_api.domains.ai import model_settings_service
from ai_do_api.domains.ai.model_discovery import DiscoveredProviderModel
from ai_do_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    get_ai_model_provider_default_model_key,
    resolve_ai_model_workload_route,
)
from tests.dev_accounts import auth_headers, dev_login


def _admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(dev_login(client)["token"])


def test_registered_plugin_provider_is_projected_and_persisted_without_core_edits(
    client: TestClient,
) -> None:
    reset_external_llm_providers()
    ensure_default_external_llm_providers_registered()
    register_external_llm_provider(
        ExternalLlmProviderDescriptor(
            "compatible-plugin",
            display_name="Compatible Plugin",
            default_endpoint_url="https://1.1.1.1/v1",
            official=False,
            openai_compatible=True,
        )
    )
    try:
        headers = _admin_headers(client)
        snapshot = client.get("/api/v1/admin/ai-model-settings", headers=headers)
        assert snapshot.status_code == 200, snapshot.text
        payload = snapshot.json()
        plugin = next(
            item
            for item in payload["providers"]
            if item["provider_id"] == "compatible-plugin"
        )
        assert plugin["display_name"] == "Compatible Plugin"
        assert plugin["route_mode"] == "external"
        assert plugin["credential_kind"] == "api_key"
        assert plugin["endpoint_url"] == "https://1.1.1.1/v1"
        assert plugin["version"] == 0

        update = client.put(
            "/api/v1/admin/ai-model-settings/providers/compatible-plugin",
            headers=headers,
            json={
                "expected_registry_digest": payload["registry_digest"],
                "expected_version": 0,
                "enabled": False,
                "endpoint_url": None,
                "default_model_id": None,
            },
        )
        assert update.status_code == 200, update.text

        with get_session_factory()() as db:
            row = db.get(model_settings_service.AiModelProviderConfig, "compatible-plugin")
            assert row is not None
            assert row.endpoint_url == "https://1.1.1.1/v1"
    finally:
        reset_external_llm_providers()
        ensure_default_external_llm_providers_registered()


def test_admin_ai_model_settings_projects_registry_and_default_catalog(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["registry_digest"]) == 64
    assert [item["provider_id"] for item in payload["providers"]] == [
        "local",
        "openai",
        "anthropic",
        "gemini",
    ]
    assert all(
        set(item).isdisjoint({"api_key", "api_key_ciphertext"}) for item in payload["providers"]
    )
    assert all(item["endpoint_url"] for item in payload["providers"])
    assert all(item["endpoint_source"] in {"default", "custom"} for item in payload["providers"])
    local_provider = next(
        item for item in payload["providers"] if item["provider_id"] == "local"
    )
    assert local_provider["route_mode"] == "local"
    assert local_provider["credential_kind"] == "none"
    assert all(item["provider_id"] != "anthropic" for item in payload["models"])
    workload_ids = {workload["workload_id"] for workload in payload["workloads"]}
    assert "chatbot" in workload_ids
    assert "ai_manager" not in workload_ids
    assert "mail_thread_brief" not in workload_ids
    assert all(item["workload_id"] != "mail_thread_brief" for item in payload["orphaned_overrides"])
    chatbot = next(item for item in payload["workloads"] if item["workload_id"] == "chatbot")
    assert chatbot["management_surface"] == "llm_routing"
    assert chatbot["ready"] is False
    assert chatbot["local_max_output_tokens"] == 32_768
    assert chatbot["external_max_output_tokens"] == 65_536
    assert chatbot["readiness_code"] == "admin.ai_model_selection_required"
    assert chatbot["resolved_routes"] == []

    document_workloads = {
        item["workload_id"]: item
        for item in payload["workloads"]
        if item["management_surface"] == "document_processing"
    }
    assert set(document_workloads) == {
        "legacy_issues.attachment_vision",
        "meal_invoice_ocr_extract",
        "meal_invoice_ocr_rescan",
    }
    assert all(item["allowed_routes"] == ["local"] for item in document_workloads.values())
    assert all(item["required_capabilities"] == ["vision"] for item in document_workloads.values())

    with get_session_factory()() as db:
        with pytest.raises(AiModelSettingsError) as error:
            resolve_ai_model_workload_route(db, workload_id="chatbot")
    assert error.value.code == "admin.ai_model_selection_required"


def test_ai_model_provider_default_model_key_resolves_enabled_catalog_entry(
    client: TestClient,
) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=headers,
    ).json()
    digest = initial["registry_digest"]
    local = next(
        provider for provider in initial["providers"] if provider["provider_id"] == "local"
    )
    created = client.post(
        "/api/v1/admin/ai-model-settings/models",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "provider_id": "local",
            "model_key": "selected-local-model",
            "display_name": "Selected local model",
            "capabilities": ["chat"],
            "enabled": True,
        },
    ).json()
    selected_model = next(
        model for model in created["models"] if model["model_key"] == "selected-local-model"
    )
    response = client.put(
        "/api/v1/admin/ai-model-settings/providers/local",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": local["version"],
            "enabled": True,
            "endpoint_url": local["endpoint_url"],
            "default_model_id": selected_model["id"],
        },
    )
    assert response.status_code == 200, response.text

    with get_session_factory()() as db:
        assert get_ai_model_provider_default_model_key(
            db,
            provider_id="local",
        ) == selected_model["model_key"]


def test_admin_ai_model_settings_provider_catalog_and_route_lifecycle(
    client: TestClient,
) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=headers,
    ).json()
    digest = initial["registry_digest"]
    local = next(item for item in initial["providers"] if item["provider_id"] == "local")

    create_model = client.post(
        "/api/v1/admin/ai-model-settings/models",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "provider_id": "local",
            "model_key": "qwen-local",
            "display_name": "Qwen Local",
            "capabilities": ["chat", "tool_calling"],
            "enabled": True,
        },
    )
    assert create_model.status_code == 201, create_model.text
    snapshot = create_model.json()
    local_model = next(
        item
        for item in snapshot["models"]
        if item["provider_id"] == "local" and item["model_key"] == "qwen-local"
    )

    update_provider = client.put(
        "/api/v1/admin/ai-model-settings/providers/local",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": local["version"],
            "enabled": True,
            "endpoint_url": "http://127.0.0.1:8001/v1",
            "default_model_id": local_model["id"],
        },
    )
    assert update_provider.status_code == 200, update_provider.text

    route_payload = {
        "expected_registry_digest": digest,
        "expected_version": None,
        "route_mode": "local",
        "provider_id": "local",
        "model_ids": {"default": local_model["id"]},
        "local_max_output_tokens": 24_576,
        "external_max_output_tokens": 49_152,
    }
    route = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json=route_payload,
    )
    assert route.status_code == 200, route.text
    workload = next(item for item in route.json()["workloads"] if item["workload_id"] == "chatbot")
    assert workload["override"]["route_mode"] == "local"
    assert workload["override"]["model_ids"] == {"default": local_model["id"]}
    assert workload["override"]["local_max_output_tokens"] == 24_576
    assert workload["override"]["external_max_output_tokens"] == 49_152
    assert workload["local_max_output_tokens"] == 24_576
    assert workload["external_max_output_tokens"] == 49_152

    stale = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json=route_payload,
    )
    assert stale.status_code == 409

    reset = client.delete(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        params={
            "expected_registry_digest": digest,
            "expected_version": workload["override"]["version"],
        },
    )
    assert reset.status_code == 200, reset.text
    reset_workload = next(
        item for item in reset.json()["workloads"] if item["workload_id"] == "chatbot"
    )
    assert reset_workload["override"] is None
    assert reset_workload["effective_route"] == reset_workload["default_route"]
    assert reset_workload["local_max_output_tokens"] == 32_768
    assert reset_workload["external_max_output_tokens"] == 65_536


def test_admin_ai_model_settings_external_route_and_secret_redaction(
    client: TestClient,
) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=headers,
    ).json()
    digest = initial["registry_digest"]
    anthropic = next(item for item in initial["providers"] if item["provider_id"] == "anthropic")
    model_response = client.post(
        "/api/v1/admin/ai-model-settings/models",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "provider_id": "anthropic",
            "model_key": "administrator-selected-model",
            "display_name": "Administrator selected model",
            "capabilities": ["chat", "tool_calling", "vision"],
            "enabled": True,
        },
    )
    assert model_response.status_code == 201, model_response.text
    sonnet = next(
        item for item in model_response.json()["models"]
        if item["provider_id"] == "anthropic"
        and item["model_key"] == "administrator-selected-model"
    )

    provider_response = client.put(
        "/api/v1/admin/ai-model-settings/providers/anthropic",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": anthropic["version"],
            "enabled": True,
            "endpoint_url": None,
            "default_model_id": sonnet["id"],
            "api_key": "test-anthropic-secret",
        },
    )
    assert provider_response.status_code == 200, provider_response.text
    response_text = provider_response.text
    assert "test-anthropic-secret" not in response_text
    updated_anthropic = next(
        item for item in provider_response.json()["providers"] if item["provider_id"] == "anthropic"
    )
    assert updated_anthropic["has_api_key"] is True

    route = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": None,
            "route_mode": "external",
            "provider_id": "anthropic",
            "model_ids": {"default": sonnet["id"]},
            "local_max_output_tokens": None,
            "external_max_output_tokens": 61_440,
        },
    )
    assert route.status_code == 200, route.text
    workload = next(item for item in route.json()["workloads"] if item["workload_id"] == "chatbot")
    assert workload["effective_route"] == "external"
    assert workload["override"]["provider_id"] == "anthropic"
    assert workload["ready"] is True
    assert workload["resolved_routes"][0]["provider_id"] == "anthropic"
    assert workload["resolved_routes"][0]["model_key"] == "administrator-selected-model"
    assert workload["resolved_routes"][0]["max_output_tokens"] == 61_440

    with get_session_factory()() as db:
        resolved = resolve_ai_model_workload_route(db, workload_id="chatbot")
    assert resolved.route == "external"
    assert resolved.provider_id == "anthropic"
    assert resolved.model_key == "administrator-selected-model"
    assert resolved.route_source == "override"
    assert resolved.max_output_tokens == 61_440
    assert resolved.config_source in {"database", "database_with_legacy_env"}
    assert resolved.api_key is not None
    assert resolved.api_key.get_secret_value() == "test-anthropic-secret"
    assert "test-anthropic-secret" not in repr(resolved)


def test_admin_ai_model_settings_rejects_stale_registry_digest(client: TestClient) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=headers,
    ).json()
    local = next(item for item in initial["providers"] if item["provider_id"] == "local")

    response = client.put(
        "/api/v1/admin/ai-model-settings/providers/local",
        headers=headers,
        json={
            "expected_registry_digest": "0" * 64,
            "expected_version": local["version"],
            "enabled": True,
            "endpoint_url": "http://127.0.0.1:8001/v1",
            "default_model_id": None,
        },
    )

    assert response.status_code == 409
    assert response.headers["X-AI-DO-Error-Code"] == "admin.ai_model_registry_changed"


def test_admin_ai_model_settings_rejects_output_token_caps_outside_bounds(
    client: TestClient,
) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=headers,
    ).json()

    too_small = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json={
            "expected_registry_digest": initial["registry_digest"],
            "expected_version": None,
            "route_mode": "local",
            "provider_id": "local",
            "model_ids": {},
            "local_max_output_tokens": 1_023,
            "external_max_output_tokens": 65_536,
        },
    )
    too_large = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json={
            "expected_registry_digest": initial["registry_digest"],
            "expected_version": None,
            "route_mode": "local",
            "provider_id": "local",
            "model_ids": {},
            "local_max_output_tokens": 32_768,
            "external_max_output_tokens": 65_537,
        },
    )
    non_increment = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json={
            "expected_registry_digest": initial["registry_digest"],
            "expected_version": None,
            "route_mode": "local",
            "provider_id": "local",
            "model_ids": {},
            "local_max_output_tokens": 1_500,
            "external_max_output_tokens": 65_536,
        },
    )

    assert too_small.status_code == 422
    assert too_large.status_code == 422
    assert non_increment.status_code == 422


def test_admin_ai_model_settings_rejects_private_external_endpoint(
    client: TestClient,
) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=headers,
    ).json()
    anthropic = next(item for item in initial["providers"] if item["provider_id"] == "anthropic")

    response = client.put(
        "/api/v1/admin/ai-model-settings/providers/anthropic",
        headers=headers,
        json={
            "expected_registry_digest": initial["registry_digest"],
            "expected_version": anthropic["version"],
            "enabled": False,
            "endpoint_url": "https://127.0.0.1",
            "default_model_id": None,
            "clear_api_key": False,
        },
    )

    assert response.status_code == 422
    assert response.headers["X-AI-DO-Error-Code"] == "admin.ai_model_endpoint_public_https_required"


def test_admin_ai_model_discovery_requires_key_then_creates_unapproved_models(
    client: TestClient,
    monkeypatch,
) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/ai-model-settings",
        headers=headers,
    ).json()
    digest = initial["registry_digest"]
    anthropic = next(item for item in initial["providers"] if item["provider_id"] == "anthropic")

    missing_key = client.post(
        "/api/v1/admin/ai-model-settings/providers/anthropic/discover-models",
        headers=headers,
        json={"expected_registry_digest": digest},
    )
    assert missing_key.status_code == 422
    assert missing_key.headers["X-AI-DO-Error-Code"] == "admin.ai_model_provider_key_required"

    configured = client.put(
        "/api/v1/admin/ai-model-settings/providers/anthropic",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": anthropic["version"],
            "enabled": True,
            "endpoint_url": anthropic["endpoint_url"],
            "default_model_id": anthropic["default_model_id"],
            "api_key": "discovery-secret",
        },
    )
    assert configured.status_code == 200, configured.text

    monkeypatch.setattr(
        model_settings_service,
        "discover_provider_models",
        lambda *_args, **_kwargs: (
            DiscoveredProviderModel(
                model_key="claude-discovered",
                display_name="Claude Discovered",
                capabilities=("chat",),
            ),
        ),
    )
    discovered = client.post(
        "/api/v1/admin/ai-model-settings/providers/anthropic/discover-models",
        headers=headers,
        json={"expected_registry_digest": digest},
    )
    assert discovered.status_code == 200, discovered.text
    assert "discovery-secret" not in discovered.text
    model = next(
        item
        for item in discovered.json()["models"]
        if item["provider_id"] == "anthropic" and item["model_key"] == "claude-discovered"
    )
    assert model["source"] == "discovered"
    assert model["discovery_status"] == "active"
    assert model["last_seen_at"] is not None
    assert model["capabilities"] == ["chat"]
    assert model["enabled"] is False

    changed_provider_key = client.put(
        f"/api/v1/admin/ai-model-settings/models/{model['id']}",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": model["version"],
            "model_key": "rewritten-provider-key",
            "display_name": model["display_name"],
            "capabilities": model["capabilities"],
            "enabled": False,
        },
    )
    assert changed_provider_key.status_code == 422
    assert (
        changed_provider_key.headers["X-AI-DO-Error-Code"]
        == "admin.ai_model_discovered_key_read_only"
    )

    rejected_route = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": None,
            "route_mode": "external",
            "provider_id": "anthropic",
            "model_ids": {"default": model["id"]},
            "local_max_output_tokens": None,
            "external_max_output_tokens": None,
        },
    )
    assert rejected_route.status_code == 422
    assert (
        rejected_route.headers["X-AI-DO-Error-Code"]
        == "admin.ai_model_catalog_invalid_for_provider"
    )

    approved = client.put(
        f"/api/v1/admin/ai-model-settings/models/{model['id']}",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": model["version"],
            "model_key": model["model_key"],
            "display_name": model["display_name"],
            "capabilities": model["capabilities"],
            "enabled": True,
        },
    )
    assert approved.status_code == 200, approved.text

    accepted_route = client.put(
        "/api/v1/admin/ai-model-settings/workloads/chatbot/route",
        headers=headers,
        json={
            "expected_registry_digest": digest,
            "expected_version": None,
            "route_mode": "external",
            "provider_id": "anthropic",
            "model_ids": {"default": model["id"]},
            "local_max_output_tokens": None,
            "external_max_output_tokens": None,
        },
    )
    assert accepted_route.status_code == 200, accepted_route.text

    monkeypatch.setattr(
        model_settings_service,
        "discover_provider_models",
        lambda *_args, **_kwargs: (),
    )
    missing_from_inventory = client.post(
        "/api/v1/admin/ai-model-settings/providers/anthropic/discover-models",
        headers=headers,
        json={"expected_registry_digest": digest},
    )
    assert missing_from_inventory.status_code == 200, missing_from_inventory.text
    assert all(
        item["id"] != model["id"]
        for item in missing_from_inventory.json()["models"]
    )
    chatbot = next(
        item
        for item in missing_from_inventory.json()["workloads"]
        if item["workload_id"] == "chatbot"
    )
    assert chatbot["ready"] is False
    assert chatbot["readiness_code"] == "admin.ai_model_selected_model_not_served"
