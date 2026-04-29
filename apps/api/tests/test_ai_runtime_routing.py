from __future__ import annotations

import json
from pathlib import Path

from aidoo_api.domains.ai.runtime.graph_execution import (
    GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID,
    GRAPH_NODE_RUNNER_ADAPTER_ID,
    attach_graph_execution_adapter_decision,
    build_graph_execution_system_prompt,
)
from aidoo_api.domains.ai.runtime.manager_validation import ManagerGraphValidationResult
from aidoo_api.domains.ai.runtime.routing import (
    attach_manager_graph_validation_result,
    attach_trace_only_graph_validation,
    select_runtime_profile,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ai_runtime"


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
    assert decision.graph_fallback_reason == "feature_disabled"
    assert decision.graph_used is False
    assert decision.graph_validation_status == "not_applicable"
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
    assert decision.graph_fallback_reason == "graph_runtime_not_implemented"
    assert decision.graph_used is False
    assert decision.graph_validation_status == "not_applicable"
    assert "grounded_report_signal" in decision.reason_codes


def test_trace_only_graph_validation_marks_candidate_unavailable() -> None:
    decision = select_runtime_profile(
        messages=_messages("회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘"),
        allowed_app_ids=["meeting", "pms"],
        max_tokens=None,
        graph_enabled=True,
    )

    traced = attach_trace_only_graph_validation(
        decision,
        registry_agent_count=9,
        write_agent_count=1,
    )

    assert traced.graph_gate == "eligible"
    assert traced.graph_used is False
    assert traced.graph_validation_status == "candidate_unavailable"
    assert traced.graph_validation_fallback_reason == "graph_runtime_not_implemented"
    assert traced.graph_registry_agent_count == 9
    assert traced.graph_write_agent_count == 1


def test_manager_graph_validation_result_marks_accepted() -> None:
    decision = select_runtime_profile(
        messages=_messages("회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘"),
        allowed_app_ids=["meeting", "pms"],
        max_tokens=None,
        graph_enabled=True,
    )

    traced = attach_manager_graph_validation_result(
        decision,
        validation=ManagerGraphValidationResult(accepted=True, graph=None),
        registry_agent_count=10,
        write_agent_count=1,
        graph_candidate_summary={
            "intent": "report",
            "risk": "medium",
            "output_kind": "artifact",
            "requires_approval_preview": False,
            "invocation_agent_ids": [],
        },
    )

    assert traced.graph_gate == "eligible"
    assert traced.graph_used is False
    assert traced.graph_validation_status == "accepted"
    assert traced.graph_validation_fallback_reason is None
    assert traced.graph_registry_agent_count == 10
    assert traced.graph_write_agent_count == 1
    assert traced.graph_candidate_summary == {
        "intent": "report",
        "risk": "medium",
        "output_kind": "artifact",
        "requires_approval_preview": False,
        "invocation_agent_ids": [],
    }
    assert traced.graph_execution_status == "not_applicable"


def test_graph_execution_adapter_gate_stays_disabled_until_flag_enabled() -> None:
    decision = select_runtime_profile(
        messages=_messages("회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘"),
        allowed_app_ids=["meeting", "pms"],
        max_tokens=None,
        graph_enabled=True,
    )
    traced = attach_manager_graph_validation_result(
        decision,
        validation=ManagerGraphValidationResult(accepted=True, graph=None),
        registry_agent_count=10,
        write_agent_count=1,
        graph_candidate_summary={
            "intent": "report",
            "risk": "medium",
            "output_kind": "artifact",
            "requires_approval_preview": False,
            "invocation_agent_ids": [],
        },
        graph_schedule_summary={
            "state": "planned",
            "execution_enabled": False,
            "step_count": 1,
            "planned_agent_ids": ["writer.template"],
            "steps": [],
        },
    )

    gated = attach_graph_execution_adapter_decision(
        traced,
        graph_execution_enabled=False,
    )

    assert gated.graph_used is False
    assert gated.graph_execution_status == "disabled"
    assert gated.graph_execution_fallback_reason == "graph_execution_disabled"
    assert gated.graph_execution_adapter is None


def test_graph_execution_adapter_gate_selects_node_runner_when_enabled() -> None:
    decision = select_runtime_profile(
        messages=_messages("회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘"),
        allowed_app_ids=["meeting", "pms"],
        max_tokens=None,
        graph_enabled=True,
    )
    traced = attach_manager_graph_validation_result(
        decision,
        validation=ManagerGraphValidationResult(accepted=True, graph=None),
        registry_agent_count=10,
        write_agent_count=1,
        graph_candidate_summary={
            "intent": "report",
            "risk": "medium",
            "output_kind": "artifact",
            "requires_approval_preview": False,
            "invocation_agent_ids": [],
        },
        graph_schedule_summary={
            "state": "planned",
            "execution_enabled": False,
            "step_count": 1,
            "planned_agent_ids": ["writer.template"],
            "steps": [],
        },
    )

    gated = attach_graph_execution_adapter_decision(
        traced,
        graph_execution_enabled=True,
    )

    assert gated.graph_used is True
    assert gated.graph_fallback_reason is None
    assert gated.graph_execution_status == "adapter_selected"
    assert gated.graph_execution_fallback_reason is None
    assert gated.graph_execution_adapter == GRAPH_NODE_RUNNER_ADAPTER_ID
    assert gated.graph_schedule_summary is not None
    assert gated.graph_schedule_summary["execution_enabled"] is True


def test_graph_execution_adapter_gate_keeps_high_risk_graph_unavailable() -> None:
    decision = select_runtime_profile(
        messages=_messages("PMS 이슈를 생성해줘"),
        allowed_app_ids=["pms"],
        max_tokens=None,
        graph_enabled=True,
    )
    traced = attach_manager_graph_validation_result(
        decision,
        validation=ManagerGraphValidationResult(accepted=True, graph=None),
        registry_agent_count=10,
        write_agent_count=1,
        graph_candidate_summary={
            "intent": "write",
            "risk": "high",
            "output_kind": "approval_preview",
            "requires_approval_preview": True,
            "invocation_agent_ids": ["domain.pms", "approval.proposal_preview"],
        },
        graph_schedule_summary={
            "state": "planned",
            "execution_enabled": False,
            "step_count": 2,
            "planned_agent_ids": ["domain.pms", "approval.proposal_preview"],
            "steps": [],
        },
    )

    gated = attach_graph_execution_adapter_decision(
        traced,
        graph_execution_enabled=True,
    )

    assert gated.graph_used is False
    assert gated.graph_execution_status == "adapter_unavailable"
    assert gated.graph_execution_fallback_reason == "graph_execution_adapter_unsupported"
    assert gated.graph_execution_adapter is None


def test_graph_execution_system_prompt_summarizes_plan_without_user_content() -> None:
    decision = select_runtime_profile(
        messages=_messages("회의록과 PMS 이슈를 비교해서 근거 있는 보고서로 정리해줘"),
        allowed_app_ids=["meeting", "pms"],
        max_tokens=None,
        graph_enabled=True,
    )
    traced = attach_manager_graph_validation_result(
        decision,
        validation=ManagerGraphValidationResult(accepted=True, graph=None),
        registry_agent_count=10,
        write_agent_count=1,
        graph_candidate_summary={
            "intent": "report",
            "domains": ["meeting", "pms"],
            "risk": "medium",
            "output_kind": "artifact",
            "requires_approval_preview": False,
        },
        graph_schedule_summary={
            "state": "planned",
            "execution_enabled": True,
            "planned_agent_ids": ["domain.meeting", "writer.template"],
            "steps": [
                {
                    "invocation_seq": 0,
                    "agent_id": "domain.meeting",
                    "depends_on_agent_ids": [],
                },
                {
                    "invocation_seq": 1,
                    "agent_id": "writer.template",
                    "depends_on_agent_ids": ["domain.meeting"],
                },
            ],
        },
    )

    gated = attach_graph_execution_adapter_decision(
        traced,
        graph_execution_enabled=True,
    )

    prompt = build_graph_execution_system_prompt(gated)

    assert GRAPH_NODE_RUNNER_ADAPTER_ID in prompt
    assert GRAPH_INSTRUCTED_SINGLE_LOOP_ADAPTER_ID not in prompt
    assert "domain.meeting" in prompt
    assert "writer.template after [domain.meeting]" in prompt
    assert "회의록과 PMS 이슈" not in prompt


def test_runtime_profile_selects_long_doc_for_large_budget() -> None:
    decision = select_runtime_profile(
        messages=_messages("전체 문서를 분석해줘"),
        allowed_app_ids=["docs"],
        max_tokens=40_000,
        graph_enabled=True,
    )

    assert decision.runtime_profile == "long_doc"
    assert decision.graph_gate == "ineligible"
    assert decision.graph_fallback_reason == "runtime_profile_ineligible"
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


def test_runtime_profile_matches_routing_eval_fixture_expectations() -> None:
    fixture = json.loads((FIXTURE_DIR / "routing_cases.json").read_text())

    for case in fixture["cases"]:
        request = case["input"]
        decision = select_runtime_profile(
            messages=_messages(request["user_message"]),
            allowed_app_ids=request.get("allowed_app_ids"),
            max_tokens=request.get("max_tokens"),
            graph_enabled=True,
        )

        assert decision.runtime_profile == case["expected"]["runtime_profile"]
