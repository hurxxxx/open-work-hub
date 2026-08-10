from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Iterable

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ai_do_api.domains.ai.gateway import (
    AiGatewayContextPack,
    AiGatewayDecision,
    LlmWorkloadContext,
    execute_llm,
)
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.legacy_issues.analysis_catalog import (
    AnalysisCatalogError,
    AnalysisFieldCapabilities,
    CATALOG_VERSION,
    FamilyExecutionKind,
    QUERY_FAMILY_CATALOG,
    QueryFamilyDescriptor,
    analysis_catalog_payload,
    build_analysis_field_catalog,
    get_query_family_descriptor,
    validate_query_request,
)
from ai_do_api.domains.legacy_issues.analysis_composites import (
    build_standard_report_plan,
)
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisCountingUnit,
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
    FilterGroupV1,
    FilterJunction,
    FilterOperator,
    LegacyIssuePlannerDiagnosticsV1,
    MetricOperator,
    QueryFamilyId,
    QueryRequestV1,
)
from ai_do_api.domains.legacy_issues.dataset_records import DatasetFieldDefinition
from ai_do_api.domains.legacy_issues.task_kinds import (
    LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID,
)
from ai_do_api.domains.retrieval.candidate_ranking import (
    CandidateDocument,
    CandidateRankingRequest,
    CandidateRankingService,
)


_PLANNER_SOURCE = "legacy_issues.analysis_plan"
_PLANNER_CONTEXT_STRATEGY = "legacy_issue_analysis_plan"
_MAX_QUESTION_CHARS = 12_000
_MAX_PROMPT_CHARS = 96_000
_MAX_REPAIR_REASON_CHARS = 600
_MAX_OUTPUT_TOKENS = 4_096
_PRIMARY_FAMILY_DETAIL_LIMIT = 8
_REPAIR_FAMILY_DETAIL_LIMIT = 16


@dataclass(frozen=True, slots=True)
class LegacyIssuePlannerResult:
    plan: AnalysisPlanV1
    decisions: list[AiGatewayDecision]
    diagnostics: LegacyIssuePlannerDiagnosticsV1

    def __iter__(self):
        # Keep the original two-value unpacking contract for callers while exposing
        # diagnostics as an explicit attribute.
        yield self.plan
        yield self.decisions


