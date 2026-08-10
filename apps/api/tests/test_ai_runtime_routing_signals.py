from __future__ import annotations

from open_work_hub_api.domains.ai.runtime.routing_signals import (
    LONG_DOC_MAX_TOKENS_THRESHOLD,
    select_runtime_profile_signal,
)


def test_runtime_profile_ignores_semantic_keywords() -> None:
    signal = select_runtime_profile_signal(
        messages=[
            {
                "role": "user",
                "content": "보고서로 분석하고 삭제 승인 create update도 검토해줘",
            }
        ],
        allowed_app_ids=["pms"],
        max_tokens=None,
    )

    assert signal.runtime_profile == "interactive_read"
    assert signal.reason_codes == ("default_interactive_read",)


def test_runtime_profile_uses_scope_and_size_signals() -> None:
    multi_scope_signal = select_runtime_profile_signal(
        messages=[{"role": "user", "content": "요약해줘"}],
        allowed_app_ids=["pms", "docs"],
        max_tokens=None,
    )
    large_budget_signal = select_runtime_profile_signal(
        messages=[{"role": "user", "content": "요약해줘"}],
        allowed_app_ids=None,
        max_tokens=LONG_DOC_MAX_TOKENS_THRESHOLD,
    )

    assert multi_scope_signal.runtime_profile == "grounded_report"
    assert multi_scope_signal.reason_codes == ("multi_app_scope",)
    assert large_budget_signal.runtime_profile == "long_doc"
    assert large_budget_signal.reason_codes == ("large_output_budget",)
