from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.principal import CallerPrincipal
from ai_do_api.domains.ai.gateway import (
    AiGatewayContextPack,
    LlmWorkloadContext,
    execute_llm,
)
from ai_do_api.domains.auth.access import resolve_workspace_enabled_app_ids
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.conversations.scope_registry import (
    ConversationExperience,
    ConversationScopeArtifact,
    ConversationScopeTurnContext,
)
from ai_do_api.domains.conversations.models import Conversation
from ai_do_api.domains.legacy_issues.analysis_graph.dispatch import (
    dispatch_legacy_issue_analysis,
)
from ai_do_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    LegacyIssueEvidence,
    LegacyIssueSearchProfile,
)
from ai_do_api.domains.legacy_issues.ai_evidence_payload import (
    COMPACT_EVIDENCE_VALUE_KEYS,
    selected_legacy_issue_evidence_values,
)
from ai_do_api.domains.legacy_issues.analysis_application import (
    compact_analysis_prompt_payload,
)
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisCountingUnit,
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
)
from ai_do_api.domains.legacy_issues.grounded_report import (
    render_grounded_legacy_issue_report,
)
from ai_do_api.domains.legacy_issues.task_kinds import (
    LEGACY_ISSUE_CONVERSATION_ANSWER_WORKLOAD_ID,
    LEGACY_ISSUE_INTENT_ROUTER_WORKLOAD_ID,
)


LEGACY_ISSUE_CONVERSATION_SCOPE_REF = "legacy_issues"
LEGACY_ISSUE_CONVERSATION_SCOPE_RESOURCE_ID = "workspace"
_PROMPT_ANALYSIS_CONTEXT_WINDOW = 8
_EXACT_ANALYSIS_UNAVAILABLE_RESPONSE = (
    "요청한 정형 집계를 안전하게 완료하지 못해 정확한 수치를 제공할 수 없습니다. "
    "잠시 후 다시 시도하거나 분석 범위를 단순화해 주세요."
)


@dataclass(frozen=True)
class LegacyIssuePromptAnalysis:
    should_search: bool
    reason: str
    action: str = "answer_only"
    analysis_mode: AnalysisMode | None = None
    family_categories: tuple[str, ...] = ()
    record_set_required: bool = False
    record_set_seed_evidence: str | None = None
    record_set_reentry_evidence: str | None = None
    data_sources: tuple[AnalysisDataSource, ...] = (AnalysisDataSource.LEGACY_ISSUES,)
    counting_unit: AnalysisCountingUnit | None = None
    report_requested: bool = False
    report_request_evidence: str | None = None