def plan_legacy_issue_analysis(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    question: str,
    fields: Iterable[DatasetFieldDefinition],
    audit_entity_id: str | None = None,
    recent_messages: list[dict[str, Any]] | None = None,
    routing_mode: AnalysisMode | None = None,
    family_categories: tuple[str, ...] = (),
    record_set_required: bool = False,
    data_sources: tuple[AnalysisDataSource, ...] = (),
    counting_unit: AnalysisCountingUnit | None = None,
    report_requested: bool = False,
) -> LegacyIssuePlannerResult:
    """Plan reusable analysis operators without allowing the model to write SQL."""

    decisions: list[AiGatewayDecision] = []
    requested_data_sources = data_sources or (AnalysisDataSource.LEGACY_ISSUES,)
    checklist_requested = AnalysisDataSource.VEHICLE_CHECKLISTS in requested_data_sources
    effective_routing_mode = (
        AnalysisMode.HYBRID
        if routing_mode == AnalysisMode.SEMANTIC and record_set_required
        else AnalysisMode.ANALYTICS
        if routing_mode == AnalysisMode.SEMANTIC and checklist_requested
        else routing_mode
    )
    if _semantic_fast_path_allowed(
        routing_mode=effective_routing_mode,
        family_categories=family_categories,
        record_set_required=record_set_required,
        data_sources=requested_data_sources,
    ):
        plan = _semantic_fallback()
        return LegacyIssuePlannerResult(
            plan=plan,
            decisions=decisions,
            diagnostics=_planner_diagnostics(
                plan=plan,
                status="fast_path",
                attempt_count=0,
                candidate_family_count=0,
                prompt_chars=0,
            ),
        )

    runtime_fields = tuple(fields)
    grounded_code_constraints: tuple[tuple[str, tuple[str, ...]], ...] = ()
    try:
        normalized_question = _bounded_question(question)
        field_catalog = build_analysis_field_catalog(runtime_fields)
        grounded_code_constraints = _grounded_code_constraints(
            normalized_question,
            fields=runtime_fields,
        )
        candidate_family_ids = _rank_candidate_family_ids(
            question=normalized_question,
            recent_messages=recent_messages or [],
            family_categories=family_categories,
            limit=_REPAIR_FAMILY_DETAIL_LIMIT,
        )
        primary_family_ids = candidate_family_ids[:_PRIMARY_FAMILY_DETAIL_LIMIT]
        primary_catalog = analysis_catalog_payload(
            fields=runtime_fields,
            detailed_family_ids=primary_family_ids,
            compact=True,
        )
        primary_messages = _planner_messages(
            question=normalized_question,
            catalog_payload=primary_catalog,
            recent_messages=recent_messages or [],
            routing_mode=effective_routing_mode,
            family_categories=family_categories,
            record_set_required=record_set_required,
            data_sources=requested_data_sources,
            counting_unit=counting_unit,
            grounded_code_constraints=grounded_code_constraints,
        )
    except ValueError:
        plan = _planner_failure_fallback(
            effective_routing_mode,
            data_sources=requested_data_sources,
            fields=runtime_fields,
        )
        return LegacyIssuePlannerResult(
            plan=plan,
            decisions=decisions,
            diagnostics=_planner_diagnostics(
                plan=plan,
                status="fallback",
                attempt_count=0,
                candidate_family_count=0,
                prompt_chars=0,
                fallback_reason="input_invalid",
            ),
        )
    except Exception:
        plan = _planner_failure_fallback(
            effective_routing_mode,
            data_sources=requested_data_sources,
            fields=runtime_fields,
            report_requested=report_requested,
        )
        return LegacyIssuePlannerResult(
            plan=plan,
            decisions=decisions,
            diagnostics=_planner_diagnostics(
                plan=plan,
                status="fallback",
                attempt_count=0,
                candidate_family_count=0,
                prompt_chars=0,
                fallback_reason="catalog_preparation_failed",
            ),
        )

    primary_prompt_chars = _prompt_chars(primary_messages)
    if not _within_prompt_budget(primary_messages):
        plan = _planner_failure_fallback(
            effective_routing_mode,
            data_sources=requested_data_sources,
            fields=runtime_fields,
            report_requested=report_requested and not grounded_code_constraints,
        )
        return LegacyIssuePlannerResult(
            plan=plan,
            decisions=decisions,
            diagnostics=_planner_diagnostics(
                plan=plan,
                status="fallback",
                attempt_count=0,
                candidate_family_count=len(primary_family_ids),
                prompt_chars=primary_prompt_chars,
                fallback_reason="prompt_budget_exceeded",
            ),
        )

    repair_reason: str | None = None
    validation_error_code: str | None = None
    attempt_count = 0
    last_prompt_chars = primary_prompt_chars
    best_partial_plan: AnalysisPlanV1 | None = None
    for attempt in range(2):
        if attempt == 0:
            attempt_messages = list(primary_messages)
        else:
            repair_catalog = analysis_catalog_payload(
                fields=runtime_fields,
                detailed_family_ids=candidate_family_ids,
                compact=True,
            )
            attempt_messages = _planner_messages(
                question=normalized_question,
                catalog_payload=repair_catalog,
                recent_messages=recent_messages or [],
                routing_mode=effective_routing_mode,
                family_categories=family_categories,
                record_set_required=record_set_required,
                data_sources=requested_data_sources,
                counting_unit=counting_unit,
                grounded_code_constraints=grounded_code_constraints,
            )
            attempt_messages.append(_repair_message(repair_reason))
        last_prompt_chars = _prompt_chars(attempt_messages)
        if not _within_prompt_budget(attempt_messages):
            plan = _attempts_exhausted_fallback(
                effective_routing_mode,
                data_sources=requested_data_sources,
                fields=runtime_fields,
                report_requested=report_requested and not grounded_code_constraints,
            )
            return LegacyIssuePlannerResult(
                plan=plan,
                decisions=decisions,
                diagnostics=_planner_diagnostics(
                    plan=plan,
                    status="fallback",
                    attempt_count=attempt_count,
                    candidate_family_count=len(primary_family_ids),
                    prompt_chars=last_prompt_chars,
                    fallback_reason="repair_prompt_budget_exceeded",
                    validation_error_code=validation_error_code,
                ),
            )
        attempt_count += 1
        try:
            result = execute_llm(
                LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID,
                LlmWorkloadContext(
                    source=_PLANNER_SOURCE,
                    workspace_id=workspace.id,
                    actor_user_id=user.id,
                    app_id="legacy-issues",
                ),
                db,
                messages=attempt_messages,
                context_pack=AiGatewayContextPack(
                    messages=attempt_messages,
                    context_strategy=_PLANNER_CONTEXT_STRATEGY,
                    estimated_input_tokens=_estimate_tokens(attempt_messages),
                ),
                audit_entity_id=audit_entity_id,
                max_tokens=_MAX_OUTPUT_TOKENS,
                temperature=0,
            )
            decisions.append(result.decision)
        except Exception:
            validation_error_code = "llm_execution_failed"
            repair_reason = "llm_execution_failed"
            continue
        try:
            payload = json.loads(result.completion.text.strip())
        except (json.JSONDecodeError, TypeError) as error:
            validation_error_code = "response_json_invalid"
            repair_reason = _bounded_error_reason(error)
            continue
        if not isinstance(payload, dict):
            validation_error_code = "response_object_invalid"
            repair_reason = "analysis_plan_response_must_be_an_object"
            continue
        payload = _normalize_plan_payload(payload)
        partial_plan = _salvage_partial_plan(
            payload,
            fields=field_catalog,
            data_sources=requested_data_sources,
            counting_unit=counting_unit,
            grounded_code_constraints=grounded_code_constraints,
            routing_mode=effective_routing_mode,
        )
        if partial_plan is not None and (
            best_partial_plan is None
            or _partial_plan_score(
                partial_plan,
                data_sources=requested_data_sources,
            )
            > _partial_plan_score(
                best_partial_plan,
                data_sources=requested_data_sources,
            )
        ):
            best_partial_plan = partial_plan
        try:
            plan = AnalysisPlanV1.model_validate(payload)
        except ValidationError as error:
            validation_error_code = "plan_schema_invalid"
            repair_reason = _bounded_error_reason(error)
            continue
        plan = _bind_single_requested_data_source(
            plan,
            data_sources=requested_data_sources,
        )
        if plan.mode == AnalysisMode.CLARIFY:
            return LegacyIssuePlannerResult(
                plan=plan,
                decisions=decisions,
                diagnostics=_planner_diagnostics(
                    plan=plan,
                    status="valid" if attempt == 0 else "repaired",
                    attempt_count=attempt_count,
                    candidate_family_count=(
                        len(primary_family_ids)
                        if attempt == 0
                        else len(candidate_family_ids)
                    ),
                    prompt_chars=last_prompt_chars,
                    validation_error_code=validation_error_code,
                ),
            )
        try:
            validated_queries = tuple(
                (query, validate_query_request(query, fields=field_catalog))
                for query in plan.queries
            )
            _validate_counting_unit(
                validated_queries,
                counting_unit=counting_unit,
            )
            if (
                attempt == 0
                and record_set_required
                and not any(query.record_set is not None for query in plan.queries)
            ):
                raise AnalysisCatalogError(
                    "routing hint suggests cohort re-entry; verify it and add record_set "
                    "when the question has a seed entity set followed by re-entry"
                )
            requested_source_set = set(requested_data_sources)
            planned_source_set = {query.data_source for query in plan.queries} or {
                plan.delegated_data_source
            }
            if not requested_source_set.issubset(planned_source_set):
                raise AnalysisCatalogError(
                    "routing hint requires the requested analysis data source"
                )
            _validate_grounded_code_constraints(
                plan,
                constraints=grounded_code_constraints,
            )
        except AnalysisCatalogError as error:
            validation_error_code = (
                "question_constraint_unrepresented"
                if str(error).startswith("question_constraint_unrepresented:")
                else "catalog_validation_failed"
            )
            repair_reason = _bounded_error_reason(error)
            continue
        return LegacyIssuePlannerResult(
            plan=plan,
            decisions=decisions,
            diagnostics=_planner_diagnostics(
                plan=plan,
                status="valid" if attempt == 0 else "repaired",
                attempt_count=attempt_count,
                candidate_family_count=(
                    len(primary_family_ids) if attempt == 0 else len(candidate_family_ids)
                ),
                prompt_chars=last_prompt_chars,
                validation_error_code=validation_error_code,
            ),
        )

    if best_partial_plan is not None:
        plan = best_partial_plan
        fallback_reason = "partial_plan_salvaged"
    else:
        plan = _attempts_exhausted_fallback(
            effective_routing_mode,
            data_sources=requested_data_sources,
            fields=runtime_fields,
            report_requested=report_requested and not grounded_code_constraints,
        )
        fallback_reason = "attempts_exhausted"
    return LegacyIssuePlannerResult(
        plan=plan,
        decisions=decisions,
        diagnostics=_planner_diagnostics(
            plan=plan,
            status="fallback",
            attempt_count=attempt_count,
            candidate_family_count=len(primary_family_ids),
            prompt_chars=last_prompt_chars,
            fallback_reason=fallback_reason,
            validation_error_code=validation_error_code,
        ),
    )


