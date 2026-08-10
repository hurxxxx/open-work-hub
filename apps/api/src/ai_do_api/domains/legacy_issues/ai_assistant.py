from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ai_do_api.domains.ai.gateway import (
    AiGatewayDecision,
)
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    LegacyIssueEvidence,
    LegacyIssueSearchProfile,
    sanitize_legacy_issue_search_plan,
)
from ai_do_api.domains.legacy_issues.analysis_application import (
    run_legacy_issue_analysis,
)
from ai_do_api.domains.legacy_issues.analysis_contracts import AnalysisMode, AnalysisPlanV1
from ai_do_api.domains.legacy_issues.conversation_scope import analyze_legacy_issue_prompt
from ai_do_api.domains.legacy_issues.grounded_report import (
    render_grounded_legacy_issue_report,
)


_EXACT_ANALYSIS_UNAVAILABLE_RESPONSE = (
    "요청한 정형 집계를 안전하게 완료하지 못해 정확한 수치를 제공할 수 없습니다. "
    "잠시 후 다시 시도하거나 분석 범위를 단순화해 주세요."
)


@dataclass(frozen=True)
class LegacyIssueAssistantResult:
    run_id: str
    answer_markdown: str
    analysis_plan: LegacyIssueAssistantSearchPlan
    evidence: list[LegacyIssueEvidence]
    search_profile: LegacyIssueSearchProfile
    analysis_result: dict[str, Any] | None = None
    gateway_decisions: list[dict[str, Any]] = field(default_factory=list)


def run_legacy_issue_assistant(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    dataset_keys: tuple[str, ...] | None,
    evidence_limit: int,
    module_keys: frozenset[str] | None = None,
) -> LegacyIssueAssistantResult:
    run_id = new_id()
    prompt_analysis = analyze_legacy_issue_prompt(
        db,
        workspace=workspace,
        user=user,
        question=question,
        messages=[],
    )
    if not prompt_analysis.should_search:
        plan = sanitize_legacy_issue_search_plan(
            question=question,
            dataset_keys=dataset_keys,
            intent=prompt_analysis.action,
            report_focus=(prompt_analysis.reason,),
        )
        return LegacyIssueAssistantResult(
            run_id=run_id,
            answer_markdown=_answer_only_response(prompt_analysis.reason),
            analysis_plan=plan,
            evidence=[],
            search_profile=_empty_search_profile(plan.dataset_keys),
            gateway_decisions=[],
        )
    outcome = run_legacy_issue_analysis(
        db,
        workspace=workspace,
        user=user,
        question=question,
        requested_dataset_keys=dataset_keys,
        module_keys=module_keys,
        evidence_limit=evidence_limit,
        audit_entity_id=run_id,
        routing_mode=prompt_analysis.analysis_mode,
        family_categories=prompt_analysis.family_categories,
        record_set_required=prompt_analysis.record_set_required,
        data_sources=prompt_analysis.data_sources,
        counting_unit=prompt_analysis.counting_unit,
        report_requested=prompt_analysis.report_requested,
    )
    if outcome.analysis_plan.mode == AnalysisMode.ANSWER_ONLY:
        answer = _answer_only_response("analysis_planner_answer_only")
        report_decision = None
    elif outcome.analysis_plan.clarification and not outcome.analysis_result:
        answer = outcome.analysis_plan.clarification
        report_decision = None
    elif outcome.degraded_reason is not None and outcome.analysis_result is None:
        answer = _EXACT_ANALYSIS_UNAVAILABLE_RESPONSE
        report_decision = None
    else:
        answer, report_decision = _generate_legacy_issue_report(
            db,
            workspace=workspace,
            user=user,
            question=question,
            plan=outcome.search_plan,
            structured_plan=outcome.analysis_plan,
            analysis_result=outcome.analysis_result,
            analysis_degraded=outcome.degraded_reason is not None,
            evidence=outcome.evidence,
            profile=outcome.search_profile,
            run_id=run_id,
        )
    decisions = [
        payload
        for payload in (
            *(_decision_payload(decision) for decision in outcome.gateway_decisions),
            _decision_payload(report_decision),
        )
        if payload is not None
    ]
    return LegacyIssueAssistantResult(
        run_id=run_id,
        answer_markdown=answer,
        analysis_plan=outcome.search_plan,
        analysis_result=outcome.analysis_result,
        evidence=outcome.evidence,
        search_profile=outcome.search_profile,
        gateway_decisions=decisions,
    )


def _answer_only_response(reason: str) -> str:
    return (
        "안녕하세요. 과거차 문제점, 차종, 증상, 원인, 개선대책처럼 업무 데이터가 필요한 "
        "질문을 주시면 근거 기반으로 분석하겠습니다."
        if reason
        else "안녕하세요. 과거차 문제점 관련 질문을 주시면 근거 기반으로 분석하겠습니다."
    )


def _empty_search_profile(dataset_keys: tuple[str, ...]) -> LegacyIssueSearchProfile:
    return LegacyIssueSearchProfile(
        semantic_enabled=False,
        vector_extension_available=False,
        vector_index_available=False,
        trigram_extension_available=False,
        full_text_enabled=False,
        searched_dataset_keys=dataset_keys,
        searched_revision_ids=(),
        candidate_count=0,
        evidence_count=0,
        methods=(),
    )


def _generate_legacy_issue_report(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    plan: LegacyIssueAssistantSearchPlan,
    structured_plan: AnalysisPlanV1 | None,
    analysis_result: dict[str, Any] | None,
    analysis_degraded: bool,
    evidence: list[LegacyIssueEvidence],
    profile: LegacyIssueSearchProfile,
    run_id: str,
) -> tuple[str, AiGatewayDecision | None]:
    del db, workspace, user, question, plan, structured_plan, profile, run_id
    return (
        render_grounded_legacy_issue_report(
            analysis_result=analysis_result,
            evidence=evidence,
            analysis_degraded=analysis_degraded,
        ),
        None,
    )


def _decision_payload(decision: AiGatewayDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "task_kind": decision.task_kind,
        "policy": decision.policy,
        "chosen_pool": decision.chosen_pool,
        "provider": decision.provider,
        "model": decision.model,
        "reason_codes": list(decision.reason_codes),
        "forced_local": decision.forced_local,
        "context_strategy": decision.context_strategy,
        "estimated_input_tokens": decision.estimated_input_tokens,
        "max_tokens": decision.max_tokens,
    }
