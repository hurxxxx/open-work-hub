from __future__ import annotations

import json
from pathlib import Path

from aidoo_api.core.settings import Settings
from aidoo_api.domains.ai.runtime.external_egress import (
    allowed_external_providers,
    evaluate_external_egress,
    normalize_external_provider,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ai_runtime"
SETTING_ALIASES = {
    "ai_external_llm_enabled": "AIDOO_AI_EXTERNAL_LLM_ENABLED",
    "ai_external_planning_enabled": "AIDOO_AI_EXTERNAL_PLANNING_ENABLED",
    "ai_external_reasoning_enabled": "AIDOO_AI_EXTERNAL_REASONING_ENABLED",
    "ai_external_quality_review_enabled": "AIDOO_AI_EXTERNAL_QUALITY_REVIEW_ENABLED",
    "ai_external_search_enabled": "AIDOO_AI_EXTERNAL_SEARCH_ENABLED",
    "ai_allowed_external_providers": "AIDOO_AI_ALLOWED_EXTERNAL_PROVIDERS",
    "ai_default_external_search_provider": "AIDOO_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER",
}


def _settings(**overrides):
    aliased_overrides = {
        SETTING_ALIASES.get(key, key): value for key, value in overrides.items()
    }
    return Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
        **aliased_overrides,
    )


def test_external_provider_aliases_normalize_to_policy_names() -> None:
    settings = _settings(ai_allowed_external_providers="openai,claude")

    assert normalize_external_provider("openai") == "openai"
    assert normalize_external_provider("claude") == "anthropic"
    assert normalize_external_provider("anthropic") == "anthropic"
    assert normalize_external_provider("unknown") is None
    assert allowed_external_providers(settings) == ("openai", "anthropic")


def test_external_planning_is_denied_until_global_and_capability_flags_enable() -> None:
    default_decision = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(),
    )
    capability_disabled = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(ai_external_llm_enabled=True),
    )
    allowed = evaluate_external_egress(
        capability="planning",
        provider="claude",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(
            ai_external_llm_enabled=True,
            ai_external_planning_enabled=True,
        ),
    )

    assert default_decision.allow_external is False
    assert default_decision.reason == "external_llm_disabled"
    assert capability_disabled.allow_external is False
    assert capability_disabled.reason == "capability_disabled"
    assert allowed.allow_external is True
    assert allowed.provider == "anthropic"
    assert allowed.sanitized_prompt == "공개 규격만 기준으로 초기 분석해줘"


def test_external_egress_denies_provider_outside_allowlist() -> None:
    decision = evaluate_external_egress(
        capability="planning",
        provider="anthropic",
        text="공개 규격만 기준으로 초기 분석해줘",
        settings=_settings(
            ai_external_llm_enabled=True,
            ai_external_planning_enabled=True,
            ai_allowed_external_providers="openai",
        ),
    )

    assert decision.allow_external is False
    assert decision.reason == "provider_not_allowed"
    assert decision.provider == "anthropic"


def test_external_egress_blocks_pii_for_planning() -> None:
    decision = evaluate_external_egress(
        capability="planning",
        provider="openai",
        text="contact@example.com 에게 보낼 답변 초안을 분석해줘",
        settings=_settings(
            ai_external_llm_enabled=True,
            ai_external_planning_enabled=True,
        ),
    )

    assert decision.allow_external is False
    assert decision.reason == "pii_detected"
    assert decision.pii_hits == ["email"]


def test_external_search_sanitizer_matches_seed_leakage_cases() -> None:
    fixture = json.loads(
        (FIXTURE_DIR / "sanitizer_leakage_cases.json").read_text(encoding="utf-8")
    )
    settings = _settings(ai_external_search_enabled=True)

    for case in fixture["cases"]:
        decision = evaluate_external_egress(
            capability="search",
            provider="openai",
            text=case["input"]["user_message"],
            settings=settings,
        )

        assert decision.allow_external is case["expected"]["allow_external"]
        assert set(decision.removed_entity_types) == set(
            case["expected"]["removed_entity_types"]
        )
        assert decision.sanitized_query == case["expected"]["sanitized_query"]


def test_external_search_blocks_sensitive_cost_contract_context() -> None:
    decision = evaluate_external_egress(
        capability="search",
        provider="openai",
        text="BOM 원가 12345원과 계약 조건을 넣어서 공개 공급사 가격을 검색해줘.",
        settings=_settings(ai_external_search_enabled=True),
    )

    assert decision.allow_external is False
    assert decision.reason == "sensitive_entity_blocked"
    assert decision.blocked_entity_types == ["bom", "contract_term", "cost"]
    assert decision.sanitized_query == ""