_SEQUENCE_FILTER_OPERATORS = frozenset(
    {
        FilterOperator.IN.value,
        FilterOperator.NOT_IN.value,
        FilterOperator.BETWEEN.value,
        FilterOperator.CONTAINS_ANY.value,
        FilterOperator.CONTAINS_ALL.value,
    }
)
_NO_OPERAND_FILTER_OPERATORS = frozenset(
    {
        FilterOperator.IS_NULL.value,
        FilterOperator.IS_NOT_NULL.value,
    }
)
_SORT_KEY_PREFIX = re.compile(r"^(?:dimension|metric|window):", re.IGNORECASE)
_SORT_DIRECTION_SUFFIX = re.compile(r"\s+(?:asc|desc)\s*$", re.IGNORECASE)


def _normalize_plan_payload(
    raw_payload: dict[str, Any],
) -> dict[str, Any]:
    """Repair harmless LLM serialization drift before contract validation.

    The model still selects the family, fields, filters, and values. This layer only
    canonicalizes optional JSON containers, redundant operands, and alias references
    whose meaning is unchanged. It never invents or removes a population predicate.
    """

    payload = deepcopy(raw_payload)
    for key in ("delegated_family_id", "delegated_data_source"):
        if payload.get(key) is None:
            payload.pop(key, None)
    if payload.get("queries") is None:
        payload["queries"] = []
    queries = payload.get("queries")
    if not isinstance(queries, list):
        return payload

    normalized_queries: list[Any] = []
    for index, raw_query in enumerate(queries):
        if not isinstance(raw_query, dict):
            normalized_queries.append(raw_query)
            continue
        query = _normalize_query_payload(raw_query, index=index)
        normalized_queries.append(query)

    mode = str(payload.get("mode") or "").strip().lower()
    query_kinds = [
        (
            _family_descriptor(family_id).execution_kind
            if isinstance(query, dict)
            and (family_id := _query_family_id(query.get("family_id"))) is not None
            else None
        )
        for query in normalized_queries
    ]
    if (
        mode == AnalysisMode.GENERATED.value
        and len(normalized_queries) == 1
        and query_kinds == [FamilyExecutionKind.GENERATED]
    ):
        query = normalized_queries[0]
        assert isinstance(query, dict)
        family_id = _query_family_id(query.get("family_id"))
        assert family_id is not None
        data_source = query.get("data_source")
        payload.update(
            {
                "queries": [],
                "delegated_family_id": family_id.value,
            }
        )
        if data_source:
            payload["delegated_data_source"] = data_source
        return payload
    if (
        mode == AnalysisMode.SEMANTIC.value
        and len(normalized_queries) == 1
        and query_kinds == [FamilyExecutionKind.SEMANTIC]
    ):
        query = normalized_queries[0]
        assert isinstance(query, dict)
        family_id = _query_family_id(query.get("family_id"))
        assert family_id is not None
        data_source = query.get("data_source")
        payload.update(
            {
                "queries": [],
                "delegated_family_id": family_id.value,
            }
        )
        if data_source:
            payload["delegated_data_source"] = data_source
        return payload

    if mode == AnalysisMode.HYBRID.value and any(
        kind == FamilyExecutionKind.SEMANTIC for kind in query_kinds
    ):
        non_semantic_queries = [
            query
            for query, kind in zip(normalized_queries, query_kinds, strict=True)
            if kind != FamilyExecutionKind.SEMANTIC
        ]
        # Hybrid execution already performs one semantic retrieval outside the typed
        # query list. Remove only those redundant semantic nodes, and only when an
        # exact node remains. Generated/composite nodes stay invalid and enter repair.
        payload["queries"] = (
            non_semantic_queries if non_semantic_queries else normalized_queries
        )
    else:
        payload["queries"] = normalized_queries
    return payload


def _salvage_partial_plan(
    payload: dict[str, Any],
    *,
    fields: Mapping[str, AnalysisFieldCapabilities],
    data_sources: tuple[AnalysisDataSource, ...],
    counting_unit: AnalysisCountingUnit | None,
    grounded_code_constraints: tuple[tuple[str, tuple[str, ...]], ...],
    routing_mode: AnalysisMode | None,
) -> AnalysisPlanV1 | None:
    """Keep only independently valid catalog queries from a broken model plan."""

    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list):
        return None
    requested_sources = set(data_sources)
    singleton_source = data_sources[0] if len(data_sources) == 1 else None
    valid_queries: list[QueryRequestV1] = []
    for raw_query in raw_queries[:6]:
        try:
            query = QueryRequestV1.model_validate(raw_query)
            if singleton_source is not None:
                query = query.model_copy(update={"data_source": singleton_source})
            if query.data_source not in requested_sources:
                continue
            descriptor = validate_query_request(query, fields=fields)
            _validate_counting_unit(
                ((query, descriptor),),
                counting_unit=counting_unit,
            )
        except (AnalysisCatalogError, ValidationError, ValueError):
            continue
        valid_queries.append(query)
    if not valid_queries:
        return None

    requested_mode = str(payload.get("mode") or "").strip().lower()
    if routing_mode == AnalysisMode.METADATA:
        mode = AnalysisMode.METADATA
    elif (
        requested_mode == AnalysisMode.HYBRID.value
        or routing_mode == AnalysisMode.HYBRID
    ):
        mode = AnalysisMode.HYBRID
    else:
        mode = AnalysisMode.ANALYTICS
    try:
        plan = AnalysisPlanV1(
            schema_version=1,
            mode=mode,
            queries=tuple(valid_queries),
            clarification=None,
        )
        _validate_grounded_code_constraints(
            plan,
            constraints=grounded_code_constraints,
        )
    except (AnalysisCatalogError, ValidationError, ValueError):
        return None
    return plan


