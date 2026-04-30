from __future__ import annotations

import pytest
from pydantic import ValidationError

from aidoo_api.domains.ai.manager_runtime import (
    AiManagerInput,
    ManagerPromptPayload,
    LocalAgentResult,
    LocalAgentTask,
    ManagerPlan,
    ManagerReview,
    build_manager_prompt_payload,
    detect_forbidden_external_payload_entities,
)


def test_manager_prompt_payload_allows_safe_raw_prompt() -> None:
    payload = build_manager_prompt_payload("이번 주 회의 내용을 요약하고 후속 일을 정리해줘.")

    assert payload.status == "raw_allowed"
    assert payload.prompt == "이번 주 회의 내용을 요약하고 후속 일을 정리해줘."
    assert payload.removed_entity_types == []


def test_manager_prompt_payload_redacts_enterprise_identifiers() -> None:
    payload = build_manager_prompt_payload(
        "가상고객A의 TEST-DX-2400 주문서 ORD-TEST-001 기준으로 리스크를 봐줘."
    )

    assert payload.status == "redacted"
    assert set(payload.removed_entity_types) == {"customer", "product_code", "order_id"}
    assert "가상고객A" not in payload.prompt
    assert "TEST-DX-2400" not in payload.prompt
    assert "ORD-TEST-001" not in payload.prompt
    assert "[redacted:customer]" in payload.prompt


def test_manager_prompt_payload_redaction_tokens_are_safe() -> None:
    payload = build_manager_prompt_payload("ORD-ABC-1 가격을 확인해줘.")

    assert payload.status == "redacted"
    assert detect_forbidden_external_payload_entities(payload.prompt) == []
    assert "[redacted:order_id]" in payload.prompt
    assert "[redacted:price]" in payload.prompt


def test_manager_prompt_payload_blocks_empty_prompt() -> None:
    payload = build_manager_prompt_payload("  ")

    assert payload.status == "blocked"
    assert payload.prompt == ""
    assert payload.blocked_reason == "empty_prompt"


def test_manager_prompt_payload_rejects_unsafe_raw_status() -> None:
    with pytest.raises(ValidationError, match="payload contains forbidden entity types"):
        ManagerPromptPayload(
            status="raw_allowed",
            prompt="가상고객A 주문서를 봐줘",
        )


def test_ai_manager_input_rejects_sensitive_metadata() -> None:
    with pytest.raises(ValidationError, match="payload contains forbidden entity types"):
        AiManagerInput(
            prompt=build_manager_prompt_payload("공개 자료 기준으로 정리해줘"),
            available_agent_ids=["domain.docs"],
            workspace_metadata={"selected_customer": "가상고객A"},
        )


def test_local_agent_result_allows_redacted_summary_only() -> None:
    result = LocalAgentResult(
        agent_id="domain.docs",
        status="completed",
        redacted_summary="문서 3건에서 일정 지연 가능성이 확인되었습니다.",
        artifact_refs=["artifact:summary-1"],
        coverage={"covered": ["일정", "리스크"], "missing": []},
        sensitivity_labels=["internal"],
    )

    assert result.redacted_summary.startswith("문서 3건")
    assert result.artifact_refs == ["artifact:summary-1"]


def test_local_agent_result_rejects_raw_internal_data() -> None:
    with pytest.raises(ValidationError, match="payload contains forbidden entity types"):
        LocalAgentResult(
            agent_id="domain.pms",
            status="completed",
            redacted_summary="가상고객A TEST-DX-2400 ORD-TEST-001 계약 리스크가 있습니다.",
            coverage={"covered": ["계약"]},
        )


def test_local_agent_result_requires_blocked_reason() -> None:
    with pytest.raises(ValidationError, match="blocked local result must include blocked_reason"):
        LocalAgentResult(
            agent_id="domain.docs",
            status="blocked",
        )


def test_manager_contracts_use_local_agent_task_boundary() -> None:
    task = LocalAgentTask(
        agent_id="domain.rag",
        objective="Find internal evidence and return only a summary.",
        allowed_tool_names=["rag.query"],
        context_boundary="workspace_current",
        expected_output="redacted summary with gaps",
    )
    plan = ManagerPlan(objective="Answer with internal evidence", tasks=[task])
    review = ManagerReview(decision="retry", gap_summary="Need one more source.", next_tasks=[task])

    assert plan.tasks == [task]
    assert review.next_tasks == [task]


def test_detect_forbidden_entities_includes_pii() -> None:
    detected = detect_forbidden_external_payload_entities("담당자 test@example.com 에게 ORD-TEST-001 확인")

    assert detected == ["order_id", "product_code", "pii:email"]
