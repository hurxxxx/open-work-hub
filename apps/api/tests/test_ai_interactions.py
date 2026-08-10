from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.ai.audit import log_ai_external_call, log_llm_call
from open_work_hub_api.domains.ai.interactions import AiInteraction
from open_work_hub_api.domains.ai.models import AiSecurityDetectedValue
from open_work_hub_api.domains.auth.models import AuditLog


def test_llm_audit_writes_raw_free_ai_interaction(client: TestClient) -> None:
    log_llm_call(
        source="tests.ai_interactions",
        actor_user_id=None,
        principal_kind="system",
        principal_id=None,
        workspace_id="workspace-1",
        task_kind="chatbot",
        app_id="test-chatbot",
        policy="local_only",
        chosen_pool="local",
        decision_reason="policy_local_only",
        forced_local=False,
        pii_hits=[],
        model="local-test-model",
        status="ok",
        latency_ms=12,
        usage={"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8},
        context_strategy="test_context",
        conversation_id="conversation-1",
    )

    with get_session_factory()() as db:
        row = db.scalars(select(AiInteraction)).one()

    assert row.action == "llm_call"
    assert row.source == "tests.ai_interactions"
    assert row.task_kind == "chatbot"
    assert row.pool == "local"
    assert row.model == "local-test-model"
    assert row.status == "ok"
    assert row.latency_ms == 12
    assert row.usage_json == {
        "prompt_tokens": 3,
        "completion_tokens": 5,
        "total_tokens": 8,
    }
    assert row.conversation_id == "conversation-1"
    assert row.metadata_json == {
        "app_id": "test-chatbot",
        "policy": "local_only",
        "decision_reason": "policy_local_only",
        "forced_local": False,
        "context_strategy": "test_context",
    }


def test_external_audit_writes_usage_without_raw_input(client: TestClient) -> None:
    raw_input = "confidential launch plan"
    log_ai_external_call(
        source="tests.ai_interactions.external",
        actor_user_id=None,
        principal_kind="system",
        principal_id=None,
        workspace_id="workspace-1",
        task_kind="web_search",
        capability="web_search",
        provider="anthropic",
        status="ok",
        latency_ms=30,
        policy_reason="allowed",
        pii_hits=[],
        input_text_count=1,
        input_char_count=len(raw_input),
        usage={"input_tokens": 11, "output_tokens": 13},
        metadata={"profile_id": "general", "model": "claude-test"},
        conversation_id="conversation-2",
    )

    with get_session_factory()() as db:
        row = db.scalars(select(AiInteraction)).one()

    assert row.action == "ai_external_call"
    assert row.task_kind == "web_search"
    assert row.capability == "web_search"
    assert row.provider == "anthropic"
    assert row.usage_json == {"input_tokens": 11, "output_tokens": 13}
    assert row.input_text_count == 1
    assert row.input_char_count == len(raw_input)
    assert row.conversation_id == "conversation-2"
    assert "confidential launch plan" not in str(row.__dict__)


def test_external_audit_records_detected_values_for_observability(
    client: TestClient,
) -> None:
    assert client is not None

    log_ai_external_call(
        source="tests.ai_interactions.external",
        actor_user_id=None,
        principal_kind="system",
        principal_id=None,
        workspace_id="synthetic-workspace",
        task_kind="web_search",
        capability="web_search",
        provider="anthropic",
        app_id="web-search",
        status="blocked",
        latency_ms=0,
        policy_reason="hard_external_transfer_blocker",
        detected_values=[
            {
                "detector": "regex",
                "entity_type": "credential",
                "blocker_type": "credential",
                "detected_value": "api_key",
                "occurrence_count": 1,
            }
        ],
    )

    with get_session_factory()() as db:
        audit_log = db.scalars(select(AuditLog)).one()
        detected_value = db.scalars(select(AiSecurityDetectedValue)).one()

    assert audit_log.payload["app_id"] == "web-search"
    assert detected_value.audit_log_id == audit_log.id
    assert detected_value.workspace_id == "synthetic-workspace"
    assert detected_value.app_id == "web-search"
    assert detected_value.detector == "regex"
    assert detected_value.entity_type == "credential"
    assert detected_value.detected_value == "api_key"