def _partial_plan_score(
    plan: AnalysisPlanV1,
    *,
    data_sources: tuple[AnalysisDataSource, ...],
) -> tuple[int, int]:
    requested_sources = set(data_sources)
    covered_sources = {query.data_source for query in plan.queries}
    return len(covered_sources & requested_sources), len(plan.queries)


def _normalize_query_payload(
    raw_query: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    query = deepcopy(raw_query)
    if not query.get("query_id"):
        query["query_id"] = f"query_{index + 1}"
    if query.get("family_version") is None:
        query.pop("family_version", None)
    if query.get("data_source") is None:
        query.pop("data_source", None)
    for key in (
        "metrics",
        "dimensions",
        "comparisons",
        "windows",
        "detail_fields",
        "sort",
    ):
        if key in query and query[key] is None:
            query[key] = []
    if query.get("limit") is None:
        query.pop("limit", None)
    if "filters" in query:
        query["filters"] = _normalize_filter_group_payload(query["filters"])
        if query["filters"] is None:
            query.pop("filters")
    if query.get("record_set") is None:
        query.pop("record_set", None)

    metrics = query.get("metrics")
    if isinstance(metrics, list):
        normalized_metrics = []
        for raw_metric in metrics:
            if not isinstance(raw_metric, dict):
                normalized_metrics.append(raw_metric)
                continue
            metric = deepcopy(raw_metric)
            operator = metric.get("operator")
            if isinstance(operator, str):
                metric["operator"] = operator.strip().lower()
            if "condition" in metric:
                metric["condition"] = _normalize_filter_group_payload(
                    metric["condition"]
                )
                if metric["condition"] is None:
                    metric.pop("condition")
            if metric.get("field_key") is None:
                metric.pop("field_key", None)
            if metric.get("percentile") is None:
                metric.pop("percentile", None)
            normalized_metrics.append(metric)
        query["metrics"] = normalized_metrics

    dimensions = query.get("dimensions")
    if isinstance(dimensions, list):
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            for key in ("alias", "time_grain", "numeric_bucket_size"):
                if dimension.get(key) is None:
                    dimension.pop(key, None)
        if (
            query.get("family_id") == QueryFamilyId.MULTIDIM_BREAKDOWN.value
            and len(dimensions) == 1
        ):
            # A one-dimensional breakdown is the same grouped count expressed
            # through the catalog's one-dimension family. Keep every selected
            # field, metric, filter, and value while canonicalizing its shape.
            query["family_id"] = QueryFamilyId.SINGLE_DISTRIBUTION.value

    comparisons = query.get("comparisons")
    if isinstance(comparisons, list):
        for comparison in comparisons:
            if not isinstance(comparison, dict):
                continue
            if "filters" in comparison:
                comparison["filters"] = _normalize_filter_group_payload(
                    comparison["filters"]
                )

    record_set = query.get("record_set")
    if isinstance(record_set, dict):
        if "key_fields" in record_set and record_set["key_fields"] is None:
            record_set["key_fields"] = []
        if "seed_filters" in record_set:
            record_set["seed_filters"] = _normalize_filter_group_payload(
                record_set["seed_filters"]
            )

    windows = query.get("windows")
    if isinstance(windows, list):
        normalized_windows = []
        for window in windows:
            if not isinstance(window, dict):
                normalized_windows.append(window)
                continue
            item = deepcopy(window)
            for key in ("partition_by", "order_by"):
                values = item.get(key)
                if values is None:
                    item[key] = []
                elif isinstance(values, list):
                    item[key] = [
                        _normalize_alias_reference(value)
                        if isinstance(value, str)
                        else value
                        for value in values
                    ]
            for key in ("preceding", "lag_offset"):
                if item.get(key) is None:
                    item.pop(key, None)
            if isinstance(item.get("metric_alias"), str):
                item["metric_alias"] = _normalize_alias_reference(
                    item["metric_alias"]
                )
            normalized_windows.append(item)
        query["windows"] = normalized_windows

    sort = query.get("sort")
    if isinstance(sort, list):
        normalized_sort = []
        for raw_sort in sort:
            if not isinstance(raw_sort, dict):
                normalized_sort.append(raw_sort)
                continue
            item = deepcopy(raw_sort)
            direction = item.get("direction")
            if isinstance(direction, str):
                item["direction"] = direction.strip().lower()
            if isinstance(item.get("key"), str):
                item["key"], suffix_direction = _normalize_sort_reference(
                    item["key"]
                )
                if suffix_direction is not None:
                    if direction is None:
                        item["direction"] = suffix_direction
                    elif str(direction).strip().lower() != suffix_direction:
                        # Preserve the conflicting suffix so catalog validation asks
                        # the model which direction it intended.
                        item["key"] = raw_sort["key"]
            normalized_sort.append(item)
        query["sort"] = normalized_sort
    return query


def _normalize_filter_group_payload(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, dict):
        return deepcopy(value)
    group = deepcopy(value)
    if group.get("junction") is None:
        group.pop("junction", None)
    elif isinstance(group.get("junction"), str):
        group["junction"] = group["junction"].strip().lower()
    conditions = group.get("conditions")
    if conditions is None:
        conditions = []
    normalized_conditions = []
    if isinstance(conditions, list):
        for raw_condition in conditions:
            if not isinstance(raw_condition, dict):
                normalized_conditions.append(raw_condition)
                continue
            condition = deepcopy(raw_condition)
            raw_operator = condition.get("operator")
            operator = (
                raw_operator.strip().lower()
                if isinstance(raw_operator, str)
                else raw_operator
            )
            if isinstance(raw_operator, str):
                condition["operator"] = operator
            if condition.get("match_mode") is None:
                condition.pop("match_mode", None)
            elif isinstance(condition.get("match_mode"), str):
                condition["match_mode"] = condition["match_mode"].strip().lower()
            if operator in _NO_OPERAND_FILTER_OPERATORS:
                if condition.get("value") is None:
                    condition.pop("value", None)
                if _empty_sequence(condition.get("values")):
                    condition.pop("values", None)
            elif operator in _SEQUENCE_FILTER_OPERATORS:
                scalar = condition.get("value")
                values = condition.get("values")
                if isinstance(scalar, (list, tuple)) and _empty_sequence(values):
                    condition["values"] = list(scalar)
                    condition.pop("value", None)
                elif (
                    operator == FilterOperator.BETWEEN.value
                    and scalar is not None
                    and isinstance(values, list)
                    and len(values) == 1
                ):
                    condition["values"] = [values[0], scalar]
                    condition.pop("value", None)
                elif scalar is None or _sequence_contains_exact(values, scalar):
                    condition.pop("value", None)
            else:
                if _empty_sequence(condition.get("values")):
                    condition.pop("values", None)
            normalized_conditions.append(condition)
        group["conditions"] = normalized_conditions
    groups = group.get("groups")
    if groups is None:
        group["groups"] = []
    elif isinstance(groups, list):
        group["groups"] = [
            _normalize_filter_group_payload(child) for child in groups
        ]
    return group


def _empty_sequence(value: Any) -> bool:
    return value is None or (isinstance(value, (list, tuple)) and len(value) == 0)


def _sequence_contains_exact(values: Any, scalar: Any) -> bool:
    return isinstance(values, (list, tuple)) and any(
        type(candidate) is type(scalar) and candidate == scalar
        for candidate in values
    )


def _normalize_alias_reference(value: str) -> str:
    return _SORT_KEY_PREFIX.sub("", value.strip()).strip()


def _normalize_sort_reference(value: str) -> tuple[str, str | None]:
    stripped = value.strip()
    suffix = _SORT_DIRECTION_SUFFIX.search(stripped)
    direction = (
        suffix.group(0).strip().lower()
        if suffix is not None
        else None
    )
    without_suffix = (
        stripped[: suffix.start()].strip() if suffix is not None else stripped
    )
    return _normalize_alias_reference(without_suffix), direction


def _query_family_id(value: Any) -> QueryFamilyId | None:
    try:
        return QueryFamilyId(str(value).strip())
    except (TypeError, ValueError):
        return None


def _family_descriptor(family_id: QueryFamilyId) -> QueryFamilyDescriptor:
    return get_query_family_descriptor(family_id, CATALOG_VERSION)


def _planner_messages(
    *,
    question: str,
    catalog_payload: dict[str, object],
    recent_messages: list[dict[str, Any]],
    routing_mode: AnalysisMode | None,
    family_categories: tuple[str, ...],
    record_set_required: bool,
    data_sources: tuple[AnalysisDataSource, ...],
    counting_unit: AnalysisCountingUnit | None,
    grounded_code_constraints: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[dict[str, Any]]:
    data_source_guidance = (
        "Use only routing_hint.data_sources. Keep different sources in separate queries. "
    )
    if AnalysisDataSource.VEHICLE_CHECKLISTS in data_sources:
        data_source_guidance += (
            "In vehicle_checklists, issue_count counts items; checklist document counts use "
            "distinct_count(checklist_id), including grouped counts. Checklist questions use "
            "typed queries, not semantic attachment search. "
        )
    if counting_unit is not None:
        data_source_guidance += (
            "Treat routing_hint.counting_unit as the counted entity and do not substitute "
            "another unit. "
        )
    return [
        {
            "role": "system",
            "content": (
                "Plan read-only legacy issue analysis; never write SQL. Return one JSON object "
                "matching response_json_schema, without markdown or prose. Omit optional keys "
                "instead of using null; collection fields must be arrays. Use only catalog family "
                "IDs, exact field keys, and declared operators. Enum/select filter values must "
                "come from listed options; free-text filter values must be literals explicitly "
                "named in the current question or recent conversation. Do not invent fields, "
                "values, periods, causes, or conclusions. Population numbers use "
                "exact analytics, not semantic candidate counts. Use semantic for evidence, "
                "analytics for structured results, hybrid only for both, and clarify only when "
                "missing scope changes the result. Keep plans minimal; decompose composite "
                "requests into at most six atomic queries. Use normalized matching only for "
                "case/space variants. family_index is complete; family_details is ranked guidance, "
                "not an allowlist. record_set_required is a routing hint: include cohort_reentry "
                "only after verifying a seed entity set followed by re-entry; otherwise omit it. "
                "Use grounded key_fields and seed_filters, and set exclude_seed_matches=true only "
                "when other rows must exclude the seed matches. Delegate semantic/generated families "
                "with empty queries; use generated only when atomic families cannot express the "
                "request. For rankings, top_bottom_n means one global N across complete dimension "
                "tuples; top_n_within_parent means N inside every parent group and is only valid "
                "when the request asks for a separate child ranking per parent. When a request "
                "needs a grouped breakdown and its overall total, emit two atomic queries: one "
                "scalar total and one distribution; never invent a combined family ID. Use limit "
                "as requested-row semantics only for Top-N, detail, or an explicit earliest/latest "
                "period request; exhaustive distributions and full time series are bounded by "
                "filters and the server safety cap. Preserve every explicitly named population "
                "constraint, such as a vehicle, region, status, grade, or period, as a filter on "
                "each applicable atomic query; never silently broaden the requested population. "
                "A new combination of supported filters, grouping, totals, or shares is not a "
                "reason to use generated SQL; prefer the matching atomic families. Server-grounded "
                "code constraints are mandatory population filters, not examples. "
                + data_source_guidance
                + "The server validates and executes the plan within the authorized scope."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "recent_conversation": _recent_conversation_payload(recent_messages),
                    "routing_hint": {
                        "mode": routing_mode.value if routing_mode is not None else None,
                        "family_categories": list(family_categories),
                        "record_set_required": record_set_required,
                        "data_sources": [data_source.value for data_source in data_sources],
                        "counting_unit": (
                            counting_unit.value if counting_unit is not None else None
                        ),
                    },
                    "grounded_code_constraints": [
                        {"field_key": field_key, "values": list(values)}
                        for field_key, values in grounded_code_constraints
                    ],
                    "analysis_catalog": catalog_payload,
                    "response_json_schema": _compact_response_schema(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


_ADJACENT_CODE_PATTERN = (
    r"[A-Za-z0-9][A-Za-z0-9._/-]{0,31}"
    r"(?:[ \t]+[A-Za-z0-9][A-Za-z0-9._/-]{0,31})?"
)
_RANKING_CODE_PREFIXES = frozenset(
    {"BOTTOM", "EARLIEST", "FIRST", "LAST", "LATEST", "TOP"}
)


def _grounded_code_constraints(
    question: str,
    *,
    fields: tuple[DatasetFieldDefinition, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Extract only explicit code-like values adjacent to a schema label.

    This is a narrow safety guard, not a general natural-language parser. It catches
    identifiers such as ``CV 차종`` while leaving phrases such as ``차종별`` or
    ``전체 차종`` to the typed planner.
    """

    constraints: dict[str, list[str]] = {}
    for field in fields:
        labels = tuple(
            dict.fromkeys(
                label.strip()
                for label in (field.label_ko, field.label_en, *field.aliases)
                if isinstance(label, str) and len(label.strip()) >= 2
            )
        )
        for label in sorted(labels, key=len, reverse=True):
            for match in re.finditer(re.escape(label), question, flags=re.IGNORECASE):
                before = re.search(
                    rf"(?P<value>{_ADJACENT_CODE_PATTERN})\s*$",
                    question[: match.start()],
                )
                after = re.match(
                    rf"\s*(?:[:：]|은|는|이|가)?\s*"
                    rf"(?P<value>{_ADJACENT_CODE_PATTERN})",
                    question[match.end() :],
                )
                for candidate in (before, after):
                    if candidate is None:
                        continue
                    value = _normalize_adjacent_code_candidate(
                        candidate.group("value"),
                        from_end=candidate is before,
                    )
                    if value is None:
                        continue
                    if candidate is before and re.search(
                        r"(?:상위|하위|최근|최초|최신)\s*$",
                        question[: candidate.start()],
                    ):
                        continue
                    values = constraints.setdefault(field.key, [])
                    if value.casefold() not in {item.casefold() for item in values}:
                        values.append(value)
    return tuple(
        (field_key, tuple(values))
        for field_key, values in constraints.items()
        if values
    )


def _normalize_adjacent_code_candidate(
    value: str,
    *,
    from_end: bool,
) -> str | None:
    tokens = value.split()
    ordered = list(reversed(tokens)) if from_end else tokens
    selected: list[str] = []
    for token in ordered:
        if not _looks_like_code_token(token):
            break
        selected.append(token)
    if from_end:
        selected.reverse()
    if not selected:
        return None
    if selected[0].upper() in _RANKING_CODE_PREFIXES:
        return None
    if re.fullmatch(r"(?:TOP|BOTTOM)\d+", selected[0], flags=re.IGNORECASE):
        return None
    return " ".join(selected)


def _looks_like_code_token(value: str) -> bool:
    compact = value.strip()
    if len(compact) < 2:
        return False
    letters = [
        character
        for character in compact
        if character.isascii() and character.isalpha()
    ]
    return any(character.isdigit() for character in compact) or bool(
        letters and all(character.isupper() for character in letters)
    )


def _validate_grounded_code_constraints(
    plan: AnalysisPlanV1,
    *,
    constraints: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    for field_key, values in constraints:
        if _plan_represents_code_constraint(
            plan,
            field_key=field_key,
            values=values,
        ):
            continue
        rendered_values = ", ".join(repr(value) for value in values)
        raise AnalysisCatalogError(
            "question_constraint_unrepresented: preserve the explicit population "
            f"constraint {field_key}={rendered_values} with an eq or exact in filter"
        )


def _plan_represents_code_constraint(
    plan: AnalysisPlanV1,
    *,
    field_key: str,
    values: tuple[str, ...],
) -> bool:
    required = {_normalized_constraint_value(value) for value in values}
    applicable_queries: list[QueryRequestV1] = []
    represented_as_dimension = False
    for query in plan.queries:
        if any(dimension.field_key == field_key for dimension in query.dimensions):
            represented_as_dimension = True
            continue
        if query.family_id == QueryFamilyId.TOTAL_COUNT:
            continue
        applicable_queries.append(query)
        represented = _filter_group_represents_values(
            query.filters,
            field_key=field_key,
            required=required,
        ) or any(
            _filter_group_represents_values(
                comparison.filters,
                field_key=field_key,
                required=required,
            )
            for comparison in query.comparisons
        )
        if not represented:
            return False
    return bool(applicable_queries) or represented_as_dimension


def _filter_group_represents_values(
    group: FilterGroupV1 | None,
    *,
    field_key: str,
    required: set[str],
) -> bool:
    if group is None:
        return False
    if group.junction == FilterJunction.NOT:
        return False
    matches = [
        _filter_condition_represents_values(
            condition,
            field_key=field_key,
            required=required,
        )
        for condition in group.conditions
    ]
    matches.extend(
        _filter_group_represents_values(
            child,
            field_key=field_key,
            required=required,
        )
        for child in group.groups
    )
    if group.junction == FilterJunction.ANY:
        return bool(matches) and all(matches)
    return any(matches)


def _filter_condition_represents_values(
    condition: Any,
    *,
    field_key: str,
    required: set[str],
) -> bool:
    if condition.field_key != field_key:
        return False
    if condition.operator == FilterOperator.EQ and condition.value is not None:
        present = {_normalized_constraint_value(condition.value)}
    elif condition.operator == FilterOperator.IN:
        present = {
            _normalized_constraint_value(value)
            for value in condition.values
        }
    else:
        return False
    return present == required


def _normalized_constraint_value(value: str) -> str:
    return "".join(value.casefold().split())


def _recent_conversation_payload(
    messages: list[dict[str, Any]],
) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for message in messages[-4:]:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        normalized = " ".join(content.split()).strip()
        if normalized:
            payload.append({"role": role, "content": normalized[:600]})
    return payload


def _rank_candidate_family_ids(
    *,
    question: str,
    recent_messages: list[dict[str, Any]],
    family_categories: tuple[str, ...],
    limit: int = _PRIMARY_FAMILY_DETAIL_LIMIT,
) -> tuple[QueryFamilyId, ...]:
    descriptors = tuple(QUERY_FAMILY_CATALOG.values())
    conversation = " ".join(
        message["content"] for message in _recent_conversation_payload(recent_messages)
    )
    ranking_query = " ".join(part for part in (question, conversation) if part).strip()
    candidates = tuple(
        CandidateDocument(
            candidate_id=descriptor.family_id.value,
            title=descriptor.purpose,
            text=" ".join(
                (
                    descriptor.family_id.value,
                    descriptor.category,
                    descriptor.execution_kind.value,
                    descriptor.purpose,
                    descriptor.recipe,
                )
            ),
        )
        for descriptor in descriptors
    )
    ranked = CandidateRankingService().rank(
        CandidateRankingRequest(
            query=ranking_query,
            candidates=candidates,
            top_k=len(candidates),
            enable_semantic=False,
            enable_rerank=False,
        )
    )
    ranked_ids = [QueryFamilyId(item.candidate.candidate_id) for item in ranked.candidates]
    valid_categories = {descriptor.category for descriptor in descriptors}
    hinted_categories = {category for category in family_categories if category in valid_categories}
    if hinted_categories:
        category_by_family = {
            descriptor.family_id: descriptor.category for descriptor in descriptors
        }
        ranked_ids = [
            family_id
            for family_id in ranked_ids
            if category_by_family[family_id] in hinted_categories
        ] + [
            family_id
            for family_id in ranked_ids
            if category_by_family[family_id] not in hinted_categories
        ]
    return tuple(dict.fromkeys(ranked_ids[: max(1, limit)]))


def _compact_response_schema() -> dict[str, Any]:
    schema = _strip_schema_noise(AnalysisPlanV1.model_json_schema())
    definitions = schema.get("$defs")
    if isinstance(definitions, dict) and "QueryFamilyId" in definitions:
        definitions["QueryFamilyId"] = {
            "type": "string",
            "description": "Use an id from analysis_catalog.family_index.",
        }
    return schema


def _strip_schema_noise(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_schema_noise(item)
            for key, item in value.items()
            if key not in {"title", "default", "examples"}
        }
    if isinstance(value, list):
        return [_strip_schema_noise(item) for item in value]
    return value


def _repair_message(reason: str | None) -> dict[str, Any]:
    return {
        "role": "user",
        "content": json.dumps(
            {
                "repair_required": True,
                "validation_error": reason or "analysis_plan_invalid",
                "instruction": (
                    "Regenerate the complete plan from the original request. Return only one "
                    "JSON object matching the supplied schema and catalog."
                ),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    payload = json.loads(text.strip())
    if not isinstance(payload, dict):
        raise ValueError("analysis_plan_response_must_be_an_object")
    return payload


def _semantic_fallback() -> AnalysisPlanV1:
    return AnalysisPlanV1(
        schema_version=1,
        mode=AnalysisMode.SEMANTIC,
        queries=(),
        clarification=None,
        delegated_family_id=QueryFamilyId.SEMANTIC_SIMILAR,
    )


def _clarify_fallback() -> AnalysisPlanV1:
    return AnalysisPlanV1(
        schema_version=1,
        mode=AnalysisMode.CLARIFY,
        queries=(),
        clarification=(
            "정확한 분석을 위해 비교 기준, 대상 기간, 또는 분석 범위를 "
            "조금 더 구체적으로 알려주세요."
        ),
        delegated_family_id=None,
    )


def _attempts_exhausted_fallback(
    routing_mode: AnalysisMode | None,
    *,
    data_sources: tuple[AnalysisDataSource, ...],
    fields: tuple[DatasetFieldDefinition, ...],
    report_requested: bool,
) -> AnalysisPlanV1:
    return _planner_failure_fallback(
        routing_mode,
        data_sources=data_sources,
        fields=fields,
        report_requested=report_requested,
        allow_generated=True,
    )


def _planner_failure_fallback(
    routing_mode: AnalysisMode | None,
    *,
    data_sources: tuple[AnalysisDataSource, ...],
    fields: tuple[DatasetFieldDefinition, ...] = (),
    report_requested: bool = False,
    allow_generated: bool = False,
) -> AnalysisPlanV1:
    if report_requested:
        report_plan = build_standard_report_plan(
            fields=fields,
            routing_mode=routing_mode,
            data_sources=data_sources,
        )
        if report_plan is not None:
            return report_plan
    if routing_mode == AnalysisMode.CLARIFY:
        return _clarify_fallback()
    if allow_generated and routing_mode in {
        AnalysisMode.ANALYTICS,
        AnalysisMode.HYBRID,
    }:
        delegated_data_source = (
            AnalysisDataSource.LEGACY_ISSUES
            if AnalysisDataSource.LEGACY_ISSUES in data_sources
            else data_sources[0]
        )
        return AnalysisPlanV1(
            schema_version=1,
            mode=AnalysisMode.GENERATED,
            queries=(),
            clarification=None,
            delegated_family_id=QueryFamilyId.GENERATED_SQL_FALLBACK,
            delegated_data_source=delegated_data_source,
        )
    if routing_mode == AnalysisMode.METADATA:
        return _semantic_fallback()
    if len(data_sources) == 1 and data_sources[0] == AnalysisDataSource.VEHICLE_CHECKLISTS:
        return _clarify_fallback().model_copy(
            update={"delegated_data_source": data_sources[0]}
        )
    return _semantic_fallback()


def _bind_single_requested_data_source(
    plan: AnalysisPlanV1,
    *,
    data_sources: tuple[AnalysisDataSource, ...],
) -> AnalysisPlanV1:
    """Treat a grounded singleton routing source as server-owned scope."""

    if len(data_sources) != 1:
        return plan
    data_source = data_sources[0]
    return plan.model_copy(
        update={
            "queries": tuple(
                query.model_copy(update={"data_source": data_source}) for query in plan.queries
            ),
            "delegated_data_source": data_source,
        }
    )


def _validate_counting_unit(
    validated_queries: tuple[tuple[QueryRequestV1, Any], ...],
    *,
    counting_unit: AnalysisCountingUnit | None,
) -> None:
    if counting_unit not in {
        AnalysisCountingUnit.CHECKLIST_ITEMS,
        AnalysisCountingUnit.CHECKLISTS,
    }:
        return
    for query, descriptor in validated_queries:
        if (
            query.data_source != AnalysisDataSource.VEHICLE_CHECKLISTS
            or descriptor.execution_kind
            not in {
                FamilyExecutionKind.AGGREGATE,
                FamilyExecutionKind.HYBRID,
            }
        ):
            continue
        if counting_unit == AnalysisCountingUnit.CHECKLIST_ITEMS and any(
            metric.operator == MetricOperator.DISTINCT_COUNT for metric in query.metrics
        ):
            raise AnalysisCatalogError("checklist_items counting_unit requires issue_count")
        if counting_unit == AnalysisCountingUnit.CHECKLISTS and any(
            metric.operator != MetricOperator.DISTINCT_COUNT
            or metric.field_key != "checklist_id"
            for metric in query.metrics
        ):
            raise AnalysisCatalogError(
                "checklists counting_unit requires distinct_count(checklist_id)"
            )


def _semantic_fast_path_allowed(
    *,
    routing_mode: AnalysisMode | None,
    family_categories: tuple[str, ...],
    record_set_required: bool,
    data_sources: tuple[AnalysisDataSource, ...],
) -> bool:
    categories = set(family_categories)
    return (
        routing_mode == AnalysisMode.SEMANTIC
        and not record_set_required
        and data_sources == (AnalysisDataSource.LEGACY_ISSUES,)
        and "semantic" in categories
        and categories <= {"semantic", "detail"}
    )


def _planner_diagnostics(
    *,
    plan: AnalysisPlanV1,
    status: str,
    attempt_count: int,
    candidate_family_count: int,
    prompt_chars: int,
    fallback_reason: str | None = None,
    validation_error_code: str | None = None,
) -> LegacyIssuePlannerDiagnosticsV1:
    return LegacyIssuePlannerDiagnosticsV1(
        status=status,
        attempt_count=attempt_count,
        candidate_family_count=candidate_family_count,
        catalog_family_count=len(QUERY_FAMILY_CATALOG),
        prompt_chars=prompt_chars,
        fallback_reason=fallback_reason,
        validation_error_code=validation_error_code,
        plan_fingerprint=_plan_shape_fingerprint(plan),
    )


def _plan_shape_fingerprint(plan: AnalysisPlanV1) -> str:
    shape = {
        "mode": plan.mode.value,
        "delegated_family_id": (
            plan.delegated_family_id.value if plan.delegated_family_id is not None else None
        ),
        "delegated_data_source": plan.delegated_data_source.value,
        "queries": [
            {
                "family_id": query.family_id.value,
                "family_version": query.family_version,
                "data_source": query.data_source.value,
                "metrics": [
                    {
                        "operator": metric.operator.value,
                        "field_key": metric.field_key,
                        "condition": _filter_shape_payload(metric.condition),
                    }
                    for metric in query.metrics
                ],
                "dimensions": [
                    {
                        "field_key": dimension.field_key,
                        "time_grain": (
                            dimension.time_grain.value if dimension.time_grain is not None else None
                        ),
                        "numeric_bucket": dimension.numeric_bucket_size is not None,
                    }
                    for dimension in query.dimensions
                ],
                "filters": _filter_shape_payload(query.filters),
                "record_set": (
                    {
                        "kind": query.record_set.kind.value,
                        "key_fields": list(query.record_set.key_fields),
                        "key_match_mode": query.record_set.key_match_mode.value,
                        "exclude_seed_matches": query.record_set.exclude_seed_matches,
                        "seed_filters": _filter_shape_payload(query.record_set.seed_filters),
                    }
                    if query.record_set is not None
                    else None
                ),
                "comparisons": [
                    _filter_shape_payload(comparison.filters) for comparison in query.comparisons
                ],
                "windows": [
                    {
                        "operator": window.operator.value,
                        "partition_count": len(window.partition_by),
                        "order_count": len(window.order_by),
                        "preceding": window.preceding,
                        "lag_offset": window.lag_offset,
                    }
                    for window in query.windows
                ],
                "detail_fields": list(query.detail_fields),
                "sort_directions": [sort.direction.value for sort in query.sort],
                "limit": query.limit,
            }
            for query in plan.queries
        ],
    }
    canonical = json.dumps(
        shape,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"plan-shape-v1:{hashlib.sha256(canonical.encode()).hexdigest()}"


def _filter_shape_payload(group: FilterGroupV1 | None) -> Any:
    if group is None:
        return None
    return {
        "junction": group.junction.value,
        "conditions": [
            {
                "field_key": condition.field_key,
                "operator": condition.operator.value,
                "match_mode": condition.match_mode.value,
                "value_type": _operand_type(condition.value),
                "value_types": [_operand_type(value) for value in condition.values],
            }
            for condition in group.conditions
        ],
        "groups": [_filter_shape_payload(child) for child in group.groups],
    }


def _operand_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def _bounded_question(question: str) -> str:
    normalized = question.strip()
    if not normalized:
        raise ValueError("analysis_question_empty")
    if len(normalized) > _MAX_QUESTION_CHARS:
        raise ValueError("analysis_question_too_large")
    return normalized


def _bounded_error_reason(error: Exception) -> str:
    reason = " ".join(str(error).split())
    if not reason:
        reason = type(error).__name__
    return reason[:_MAX_REPAIR_REASON_CHARS]


def _within_prompt_budget(messages: list[dict[str, Any]]) -> bool:
    return _prompt_chars(messages) <= _MAX_PROMPT_CHARS


def _prompt_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(message.get("content", ""))) for message in messages)


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    size = _prompt_chars(messages)
    return max(1, size // 4)


__all__ = ["LegacyIssuePlannerResult", "plan_legacy_issue_analysis"]