class LegacyIssueConversationScopeAdapter:
    scope_ref = LEGACY_ISSUE_CONVERSATION_SCOPE_REF
    server_owned_artifact_types = frozenset(
        {
            "legacy-issue-analysis",
            "legacy-issue-evidence",
        }
    )
    experience = ConversationExperience(
        owner_app_id="legacy-issues",
        chat_workload_id=LEGACY_ISSUE_CONVERSATION_ANSWER_WORKLOAD_ID,
        execution_mode="durable_background",
    )

    def validate(
        self,
        *,
        db: Session,
        workspace: Workspace,
        principal: CallerPrincipal,
        user: User,
        scope_resource_id: str,
    ) -> None:
        if scope_resource_id != LEGACY_ISSUE_CONVERSATION_SCOPE_RESOURCE_ID:
            raise ValueError("unsupported legacy issue conversation resource")
        enabled_app_ids = set(resolve_workspace_enabled_app_ids(db, workspace.id))
        if "legacy-issues" not in enabled_app_ids:
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="legacy_issues.app_disabled",
            )

    def system_prompt(
        self,
        *,
        db: Session,
        workspace: Workspace,
        principal: CallerPrincipal,
        user: User,
        scope_resource_id: str,
    ) -> str:
        return (
            "너는 두원공조 과거차 문제점 분석 AI다. 인사, 감사, 기능 질문, "
            "과거차와 무관한 일반 대화에는 업무 데이터 검색을 했다고 말하지 말고 "
            "짧게 응답한다. 사용자가 과거차 문제점, 차종, 증상, 원인, 개선대책, "
            "빈도, 비교, 리포트처럼 업무 데이터가 필요한 질문을 했을 때만 제공된 "
            "검색 근거 범위에서 분석한다. 근거 행에 없는 원인, 차종, 개선대책, "
            "날짜, 판단을 만들지 않는다.\n\n"
            "서버가 제공한 exact_analysis의 수치만 전체 건수, 비율, 순위, 추세 같은 "
            "정량 결론에 사용한다. retrieval_profile의 candidate_count와 evidence_count는 "
            "검색 후보/근거 수일 뿐 전체 모집단 수가 아니다. 정형 집계와 의미 검색 근거를 "
            "서로 바꾸어 해석하지 않는다. exact_analysis에서 source_count는 필터 전 허용 "
            "원천 수이고, 각 query의 totals.filtered_population_count는 필터 후, "
            "totals.population_count는 그중 차원 형식이 유효해 그룹화에 참여한 행 수다. "
            "필드별 입력 건수는 같은 query coverage의 present_count를 따르고 invalid_count는 "
            "형식이 잘못된 값이다. coverage는 "
            "필터 후 모집단의 입력 품질이며 다른 "
            "query나 전체 원천의 건수로 재사용하지 않는다. 근거에 없는 작성일이나 "
            "분석 기준일을 만들지 않고, 서로 다른 필드의 결측 건수나 비율을 하나로 "
            "합쳐 말하지 않는다.\n\n"
            "긴 분석 결과는 chat 말풍선에 길게 쓰지 말고 artifact로 분리한다. "
            "chat에는 핵심 결론 1-2문장만 남긴다. 사용자가 리포트나 상세 정리를 "
            "요청했고 근거 데이터가 제공된 경우 "
            '<artifact type="document" title="과거차 문제점 분석 리포트"> 안에 '
            "markdown 보고서를 작성한다. 근거 데이터 그리드는 서버가 별도로 생성하므로 "
            "legacy-issue-evidence artifact를 직접 만들지 않는다. 보고서의 출처 표기는 "
            "[E1], [E2] 형식을 사용한다.\n\n"
            "정형 분석 그리드와 차트는 서버가 legacy-issue-analysis artifact로 별도 "
            "생성하므로 해당 artifact를 직접 만들거나 수치를 다시 계산하지 않는다.\n\n"
            "검색 결과가 부족하면 부족하다고 말하고, 재질문 없이 현재 근거의 한계를 "
            "명확히 쓴다. follow-up 질문에서는 이전 대화 맥락과 새 검색 근거를 함께 "
            "반영하되, 새 근거가 기존 결론과 충돌하면 충돌을 설명한다."
        )

    def turn_context(
        self,
        *,
        db: Session,
        workspace: Workspace,
        principal: CallerPrincipal,
        user: User,
        scope_resource_id: str,
        messages: list[dict[str, Any]],
        conversation: Conversation | None = None,
    ) -> ConversationScopeTurnContext:
        question = _latest_user_text(messages)
        if not question:
            return ConversationScopeTurnContext()
        if conversation is None:
            return ConversationScopeTurnContext(
                direct_response=(
                    "분석 대화를 저장할 수 없어 요청을 시작하지 못했습니다. "
                    "대화를 저장한 뒤 다시 시도해 주세요."
                )
            )
        run_id, artifact_id, _assistant_turn_id = dispatch_legacy_issue_analysis(
            db,
            workspace=workspace,
            user=user,
            conversation=conversation,
            question=question,
            recent_messages=messages[:-1],
        )
        return ConversationScopeTurnContext(
            direct_response="요청을 접수했습니다. 분석을 계속 진행합니다.",
            background_run_id=run_id,
            background_artifact_id=artifact_id,
            assistant_turn_persisted=True,
        )

    def turn_context_prompt(
        self,
        *,
        db: Session,
        workspace: Workspace,
        principal: CallerPrincipal,
        user: User,
        scope_resource_id: str,
        messages: list[dict[str, Any]],
    ) -> str | None:
        return self.turn_context(
            db=db,
            workspace=workspace,
            principal=principal,
            user=user,
            scope_resource_id=scope_resource_id,
            messages=messages,
        ).prompt


