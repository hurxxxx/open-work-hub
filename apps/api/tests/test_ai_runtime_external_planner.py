from __future__ import annotations

import json

from aidoo_api.core.settings import Settings
from aidoo_api.domains.ai.runtime.external_egress import evaluate_external_egress
from aidoo_api.domains.ai.runtime.external_planner import (
    EXTERNAL_PLANNER_ADAPTER_ID,
    build_external_planner_request,
    execute_mock_external_planner,
    summarize_external_planner_execution,
    summarize_external_planner_request,
)


def _settings(**overrides):
    aliases = {
        "ai_external_llm_enabled": "AIDOO_AI_EXTERNAL_LLM_ENABLED",
        "ai_external_planning_enabled": "AIDOO_AI_EXTERNAL_PLANNING_ENABLED",
        "ai_external_search_enabled": "AIDOO_AI_EXTERNAL_SEARCH_ENABLED",
    }
    return Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
        **{aliases.get(key, key): value for key, value in overrides.items()},
    )


def test_external_planner_stays_disabled_when_egress_denies() -> None:
    egress = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(),
    )

    request = build_external_planner_request(
        egress_decision=egress,
        runtime_profile="grounded_report",
        agent_ids=["domain.pms", "writer.template"],
    )

    assert request.adapter_id == EXTERNAL_PLANNER_ADAPTER_ID
    assert request.status == "disabled"
    assert request.disabled_reason == "egress_denied"
    assert request.egress_reason == "external_llm_disabled"
    assert request.messages == []


def test_external_planner_rejects_non_planning_egress_decision() -> None:
    egress = evaluate_external_egress(
        capability="search",
        provider="openai",
        text="EU CE 인증 요건 검색",
        settings=_settings(ai_external_search_enabled=True),
    )

    request = build_external_planner_request(
        egress_decision=egress,
        runtime_profile="grounded_report",
        agent_ids=["search.executor", "writer.template"],
    )

    assert request.status == "disabled"
    assert request.disabled_reason == "capability_mismatch"
    assert request.messages == []


def test_external_planner_prompt_uses_only_sanitized_prompt() -> None:
    raw_prompt = "가상고객A의 TEST-DX-2400 주문서 ORD-TEST-001 기준으로 EU CE 인증 리스크를 분석해줘."
    egress = evaluate_external_egress(
        capability="planning",
        provider="claude",
        text=raw_prompt,
        settings=_settings(
            ai_external_llm_enabled=True,
            ai_external_planning_enabled=True,
        ),
    )

    request = build_external_planner_request(
        egress_decision=egress,
        runtime_profile="grounded_report",
        agent_ids=["domain.pms", "search.executor", "writer.template"],
    )

    assert egress.allow_external is True
    assert egress.provider == "anthropic"
    assert request.status == "ready"
    assert request.provider == "anthropic"
    assert len(request.messages) == 2
    rendered_messages = json.dumps(request.messages, ensure_ascii=False)
    assert "가상고객A" not in rendered_messages
    assert "TEST-DX-2400" not in rendered_messages
    assert "ORD-TEST-001" not in rendered_messages
    assert egress.sanitized_prompt in rendered_messages
    user_payload = json.loads(request.messages[1]["content"])
    assert user_payload == {
        "available_agent_ids": ["domain.pms", "search.executor", "writer.template"],
        "runtime_profile": "grounded_report",
        "sanitized_user_prompt": egress.sanitized_prompt,
    }


def test_external_planner_summary_excludes_prompt_payload() -> None:
    egress = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(
            ai_external_llm_enabled=True,
            ai_external_planning_enabled=True,
        ),
    )
    request = build_external_planner_request(
        egress_decision=egress,
        runtime_profile="interactive_read",
        agent_ids=["writer.template"],
    )

    summary = summarize_external_planner_request(request)

    assert summary == {
        "adapter_id": EXTERNAL_PLANNER_ADAPTER_ID,
        "status": "ready",
        "provider": "openai",
        "disabled_reason": None,
        "egress_reason": "allowed",
        "message_count": 2,
    }
    assert "공개 규격" not in json.dumps(summary, ensure_ascii=False)


def test_mock_external_planner_execution_requires_explicit_flag() -> None:
    egress = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(
            ai_external_llm_enabled=True,
            ai_external_planning_enabled=True,
        ),
    )
    request = build_external_planner_request(
        egress_decision=egress,
        runtime_profile="grounded_report",
        agent_ids=["domain.pms", "search.executor", "writer.template"],
    )

    disabled = execute_mock_external_planner(request, execution_enabled=False)
    completed = execute_mock_external_planner(request, execution_enabled=True)

    assert summarize_external_planner_execution(disabled) == {
        "adapter_id": EXTERNAL_PLANNER_ADAPTER_ID,
        "execution_provider": "mock",
        "status": "disabled",
        "provider": "openai",
        "disabled_reason": "execution_flag_disabled",
        "planned_agent_count": 0,
        "intent_hint": None,
        "output_kind_hint": None,
        "latency_ms": 0,
        "retry_count": 0,
        "error_class": None,
        "estimated_cost_microunits": 0,
        "raw_output_persisted": False,
    }
    assert summarize_external_planner_execution(completed) == {
        "adapter_id": EXTERNAL_PLANNER_ADAPTER_ID,
        "execution_provider": "mock",
        "status": "completed",
        "provider": "openai",
        "disabled_reason": None,
        "planned_agent_count": 3,
        "intent_hint": "report",
        "output_kind_hint": "artifact",
        "latency_ms": 0,
        "retry_count": 0,
        "error_class": None,
        "estimated_cost_microunits": 0,
        "raw_output_persisted": False,
    }


def test_mock_external_planner_skips_when_request_not_ready() -> None:
    egress = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(),
    )
    request = build_external_planner_request(
        egress_decision=egress,
        runtime_profile="grounded_report",
        agent_ids=["writer.template"],
    )

    result = execute_mock_external_planner(request, execution_enabled=True)

    assert result.status == "skipped"
    assert result.disabled_reason == "request_not_ready"
    assert result.planned_agent_ids == []


def test_mock_external_planner_records_forced_provider_error() -> None:
    egress = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(
            ai_external_llm_enabled=True,
            ai_external_planning_enabled=True,
        ),
    )
    request = build_external_planner_request(
        egress_decision=egress,
        runtime_profile="grounded_report",
        agent_ids=["domain.pms", "writer.template"],
    )

    result = execute_mock_external_planner(
        request,
        execution_enabled=True,
        force_error_class="provider_timeout",
    )

    assert summarize_external_planner_execution(result) == {
        "adapter_id": EXTERNAL_PLANNER_ADAPTER_ID,
        "execution_provider": "mock",
        "status": "failed",
        "provider": "openai",
        "disabled_reason": None,
        "planned_agent_count": 0,
        "intent_hint": None,
        "output_kind_hint": None,
        "latency_ms": 0,
        "retry_count": 0,
        "error_class": "provider_timeout",
        "estimated_cost_microunits": 0,
        "raw_output_persisted": False,
    }
