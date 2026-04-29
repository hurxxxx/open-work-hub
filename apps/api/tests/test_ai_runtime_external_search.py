from __future__ import annotations

import json

from aidoo_api.core.settings import Settings
from aidoo_api.domains.ai.runtime.external_egress import evaluate_external_egress
from aidoo_api.domains.ai.runtime.external_search import (
    EXTERNAL_SEARCH_ADAPTER_ID,
    build_external_search_request,
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