def iter_extension_conversation_scope_adapters() -> tuple[LegacyIssueConversationScopeAdapter, ...]:
    return (LegacyIssueConversationScopeAdapter(),)


def _latest_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return " ".join(content.split())
    return ""


def analyze_legacy_issue_prompt(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    messages: list[dict[str, Any]] | None = None,
) -> LegacyIssuePromptAnalysis:
    normalized = _normalize_prompt(question)
    if not normalized:
        return LegacyIssuePromptAnalysis(False, "empty", "answer_only")
    classifier_messages = _build_prompt_analysis_messages(
        question=normalized,
        messages=messages or [],
    )
    try:
        completion = execute_llm(
            LEGACY_ISSUE_INTENT_ROUTER_WORKLOAD_ID,
            LlmWorkloadContext(
                source="legacy_issues.conversation.intent",
                workspace_id=workspace.id,
                actor_user_id=user.id,
                app_id="legacy-issues",
            ),
            db,
            messages=classifier_messages,
            context_pack=AiGatewayContextPack(
                messages=classifier_messages,
                context_strategy="legacy_issue_conversation_prompt_analysis",
                estimated_input_tokens=_estimate_tokens(classifier_messages),
            ),
            max_tokens=512,
            temperature=0,
        ).completion
        payload = _parse_json_object(completion.text)
    except Exception:
        return LegacyIssuePromptAnalysis(
            False,
            "intent_classifier_failed",
            "answer_only",
        )
    action = str(payload.get("action") or "").strip().lower()
    reason = _normalize_prompt(str(payload.get("reason") or "llm_prompt_analysis"))
    analysis_mode = _analysis_mode(payload.get("analysis_mode"))
    family_categories = _family_categories(payload.get("family_categories"))
    checklist_evidence = _validated_question_evidence(
        payload.get("vehicle_checklist_evidence"),
        question=normalized,
    )
    counting_unit_evidence = _validated_question_evidence(
        payload.get("counting_unit_evidence"),
        question=normalized,
    )
    raw_counting_unit = _parse_counting_unit(payload.get("counting_unit"))
    report_request_evidence = _validated_question_evidence(
        payload.get("report_request_evidence"),
        question=normalized,
    )
    report_requested = (
        str(payload.get("response_format") or "").strip().lower() == "report"
        and report_request_evidence is not None
    )
    data_sources = _analysis_data_sources(
        payload.get("data_sources"),
        checklist_evidence=checklist_evidence,
        counting_unit=raw_counting_unit,
        counting_unit_evidence=counting_unit_evidence,
    )
    counting_unit = _analysis_counting_unit(
        raw_counting_unit,
        data_sources=data_sources,
        evidence=counting_unit_evidence,
    )
    has_retrieval_signal = (
        analysis_mode is not None or bool(family_categories) or checklist_evidence is not None
    )
    if action == "retrieve" or has_retrieval_signal:
        analysis_mode = _resolve_missing_analysis_mode(
            analysis_mode,
            family_categories=family_categories,
        )
        seed_evidence = _validated_question_evidence(
            payload.get("record_set_seed_evidence"),
            question=normalized,
        )
        reentry_evidence = _validated_question_evidence(
            payload.get("record_set_reentry_evidence"),
            question=normalized,
        )
        record_set_required = (
            payload.get("record_set_required") is True
            and seed_evidence is not None
            and reentry_evidence is not None
            and seed_evidence.casefold() != reentry_evidence.casefold()
        )
        return LegacyIssuePromptAnalysis(
            True,
            reason or "retrieve",
            "retrieve",
            analysis_mode,
            family_categories,
            record_set_required,
            seed_evidence if record_set_required else None,
            reentry_evidence if record_set_required else None,
            data_sources,
            counting_unit,
            report_requested,
            report_request_evidence if report_requested else None,
        )
    return LegacyIssuePromptAnalysis(False, reason or "answer_only", "answer_only")


