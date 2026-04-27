from __future__ import annotations

from aidoo_api.domains.ai.runtime.routing import select_runtime_profile


def _messages(text: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": text}]


def test_runtime_profile_defaults_to_interactive_read() -> None:
    decision = select_runtime_profile(
        messages=_messages("회의 결정사항 알려줘"),
        allowed_app_ids=["meeting"],
        max_tokens=None,
        graph_enabled=False,
    )

    assert decision.runtime_profile == "interactive_read"
    assert decision.graph_gate == "disabled"
    assert "default_interactive_read" in decision.reason_codes


def test_runtime_profile_selects_grounded_report_for_report_signal() -> None:
    decision = select_runtime_profile(
        messages=_messages("회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘"),
        allowed_app_ids=["meeting", "pms"],
        max_tokens=None,
        graph_enabled=True,
    )

    assert decision.runtime_profile == "grounded_report"
    assert decision.graph_gate == "eligible"
    assert "grounded_report_signal" in decision.reason_codes


def test_runtime_profile_selects_long_doc_for_large_budget() -> None:
    decision = select_runtime_profile(
        messages=_messages("전체 문서를 분석해줘"),
        allowed_app_ids=["docs"],
        max_tokens=40_000,
        graph_enabled=True,
    )

    assert decision.runtime_profile == "long_doc"
    assert decision.graph_gate == "ineligible"
    assert "large_output_budget" in decision.reason_codes


def test_runtime_profile_selects_high_risk_action_for_write_signal() -> None:
    decision = select_runtime_profile(
        messages=_messages("PMS 이슈를 생성해줘"),
        allowed_app_ids=["pms"],
        max_tokens=None,
        graph_enabled=True,
    )

    assert decision.runtime_profile == "high_risk_action"
    assert decision.graph_gate == "eligible"
    assert "write_or_external_action_signal" in decision.reason_codes


def test_runtime_profile_keeps_text_only_scope_out_of_high_risk_action() -> None:
    decision = select_runtime_profile(
        messages=_messages("PMS 이슈를 생성해줘"),
        allowed_app_ids=[],
        max_tokens=None,
        graph_enabled=True,
    )

    assert decision.runtime_profile == "interactive_read"
    assert decision.graph_gate == "ineligible"
    assert "text_only_scope" in decision.reason_codes
