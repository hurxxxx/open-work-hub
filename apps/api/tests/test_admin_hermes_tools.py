from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from open_work_hub_api.domains.hermes import admin_router
from open_work_hub_api.domains.hermes.research_sources import (
    DEFAULT_RESEARCH_SOURCE_POLICY,
    academic_research_environment_hint,
    disabled_research_source_domains,
)
from dev_accounts import auth_headers, dev_login


def _admin_headers(client: TestClient) -> dict[str, str]:
    return auth_headers(dev_login(client)["token"])


def test_admin_can_toggle_each_research_source_with_revision_control(
    client: TestClient,
) -> None:
    headers = _admin_headers(client)
    initial = client.get(
        "/api/v1/admin/hermes/research-sources",
        headers=headers,
    )

    assert initial.status_code == 200, initial.text
    payload = initial.json()
    assert payload["revision"] == 0
    assert {
        source["id"]: source["enabled"] for source in payload["sources"]
    } == DEFAULT_RESEARCH_SOURCE_POLICY

    updated = client.put(
        "/api/v1/admin/hermes/research-sources/semantic_scholar",
        headers=headers,
        json={"enabled": True, "expected_revision": payload["revision"]},
    )

    assert updated.status_code == 200, updated.text
    updated_payload = updated.json()
    assert updated_payload["revision"] == 1
    assert (
        next(source for source in updated_payload["sources"] if source["id"] == "semantic_scholar")[
            "enabled"
        ]
        is True
    )

    conflict = client.put(
        "/api/v1/admin/hermes/research-sources/crossref",
        headers=headers,
        json={"enabled": False, "expected_revision": payload["revision"]},
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "hermes.research_settings_conflict"


def test_admin_runtime_health_exposes_recovery_and_quarantine_counts(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/admin/hermes/runtime-health",
        headers=_admin_headers(client),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload["services"]) == {"headless", "terminal_broker"}
    assert payload["active_runs"] >= 0
    assert payload["pending_dispatches"] >= 0
    assert payload["pending_approvals"] >= 0
    assert payload["active_terminal_sessions"] >= 0
    assert payload["quarantined_terminal_workspaces"] >= 0


def test_research_source_policy_generates_guidance_and_terminal_blocks() -> None:
    policy = dict(DEFAULT_RESEARCH_SOURCE_POLICY)
    hint = academic_research_environment_hint(policy)

    assert "Semantic Scholar is disabled" in hint
    assert "arXiv, OpenAlex, Crossref" in hint
    assert disabled_research_source_domains(policy) == (
        "semanticscholar.org",
        ".semanticscholar.org",
    )

    all_enabled = {source_id: True for source_id in policy}
    assert academic_research_environment_hint(all_enabled) == ""
    assert disabled_research_source_domains(all_enabled) == ()


@pytest.mark.anyio
async def test_profile_inventory_includes_official_toolset_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = SimpleNamespace(
        id="binding-id",
        user_id="user-id",
        profile_name="owh-profile",
        status="active",
        provider="openrouter",
        model="qwen/qwen3.8-flash",
        policy_revision=1,
        last_error_code=None,
    )

    class FakeDb:
        def get(self, _model, binding_id):
            return binding if binding_id == binding.id else None

    class FakeRuntimeClient:
        async def capabilities(self, profile_name):
            assert profile_name == binding.profile_name
            return {"features": {"skills_api": True}}

        async def toolsets(self, profile_name):
            assert profile_name == binding.profile_name
            return {
                "data": [
                    {
                        "name": "web",
                        "label": "Web Search & Scraping",
                        "description": "web_search, web_extract",
                        "enabled": True,
                        "configured": True,
                        "tools": ["web_search", "web_extract"],
                    }
                ]
            }

    class FakeManagementClient:
        async def list_mcp_servers(self, profile_name):
            assert profile_name == binding.profile_name
            return {"servers": []}

        async def list_skills(self, profile_name):
            assert profile_name == binding.profile_name
            return {"skills": []}

    monkeypatch.setattr(admin_router, "runtime_client", FakeRuntimeClient)
    monkeypatch.setattr(admin_router, "management_client", FakeManagementClient)

    inventory = await admin_router.get_hermes_profile_inventory(
        binding.id,
        db=FakeDb(),  # type: ignore[arg-type]
        _admin=SimpleNamespace(),  # type: ignore[arg-type]
    )

    assert inventory.toolsets[0].name == "web"
    assert inventory.toolsets[0].enabled is True