def _build_prompt_analysis_messages(
    *,
    question: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an intent router for a Korean legacy vehicle issue analysis "
                "chatbot. Return only compact JSON. Decide whether the assistant can "
                "answer directly or must retrieve internal legacy issue records before "
                "answering. Do not use keyword matching; infer the user's actual intent "
                "from the current message and recent conversation.\n\n"
                "Return action='answer_only' for greetings, thanks, small talk, capability "
                "questions, UI/help questions, or general replies that do not require "
                "internal business data. Return action='retrieve' only when the user asks "
                "for analysis, search, report, comparison, counts, causes, countermeasures, "
                "vehicle models, symptoms, or follow-up reasoning that needs legacy issue "
                "records. A short domain phrase can itself be a record search request; do "
                "not classify it as answer_only merely because it lacks a verb. In this "
                "scoped business assistant, treat an unexplained acronym or terse technical "
                "or product noun phrase as a domain record search unless the conversation "
                "clearly makes it a general/help question. A terse follow-up inherits the "
                "active business-data topic from recent conversation. If routing fails "
                "between structured and unstructured analysis, prefer semantic retrieval "
                "rather than answering without evidence.\n\n"
                "For retrieve, classify analysis_mode. Use semantic for qualitative cases, "
                "similar incidents, causes, countermeasures, explanations, or evidence. Use "
                "analytics for exact counts, ranges, distributions, rankings, time trends, "
                "or comparisons. Use hybrid only when the same request needs both exact "
                "statistics and record evidence. Use metadata for schema, coverage, or data "
                "scope questions. Use clarify only when ambiguity materially changes the "
                "result. A comparison request without named comparison periods, a baseline, "
                "or usable values in recent conversation is materially ambiguous: use clarify "
                "instead of inventing current/previous periods. A time trend with an explicit "
                "range or a conventional period such as year-over-year is not ambiguous. "
                "family_categories may contain up to four generic catalog categories: "
                "metadata, scalar, distribution, time, comparison, association, quality, "
                "detail, semantic, hybrid, or composite. Set record_set_required=true when "
                "the request first identifies entities by a seed condition and then asks to "
                "analyze all or other records belonging to those entities. This is a generic "
                "cohort re-entry signal, independent of particular words or vehicle models. "
                "It requires two distinct clauses in the current message: one clause that "
                "selects seed records and another clause that asks for all or other records "
                "belonging to the resulting entities. Ordinary filtering, grouping, Top-N, "
                "shares, or asking for details of the matching records is not cohort re-entry. "
                "When true, copy those two clauses verbatim into record_set_seed_evidence and "
                "record_set_reentry_evidence. Otherwise set both to null. "
                "data_sources must contain legacy_issues for master problem records and "
                "vehicle_checklists for questions about vehicle/module checklist snapshots, "
                "their status, independently edited values, or checklist items. Include both "
                "only for an explicit cross-source request. When vehicle_checklists is present, "
                "copy the exact checklist-related clause into vehicle_checklist_evidence; "
                "otherwise set it to null. "
                "counting_unit identifies the entity being counted: legacy_records for master "
                "problem records, checklist_items for rows/items inside latest checklists, and "
                "checklists for checklist documents/snapshots themselves. The presence of the "
                "word checklist alone does not mean checklists: decide whether the user counts "
                "items inside them or the checklist documents. Copy the exact counted-entity "
                "clause into counting_unit_evidence; otherwise set both fields to null. "
                "Do not emit field names or SQL."
                " Set response_format='report' only when the current message explicitly "
                "asks for a report, briefing document, or report-style written deliverable. "
                "When it does, copy the exact request clause into report_request_evidence; "
                "otherwise use response_format='answer' and null evidence."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "current_user_message": question,
                    "recent_conversation": _recent_conversation_payload(messages),
                    "response_schema": {
                        "action": "answer_only | retrieve",
                        "reason": "short reason in Korean or English",
                        "analysis_mode": (
                            "metadata | analytics | semantic | hybrid | clarify | null"
                        ),
                        "family_categories": ["up to four generic catalog category strings"],
                        "record_set_required": "boolean",
                        "record_set_seed_evidence": "exact quote from current message | null",
                        "record_set_reentry_evidence": (
                            "different exact quote from current message | null"
                        ),
                        "data_sources": ["legacy_issues | vehicle_checklists"],
                        "vehicle_checklist_evidence": ("exact quote from current message | null"),
                        "counting_unit": ("legacy_records | checklist_items | checklists | null"),
                        "counting_unit_evidence": (
                            "exact counted-entity quote from current message | null"
                        ),
                        "response_format": "answer | report",
                        "report_request_evidence": (
                            "exact report-request clause from current message | null"
                        ),
                    },
                },
                ensure_ascii=False,
            ),
        },
    ]


