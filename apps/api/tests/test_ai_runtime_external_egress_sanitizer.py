from __future__ import annotations

from ai_do_api.domains.ai.runtime.external_egress_sanitizer import (
    build_external_egress_sanitization,
    detect_enterprise_entity_types,
    explicitly_disallows_external_search,
    sanitize_external_prompt,
    sanitize_external_search_query,
)


def test_external_egress_sanitizer_blocks_sensitive_entity_context() -> None:
    sanitization = build_external_egress_sanitization(
        "BOM 원가 12345원과 계약 조건을 넣어서 공개 공급사 가격을 검색해줘."
    )

    assert sanitization.removed_entity_types == ["bom", "cost", "contract_term"]
    assert sanitization.blocked_entity_types == ["bom", "contract_term", "cost"]
    assert sanitization.sanitized_query == ""


def test_external_egress_sanitizer_detects_no_external_search_directives() -> None:
    for prompt in (
        "외부 검색 금지. 내부 자료만 써줘.",
        "인터넷검색하지말고 CE 인증 기준을 요약해줘.",
        "Do not search the web for this.",
        "dont search online; summarize internal notes.",
    ):
        assert explicitly_disallows_external_search(prompt) is True

    assert explicitly_disallows_external_search("Search online for public CE rules") is False


def test_external_egress_sanitizer_removes_enterprise_tokens_and_synthesizes_query() -> None:
    text = (
        "ORD-ALPHA-1 AB-1234 VIP고객 EU CE 인증 리스크를 공개 자료로 확인해줘. "
        "ORD-ALPHA-2 AB-9999"
    )

    sanitization = build_external_egress_sanitization(text)

    assert sanitization.removed_entity_types == ["order_id", "product_code", "customer"]
    assert sanitization.blocked_entity_types == []
    assert "ORD-ALPHA-1" not in sanitization.sanitized_prompt
    assert "ORD-ALPHA-2" not in sanitization.sanitized_prompt
    assert "AB-1234" not in sanitization.sanitized_prompt
    assert "AB-9999" not in sanitization.sanitized_prompt
    assert "VIP고객" not in sanitization.sanitized_prompt
    assert sanitization.sanitized_query == (
        "industrial electronic component EU CE certification regulatory requirements"
    )


def test_external_egress_sanitizer_preserves_public_prompt_when_no_tokens() -> None:
    prompt = "공개 규격만 기준으로 초기 분석해줘"

    assert detect_enterprise_entity_types(prompt) == []
    assert sanitize_external_prompt(prompt) == prompt
    assert sanitize_external_search_query(prompt) == prompt


def test_external_egress_sanitizer_removes_currency_and_truncates_prompt() -> None:
    prompt = f"공개 규격 검토 12345원 {'x' * 1300}"

    sanitized = sanitize_external_prompt(prompt)

    assert "12345" not in sanitized
    assert "원" not in sanitized
    assert sanitized.startswith("공개 규격 검토")
    assert len(sanitized) == 1200
