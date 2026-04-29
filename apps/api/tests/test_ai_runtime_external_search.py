from __future__ import annotations

import json

from aidoo_api.core.settings import Settings
from aidoo_api.domains.ai.runtime.external_egress import evaluate_external_egress
from aidoo_api.domains.ai.runtime.external_search import (
    EXTERNAL_SEARCH_ADAPTER_ID,
    build_external_search_request,
    execute_mock_external_search,
    summarize_external_search_execution,
    summarize_external_search_request,
)


def _settings(**overrides):
    aliases = {
        "ai_external_planning_enabled": "AIDOO_AI_EXTERNAL_PLANNING_ENABLED",
        "ai_external_search_enabled": "AIDOO_AI_EXTERNAL_SEARCH_ENABLED",
    }
    return Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
        **{aliases.get(key, key): value for key, value in overrides.items()},
    )


def test_external_search_stays_disabled_when_egress_denies() -> None:
    egress = evaluate_external_egress(
        capability="search",
        provider="openai",
        text="EU CE 인증 요건 검색",
        settings=_settings(),
    )

    request = build_external_search_request(egress_decision=egress)

    assert request.adapter_id == EXTERNAL_SEARCH_ADAPTER_ID
    assert request.status == "disabled"
    assert request.disabled_reason == "egress_denied"
    assert request.egress_reason == "capability_disabled"
    assert request.query == ""


def test_external_search_rejects_non_search_egress_decision() -> None:
    egress = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(ai_external_planning_enabled=True),
    )

    request = build_external_search_request(egress_decision=egress)

    assert request.status == "disabled"
    assert request.disabled_reason == "capability_mismatch"
    assert request.query == ""


def test_external_search_request_uses_only_sanitized_query() -> None:
    raw_prompt = "가상고객A의 TEST-DX-2400 주문서 ORD-TEST-001 기준으로 EU CE 인증 리스크를 검색해줘."
    egress = evaluate_external_egress(
        capability="search",
        provider="openai",
        text=raw_prompt,
        settings=_settings(ai_external_search_enabled=True),
    )

    request = build_external_search_request(egress_decision=egress)

    assert egress.allow_external is True
    assert request.status == "ready"
    assert request.query == "industrial electronic component EU CE certification regulatory requirements"
    rendered = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    assert "가상고객A" not in rendered
    assert "TEST-DX-2400" not in rendered
    assert "ORD-TEST-001" not in rendered


def test_external_search_summary_excludes_query_payload() -> None:
    egress = evaluate_external_egress(
        capability="search",
        provider="openai",
        text="EU CE 인증 요건 검색",
        settings=_settings(ai_external_search_enabled=True),
    )
    request = build_external_search_request(egress_decision=egress)

    summary = summarize_external_search_request(request)

    assert summary == {
        "adapter_id": EXTERNAL_SEARCH_ADAPTER_ID,
        "status": "ready",
        "provider": "openai",
        "disabled_reason": None,
        "egress_reason": "allowed",
        "query_present": True,
    }
    assert "EU CE" not in json.dumps(summary, ensure_ascii=False)


def test_mock_external_search_execution_requires_explicit_flag() -> None:
    egress = evaluate_external_egress(
        capability="search",
        provider="openai",
        text="EU CE 인증 요건 검색",
        settings=_settings(ai_external_search_enabled=True),
    )
    request = build_external_search_request(egress_decision=egress)

    disabled = execute_mock_external_search(request, execution_enabled=False)
    completed = execute_mock_external_search(request, execution_enabled=True)

    assert summarize_external_search_execution(disabled) == {
        "adapter_id": EXTERNAL_SEARCH_ADAPTER_ID,
        "execution_provider": "mock",
        "status": "disabled",
        "provider": "openai",
        "disabled_reason": "execution_flag_disabled",
        "query_digest": None,
        "cache_key": None,
        "cache_hit": False,
        "result_count": 0,
        "result_refs": [],
        "source_kinds": [],
        "latency_ms": 0,
        "retry_count": 0,
        "error_class": None,
        "estimated_cost_microunits": 0,
        "raw_output_persisted": False,
    }
    completed_summary = summarize_external_search_execution(completed)
    assert completed_summary["adapter_id"] == EXTERNAL_SEARCH_ADAPTER_ID
    assert completed_summary["execution_provider"] == "mock"
    assert completed_summary["status"] == "completed"
    assert completed_summary["provider"] == "openai"
    assert completed_summary["disabled_reason"] is None
    assert completed_summary["query_digest"]
    assert completed_summary["cache_key"] == (
        f"external_search_v0:mock:openai:{completed_summary['query_digest']}"
    )
    assert completed_summary["cache_hit"] is False
    assert completed_summary["result_count"] == 2
    assert completed_summary["result_refs"] == [
        f"mock://external-search/{completed_summary['query_digest']}/result-1",
        f"mock://external-search/{completed_summary['query_digest']}/result-2",
    ]
    assert completed_summary["source_kinds"] == ["public_web_mock"]
    assert completed_summary["latency_ms"] == 0
    assert completed_summary["retry_count"] == 0
    assert completed_summary["error_class"] is None
    assert completed_summary["estimated_cost_microunits"] == 0
    assert completed_summary["raw_output_persisted"] is False
    assert "EU CE" not in json.dumps(completed_summary, ensure_ascii=False)


def test_mock_external_search_skips_when_request_not_ready() -> None:
    egress = evaluate_external_egress(
        capability="search",
        provider="openai",
        text="BOM 원가 12345원과 계약 조건을 넣어서 공개 공급사 가격을 검색해줘.",
        settings=_settings(ai_external_search_enabled=True),
    )
    request = build_external_search_request(egress_decision=egress)

    result = execute_mock_external_search(request, execution_enabled=True)

    assert result.status == "skipped"
    assert result.disabled_reason == "request_not_ready"
    assert result.result_count == 0


def test_mock_external_search_records_forced_provider_error() -> None:
    egress = evaluate_external_egress(
        capability="search",
        provider="openai",
        text="EU CE 인증 요건 검색",
        settings=_settings(ai_external_search_enabled=True),
    )
    request = build_external_search_request(egress_decision=egress)

    result = execute_mock_external_search(
        request,
        execution_enabled=True,
        force_error_class="provider_timeout",
    )
    summary = summarize_external_search_execution(result)

    assert summary["adapter_id"] == EXTERNAL_SEARCH_ADAPTER_ID
    assert summary["execution_provider"] == "mock"
    assert summary["status"] == "failed"
    assert summary["provider"] == "openai"
    assert summary["disabled_reason"] is None
    assert summary["query_digest"]
    assert summary["cache_key"] == (
        f"external_search_v0:mock:openai:{summary['query_digest']}"
    )
    assert summary["cache_hit"] is False
    assert summary["result_count"] == 0
    assert summary["result_refs"] == []
    assert summary["source_kinds"] == []
    assert summary["latency_ms"] == 0
    assert summary["retry_count"] == 0
    assert summary["error_class"] == "provider_timeout"
    assert summary["estimated_cost_microunits"] == 0
    assert summary["raw_output_persisted"] is False
