from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest

from open_alm_api.core.db import get_session_factory
from open_alm_api.core.llm import LlmPoolConfig
from open_alm_api.core.settings import Settings
from open_alm_api.domains.ai import masking as masking_module
from open_alm_api.domains.ai import external_gateway
from open_alm_api.domains.ai.boundary_safety import evaluate_external_payload_safety
from open_alm_api.domains.ai.external_gateway import (
    AiExternalCapabilityPolicyViolation,
    AiExternalCapabilityRequest,
    execute_external_capability,
)
from open_alm_api.domains.ai.gateway import (
    AiGatewayPolicyViolation,
    AiGatewayRequest,
    resolve_gateway_execution,
)
from open_alm_api.domains.ai.privacy_filter import PrivacyFilterDetection
from open_alm_api.domains.ai.models import (
    AiSecurityDataProtectionSettings,
    AiSecurityDetectedValue,
    AiSecurityExternalTransferException,
    AiSecurityPolicyRule,
)
from open_alm_api.domains.ai.security_policy import (
    DATA_PROTECTION_SETTINGS_ID,
    EXTERNAL_TRANSFER_EXCEPTION_REASON,
    external_transfer_blockers_from_safety,
    resolve_ai_security_external_transfer_exception,
    resolve_ai_security_policy,
    AiSecurityPolicyContext,
)
from open_alm_api.domains.auth.models import AuditLog
from open_alm_api.domains.auth.security import new_id


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _external_test_llm_config() -> LlmPoolConfig:
    return LlmPoolConfig(
        pool="external",
        provider="anthropic",
        base_url="https://api.anthropic.com",
        api_key="test-key",
        default_model="claude-test",
        canonical_model="claude-test",
        healthcheck_timeout_seconds=1.0,
        long_generation_timeout_seconds=30.0,
    )


def _bootstrap_admin_session(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/setup",
        json={
            "full_name": "Open ALM Admin",
            "email": "admin@open-alm.local",
            "password": "supersecret123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _patch_privacy_filter_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            enabled=True,
            used=True,
        ),
    )


def _audit_record_without_detected_values(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "detected_values"}