def _validated_question_evidence(value: Any, *, question: str) -> str | None:
    if not isinstance(value, str):
        return None
    evidence = _normalize_prompt(value)
    if len(evidence) < 2 or len(evidence) > 240:
        return None
    normalized_question = _normalize_prompt(question)
    if evidence.casefold() not in normalized_question.casefold():
        return None
    return evidence


def _analysis_data_sources(
    value: Any,
    *,
    checklist_evidence: str | None,
    counting_unit: AnalysisCountingUnit | None,
    counting_unit_evidence: str | None,
) -> tuple[AnalysisDataSource, ...]:
    grounded_checklist_unit = (
        counting_unit
        in {
            AnalysisCountingUnit.CHECKLIST_ITEMS,
            AnalysisCountingUnit.CHECKLISTS,
        }
        and counting_unit_evidence is not None
    )
    selected: list[AnalysisDataSource] = []
    for item in value if isinstance(value, list) else ():
        try:
            data_source = AnalysisDataSource(str(item).strip().lower())
        except ValueError:
            continue
        if (
            data_source == AnalysisDataSource.VEHICLE_CHECKLISTS
            and checklist_evidence is None
            and not grounded_checklist_unit
        ):
            continue
        if data_source not in selected:
            selected.append(data_source)
    if grounded_checklist_unit:
        # A grounded counted entity owns its physical source. This reconciles
        # internally inconsistent router output without inspecting question words.
        return (AnalysisDataSource.VEHICLE_CHECKLISTS,)
    return tuple(selected) or (AnalysisDataSource.LEGACY_ISSUES,)


def _parse_counting_unit(value: Any) -> AnalysisCountingUnit | None:
    try:
        return AnalysisCountingUnit(str(value).strip().lower())
    except ValueError:
        return None


def _analysis_counting_unit(
    value: AnalysisCountingUnit | None,
    *,
    data_sources: tuple[AnalysisDataSource, ...],
    evidence: str | None,
) -> AnalysisCountingUnit | None:
    if evidence is None or value is None:
        return None
    counting_unit = value
    if (
        counting_unit
        in {
            AnalysisCountingUnit.CHECKLIST_ITEMS,
            AnalysisCountingUnit.CHECKLISTS,
        }
        and AnalysisDataSource.VEHICLE_CHECKLISTS not in data_sources
    ):
        return None
    if (
        counting_unit == AnalysisCountingUnit.LEGACY_RECORDS
        and AnalysisDataSource.LEGACY_ISSUES not in data_sources
    ):
        return None
    return counting_unit


def _analysis_mode(value: Any) -> AnalysisMode | None:
    if not isinstance(value, str):
        return None
    try:
        mode = AnalysisMode(value.strip().lower())
    except ValueError:
        return None
    if mode in {
        AnalysisMode.METADATA,
        AnalysisMode.ANALYTICS,
        AnalysisMode.SEMANTIC,
        AnalysisMode.HYBRID,
        AnalysisMode.CLARIFY,
    }:
        return mode
    return None


def _resolve_missing_analysis_mode(
    mode: AnalysisMode | None,
    *,
    family_categories: tuple[str, ...],
) -> AnalysisMode:
    if mode is not None:
        return mode
    categories = set(family_categories)
    if "comparison" in categories:
        # A comparison classification without a valid mode is internally
        # inconsistent. Clarification is safer than inventing periods.
        return AnalysisMode.CLARIFY
    if "metadata" in categories:
        return AnalysisMode.METADATA
    structured = {
        "scalar",
        "distribution",
        "time",
        "association",
        "quality",
    }
    if categories.intersection(structured):
        if "semantic" in categories:
            return AnalysisMode.HYBRID
        return AnalysisMode.ANALYTICS
    return AnalysisMode.SEMANTIC


