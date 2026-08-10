from __future__ import annotations

import json
from dataclasses import dataclass, field
import logging
from typing import Any

from sqlalchemy.orm import Session

from open_alm_api.domains.ai.gateway import AiGatewayDecision
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.legacy_issues.ai_search import (
    LegacyIssueAssistantSearchPlan,
    LegacyIssueEvidence,
    LegacyIssueSearchProfile,
    sanitize_legacy_issue_search_plan,
)
from open_alm_api.domains.legacy_issues.ai_search_planner import plan_legacy_issue_search
from open_alm_api.domains.legacy_issues.analysis_contracts import (
    AnalysisCountingUnit,
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
    LegacyIssuePlannerDiagnosticsV1,
    QueryFamilyId,
)
from open_alm_api.domains.legacy_issues.analysis_planner import (
    plan_legacy_issue_analysis,
)
from open_alm_api.domains.legacy_issues.analysis_sql import (
    CHECKLIST_ANALYSIS_FIELDS,
    execute_analysis_plan,
)
from open_alm_api.domains.legacy_issues.dataset_records import (
    DatasetFieldDefinition,
    get_dataset_definition_with_all_module_fields,
)
from open_alm_api.domains.retrieval import application as retrieval_application


_MAX_ANALYSIS_PROMPT_CHARS = 60_000
_MAX_ANALYSIS_PROMPT_STRING_CHARS = 240
_MAX_ANALYSIS_PROMPT_ROWS_PER_QUERY = 64
_TIME_CONTEXT_FAMILIES = frozenset(
    {
        QueryFamilyId.TIME_SERIES.value,
        QueryFamilyId.ABSOLUTE_CHANGE.value,
        QueryFamilyId.RATE_CHANGE.value,
        QueryFamilyId.YOY_MOM.value,
        QueryFamilyId.ROLLING.value,
        QueryFamilyId.CUMULATIVE.value,
    }
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LegacyIssueAnalysisOutcome:
    analysis_plan: AnalysisPlanV1
    search_plan: LegacyIssueAssistantSearchPlan
    analysis_result: dict[str, Any] | None
    evidence: list[LegacyIssueEvidence]
    search_profile: LegacyIssueSearchProfile
    gateway_decisions: list[AiGatewayDecision] = field(default_factory=list)
    degraded_reason: str | None = None
    planner_diagnostics: LegacyIssuePlannerDiagnosticsV1 | None = None


def run_legacy_issue_analysis(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    requested_dataset_keys: tuple[str, ...] | None,
    module_keys: frozenset[str] | None,
    evidence_limit: int,
    audit_entity_id: str | None,
    recent_messages: list[dict[str, Any]] | None = None,
    routing_mode: AnalysisMode | None = None,
    family_categories: tuple[str, ...] = (),
    record_set_required: bool = False,
    data_sources: tuple[AnalysisDataSource, ...] = (),
    counting_unit: AnalysisCountingUnit | None = None,
    report_requested: bool = False,
) -> LegacyIssueAnalysisOutcome:
    """Plan and execute exact, semantic, hybrid, or guarded generated analysis.

    The LLM selects a typed plan. All data scope, query compilation, and execution stay
    server-owned. A structured execution failure degrades to the established semantic
    retrieval path without exposing a partial aggregate as an exact result.
    """

    definition = get_dataset_definition_with_all_module_fields(
        db,
        dataset_key="common-master",
        workspace=workspace,
    )
    requested_data_sources = data_sources or (AnalysisDataSource.LEGACY_ISSUES,)
    legacy_semantic_allowed = AnalysisDataSource.LEGACY_ISSUES in requested_data_sources
    fields_by_key = {field.key: field for field in definition.fields if field.active}
    if AnalysisDataSource.VEHICLE_CHECKLISTS in requested_data_sources:
        for checklist_field in CHECKLIST_ANALYSIS_FIELDS:
            fields_by_key.setdefault(checklist_field.key, checklist_field)
    fields = tuple(fields_by_key.values())
    planning = plan_legacy_issue_analysis(
        db,
        workspace=workspace,
        user=user,
        question=question,
        fields=fields,
        audit_entity_id=audit_entity_id,
        recent_messages=recent_messages,
        routing_mode=routing_mode,
        family_categories=family_categories,
        record_set_required=record_set_required,
        data_sources=requested_data_sources,
        counting_unit=counting_unit,
        report_requested=report_requested,
    )
    plan, decisions = planning
    planner_diagnostics = getattr(planning, "diagnostics", None)
    if planner_diagnostics is not None:
        logger.info(
            "legacy issue analysis planner completed",
            extra={
                "legacy_issue_planner": planner_diagnostics.model_dump(
                    mode="json",
                    exclude_none=True,
                )
            },
        )
    planner_degraded_reason = (
        "analysis_planner_fallback"
        if planner_diagnostics is not None and planner_diagnostics.status == "fallback"
        else None
    )
    search_plan = _neutral_search_plan(
        question=question,
        requested_dataset_keys=requested_dataset_keys,
        intent=plan.mode.value,
    )

    if plan.mode in {
        AnalysisMode.ANSWER_ONLY,
        AnalysisMode.CLARIFY,
    }:
        return LegacyIssueAnalysisOutcome(
            analysis_plan=plan,
            search_plan=search_plan,
            analysis_result=None,
            evidence=[],
            search_profile=_empty_search_profile(search_plan.dataset_keys),
            gateway_decisions=decisions,
            degraded_reason=planner_degraded_reason,
            planner_diagnostics=planner_diagnostics,
        )

    if plan.mode == AnalysisMode.SEMANTIC:
        if not legacy_semantic_allowed:
            return _empty_analysis_outcome(
                question=question,
                requested_dataset_keys=requested_dataset_keys,
                analysis_plan=plan,
                analysis_decisions=decisions,
                degraded_reason="vehicle_checklist_semantic_unavailable",
                planner_diagnostics=planner_diagnostics,
            )
        return _semantic_outcome(
            db,
            workspace=workspace,
            user=user,
            question=question,
            requested_dataset_keys=requested_dataset_keys,
            module_keys=module_keys,
            evidence_limit=evidence_limit,
            audit_entity_id=audit_entity_id,
            analysis_plan=plan,
            analysis_decisions=decisions,
            degraded_reason=planner_degraded_reason,
            planner_diagnostics=planner_diagnostics,
        )

    if (
        plan.mode == AnalysisMode.GENERATED
        and planner_diagnostics is not None
        and planner_diagnostics.validation_error_code
        == "question_constraint_unrepresented"
    ):
        return _empty_analysis_outcome(
            question=question,
            requested_dataset_keys=requested_dataset_keys,
            analysis_plan=plan,
            analysis_decisions=decisions,
            degraded_reason="question_constraint_unrepresented",
            planner_diagnostics=planner_diagnostics,
        )

    if plan.mode == AnalysisMode.GENERATED:
        return _generated_outcome(
            db,
            workspace=workspace,
            user=user,
            question=question,
            requested_dataset_keys=requested_dataset_keys,
            module_keys=module_keys,
            evidence_limit=evidence_limit,
            audit_entity_id=audit_entity_id,
            analysis_plan=plan,
            analysis_decisions=decisions,
            fields=fields,
            planner_diagnostics=planner_diagnostics,
            include_semantic=(
                legacy_semantic_allowed
                and (
                    routing_mode == AnalysisMode.HYBRID
                    or (routing_mode == AnalysisMode.SEMANTIC and record_set_required)
                )
            ),
            semantic_fallback_allowed=legacy_semantic_allowed,
            counting_unit=counting_unit,
            # A guarded generated query is an intended exact fallback path. Keep
            # planner fallback status in diagnostics, but only mark the outcome
            # degraded when the single generated relation cannot cover every
            # requested source. Generated validation/execution failures are handled
            # inside _generated_outcome.
            degraded_reason=(
                planner_degraded_reason
                if len(requested_data_sources) > 1
                else None
            ),
        )

    try:
        artifact = execute_analysis_plan(
            db,
            plan,
            workspace_id=workspace.id,
            enabled_module_keys=module_keys,
            field_definitions=fields,
            title="과거차 문제점 정형 분석",
            planner_diagnostics=planner_diagnostics,
        )
        analysis_result = artifact.to_payload()
    except Exception as error:
        if not legacy_semantic_allowed:
            return _empty_analysis_outcome(
                question=question,
                requested_dataset_keys=requested_dataset_keys,
                analysis_plan=plan,
                analysis_decisions=decisions,
                degraded_reason=_bounded_reason(error),
                planner_diagnostics=planner_diagnostics,
            )
        return _semantic_outcome(
            db,
            workspace=workspace,
            user=user,
            question=question,
            requested_dataset_keys=requested_dataset_keys,
            module_keys=module_keys,
            evidence_limit=evidence_limit,
            audit_entity_id=audit_entity_id,
            analysis_plan=_semantic_plan(),
            analysis_decisions=decisions,
            degraded_reason=_bounded_reason(error),
            planner_diagnostics=planner_diagnostics,
        )

    if plan.mode != AnalysisMode.HYBRID:
        return LegacyIssueAnalysisOutcome(
            analysis_plan=plan,
            search_plan=search_plan,
            analysis_result=analysis_result,
            evidence=[],
            search_profile=_empty_search_profile(search_plan.dataset_keys),
            gateway_decisions=decisions,
            degraded_reason=planner_degraded_reason,
            planner_diagnostics=planner_diagnostics,
        )

    if not legacy_semantic_allowed:
        return LegacyIssueAnalysisOutcome(
            analysis_plan=plan,
            search_plan=search_plan,
            analysis_result=analysis_result,
            evidence=[],
            search_profile=_empty_search_profile(search_plan.dataset_keys),
            gateway_decisions=decisions,
            degraded_reason="vehicle_checklist_semantic_unavailable",
            planner_diagnostics=planner_diagnostics,
        )

    semantic = _semantic_outcome(
        db,
        workspace=workspace,
        user=user,
        question=question,
        requested_dataset_keys=requested_dataset_keys,
        module_keys=module_keys,
        evidence_limit=evidence_limit,
        audit_entity_id=audit_entity_id,
        analysis_plan=plan,
        analysis_decisions=decisions,
        degraded_reason=planner_degraded_reason,
        planner_diagnostics=planner_diagnostics,
    )
    return LegacyIssueAnalysisOutcome(
        analysis_plan=plan,
        search_plan=semantic.search_plan,
        analysis_result=analysis_result,
        evidence=semantic.evidence,
        search_profile=semantic.search_profile,
        gateway_decisions=semantic.gateway_decisions,
        degraded_reason=semantic.degraded_reason,
        planner_diagnostics=planner_diagnostics,
    )


def _generated_outcome(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    requested_dataset_keys: tuple[str, ...] | None,
    module_keys: frozenset[str] | None,
    evidence_limit: int,
    audit_entity_id: str | None,
    analysis_plan: AnalysisPlanV1,
    analysis_decisions: list[AiGatewayDecision],
    fields: tuple[DatasetFieldDefinition, ...],
    planner_diagnostics: LegacyIssuePlannerDiagnosticsV1 | None,
    include_semantic: bool,
    semantic_fallback_allowed: bool,
    counting_unit: AnalysisCountingUnit | None,
    degraded_reason: str | None,
) -> LegacyIssueAnalysisOutcome:
    generated_decisions: list[AiGatewayDecision] = []
    try:
        from open_alm_api.domains.legacy_issues.analysis_generated_executor import (
            execute_generated_analysis,
        )
        from open_alm_api.domains.legacy_issues.analysis_sql_fallback import (
            plan_legacy_issue_generated_sql,
        )

        logical_columns = [
            {"key": "record_id", "label": "레코드 ID", "type": "text"},
            {
                "key": "stable_record_id",
                "label": "안정 레코드 ID",
                "type": "text",
            },
            {"key": "module_key", "label": "모듈", "type": "text"},
            {"key": "revision_id", "label": "리비전 ID", "type": "text"},
            *[
                {
                    "key": field.key,
                    "label": field.label_ko,
                    "aliases": list(field.aliases),
                    "type": field.field_type,
                }
                for field in fields
            ],
            *[
                {
                    "key": f"{field.key}__date",
                    "label": f"{field.label_ko} (검증된 날짜)",
                    "type": "date",
                }
                for field in fields
                if field.field_type == "date"
            ],
        ]
        generated_plan, generated_decisions = plan_legacy_issue_generated_sql(
            db,
            workspace=workspace,
            user=user,
            question=question,
            logical_columns=logical_columns,
            audit_entity_id=audit_entity_id,
            family_id=(
                analysis_plan.delegated_family_id.value
                if analysis_plan.delegated_family_id is not None
                else None
            ),
            data_source=analysis_plan.delegated_data_source,
            counting_unit=counting_unit,
        )
        analysis_result = execute_generated_analysis(
            db,
            workspace_id=workspace.id,
            enabled_module_keys=module_keys,
            field_definitions=fields,
            generated_plan=generated_plan,
            family_id=(
                analysis_plan.delegated_family_id.value
                if analysis_plan.delegated_family_id is not None
                else "generated_sql"
            ),
        )
        if planner_diagnostics is not None:
            analysis_result["planner_diagnostics"] = planner_diagnostics.model_dump(
                mode="json",
                exclude_none=True,
            )
        search_plan = _neutral_search_plan(
            question=question,
            requested_dataset_keys=requested_dataset_keys,
            intent=AnalysisMode.GENERATED.value,
        )
        if include_semantic:
            semantic = _semantic_outcome(
                db,
                workspace=workspace,
                user=user,
                question=question,
                requested_dataset_keys=requested_dataset_keys,
                module_keys=module_keys,
                evidence_limit=evidence_limit,
                audit_entity_id=audit_entity_id,
                analysis_plan=analysis_plan,
                analysis_decisions=[
                    *analysis_decisions,
                    *generated_decisions,
                ],
                degraded_reason=degraded_reason,
                planner_diagnostics=planner_diagnostics,
            )
            return LegacyIssueAnalysisOutcome(
                analysis_plan=analysis_plan,
                search_plan=semantic.search_plan,
                analysis_result=analysis_result,
                evidence=semantic.evidence,
                search_profile=semantic.search_profile,
                gateway_decisions=semantic.gateway_decisions,
                degraded_reason=semantic.degraded_reason,
                planner_diagnostics=planner_diagnostics,
            )
        return LegacyIssueAnalysisOutcome(
            analysis_plan=analysis_plan,
            search_plan=search_plan,
            analysis_result=analysis_result,
            evidence=[],
            search_profile=_empty_search_profile(search_plan.dataset_keys),
            gateway_decisions=[*analysis_decisions, *generated_decisions],
            degraded_reason=degraded_reason,
            planner_diagnostics=planner_diagnostics,
        )
    except Exception as error:
        if not semantic_fallback_allowed:
            return _empty_analysis_outcome(
                question=question,
                requested_dataset_keys=requested_dataset_keys,
                analysis_plan=analysis_plan,
                analysis_decisions=[*analysis_decisions, *generated_decisions],
                degraded_reason=_bounded_reason(error),
                planner_diagnostics=planner_diagnostics,
            )
        return _semantic_outcome(
            db,
            workspace=workspace,
            user=user,
            question=question,
            requested_dataset_keys=requested_dataset_keys,
            module_keys=module_keys,
            evidence_limit=evidence_limit,
            audit_entity_id=audit_entity_id,
            analysis_plan=_semantic_plan(),
            analysis_decisions=[*analysis_decisions, *generated_decisions],
            degraded_reason=_bounded_reason(error),
            planner_diagnostics=planner_diagnostics,
        )


def _empty_analysis_outcome(
    *,
    question: str,
    requested_dataset_keys: tuple[str, ...] | None,
    analysis_plan: AnalysisPlanV1,
    analysis_decisions: list[AiGatewayDecision],
    degraded_reason: str,
    planner_diagnostics: LegacyIssuePlannerDiagnosticsV1 | None,
) -> LegacyIssueAnalysisOutcome:
    search_plan = _neutral_search_plan(
        question=question,
        requested_dataset_keys=requested_dataset_keys,
        intent=analysis_plan.mode.value,
    )
    return LegacyIssueAnalysisOutcome(
        analysis_plan=analysis_plan,
        search_plan=search_plan,
        analysis_result=None,
        evidence=[],
        search_profile=_empty_search_profile(search_plan.dataset_keys),
        gateway_decisions=analysis_decisions,
        degraded_reason=degraded_reason,
        planner_diagnostics=planner_diagnostics,
    )


def _semantic_outcome(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    requested_dataset_keys: tuple[str, ...] | None,
    module_keys: frozenset[str] | None,
    evidence_limit: int,
    audit_entity_id: str | None,
    analysis_plan: AnalysisPlanV1,
    analysis_decisions: list[AiGatewayDecision],
    degraded_reason: str | None = None,
    planner_diagnostics: LegacyIssuePlannerDiagnosticsV1 | None = None,
) -> LegacyIssueAnalysisOutcome:
    search_plan, search_decision = plan_legacy_issue_search(
        db,
        workspace=workspace,
        user=user,
        question=question,
        requested_dataset_keys=requested_dataset_keys,
        audit_entity_id=audit_entity_id,
        source="legacy_issues.analysis.semantic_plan",
        context_strategy="legacy_issue_analysis_semantic_plan",
    )
    evidence, profile = retrieval_application.search_legacy_issue_evidence_response(
        db,
        workspace=workspace,
        plan=search_plan,
        limit=evidence_limit,
        module_keys=module_keys,
    )
    decisions = list(analysis_decisions)
    if search_decision is not None:
        decisions.append(search_decision)
    return LegacyIssueAnalysisOutcome(
        analysis_plan=analysis_plan,
        search_plan=search_plan,
        analysis_result=None,
        evidence=evidence,
        search_profile=profile,
        gateway_decisions=decisions,
        degraded_reason=degraded_reason,
        planner_diagnostics=planner_diagnostics,
    )


def _neutral_search_plan(
    *,
    question: str,
    requested_dataset_keys: tuple[str, ...] | None,
    intent: str,
) -> LegacyIssueAssistantSearchPlan:
    return sanitize_legacy_issue_search_plan(
        question=question,
        dataset_keys=requested_dataset_keys or ("common-master",),
        intent=intent,
        report_focus=("structured_analysis",),
    )


def _empty_search_profile(
    dataset_keys: tuple[str, ...],
) -> LegacyIssueSearchProfile:
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


def _semantic_plan() -> AnalysisPlanV1:
    return AnalysisPlanV1(
        schema_version=1,
        mode=AnalysisMode.SEMANTIC,
        queries=(),
        clarification=None,
        delegated_family_id=QueryFamilyId.SEMANTIC_SIMILAR,
    )


def _bounded_reason(error: Exception) -> str:
    reason = " ".join(str(error).split()) or type(error).__name__
    return reason[:240]


def compact_analysis_prompt_payload(
    analysis_result: dict[str, Any] | None,
    *,
    analysis_plan: AnalysisPlanV1 | None = None,
) -> dict[str, Any] | None:
    """Keep exact result context bounded while the full artifact remains available."""

    if analysis_result is None:
        return None
    request_by_id = (
        {request.query_id: request for request in analysis_plan.queries}
        if analysis_plan is not None
        else {}
    )
    queries = analysis_result.get("queries")
    compact_queries: list[dict[str, Any]] = []
    if isinstance(queries, list):
        for query in queries[:6]:
            if not isinstance(query, dict):
                continue
            columns = query.get("columns")
            coverage = query.get("coverage")
            request = request_by_id.get(str(query.get("id") or ""))
            selected_rows, available_row_count = _select_analysis_prompt_rows(
                query,
                request=request,
            )
            compact_queries.append(
                {
                    "id": query.get("id"),
                    "title": query.get("title"),
                    "family_id": query.get("family_id"),
                    "family_version": query.get("family_version"),
                    "shape": query.get("shape"),
                    "exactness": query.get("exactness"),
                    "columns": columns[:32] if isinstance(columns, list) else [],
                    "rows": selected_rows,
                    "available_row_count": available_row_count,
                    "context_row_count": len(selected_rows),
                    "context_truncated": len(selected_rows) < available_row_count,
                    "request": _compact_query_request(request),
                    "totals": _compact_json_value(query.get("totals")),
                    "coverage": coverage[:32] if isinstance(coverage, list) else [],
                    "warnings": _compact_json_value(query.get("warnings")),
                    "truncated": query.get("truncated"),
                }
            )
    payload = {
        "version": analysis_result.get("version"),
        "mode": analysis_result.get("mode"),
        "title": _compact_json_value(analysis_result.get("title")),
        "exactness": analysis_result.get("exactness"),
        "scope": _compact_json_value(analysis_result.get("scope")),
        "queries": compact_queries,
        "warnings": _compact_json_value(analysis_result.get("warnings")),
    }
    payload = _compact_json_value(payload)
    if not isinstance(payload, dict):
        return None
    _fit_analysis_prompt_budget(payload)
    return payload


def _compact_query_request(request: Any) -> dict[str, Any] | None:
    if request is None:
        return None
    return {
        "query_id": request.query_id,
        "family_id": request.family_id.value,
        "data_source": request.data_source.value,
        "metrics": [
            {
                "operator": metric.operator.value,
                "field_key": metric.field_key,
                "alias": metric.alias,
            }
            for metric in request.metrics
        ],
        "dimensions": [
            {
                "field_key": dimension.field_key,
                "alias": dimension.alias,
                "time_grain": (
                    dimension.time_grain.value
                    if dimension.time_grain is not None
                    else None
                ),
            }
            for dimension in request.dimensions
        ],
        "filters": (
            request.filters.model_dump(mode="json", exclude_none=True)
            if request.filters is not None
            else None
        ),
        "record_set": (
            request.record_set.model_dump(mode="json", exclude_none=True)
            if request.record_set is not None
            else None
        ),
        "comparisons": [
            comparison.model_dump(mode="json", exclude_none=True)
            for comparison in request.comparisons
        ],
        "windows": [
            window.model_dump(mode="json", exclude_none=True)
            for window in request.windows
        ],
        "detail_fields": list(request.detail_fields),
        "sort": [sort.model_dump(mode="json") for sort in request.sort],
        "limit": request.limit,
    }


def _select_analysis_prompt_rows(
    query: dict[str, Any],
    *,
    request: Any = None,
) -> tuple[list[dict[str, Any]], int]:
    rows = query.get("rows")
    if not isinstance(rows, list):
        return [], 0
    normalized_rows = [row for row in rows if isinstance(row, dict)]
    available = len(normalized_rows)
    if available <= _MAX_ANALYSIS_PROMPT_ROWS_PER_QUERY:
        return normalized_rows, available

    family_id = str(query.get("family_id") or "")
    if family_id in _TIME_CONTEXT_FAMILIES:
        return (
            _balanced_time_rows(
                query,
                normalized_rows,
                limit=_MAX_ANALYSIS_PROMPT_ROWS_PER_QUERY,
                request=request,
            ),
            available,
        )
    if family_id == QueryFamilyId.TOP_N_WITHIN_PARENT.value:
        balanced = _balanced_parent_rows(
            query,
            normalized_rows,
            limit=_MAX_ANALYSIS_PROMPT_ROWS_PER_QUERY,
            request=request,
        )
        return balanced, available
    return normalized_rows[:_MAX_ANALYSIS_PROMPT_ROWS_PER_QUERY], available


def _balanced_time_rows(
    query: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    limit: int,
    request: Any = None,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    group_keys, time_key = _time_context_keys(query, request=request)
    if time_key is None:
        return _evenly_sampled_rows(rows, limit=limit)

    groups = list(_rows_by_group(rows, group_keys).items())
    selected_groups = groups
    if sum(min(len(group_rows), 2) for _, group_rows in groups) > limit:
        selected_count = min(len(groups), limit)
        while selected_count > 1:
            candidates = _evenly_sampled_rows(groups, limit=selected_count)
            if sum(min(len(group_rows), 2) for _, group_rows in candidates) <= limit:
                selected_groups = candidates
                break
            selected_count -= 1
        else:
            selected_groups = _evenly_sampled_rows(groups, limit=1)

    quotas = [min(len(group_rows), 2) for _, group_rows in selected_groups]
    remaining = limit - sum(quotas)
    while remaining > 0:
        added = False
        for index, (_, group_rows) in enumerate(selected_groups):
            if quotas[index] >= len(group_rows):
                continue
            quotas[index] += 1
            remaining -= 1
            added = True
            if remaining == 0:
                break
        if not added:
            break

    selected: list[dict[str, Any]] = []
    for (_, group_rows), quota in zip(selected_groups, quotas, strict=True):
        selected.extend(_evenly_sampled_rows(group_rows, limit=quota))
    return selected[:limit]


def _balanced_parent_rows(
    query: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    limit: int,
    request: Any = None,
) -> list[dict[str, Any]]:
    dimension_keys = _query_dimension_keys(query, request=request)
    parent_keys = dimension_keys[:-1]
    if not parent_keys:
        return rows[:limit]

    groups = list(_rows_by_group(rows, parent_keys).values())
    if len(groups) > limit:
        groups = _evenly_sampled_rows(groups, limit=limit)
    selected: list[dict[str, Any]] = []
    depth = 0
    while len(selected) < limit:
        added = False
        for group_rows in groups:
            if depth < len(group_rows):
                selected.append(group_rows[depth])
                added = True
                if len(selected) == limit:
                    break
        if not added:
            break
        depth += 1
    return selected


def _time_context_keys(
    query: dict[str, Any],
    *,
    request: Any = None,
) -> tuple[list[str], str | None]:
    dimension_keys = _query_dimension_keys(query, request=request)
    request_dimensions = _request_dimensions(request)
    time_keys = {
        str(dimension.get("alias") or dimension.get("field_key"))
        for dimension in request_dimensions
        if dimension.get("time_grain") is not None
    }
    columns = query.get("columns")
    if isinstance(columns, list):
        time_keys.update(
            str(column.get("key"))
            for column in columns
            if isinstance(column, dict)
            and column.get("role") == "dimension"
            and column.get("type") == "date"
            and isinstance(column.get("key"), str)
        )
    ordered_time_keys = [key for key in dimension_keys if key in time_keys]
    if not ordered_time_keys and len(dimension_keys) == 1:
        ordered_time_keys = dimension_keys
    if not ordered_time_keys:
        return [], None
    return (
        [key for key in dimension_keys if key not in set(ordered_time_keys)],
        ordered_time_keys[-1],
    )


def _query_dimension_keys(
    query: dict[str, Any],
    *,
    request: Any = None,
) -> list[str]:
    columns = query.get("columns")
    dimension_keys = [
        str(column.get("key"))
        for column in columns
        if isinstance(column, dict)
        and column.get("role") == "dimension"
        and isinstance(column.get("key"), str)
    ] if isinstance(columns, list) else []
    if dimension_keys:
        return dimension_keys
    return [
        str(dimension.get("alias") or dimension.get("field_key"))
        for dimension in _request_dimensions(request)
        if dimension.get("alias") or dimension.get("field_key")
    ]


def _request_dimensions(request: Any) -> list[dict[str, Any]]:
    if request is None:
        return []
    dimensions = (
        request.get("dimensions")
        if isinstance(request, dict)
        else getattr(request, "dimensions", ())
    )
    if not isinstance(dimensions, (list, tuple)):
        return []
    normalized: list[dict[str, Any]] = []
    for dimension in dimensions:
        if isinstance(dimension, dict):
            normalized.append(dimension)
            continue
        normalized.append(
            {
                "field_key": getattr(dimension, "field_key", None),
                "alias": getattr(dimension, "alias", None),
                "time_grain": getattr(dimension, "time_grain", None),
            }
        )
    return normalized


def _rows_by_group(
    rows: list[dict[str, Any]],
    group_keys: list[str],
) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(tuple(row.get(key) for key in group_keys), []).append(row)
    return groups


def _evenly_sampled_rows[T](rows: list[T], *, limit: int) -> list[T]:
    if limit <= 0:
        return []
    if len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[-1]]
    return [
        rows[index * (len(rows) - 1) // (limit - 1)]
        for index in range(limit)
    ]


def _compact_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 10:
        return str(value)[:_MAX_ANALYSIS_PROMPT_STRING_CHARS]
    if isinstance(value, str):
        return value[:_MAX_ANALYSIS_PROMPT_STRING_CHARS]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {
            str(key)[:80]: _compact_json_value(item, depth=depth + 1)
            for key, item in list(value.items())[:64]
        }
    if isinstance(value, (list, tuple)):
        return [_compact_json_value(item, depth=depth + 1) for item in value[:64]]
    return str(value)[:_MAX_ANALYSIS_PROMPT_STRING_CHARS]


def _fit_analysis_prompt_budget(payload: dict[str, Any]) -> None:
    queries = payload.get("queries")
    if not isinstance(queries, list):
        return

    def oversized() -> bool:
        return (
            len(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            > _MAX_ANALYSIS_PROMPT_CHARS
        )

    while oversized():
        changed = False
        for query in reversed(queries):
            rows = query.get("rows") if isinstance(query, dict) else None
            if isinstance(rows, list) and len(rows) > 1:
                _drop_analysis_prompt_row(query, rows)
                query["context_row_count"] = len(rows)
                query["context_truncated"] = True
                changed = True
                if not oversized():
                    return
        if not changed:
            break
    if not oversized():
        return
    for query in reversed(queries):
        if not isinstance(query, dict):
            continue
        coverage = query.get("coverage")
        if isinstance(coverage, list):
            coverage.clear()
        if not oversized():
            return
    for query in reversed(queries):
        if not isinstance(query, dict):
            continue
        columns = query.get("columns")
        rows = query.get("rows")
        if not isinstance(columns, list) or len(columns) <= 16:
            continue
        columns[:] = columns[:16]
        allowed_keys = {
            column.get("key")
            for column in columns
            if isinstance(column, dict) and isinstance(column.get("key"), str)
        }
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    for key in tuple(row):
                        if key not in allowed_keys:
                            row.pop(key, None)
        if not oversized():
            return
    if oversized():
        payload["warnings"] = ["분석 요약 컨텍스트가 축약되었습니다."]
        for query in queries:
            if isinstance(query, dict):
                query["rows"] = []
                query["coverage"] = []
                query["totals"] = {}
                query["warnings"] = []
                columns = query.get("columns")
                if isinstance(columns, list):
                    query["columns"] = columns[:8]
    if oversized():
        payload["scope"] = {
            key: value
            for key, value in (
                payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
            ).items()
            if key in {"dataset_key", "module_keys", "revision_ids", "source_count"}
        }
        payload["queries"] = [
            {
                "id": query.get("id"),
                "title": query.get("title"),
                "family_id": query.get("family_id"),
                "family_version": query.get("family_version"),
                "exactness": query.get("exactness"),
                "columns": [],
                "rows": [],
                "totals": {},
                "coverage": [],
                "warnings": [],
                "truncated": query.get("truncated"),
            }
            for query in queries
            if isinstance(query, dict)
        ]


def _drop_analysis_prompt_row(
    query: dict[str, Any],
    rows: list[Any],
) -> None:
    family_id = str(query.get("family_id") or "")
    if family_id in _TIME_CONTEXT_FAMILIES and len(rows) > 2:
        normalized_rows = [row for row in rows if isinstance(row, dict)]
        rows[:] = _balanced_time_rows(
            query,
            normalized_rows,
            limit=len(rows) - 1,
            request=query.get("request"),
        )
        return
    if family_id == QueryFamilyId.TOP_N_WITHIN_PARENT.value:
        normalized_rows = [row for row in rows if isinstance(row, dict)]
        rows[:] = _balanced_parent_rows(
            query,
            normalized_rows,
            limit=len(rows) - 1,
            request=query.get("request"),
        )
        return
    rows.pop()


__all__ = [
    "LegacyIssueAnalysisOutcome",
    "compact_analysis_prompt_payload",
    "run_legacy_issue_analysis",
]