def _enable_ai_security_enforcement(
    client: TestClient,
    headers: dict[str, str],
) -> dict:
    response = client.patch(
        "/api/v1/admin/ai-security/enforcement",
        headers=headers,
        json={"enforcement_enabled": True},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _put_ai_security_data_protection(
    client: TestClient,
    headers: dict[str, str],
    *,
    external_app_actions: dict[str, dict[str, str]] | None = None,
    blocker_actions: dict[str, str] | None = None,
) -> dict:
    _enable_ai_security_enforcement(client, headers)
    response = client.put(
        "/api/v1/admin/ai-security/data-protection",
        headers=headers,
        json={
            "custom_block_terms": [],
            "blocker_actions": blocker_actions or {},
            "external_app_actions": external_app_actions or {},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _simulate_ai_security(
    client: TestClient,
    headers: dict[str, str],
    **payload,
) -> dict:
    response = client.post(
        "/api/v1/admin/ai-security/simulate",
        headers=headers,
        json={
            "app_id": "web-search",
            "task_kind": "web_search",
            "capability": "web_search",
            "provider": "anthropic",
            "content_origin": "user_prompt",
            **payload,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _get_or_create_data_protection_settings(db) -> AiSecurityDataProtectionSettings:
    settings = db.get(AiSecurityDataProtectionSettings, DATA_PROTECTION_SETTINGS_ID)
    if settings is not None:
        return settings
    settings = AiSecurityDataProtectionSettings(
        id=DATA_PROTECTION_SETTINGS_ID,
        enforcement_enabled=True,
        custom_block_terms_json=[],
    )
    db.add(settings)
    return settings


def test_admin_ai_security_policy_crud_simulation_and_audit_payload(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    workspaces_response = client.get("/api/v1/admin/workspaces", headers=headers)
    assert workspaces_response.status_code == 200, workspaces_response.text
    workspace_id = workspaces_response.json()[0]["id"]
    term = f"Falcon-{new_id()}"

    summary_response = client.get("/api/v1/admin/ai-security/summary", headers=headers)
    assert summary_response.status_code == 200, summary_response.text
    summary = summary_response.json()
    assert summary["data_protection"]["enforcement_enabled"] is False
    assert "task_policies" not in summary
    assert "task_policy_apps" not in summary
    assert client.get("/api/v1/admin/ai-security/task-policies", headers=headers).status_code == 404
    external_candidate_ids = {item["app_id"] for item in summary["external_app_candidates"]}
    assert {"web-search", "research-trends", "standards-monitor"}.issubset(external_candidate_ids)
    assert summary["condition_options"]["apps"]
    assert {option["value"] for option in summary["condition_options"]["external_apps"]} >= {
        "web-search",
        "research-trends",
        "standards-monitor",
    }
    assert any(option["value"] == "llm" for option in summary["condition_options"]["capabilities"])
    assert any(
        option["value"] == "anthropic" for option in summary["condition_options"]["providers"]
    )
    assert any(
        option["value"] == "internal_context"
        for option in summary["condition_options"]["content_origins"]
    )
    _enable_ai_security_enforcement(client, headers)

    data_response = client.put(
        "/api/v1/admin/ai-security/data-protection",
        headers=headers,
        json={
            "custom_block_terms": [term, term],
            "blocker_actions": {
                "credential": "mask_and_send",
                "pii": "mask_and_send",
            },
            "external_app_actions": {
                "web-search": {
                    "credential": "mask_and_send",
                    "pii": "mask_and_send",
                },
            },
        },
    )
    assert data_response.status_code == 200, data_response.text
    data_protection = data_response.json()
    assert data_protection["custom_block_terms"] == [term]
    assert data_protection["blocker_actions"]["pii"] == "mask_and_send"
    assert "credential" not in data_protection["blocker_actions"]
    assert data_protection["external_app_actions"]["web-search"]["pii"] == "mask_and_send"
    assert "credential" not in data_protection["external_app_actions"]["web-search"]

    rule_response = client.post(
        "/api/v1/admin/ai-security/rules",
        headers=headers,
        json={
            "name": "Workspace web search deny",
            "description": "deny external search in this workspace",
            "enabled": True,
            "workspace_id": workspace_id,
            "task_kind": "web_search",
            "capability": "web_search",
            "provider": "anthropic",
            "effect": "block_external",
            "custom_block_terms": [],
        },
    )
    assert rule_response.status_code == 201, rule_response.text
    rule = rule_response.json()
    assert rule["workspace_id"] == workspace_id
    assert rule["effect"] == "block_external"
    assert rule["task_kinds"] == ["web_search"]

    exception_response = client.post(
        "/api/v1/admin/ai-security/exceptions",
        headers=headers,
        json={
            "name": "Approved internal context export",
            "description": "approved scoped exception",
            "enabled": True,
            "workspace_id": workspace_id,
            "task_kind": "qna_answer",
            "capability": "llm",
            "allowed_blocker_types": ["internal_context"],
            "reason": "Approved for a short-lived external summarization workflow.",
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        },
    )
    assert exception_response.status_code == 201, exception_response.text
    exception = exception_response.json()
    assert exception["allowed_blocker_types"] == ["internal_context"]
    assert exception["task_kinds"] == ["qna_answer"]

    exception_simulation_response = client.post(
        "/api/v1/admin/ai-security/simulate",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "task_kind": "qna_answer",
            "capability": "llm",
            "content_origin": "internal_context",
            "sample_text": "internal context without hard blockers",
        },
    )
    assert exception_simulation_response.status_code == 200
    exception_simulation = exception_simulation_response.json()
    assert exception_simulation["route_action"] == "external_exception"
    assert exception_simulation["external_transfer_exception_id"] == exception["id"]
    assert exception_simulation["hard_blocker_types"] == []

    simulation_response = client.post(
        "/api/v1/admin/ai-security/simulate",
        headers=headers,
        json={
            "workspace_id": workspace_id,
            "task_kind": "web_search",
            "capability": "web_search",
            "provider": "anthropic",
            "content_origin": "user_prompt",
            "sample_text": "public question",
        },
    )
    assert simulation_response.status_code == 200, simulation_response.text
    simulation = simulation_response.json()
    assert simulation["route_action"] == "blocked"
    assert simulation["rule_id"] == rule["id"]

    term_simulation_response = client.post(
        "/api/v1/admin/ai-security/simulate",
        headers=headers,
        json={
            "workspace_id": "other-workspace",
            "task_kind": "web_search",
            "capability": "web_search",
            "provider": "anthropic",
            "content_origin": "user_prompt",
            "sample_text": f"Please summarize {term}",
        },
    )
    assert term_simulation_response.status_code == 200, term_simulation_response.text
    term_simulation = term_simulation_response.json()
    assert term_simulation["route_action"] == "blocked"
    assert term_simulation["custom_block_term_count"] == 1
    assert "custom_block_term" in term_simulation["blocked_entity_types"]

    audit_response = client.get(
        "/api/v1/admin/audit-logs?q=ai_security&limit=20",
        headers=headers,
    )
    assert audit_response.status_code == 200, audit_response.text
    audit_payload = str([item["payload"] for item in audit_response.json()["items"]])
    assert "custom_block_term_count" in audit_payload
    assert term not in audit_payload


def test_admin_ai_security_monitoring_and_blocked_audit_filter(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    actor_id = admin["user"]["id"]
    now = datetime.now(UTC).replace(tzinfo=None)
    with get_session_factory()() as db:
        db.add_all(
            [
                AuditLog(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="ai_external_call",
                    entity_kind="ai_external",
                    entity_id="web-search",
                    summary="External web search blocked",
                    payload={
                        "status": "blocked_external",
                        "app_id": "web-search",
                        "task_kind": "web_search",
                        "policy_reason": "external_payload_blocked",
                        "blocked_entity_types": ["credential"],
                    },
                    created_at=now - timedelta(hours=3),
                ),
                AuditLog(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="llm_call",
                    entity_kind="llm",
                    entity_id="web-search",
                    summary="LLM call switched to local",
                    payload={
                        "status": "success",
                        "app_id": "web-search",
                        "task_kind": "web_search",
                        "forced_local": True,
                        "ai_security_policy_effect": "local_only",
                        "ai_security_policy_reason": "pii_detected",
                        "blocked_entity_types": ["pii"],
                    },
                    created_at=now - timedelta(hours=2),
                ),
                AuditLog(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="ai_external_call",
                    entity_kind="ai_external",
                    entity_id="web-search",
                    summary="External web search masked",
                    payload={
                        "status": "success",
                        "app_id": "web-search",
                        "task_kind": "web_search",
                        "mask_applied": True,
                        "masked_entity_types": ["pii:email"],
                        "ai_security_policy_effect": "mask_and_send",
                    },
                    created_at=now - timedelta(hours=1),
                ),
                AuditLog(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="llm_call",
                    entity_kind="llm_task",
                    entity_id="ppt-generate",
                    summary="Local LLM call by routing hint",
                    payload={
                        "status": "ok",
                        "app_id": "ppt-assistant",
                        "task_kind": "ppt_generate",
                        "chosen_pool": "local",
                        "forced_local": True,
                        "decision_reason": "local_hint",
                        "blocked_entity_types": [],
                        "ai_security_policy_reason": "no_matching_rule",
                    },
                    created_at=now - timedelta(minutes=30),
                ),
                AuditLog(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="admin.ai_security.data_protection.update",
                    entity_kind="ai_security",
                    entity_id=DATA_PROTECTION_SETTINGS_ID,
                    summary="Updated AI security data protection settings",
                    payload={"custom_block_term_count": 1},
                    created_at=now,
                ),
                AiSecurityDetectedValue(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="ai_external_call",
                    source="api.general.web_search",
                    app_id="web-search",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    reason_code="external_payload_blocked",
                    detector="regex",
                    entity_type="pii:email",
                    blocker_type="pii",
                    detected_value="owner@example.com",
                    value_hash="email-hash",
                    occurrence_count=2,
                    created_at=now - timedelta(hours=3),
                ),
                AiSecurityDetectedValue(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="ai_external_call",
                    source="api.general.web_search",
                    app_id="web-search",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    reason_code="custom_block_term_blocked",
                    detector="custom_block_term",
                    entity_type="custom_block_term",
                    blocker_type="custom_block_term",
                    detected_value="Falcon-X",
                    value_hash="term-hash",
                    occurrence_count=1,
                    created_at=now - timedelta(hours=2),
                ),
                AiSecurityDetectedValue(
                    id=new_id(),
                    actor_user_id=actor_id,
                    action="ai_external_call",
                    source="api.general.web_search",
                    app_id="web-search",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    reason_code="external_payload_masked",
                    detector="privacy_filter",
                    entity_type="pii:person",
                    blocker_type="pii",
                    detected_value=None,
                    value_hash=None,
                    occurrence_count=3,
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
        db.commit()

    monitoring_response = client.get(
        "/api/v1/admin/ai-security/monitoring?days=7",
        headers=headers,
    )
    assert monitoring_response.status_code == 200, monitoring_response.text
    monitoring = monitoring_response.json()
    assert monitoring["totals"]["security_event_count"] == 3
    assert monitoring["totals"]["blocked_event_count"] == 1
    assert monitoring["totals"]["forced_local_count"] == 1
    assert monitoring["totals"]["masked_event_count"] == 1
    assert monitoring["totals"]["hard_blocker_count"] == 1
    assert monitoring["blocked_by_user"][0]["user_id"] == actor_id
    assert monitoring["blocked_by_user"][0]["blocked_count"] == 1
    assert monitoring["blocked_by_user"][0]["forced_local_count"] == 1
    assert monitoring["blocked_by_user"][0]["masked_count"] == 1
    assert {item["key"] for item in monitoring["blocked_by_reason"]} >= {
        "external_payload_blocked",
        "pii_detected",
    }
    assert {item["key"] for item in monitoring["blocked_by_entity_type"]} >= {
        "credential",
        "pii",
    }
    assert monitoring["detected_value_groups"][0]["entity_type"] == "pii:email"
    assert monitoring["detected_value_groups"][0]["occurrence_count"] == 2
    assert monitoring["detected_value_groups"][0]["distinct_value_count"] == 1
    assert monitoring["detected_value_groups"][0]["detail_available"] is True
    assert monitoring["privacy_filter_groups"][0]["entity_type"] == "pii:person"
    assert monitoring["privacy_filter_groups"][0]["occurrence_count"] == 3
    assert monitoring["privacy_filter_groups"][0]["distinct_value_count"] == 0
    assert monitoring["privacy_filter_groups"][0]["detail_available"] is False
    assert monitoring["detected_value_rankings"][0]["detected_value"] == "owner@example.com"
    assert monitoring["detected_value_rankings"][0]["occurrence_count"] == 2
    assert monitoring["privacy_filter_rankings"][0]["entity_type"] == "pii:person"
    assert monitoring["privacy_filter_rankings"][0]["detected_value"] is None
    assert monitoring["privacy_filter_rankings"][0]["occurrence_count"] == 3
    assert len(monitoring["blocked_events"]) == 2

    groups_response = client.get(
        "/api/v1/admin/ai-security/detected-values/groups",
        params={"days": 7, "limit": 1},
        headers=headers,
    )
    assert groups_response.status_code == 200, groups_response.text
    groups = groups_response.json()
    assert groups["total"] == 2
    assert len(groups["items"]) == 1
    assert groups["items"][0]["entity_type"] == "pii:email"
    assert "detected_value" not in groups["items"][0]

    filtered_groups_response = client.get(
        "/api/v1/admin/ai-security/detected-values/groups",
        params={"days": 7, "q": "Falcon"},
        headers=headers,
    )
    assert filtered_groups_response.status_code == 200, filtered_groups_response.text
    filtered_groups = filtered_groups_response.json()
    assert filtered_groups["total"] == 1
    assert filtered_groups["items"][0]["entity_type"] == "custom_block_term"

    privacy_groups_response = client.get(
        "/api/v1/admin/ai-security/detected-values/groups",
        params={"days": 7, "privacy_filter": "true"},
        headers=headers,
    )
    assert privacy_groups_response.status_code == 200, privacy_groups_response.text
    privacy_groups = privacy_groups_response.json()
    assert privacy_groups["total"] == 1
    assert privacy_groups["items"][0]["entity_type"] == "pii:person"
    assert privacy_groups["items"][0]["detail_available"] is False

    details_response = client.get(
        "/api/v1/admin/ai-security/detected-values/details",
        params={
            "days": 7,
            "detector": "regex",
            "entity_type": "pii:email",
            "blocker_type": "pii",
        },
        headers=headers,
    )
    assert details_response.status_code == 200, details_response.text
    details = details_response.json()
    assert details["total"] == 1
    assert details["items"][0]["detected_value"] == "owner@example.com"
    assert details["items"][0]["occurrence_count"] == 2

    audit_response = client.get(
        "/api/v1/admin/audit-logs?q=ai_security&ai_security_blocked_only=true&days=7",
        headers=headers,
    )
    assert audit_response.status_code == 200, audit_response.text
    audit = audit_response.json()
    assert audit["total"] == 2
    assert {item["action"] for item in audit["items"]} == {
        "ai_external_call",
        "llm_call",
    }


def test_admin_ai_security_simulation_returns_masked_external_preview(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            enabled=True,
            used=True,
        ),
    )
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    _enable_ai_security_enforcement(client, headers)

    rule_response = client.post(
        "/api/v1/admin/ai-security/rules",
        headers=headers,
        json={
            "name": "Mask PII before external LLM",
            "description": "mask eligible blockers",
            "enabled": True,
            "task_kind": "patent_analysis",
            "capability": "llm",
            "effect": "mask_and_send",
            "custom_block_terms": [],
        },
    )
    assert rule_response.status_code == 201, rule_response.text

    simulation_response = client.post(
        "/api/v1/admin/ai-security/simulate",
        headers=headers,
        json={
            "task_kind": "patent_analysis",
            "capability": "llm",
            "content_origin": "user_prompt",
            "sample_text": "Contact owner@example.com for review",
        },
    )
    assert simulation_response.status_code == 200, simulation_response.text
    simulation = simulation_response.json()

    assert simulation["effect"] == "mask_and_send"
    assert simulation["route_action"] == "masked_external"
    assert simulation["allow_external"] is True
    assert simulation["mask_applied"] is True
    assert simulation["privacy_filter_status"] == "ok"
    assert "pii:email" in simulation["masked_entity_types"]
    assert "owner@example.com" not in simulation["masked_text_preview"]
    assert "[masked:pii]" in simulation["masked_text_preview"]


def test_admin_ai_security_simulation_uses_global_mask_action(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            enabled=True,
            used=True,
        ),
    )
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    _enable_ai_security_enforcement(client, headers)

    data_response = client.put(
        "/api/v1/admin/ai-security/data-protection",
        headers=headers,
        json={
            "custom_block_terms": [],
            "blocker_actions": {"pii": "mask_and_send"},
        },
    )
    assert data_response.status_code == 200, data_response.text

    simulation_response = client.post(
        "/api/v1/admin/ai-security/simulate",
        headers=headers,
        json={
            "task_kind": "patent_analysis",
            "capability": "llm",
            "content_origin": "user_prompt",
            "sample_text": "Contact owner@example.com for review",
        },
    )
    assert simulation_response.status_code == 200, simulation_response.text
    simulation = simulation_response.json()

    assert simulation["effect"] == "inherit"
    assert simulation["route_action"] == "masked_external"
    assert simulation["allow_external"] is True
    assert simulation["mask_applied"] is True
    assert "owner@example.com" not in simulation["masked_text_preview"]
    assert "[masked:pii]" in simulation["masked_text_preview"]


def test_admin_ai_security_enforcement_switch_bypasses_simulation(
    client: TestClient,
) -> None:
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])

    summary_response = client.get("/api/v1/admin/ai-security/summary", headers=headers)
    assert summary_response.status_code == 200, summary_response.text
    assert summary_response.json()["data_protection"]["enforcement_enabled"] is False

    response = client.patch(
        "/api/v1/admin/ai-security/enforcement",
        headers=headers,
        json={
            "enforcement_enabled": False,
            "enforcement_disabled_reason": "maintenance window",
        },
    )

    assert response.status_code == 200, response.text
    data_protection = response.json()
    assert data_protection["enforcement_enabled"] is False
    assert data_protection["enforcement_disabled_reason"] == "maintenance window"

    simulation = _simulate_ai_security(
        client,
        headers,
        sample_text="851212-1045612 이지호 api_key=sk-sensitive-token-value",
    )
    assert simulation["reason_code"] == "ai_security_enforcement_disabled"
    assert simulation["route_action"] == "unchanged"
    assert simulation["pii_hits"] == []
    assert simulation["hard_blocker_types"] == []
    assert simulation["external_transfer_blocker_types"] == []

    audit_response = client.get(
        "/api/v1/admin/audit-logs?action=admin.ai_security.enforcement.update",
        headers=headers,
    )
    assert audit_response.status_code == 200, audit_response.text
    audit_item = audit_response.json()["items"][0]
    assert audit_item["payload"]["enforcement_enabled"] is False

    enable_response = client.patch(
        "/api/v1/admin/ai-security/enforcement",
        headers=headers,
        json={"enforcement_enabled": True},
    )
    assert enable_response.status_code == 200, enable_response.text
    assert enable_response.json()["enforcement_enabled"] is True
    assert enable_response.json()["enforcement_disabled_reason"] == ""


def test_admin_ai_security_simulation_uses_configured_external_app_mask_action(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_privacy_filter_ok(monkeypatch)
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    _put_ai_security_data_protection(
        client,
        headers,
        external_app_actions={"web-search": {"pii": "mask_and_send"}},
    )

    simulation = _simulate_ai_security(
        client,
        headers,
        sample_text="Contact owner@example.com or 010-1234-5678 for public news",
    )

    assert simulation["effect"] == "inherit"
    assert simulation["route_action"] == "masked_external"
    assert simulation["allow_external"] is True
    assert simulation["mask_applied"] is True
    assert simulation["privacy_filter_status"] == "ok"
    assert "pii" in simulation["external_transfer_blocker_types"]
    assert "pii:email" in simulation["masked_entity_types"]
    assert "owner@example.com" not in simulation["masked_text_preview"]
    assert "010-1234-5678" not in simulation["masked_text_preview"]
    assert "[masked:pii]" in simulation["masked_text_preview"]


def test_admin_ai_security_simulation_scopes_external_app_action_to_app(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_privacy_filter_ok(monkeypatch)
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    _put_ai_security_data_protection(
        client,
        headers,
        external_app_actions={"web-search": {"pii": "mask_and_send"}},
    )

    simulation = _simulate_ai_security(
        client,
        headers,
        app_id="research-trends",
        task_kind="research_trends",
        sample_text="Contact owner@example.com for public research news",
    )

    assert simulation["effect"] == "inherit"
    assert simulation["route_action"] == "blocked"
    assert simulation["allow_external"] is False
    assert simulation["mask_applied"] is False
    assert simulation["masked_text_preview"] is None
    assert "pii" in simulation["external_transfer_blocker_types"]


def test_admin_ai_security_simulation_blocks_mixed_external_app_blockers(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_privacy_filter_ok(monkeypatch)
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    _put_ai_security_data_protection(
        client,
        headers,
        external_app_actions={"web-search": {"pii": "mask_and_send"}},
    )

    simulation = _simulate_ai_security(
        client,
        headers,
        sample_text="Contact owner@example.com about contract terms",
    )

    assert simulation["effect"] == "inherit"
    assert simulation["route_action"] == "blocked"
    assert simulation["allow_external"] is False
    assert simulation["mask_applied"] is False
    assert simulation["masked_text_preview"] is None
    assert set(simulation["external_transfer_blocker_types"]) == {
        "company_sensitive_entity",
        "pii",
    }


def test_admin_ai_security_simulation_hard_blockers_override_external_app_mask(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_privacy_filter_ok(monkeypatch)
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    _put_ai_security_data_protection(
        client,
        headers,
        external_app_actions={
            "web-search": {
                "company_sensitive_entity": "mask_and_send",
                "pii": "mask_and_send",
                "internal_url": "mask_and_send",
                "security_document": "mask_and_send",
            }
        },
    )

    simulation = _simulate_ai_security(
        client,
        headers,
        sample_text="Use API key sk-abcdefghijklmnopqrstuvwxyz123456",
    )

    assert simulation["route_action"] == "blocked"
    assert simulation["allow_external"] is False
    assert simulation["mask_applied"] is False
    assert simulation["hard_blocker_types"] == ["credential"]
    assert "credential" in simulation["external_transfer_blocker_types"]


def test_admin_ai_security_simulation_block_external_overrides_external_app_mask(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_privacy_filter_ok(monkeypatch)
    admin = _bootstrap_admin_session(client)
    headers = _auth_headers(admin["token"])
    _put_ai_security_data_protection(
        client,
        headers,
        external_app_actions={"web-search": {"pii": "mask_and_send"}},
    )
    rule_response = client.post(
        "/api/v1/admin/ai-security/rules",
        headers=headers,
        json={
            "name": "Web search local only",
            "description": "explicit rule wins over external app masking",
            "enabled": True,
            "app_id": "web-search",
            "task_kind": "web_search",
            "capability": "web_search",
            "provider": "anthropic",
            "effect": "block_external",
            "custom_block_terms": [],
        },
    )
    assert rule_response.status_code == 201, rule_response.text
    rule = rule_response.json()

    simulation = _simulate_ai_security(
        client,
        headers,
        sample_text="Contact owner@example.com for public news",
    )

    assert simulation["effect"] == "block_external"
    assert simulation["rule_id"] == rule["id"]
    assert simulation["route_action"] == "blocked"
    assert simulation["allow_external"] is False
    assert simulation["mask_applied"] is False
    assert simulation["masked_text_preview"] is None
    assert simulation["external_transfer_blocker_types"] == ["policy_block_external", "pii"]


def test_external_transfer_exception_allows_soft_blocker(client: TestClient) -> None:
    assert client is not None
    with get_session_factory()() as db:
        exception = AiSecurityExternalTransferException(
            id=new_id(),
            name="Internal context exception",
            description="",
            enabled=True,
            task_kind="patent_analysis",
            capability="llm",
            allowed_blocker_types_json=["internal_context"],
            reason="approved",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        db.add(exception)
        db.commit()

        safety = evaluate_external_payload_safety(
            ["server-built evidence"],
            content_origin="internal_context",
            source_kinds=("docs",),
        )
        decision = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                workspace_id="workspace-1",
                task_kind="patent_analysis",
                capability="llm",
            ),
            external_transfer_blockers_from_safety(safety),
        )

    assert decision.allowed is True
    assert decision.exception_id == exception.id


def test_external_transfer_exception_can_approve_block_external_rule(
    client: TestClient,
) -> None:
    assert client is not None
    with get_session_factory()() as db:
        exception = AiSecurityExternalTransferException(
            id=new_id(),
            name="Approved external policy override",
            description="",
            enabled=True,
            task_kind="patent_analysis",
            capability="llm",
            allowed_blocker_types_json=["policy_block_external"],
            reason="approved",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        db.add(exception)
        db.commit()

        safety = evaluate_external_payload_safety(["public patent abstract"])
        decision = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                task_kind="patent_analysis",
                capability="llm",
            ),
            external_transfer_blockers_from_safety(
                safety,
                policy_block_external=True,
            ),
        )

    assert decision.allowed is True
    assert decision.exception_id == exception.id
    assert decision.matched_blocker_types == ("policy_block_external",)
    assert decision.reason_code == EXTERNAL_TRANSFER_EXCEPTION_REASON


def test_policy_rule_matches_any_configured_task_kind(client: TestClient) -> None:
    assert client is not None
    with get_session_factory()() as db:
        _get_or_create_data_protection_settings(db).enforcement_enabled = True
        rule_id = new_id()
        rule = AiSecurityPolicyRule(
            id=rule_id,
            name="External search family deny",
            description="",
            enabled=True,
            app_id="web-search",
            task_kinds_json=["web_search", "research_trends"],
            capability="web_search",
            effect="block_external",
            custom_block_terms_json=[],
        )
        db.add(rule)
        db.commit()

        matched = resolve_ai_security_policy(
            db,
            AiSecurityPolicyContext(
                app_id="web-search",
                task_kind="research_trends",
                capability="web_search",
            ),
        )
        missed = resolve_ai_security_policy(
            db,
            AiSecurityPolicyContext(
                app_id="web-search",
                task_kind="patent_analysis",
                capability="web_search",
            ),
        )

    assert matched.effect == "block_external"
    assert matched.rule_id == rule_id
    assert missed.effect == "inherit"


def test_external_transfer_exception_matches_any_configured_task_kind(
    client: TestClient,
) -> None:
    assert client is not None
    with get_session_factory()() as db:
        exception_id = new_id()
        exception = AiSecurityExternalTransferException(
            id=exception_id,
            name="Approved research exports",
            description="",
            enabled=True,
            app_id="web-search",
            task_kinds_json=["web_search", "research_trends"],
            capability="web_search",
            allowed_blocker_types_json=["internal_context"],
            reason="approved",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        db.add(exception)
        db.commit()

        safety = evaluate_external_payload_safety(
            ["server-built evidence"],
            content_origin="internal_context",
            source_kinds=("docs",),
        )
        matched = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                app_id="web-search",
                task_kind="research_trends",
                capability="web_search",
            ),
            external_transfer_blockers_from_safety(safety),
        )
        missed = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                app_id="web-search",
                task_kind="patent_analysis",
                capability="web_search",
            ),
            external_transfer_blockers_from_safety(safety),
        )

    assert matched.allowed is True
    assert matched.exception_id == exception_id
    assert missed.allowed is False


def test_external_transfer_exception_allows_approved_pii_internal_url_and_security_document(
    client: TestClient,
) -> None:
    assert client is not None
    with get_session_factory()() as db:
        exception = AiSecurityExternalTransferException(
            id=new_id(),
            name="Approved security review export",
            description="",
            enabled=True,
            task_kind="patent_analysis",
            capability="llm",
            allowed_blocker_types_json=[
                "internal_context",
                "pii",
                "internal_url",
                "security_document",
            ],
            reason="approved",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        db.add(exception)
        db.commit()

        safety = evaluate_external_payload_safety(
            ["security policy review for owner@example.com at http://10.10.0.5/runbook"],
            content_origin="internal_context",
        )
        decision = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                workspace_id="workspace-1",
                task_kind="patent_analysis",
                capability="llm",
            ),
            external_transfer_blockers_from_safety(safety),
        )

    assert decision.allowed is True
    assert decision.exception_id == exception.id
    assert decision.hard_blocker_types == ()


def test_external_transfer_exception_cannot_bypass_absolute_blocker(
    client: TestClient,
) -> None:
    assert client is not None
    with get_session_factory()() as db:
        db.add(
            AiSecurityExternalTransferException(
                id=new_id(),
                name="Internal context exception",
                description="",
                enabled=True,
                task_kind="patent_analysis",
                capability="llm",
                allowed_blocker_types_json=["internal_context"],
                reason="approved",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
            )
        )
        db.commit()

        safety = evaluate_external_payload_safety(
            ["internal api_key=sk-secretsecretsecretsecret evidence"],
            content_origin="internal_context",
        )
        decision = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                workspace_id="workspace-1",
                task_kind="patent_analysis",
                capability="llm",
            ),
            external_transfer_blockers_from_safety(safety),
        )

    assert decision.allowed is False
    assert "credential" in decision.hard_blocker_types


def test_gateway_external_transfer_exception_allows_company_sensitive_entity(
    client: TestClient,
) -> None:
    assert client is not None
    with get_session_factory()() as db:
        _get_or_create_data_protection_settings(db).enforcement_enabled = True
        exception = AiSecurityExternalTransferException(
            id=new_id(),
            name="Order summary export",
            description="",
            enabled=True,
            task_kind="patent_analysis",
            capability="llm",
            allowed_blocker_types_json=["company_sensitive_entity"],
            reason="approved",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        db.add(exception)
        db.commit()

        execution = resolve_gateway_execution(
            AiGatewayRequest(
                task_kind="patent_analysis",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                source="tests.ai_security",
                app="patent-analysis",
                workload_id="patent_analysis",
                workload_route="external",
                workload_config=_external_test_llm_config(),
                requested_model="claude-test",
                requested_provider="anthropic",
                max_tokens=4_096,
                messages=[{"role": "user", "content": "Summarize ORD-2026-001"}],
            ),
            db,
        )

    assert execution.decision.chosen_pool == "external"
    assert execution.decision.forced_local is False
    assert execution.decision.reason_codes == (EXTERNAL_TRANSFER_EXCEPTION_REASON,)
    assert execution.decision.external_transfer_exception_id == exception.id


def test_gateway_blocks_external_when_global_custom_block_term_matches(
    client: TestClient,
) -> None:
    assert client is not None
    term = f"Falcon-{new_id()}"
    with get_session_factory()() as db:
        settings = db.get(AiSecurityDataProtectionSettings, DATA_PROTECTION_SETTINGS_ID)
        if settings is None:
            settings = AiSecurityDataProtectionSettings(
                id=DATA_PROTECTION_SETTINGS_ID,
                enforcement_enabled=True,
                custom_block_terms_json=[term],
            )
            db.add(settings)
        else:
            settings.enforcement_enabled = True
            settings.custom_block_terms_json = [term]
        db.commit()

        with pytest.raises(AiGatewayPolicyViolation) as error:
            resolve_gateway_execution(
                AiGatewayRequest(
                    task_kind="patent_analysis",
                    workspace_id="workspace-1",
                    actor_user_id="user-1",
                    source="tests.ai_security",
                    app="patent-analysis",
                    workload_id="patent_analysis",
                    workload_route="external",
                    workload_config=_external_test_llm_config(),
                    requested_model="claude-test",
                    requested_provider="anthropic",
                    messages=[{"role": "user", "content": f"Analyze {term}"}],
                ),
                db,
            )

    assert error.value.reason_code == "external_transfer_blocked"


def test_gateway_uses_llm_routing_when_ai_security_enforcement_disabled(
    client: TestClient,
) -> None:
    assert client is not None
    term = f"Falcon-{new_id()}"
    with get_session_factory()() as db:
        settings = _get_or_create_data_protection_settings(db)
        settings.enforcement_enabled = False
        settings.custom_block_terms_json = [term]
        db.commit()

        execution = resolve_gateway_execution(
            AiGatewayRequest(
                task_kind="patent_analysis",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                source="tests.ai_security",
                app="patent-analysis",
                workload_id="patent_analysis",
                workload_route="external",
                workload_config=_external_test_llm_config(),
                requested_model="claude-test",
                requested_provider="anthropic",
                max_tokens=4_096,
                messages=[{"role": "user", "content": f"Analyze {term}"}],
            ),
            db,
        )

    assert execution.decision.chosen_pool == "external"
    assert execution.decision.forced_local is False
    assert execution.decision.reason_codes == ("ai_security_enforcement_disabled",)
    assert execution.decision.custom_block_term_count == 0


def test_external_capability_blocks_when_policy_blocks_external(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    with get_session_factory()() as db:
        _get_or_create_data_protection_settings(db).enforcement_enabled = True
        rule_id = new_id()
        rule = AiSecurityPolicyRule(
            id=rule_id,
            name="Search local only",
            description="",
            enabled=True,
            task_kind="web_search",
            capability="web_search",
            provider="anthropic",
            effect="block_external",
            custom_block_terms_json=[],
        )
        db.add(rule)
        db.commit()

        with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
            execute_external_capability(
                AiExternalCapabilityRequest(
                    source="tests.ai_security",
                    workspace_id="workspace-1",
                    actor_user_id="user-1",
                    principal_id="user-1",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    input_texts=["public launch plan"],
                ),
                lambda execution: execution.sanitized_text(fallback="fallback"),
                settings=Settings(),
                db=db,
            )

    assert error.value.reason_code == "ai_security_policy_block_external"
    assert records[0]["status"] == "blocked"
    assert records[0]["ai_security_policy_effect"] == "block_external"
    assert records[0]["ai_security_policy_rule_id"] == rule_id
    assert "public launch plan" not in str(_audit_record_without_detected_values(records[0]))


def test_external_capability_bypasses_all_ai_security_when_enforcement_disabled(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    raw_text = "851212-1045612 이지호 api_key=sk-sensitive-token-value"
    with get_session_factory()() as db:
        settings = _get_or_create_data_protection_settings(db)
        settings.enforcement_enabled = False
        settings.enforcement_disabled_reason = "maintenance window"
        settings.external_app_actions_json = {"web-search": {"pii": "mask_and_send"}}
        db.add(
            AiSecurityPolicyRule(
                id=new_id(),
                name="Search denied",
                description="",
                enabled=True,
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                effect="block_external",
                custom_block_terms_json=[],
            )
        )
        db.commit()

        result = execute_external_capability(
            AiExternalCapabilityRequest(
                source="tests.ai_security",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                app="web-search",
                input_texts=[raw_text],
            ),
            lambda execution: execution.sanitized_text(fallback="fallback"),
            settings=Settings(),
            db=db,
        )

    assert result == raw_text
    assert records[0]["status"] == "ok"
    assert records[0]["policy_reason"] == "ai_security_enforcement_disabled"
    assert records[0]["pii_hits"] == []
    assert records[0]["blocked_entity_types"] == []
    assert records[0]["mask_applied"] is False
    assert raw_text not in str(_audit_record_without_detected_values(records[0]))


def test_external_capability_uses_configured_external_app_mask_action(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            enabled=True,
            used=True,
        ),
    )
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    sensitive_text = "Contact owner@example.com for latest public news"
    with get_session_factory()() as db:
        settings = db.get(AiSecurityDataProtectionSettings, DATA_PROTECTION_SETTINGS_ID)
        if settings is None:
            settings = AiSecurityDataProtectionSettings(
                id=DATA_PROTECTION_SETTINGS_ID,
                enforcement_enabled=True,
                custom_block_terms_json=[],
            )
            db.add(settings)
        else:
            settings.enforcement_enabled = True
        settings.external_app_actions_json = {"web-search": {"pii": "mask_and_send"}}
        db.commit()

        result = execute_external_capability(
            AiExternalCapabilityRequest(
                source="tests.ai_security",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                app="web-search",
                input_texts=[sensitive_text],
            ),
            lambda execution: execution.sanitized_text(fallback="fallback"),
            settings=Settings(),
            db=db,
        )

    assert "[masked:pii]" in result
    assert "owner@example.com" not in result
    assert records[0]["status"] == "ok"
    assert records[0]["policy_reason"] == "external_payload_masked"
    assert records[0]["mask_applied"] is True
    assert records[0]["masked_entity_types"] == ["pii:email"]
    assert records[0]["privacy_filter_status"] == "ok"
    assert sensitive_text not in str(_audit_record_without_detected_values(records[0]))
    assert records[0]["detected_values"][0]["detected_value"] == "owner@example.com"


def test_external_capability_mask_action_is_scoped_to_app(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    monkeypatch.setattr(
        masking_module,
        "detect_privacy_filter_spans",
        lambda *_args, **_kwargs: PrivacyFilterDetection(
            status="ok",
            enabled=True,
            used=True,
        ),
    )
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    with get_session_factory()() as db:
        settings = db.get(AiSecurityDataProtectionSettings, DATA_PROTECTION_SETTINGS_ID)
        if settings is None:
            settings = AiSecurityDataProtectionSettings(
                id=DATA_PROTECTION_SETTINGS_ID,
                enforcement_enabled=True,
                custom_block_terms_json=[],
            )
            db.add(settings)
        else:
            settings.enforcement_enabled = True
        settings.external_app_actions_json = {"web-search": {"pii": "mask_and_send"}}
        db.commit()

        with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
            execute_external_capability(
                AiExternalCapabilityRequest(
                    source="tests.ai_security",
                    workspace_id="workspace-1",
                    actor_user_id="user-1",
                    principal_id="user-1",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    app="research-trends",
                    input_texts=["Contact owner@example.com for latest public news"],
                ),
                lambda execution: execution.sanitized_text(fallback="fallback"),
                settings=Settings(),
                db=db,
            )

    assert error.value.reason_code == "pii_detected"
    assert records[0]["status"] == "blocked"
    assert records[0]["mask_applied"] is False


def test_external_capability_blocks_mixed_external_app_blockers(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    _patch_privacy_filter_ok(monkeypatch)
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    sensitive_text = "Contact owner@example.com about contract terms"
    with get_session_factory()() as db:
        settings = _get_or_create_data_protection_settings(db)
        settings.external_app_actions_json = {"web-search": {"pii": "mask_and_send"}}
        db.commit()

        with pytest.raises(AiExternalCapabilityPolicyViolation):
            execute_external_capability(
                AiExternalCapabilityRequest(
                    source="tests.ai_security",
                    workspace_id="workspace-1",
                    actor_user_id="user-1",
                    principal_id="user-1",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    app="web-search",
                    input_texts=[sensitive_text],
                ),
                lambda execution: execution.sanitized_text(fallback="fallback"),
                settings=Settings(),
                db=db,
            )

    assert records[0]["status"] == "blocked"
    assert records[0]["mask_applied"] is False
    assert "contract" in records[0]["blocked_entity_types"]
    assert "pii:email" in records[0]["blocked_entity_types"]
    assert sensitive_text not in str(_audit_record_without_detected_values(records[0]))


def test_external_capability_hard_blockers_override_external_app_mask(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    _patch_privacy_filter_ok(monkeypatch)
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    sensitive_text = "Use API key sk-abcdefghijklmnopqrstuvwxyz123456"
    with get_session_factory()() as db:
        settings = _get_or_create_data_protection_settings(db)
        settings.external_app_actions_json = {
            "web-search": {
                "company_sensitive_entity": "mask_and_send",
                "pii": "mask_and_send",
                "internal_url": "mask_and_send",
                "security_document": "mask_and_send",
            }
        }
        db.commit()

        with pytest.raises(AiExternalCapabilityPolicyViolation):
            execute_external_capability(
                AiExternalCapabilityRequest(
                    source="tests.ai_security",
                    workspace_id="workspace-1",
                    actor_user_id="user-1",
                    principal_id="user-1",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    app="web-search",
                    input_texts=[sensitive_text],
                ),
                lambda execution: execution.sanitized_text(fallback="fallback"),
                settings=Settings(),
                db=db,
            )

    assert records[0]["status"] == "blocked"
    assert records[0]["mask_applied"] is False
    assert "credential" in records[0]["blocked_entity_types"]
    assert sensitive_text not in str(_audit_record_without_detected_values(records[0]))


def test_external_capability_block_external_overrides_external_app_mask(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    _patch_privacy_filter_ok(monkeypatch)
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    with get_session_factory()() as db:
        settings = _get_or_create_data_protection_settings(db)
        settings.external_app_actions_json = {"web-search": {"pii": "mask_and_send"}}
        rule_id = new_id()
        db.add(
            AiSecurityPolicyRule(
                id=rule_id,
                name="Search local only",
                description="",
                enabled=True,
                app_id="web-search",
                task_kind="web_search",
                capability="web_search",
                provider="anthropic",
                effect="block_external",
                custom_block_terms_json=[],
            )
        )
        db.commit()

        with pytest.raises(AiExternalCapabilityPolicyViolation) as error:
            execute_external_capability(
                AiExternalCapabilityRequest(
                    source="tests.ai_security",
                    workspace_id="workspace-1",
                    actor_user_id="user-1",
                    principal_id="user-1",
                    task_kind="web_search",
                    capability="web_search",
                    provider="anthropic",
                    app="web-search",
                    input_texts=["Contact owner@example.com for public news"],
                ),
                lambda execution: execution.sanitized_text(fallback="fallback"),
                settings=Settings(),
                db=db,
            )

    assert error.value.reason_code == "ai_security_policy_block_external"
    assert records[0]["status"] == "blocked"
    assert records[0]["ai_security_policy_effect"] == "block_external"
    assert records[0]["ai_security_policy_rule_id"] == rule_id
    assert records[0]["mask_applied"] is False
    assert "owner@example.com" not in str(_audit_record_without_detected_values(records[0]))
    assert records[0]["detected_values"][0]["detected_value"] == "owner@example.com"


def test_external_capability_exception_allows_internal_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client is not None
    records: list[dict] = []
    monkeypatch.setattr(
        external_gateway,
        "log_ai_external_call",
        lambda **kwargs: records.append(kwargs),
    )
    with get_session_factory()() as db:
        _get_or_create_data_protection_settings(db).enforcement_enabled = True
        exception = AiSecurityExternalTransferException(
            id=new_id(),
            name="Image brief internal context export",
            description="",
            enabled=True,
            task_kind="image_brief",
            capability="image_brief",
            provider="openai",
            allowed_blocker_types_json=["internal_context"],
            reason="approved",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        db.add(exception)
        db.commit()

        result = execute_external_capability(
            AiExternalCapabilityRequest(
                source="tests.ai_security",
                workspace_id="workspace-1",
                actor_user_id="user-1",
                principal_id="user-1",
                task_kind="image_brief",
                capability="image_brief",
                provider="openai",
                input_texts=["internal deployment evidence"],
                source_kinds=("docs",),
                content_origin="internal_context",
            ),
            lambda execution: execution.sanitized_text(fallback="fallback"),
            settings=Settings(),
            db=db,
        )

    assert result == "internal deployment evidence"
    assert records[0]["status"] == "ok"
    assert records[0]["policy_reason"] == EXTERNAL_TRANSFER_EXCEPTION_REASON
    assert records[0]["external_transfer_exception_id"] == exception.id
    assert "internal deployment evidence" not in str(
        _audit_record_without_detected_values(records[0])
    )