def _family_categories(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    allowed = {
        "metadata",
        "scalar",
        "distribution",
        "time",
        "comparison",
        "association",
        "quality",
        "detail",
        "semantic",
        "hybrid",
        "composite",
    }
    normalized = [
        str(item).strip().lower()
        for item in value
        if isinstance(item, str) and str(item).strip().lower() in allowed
    ]
    return tuple(dict.fromkeys(normalized[:4]))


def _build_no_search_turn_prompt(
    *,
    question: str,
    analysis: LegacyIssuePromptAnalysis,
) -> str:
    return (
        "이번 사용자 메시지는 서버 프롬프트 분석 단계에서 "
        f"'{analysis.reason}' 의도로 분류되어 과거차 업무 데이터 검색을 실행하지 않았다. "
        "검색을 수행했다고 말하지 말고, 근거 데이터나 legacy-issue-evidence artifact를 "
        "생성하지 않는다. 인사/일반 대화면 짧게 답하고, 필요하면 차종·증상·문제점·"
        "원인·개선대책을 물어보면 근거 기반으로 분석할 수 있다고 안내한다.\n\n"
        f"사용자 메시지: {json.dumps(question, ensure_ascii=False)}"
    )


def _normalize_prompt(text: str) -> str:
    return " ".join(text.split()).strip()


def _recent_conversation_payload(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for message in messages[-_PROMPT_ANALYSIS_CONTEXT_WINDOW:]:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        payload.append({"role": role, "content": _normalize_prompt(content)[:1000]})
    return payload


def conversation_id_from_messages(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        conversation_id = message.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id.strip():
            return conversation_id.strip()
    return None


def _build_turn_prompt(
    *,
    question: str,
    plan: LegacyIssueAssistantSearchPlan,
    analysis_result: dict[str, Any] | None,
    analysis_mode: str,
    clarification: str | None,
    evidence: list[LegacyIssueEvidence],
    profile: LegacyIssueSearchProfile,
    structured_plan: AnalysisPlanV1 | None = None,
    analysis_degraded: bool = False,
) -> str:
    evidence_payload = [_llm_evidence_payload(item, plan=plan) for item in evidence]
    profile_payload = _profile_payload(profile)
    context_payload = {
        "question": question,
        "analysis_mode": analysis_mode,
        "analysis_degraded": analysis_degraded,
        "clarification": clarification,
        "retrieval_plan": _plan_payload(plan),
        "exact_analysis": compact_analysis_prompt_payload(
            analysis_result,
            analysis_plan=structured_plan,
        ),
        "retrieval_profile": profile_payload,
        "evidence_refs": evidence_payload,
    }
    if analysis_mode == "answer_only":
        artifact_contract = (
            "내부 업무 데이터 조회가 필요하지 않은 메시지다. 검색이나 분석을 수행했다고 "
            "말하지 말고 짧게 직접 답하며 artifact를 만들지 않는다."
        )
    elif clarification:
        artifact_contract = (
            "정확한 분석 범위를 결정할 핵심 정보가 부족하다. clarification 내용을 "
            "간단히 확인하고 검색이나 집계를 수행했다고 말하지 않는다."
        )
    elif analysis_degraded:
        artifact_contract = (
            "요청한 정형 분석은 안전하게 완료되지 않아 의미 검색으로 전환됐다. "
            "정확한 전체 수치를 제공할 수 없다고 밝히고, candidate_count나 "
            "evidence_count를 전체 건수로 대신 사용하지 않는다. 근거 행이 있으면 "
            "[E1] 형식의 사례 근거로만 사용한다."
        )
    elif analysis_result is not None and evidence_payload:
        artifact_contract = (
            "서버가 exact 분석 artifact와 근거 artifact를 각각 생성했다. 수치는 "
            "exact_analysis에서만 인용하고, 의미 검색 행은 [E1] 형식의 사례 근거로만 "
            "사용한다. 두 artifact를 직접 만들지 않는다."
        )
    elif analysis_result is not None:
        artifact_contract = (
            "서버가 정형 분석 artifact를 생성했다. exact_analysis의 수치만 사용하고 "
            "검색 근거가 없다는 이유로 집계 결과가 없다고 말하지 않는다. "
            "legacy-issue-analysis artifact를 직접 만들지 않는다."
        )
    elif evidence_payload:
        artifact_contract = (
            "근거 행이 있으므로 사용자가 리포트/정리/분석을 요청한 경우 document artifact를 "
            "만들고, 출처 표시는 [E1] 형식을 사용한다. 근거 데이터 그리드는 서버가 "
            "별도 artifact로 생성하므로 legacy-issue-evidence artifact를 직접 만들지 않는다."
        )
    else:
        artifact_contract = (
            "검색은 수행했지만 매칭되는 근거 행이 없다. 근거가 없다고 명확히 말하고, "
            "legacy-issue-evidence artifact를 직접 만들지 않는다. 필요한 경우 검색 조건을 더 구체화하도록 안내한다."
        )
    return (
        "아래 JSON은 이번 사용자 질문에 대해 서버가 과거차 문제점 데이터에서 계산하거나 "
        "검색한 정형 분석과 compact 근거 참조다. 수치는 exact_analysis에서만 사용하고, "
        "각 query.request와 같은 query의 rows·totals·coverage만 함께 해석한다. source_count는 "
        "필터 전 원천, totals.filtered_population_count는 필터 후, "
        "totals.population_count는 차원 형식이 유효해 그룹화에 참여한 행 수다. "
        "필드별 입력 건수는 같은 query coverage의 present_count를 따르고 invalid_count는 "
        "형식이 잘못된 값이다. 근거에 없는 작성일이나 분석 기준일을 만들지 않고, "
        "서로 다른 필드의 결측률을 하나로 합치지 않는다. "
        "이 JSON 안의 evidence id만 사례 출처로 "
        f"사용한다. {artifact_contract}\n\n"
        f"{json.dumps(context_payload, ensure_ascii=False)}"
    )


def _plan_payload(plan: LegacyIssueAssistantSearchPlan) -> dict[str, Any]:
    return {
        "query": plan.query,
        "dataset_keys": list(plan.dataset_keys),
        "primary_keywords": list(plan.primary_keywords),
        "keywords": list(plan.keywords),
        "supporting_keywords": list(plan.supporting_keywords),
        "field_hints": list(plan.field_hints),
        "intent": plan.intent,
        "report_focus": list(plan.report_focus),
        "related_field_expansions": list(plan.related_field_expansions),
    }


def _profile_payload(profile: LegacyIssueSearchProfile) -> dict[str, Any]:
    return {
        "semantic_enabled": profile.semantic_enabled,
        "vector_extension_available": profile.vector_extension_available,
        "vector_index_available": profile.vector_index_available,
        "trigram_extension_available": profile.trigram_extension_available,
        "full_text_enabled": profile.full_text_enabled,
        "searched_dataset_keys": list(profile.searched_dataset_keys),
        "searched_revision_ids": list(profile.searched_revision_ids),
        "candidate_count": profile.candidate_count,
        "evidence_count": profile.evidence_count,
        "methods": list(profile.methods),
    }


def _llm_evidence_payload(
    item: LegacyIssueEvidence,
    *,
    plan: LegacyIssueAssistantSearchPlan,
) -> dict[str, Any]:
    return {
        "id": item.evidence_id,
        "dataset_key": item.dataset_key,
        "dataset_title": item.dataset_title,
        "revision_id": item.revision_id,
        "record_id": item.stable_record_id or item.record_id,
        "label": item.label,
        "score": item.score,
        "methods": list(item.methods),
        "retrieval_role": _retrieval_role(item.methods),
        "matched_fields": list(item.matched_fields)[:8],
        "matched_excerpts": [
            {
                "field_key": chunk.field_key,
                "field_label": chunk.field_label,
                "excerpt": chunk.excerpt[:500],
            }
            for chunk in item.matched_chunks[:4]
        ],
        "key_values": selected_legacy_issue_evidence_values(
            item.values,
            plan=plan,
            matched_field_keys=item.matched_fields,
            base_keys=COMPACT_EVIDENCE_VALUE_KEYS,
            max_value_length=320,
            fallback_limit=10,
        ),
    }


def _evidence_ref_payload(item: LegacyIssueEvidence) -> dict[str, Any]:
    return {
        "id": item.evidence_id,
        "dataset_key": item.dataset_key,
        "dataset_title": item.dataset_title,
        "revision_id": item.revision_id,
        "revision_no": item.revision_no,
        "record_id": item.stable_record_id or item.record_id,
        "source_record_id": item.record_id,
        "label": item.label,
        "score": item.score,
        "methods": list(item.methods),
        "retrieval_role": _retrieval_role(item.methods),
        "matched_fields": list(item.matched_fields),
        "matched_chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "chunk_key": chunk.chunk_key,
                "chunk_kind": chunk.chunk_kind,
                "field_key": chunk.field_key,
                "field_label": chunk.field_label,
                "field_value": chunk.field_value,
                "excerpt": chunk.excerpt,
                "methods": list(chunk.methods),
                "score": chunk.score,
            }
            for chunk in item.matched_chunks
        ],
    }


def _retrieval_role(methods: tuple[str, ...]) -> str:
    method_set = set(methods)
    if "keyword" in method_set or "fulltext" in method_set:
        return "direct_candidate"
    if "related_field" in method_set:
        return "related_by_field"
    if "supporting_keyword" in method_set:
        return "supporting_candidate"
    return "semantic_candidate"


def _build_evidence_artifact(
    *,
    evidence: list[LegacyIssueEvidence],
    profile: LegacyIssueSearchProfile,
    title: str | None = None,
) -> ConversationScopeArtifact | None:
    if not evidence:
        return None
    content = json.dumps(
        {
            "version": 2,
            "mode": "server_resolved",
            "retrieval_profile": _profile_payload(profile),
            "evidence_refs": [_evidence_ref_payload(item) for item in evidence],
        },
        ensure_ascii=False,
    )
    return ConversationScopeArtifact(
        id=new_id(),
        type="legacy-issue-evidence",
        title=title or "근거 데이터",
        content=content,
    )


def _build_analysis_artifact(
    analysis_result: dict[str, Any] | None,
    *,
    title: str | None = None,
) -> ConversationScopeArtifact | None:
    if analysis_result is None:
        return None
    artifact_title = title or str(
        analysis_result.get("title") or "과거차 문제점 정형 분석"
    )
    return ConversationScopeArtifact(
        id=new_id(),
        type="legacy-issue-analysis",
        title=artifact_title,
        content=json.dumps(analysis_result, ensure_ascii=False),
    )


def _build_grounded_report_artifact(
    *,
    analysis_result: dict[str, Any] | None,
    analysis_degraded: bool,
    evidence: list[LegacyIssueEvidence],
) -> ConversationScopeArtifact:
    return ConversationScopeArtifact(
        id=new_id(),
        type="document",
        title="과거차 문제점 근거 기반 보고서",
        language="markdown",
        content=render_grounded_legacy_issue_report(
            analysis_result=analysis_result,
            evidence=evidence,
            analysis_degraded=analysis_degraded,
        ),
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    if not stripped.startswith("{"):
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            stripped = stripped[start : end + 1]
    payload = json.loads(stripped)
    return payload if isinstance(payload, dict) else {}


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    size = sum(len(str(message.get("content", ""))) for message in messages)
    return max(1, size // 4)


__all__ = [
    "LEGACY_ISSUE_CONVERSATION_SCOPE_REF",
    "LEGACY_ISSUE_CONVERSATION_SCOPE_RESOURCE_ID",
    "LegacyIssuePromptAnalysis",
    "LegacyIssueConversationScopeAdapter",
    "analyze_legacy_issue_prompt",
]
