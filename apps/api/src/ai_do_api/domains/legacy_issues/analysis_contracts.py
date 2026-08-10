from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_RESERVED_QUERY_OUTPUT_ALIASES = frozenset(
    {
        "source_count",
        "base_population_count",
        "filtered_population_count",
        "population_count",
    }
)


class AnalysisMode(str, Enum):
    ANSWER_ONLY = "answer_only"
    METADATA = "metadata"
    ANALYTICS = "analytics"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    GENERATED = "generated"
    CLARIFY = "clarify"


class AnalysisDataSource(str, Enum):
    LEGACY_ISSUES = "legacy_issues"
    VEHICLE_CHECKLISTS = "vehicle_checklists"


class AnalysisCountingUnit(str, Enum):
    LEGACY_RECORDS = "legacy_records"
    CHECKLIST_ITEMS = "checklist_items"
    CHECKLISTS = "checklists"


class QueryFamilyId(str, Enum):
    FIELD_CATALOG = "field_catalog"
    VALUE_DOMAIN = "value_domain"
    SCOPE_INVENTORY = "scope_inventory"
    DATE_RANGE_COVERAGE = "date_range_coverage"
    FIELD_COVERAGE_CARDINALITY = "field_coverage_cardinality"
    ACTIVE_REVISION_FRESHNESS = "active_revision_freshness"

    TOTAL_COUNT = "total_count"
    FILTERED_COUNT = "filtered_count"
    DISTINCT_COUNT = "distinct_count"
    MISSING_POPULATED_RATE = "missing_populated_rate"
    NUMERIC_SUMMARY = "numeric_summary"
    DURATION_SUMMARY = "duration_summary"

    SINGLE_DISTRIBUTION = "single_distribution"
    MULTIDIM_BREAKDOWN = "multidim_breakdown"
    SHARE = "share"
    TOP_BOTTOM_N = "top_bottom_n"
    TOP_N_WITHIN_PARENT = "top_n_within_parent"
    CROSSTAB = "crosstab"
    HISTOGRAM = "histogram"

    TIME_SERIES = "time_series"
    PERIOD_COMPARE = "period_compare"
    ABSOLUTE_CHANGE = "absolute_change"
    RATE_CHANGE = "rate_change"
    YOY_MOM = "yoy_mom"
    ROLLING = "rolling"
    CUMULATIVE = "cumulative"
    FIRST_LAST = "first_last"
    EMERGING_DECLINING_SPIKE = "emerging_declining_spike"

    COHORT_COMPARE = "cohort_compare"
    BENCHMARK = "benchmark"
    BEFORE_AFTER = "before_after"
    MIX_SHIFT = "mix_shift"
    RANK_SHIFT = "rank_shift"
    CONTRIBUTION_CHANGE = "contribution_change"
    OVERLAP_INTERSECTION_EXCLUSIVE = "overlap_intersection_exclusive"

    PARETO = "pareto"
    CONCENTRATION = "concentration"
    CONDITIONAL_RATE = "conditional_rate"
    CATEGORICAL_ASSOCIATION = "categorical_association"
    SYMPTOM_CAUSE = "symptom_cause"
    CAUSE_COUNTERMEASURE = "cause_countermeasure"
    SUPPLIER_PART_PROCESS = "supplier_part_process"

    SEVERITY = "severity"
    APPLIED_BACKLOG = "applied_backlog"
    MASTER_STATUS = "master_status"
    EVIDENCE_COVERAGE = "evidence_coverage"
    COMPLETENESS = "completeness"
    INVALID_VALUES = "invalid_values"
    DUPLICATE_NORMALIZATION_STALE = "duplicate_normalization_stale"

    DETAIL_LIST = "detail_list"
    GROUP_DRILLDOWN = "group_drilldown"
    REPRESENTATIVE_RECORDS = "representative_records"
    SEMANTIC_SIMILAR = "semantic_similar"
    EXACT_AGGREGATE_PLUS_SEMANTIC = "exact_aggregate_plus_semantic"
    ATTACHMENT_EVIDENCE = "attachment_evidence"

    EXECUTIVE_SCORECARD = "executive_scorecard"
    EXECUTIVE_BRIEFING = "executive_briefing"
    PRACTITIONER_INVESTIGATION = "practitioner_investigation"
    MULTI_SCOPE_MATRIX = "multi_scope_matrix"
    ISSUE_CAUSE_COUNTERMEASURE_REVIEW = "issue_cause_countermeasure_review"
    CONTEXTUAL_FOLLOWUP = "contextual_followup"
    GENERATED_SQL_FALLBACK = "generated_sql_fallback"


class MetricOperator(str, Enum):
    ISSUE_COUNT = "issue_count"
    DISTINCT_COUNT = "distinct_count"
    PRESENT_COUNT = "present_count"
    MISSING_COUNT = "missing_count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"
    PERCENTILE = "percentile"
    CONDITIONAL_RATE = "conditional_rate"


class FilterOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    CONTAINS_ANY = "contains_any"
    CONTAINS_ALL = "contains_all"


class FilterJunction(str, Enum):
    ALL = "all"
    ANY = "any"
    NOT = "not"


class ValueMatchMode(str, Enum):
    LITERAL = "literal"
    NORMALIZED = "normalized"


class RecordSetKind(str, Enum):
    COHORT_REENTRY = "cohort_reentry"


class TimeGrain(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"


class WindowOperator(str, Enum):
    RANK = "rank"
    DENSE_RANK = "dense_rank"
    PERCENT_OF_TOTAL = "percent_of_total"
    CUMULATIVE_SUM = "cumulative_sum"
    MOVING_AVERAGE = "moving_average"
    MOVING_SUM = "moving_sum"
    LAG = "lag"
    ABSOLUTE_CHANGE = "absolute_change"
    RATE_CHANGE = "rate_change"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class Exactness(str, Enum):
    EXACT = "exact"
    SEMANTIC_EVIDENCE = "semantic_evidence"
    MIXED = "mixed"


class AnalysisContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=False)


AnalysisScalar = str | int | float | bool
PUBLIC_CELL_MAX_CHARS = 10_000
PUBLIC_QUERY_ROWS_MAX_BYTES = 250_000
DEFAULT_QUERY_LIMIT = 10


class FilterConditionV1(AnalysisContractModel):
    field_key: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.-]+$")
    operator: FilterOperator
    match_mode: ValueMatchMode = ValueMatchMode.LITERAL
    value: AnalysisScalar | None = None
    values: tuple[AnalysisScalar, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def validate_operands(self) -> "FilterConditionV1":
        no_operand = {
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }
        sequence_operand = {
            FilterOperator.IN,
            FilterOperator.NOT_IN,
            FilterOperator.BETWEEN,
            FilterOperator.CONTAINS_ANY,
            FilterOperator.CONTAINS_ALL,
        }
        if self.operator in no_operand:
            if self.value is not None or self.values:
                raise ValueError(f"{self.operator.value} does not accept operands")
            return self
        if self.operator in sequence_operand:
            expected = 2 if self.operator == FilterOperator.BETWEEN else None
            if not self.values or (expected is not None and len(self.values) != expected):
                raise ValueError(f"{self.operator.value} requires valid values")
            if self.value is not None:
                raise ValueError(f"{self.operator.value} accepts values, not value")
            return self
        if self.value is None or self.values:
            raise ValueError(f"{self.operator.value} requires one value")
        return self


class FilterGroupV1(AnalysisContractModel):
    junction: FilterJunction = FilterJunction.ALL
    conditions: tuple[FilterConditionV1, ...] = Field(default=(), max_length=16)
    groups: tuple["FilterGroupV1", ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_group(self) -> "FilterGroupV1":
        if not self.conditions and not self.groups:
            raise ValueError("filter group must not be empty")
        if self.junction == FilterJunction.NOT and len(self.conditions) + len(self.groups) != 1:
            raise ValueError("not filter group must contain exactly one child")
        return self


class RecordSetSpecV1(AnalysisContractModel):
    kind: Literal[RecordSetKind.COHORT_REENTRY] = RecordSetKind.COHORT_REENTRY
    key_fields: tuple[str, ...] = Field(min_length=1, max_length=3)
    seed_filters: FilterGroupV1
    key_match_mode: ValueMatchMode = ValueMatchMode.NORMALIZED
    exclude_seed_matches: bool = False

    @field_validator("key_fields")
    @classmethod
    def validate_key_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not value or len(value) > 160:
                raise ValueError("record-set key must be between 1 and 160 characters")
            if re.fullmatch(r"[A-Za-z0-9_.-]+", value) is None:
                raise ValueError("record-set key contains unsupported characters")
        if len(set(values)) != len(values):
            raise ValueError("record-set keys must be unique")
        return values

    @model_validator(mode="after")
    def validate_seed_shape(self) -> "RecordSetSpecV1":
        count, depth = _filter_shape(self.seed_filters)
        if count > 16 or depth > 3:
            raise ValueError("record-set seed filters support at most 16 conditions and depth 3")
        return self


class MetricSpecV1(AnalysisContractModel):
    operator: MetricOperator = MetricOperator.ISSUE_COUNT
    field_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    alias: str = Field(default="issue_count", min_length=1, max_length=80)
    percentile: float | None = Field(default=None, gt=0, lt=1)
    condition: FilterGroupV1 | None = None

    @model_validator(mode="after")
    def validate_metric(self) -> "MetricSpecV1":
        field_required = {
            MetricOperator.DISTINCT_COUNT,
            MetricOperator.PRESENT_COUNT,
            MetricOperator.MISSING_COUNT,
            MetricOperator.SUM,
            MetricOperator.AVG,
            MetricOperator.MIN,
            MetricOperator.MAX,
            MetricOperator.MEDIAN,
            MetricOperator.PERCENTILE,
        }
        if self.operator in field_required and not self.field_key:
            raise ValueError(f"{self.operator.value} requires field_key")
        if self.operator == MetricOperator.ISSUE_COUNT and self.field_key:
            raise ValueError("issue_count does not accept field_key")
        if self.operator == MetricOperator.PERCENTILE and self.percentile is None:
            raise ValueError("percentile metric requires percentile")
        if self.operator != MetricOperator.PERCENTILE and self.percentile is not None:
            raise ValueError("percentile is only valid for percentile metric")
        if self.operator == MetricOperator.CONDITIONAL_RATE and self.condition is None:
            raise ValueError("conditional_rate requires condition")
        if self.operator != MetricOperator.CONDITIONAL_RATE and self.condition is not None:
            raise ValueError("condition is only valid for conditional_rate")
        return self


class DimensionSpecV1(AnalysisContractModel):
    field_key: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.-]+$")
    alias: str | None = Field(default=None, min_length=1, max_length=80)
    time_grain: TimeGrain | None = None
    numeric_bucket_size: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_bucket(self) -> "DimensionSpecV1":
        if self.time_grain is not None and self.numeric_bucket_size is not None:
            raise ValueError("dimension cannot use time and numeric buckets together")
        return self


class WindowSpecV1(AnalysisContractModel):
    operator: WindowOperator
    metric_alias: str = Field(min_length=1, max_length=80)
    alias: str = Field(min_length=1, max_length=80)
    partition_by: tuple[str, ...] = Field(default=(), max_length=3)
    order_by: tuple[str, ...] = Field(default=(), max_length=4)
    preceding: int | None = Field(default=None, ge=1, le=52)
    lag_offset: int | None = Field(default=None, ge=1, le=60)

    @model_validator(mode="after")
    def validate_window(self) -> "WindowSpecV1":
        moving = {
            WindowOperator.MOVING_AVERAGE,
            WindowOperator.MOVING_SUM,
        }
        if self.operator in moving and self.preceding is None:
            raise ValueError("moving window requires preceding")
        if self.operator not in moving and self.preceding is not None:
            raise ValueError("preceding is only valid for moving windows")
        lag_based = {
            WindowOperator.LAG,
            WindowOperator.ABSOLUTE_CHANGE,
            WindowOperator.RATE_CHANGE,
        }
        if self.operator not in lag_based and self.lag_offset is not None:
            raise ValueError("lag_offset is only valid for lag/change windows")
        return self


class SortSpecV1(AnalysisContractModel):
    key: str = Field(min_length=1, max_length=80)
    direction: SortDirection = SortDirection.DESC


class ComparisonSpecV1(AnalysisContractModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    filters: FilterGroupV1


class QueryRequestV1(AnalysisContractModel):
    query_id: str = Field(min_length=1, max_length=80)
    family_id: QueryFamilyId
    family_version: int = Field(default=1, ge=1)
    data_source: AnalysisDataSource = AnalysisDataSource.LEGACY_ISSUES
    metrics: tuple[MetricSpecV1, ...] = Field(
        default_factory=lambda: (MetricSpecV1(),),
        min_length=1,
        max_length=4,
    )
    dimensions: tuple[DimensionSpecV1, ...] = Field(default=(), max_length=4)
    filters: FilterGroupV1 | None = None
    record_set: RecordSetSpecV1 | None = None
    comparisons: tuple[ComparisonSpecV1, ...] = Field(default=(), max_length=4)
    windows: tuple[WindowSpecV1, ...] = Field(default=(), max_length=3)
    detail_fields: tuple[str, ...] = Field(default=(), max_length=16)
    sort: tuple[SortSpecV1, ...] = Field(default=(), max_length=4)
    limit: int = Field(default=DEFAULT_QUERY_LIMIT, ge=1, le=500)

    @field_validator("detail_fields")
    @classmethod
    def validate_detail_fields(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not value or len(value) > 160:
                raise ValueError("detail field key must be between 1 and 160 characters")
        if len(set(values)) != len(values):
            raise ValueError("detail field keys must be unique")
        return values

    @model_validator(mode="after")
    def validate_aliases_and_filters(self) -> "QueryRequestV1":
        aliases = [metric.alias for metric in self.metrics]
        aliases.extend(dimension.alias or dimension.field_key for dimension in self.dimensions)
        aliases.extend(window.alias for window in self.windows)
        if len(set(aliases)) != len(aliases):
            raise ValueError("metric, dimension, and window aliases must be unique")
        reserved_aliases = sorted(set(aliases) & _RESERVED_QUERY_OUTPUT_ALIASES)
        if reserved_aliases:
            raise ValueError(
                "query output aliases are reserved for population metadata: "
                + ", ".join(reserved_aliases)
            )
        comparison_keys = [comparison.key for comparison in self.comparisons]
        if len(set(comparison_keys)) != len(comparison_keys):
            raise ValueError("comparison keys must be unique")
        filter_count, filter_depth = _filter_shape(self.filters)
        if filter_count > 16 or filter_depth > 3:
            raise ValueError("filters support at most 16 conditions and depth 3")
        for comparison in self.comparisons:
            count, depth = _filter_shape(comparison.filters)
            if count > 16 or depth > 3:
                raise ValueError("comparison filters support at most 16 conditions and depth 3")
        return self

    @property
    def family_ref(self) -> str:
        return f"{self.family_id.value}@{self.family_version}"


class AnalysisPlanV1(AnalysisContractModel):
    schema_version: Literal[1] = 1
    mode: AnalysisMode
    queries: tuple[QueryRequestV1, ...] = Field(default=(), max_length=6)
    clarification: str | None = Field(default=None, max_length=600)
    delegated_family_id: QueryFamilyId | None = None
    delegated_data_source: AnalysisDataSource = AnalysisDataSource.LEGACY_ISSUES

    @model_validator(mode="after")
    def validate_mode(self) -> "AnalysisPlanV1":
        query_ids = [query.query_id for query in self.queries]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("query_id values must be unique within an analysis plan")
        catalog_executable = {
            AnalysisMode.METADATA,
            AnalysisMode.ANALYTICS,
            AnalysisMode.HYBRID,
        }
        if self.mode in catalog_executable and not self.queries:
            raise ValueError(f"{self.mode.value} mode requires at least one query")
        if self.mode == AnalysisMode.CLARIFY and not self.clarification:
            raise ValueError("clarify mode requires clarification")
        if self.mode != AnalysisMode.CLARIFY and self.clarification is not None:
            raise ValueError("clarification is only valid for clarify mode")
        delegated = {
            AnalysisMode.ANSWER_ONLY,
            AnalysisMode.CLARIFY,
            AnalysisMode.SEMANTIC,
            AnalysisMode.GENERATED,
        }
        if self.mode in delegated and self.queries:
            raise ValueError(f"{self.mode.value} mode does not accept queries")
        semantic_families = {
            QueryFamilyId.SEMANTIC_SIMILAR,
            QueryFamilyId.ATTACHMENT_EVIDENCE,
            QueryFamilyId.REPRESENTATIVE_RECORDS,
        }
        generated_families = {
            QueryFamilyId.DURATION_SUMMARY,
            QueryFamilyId.EMERGING_DECLINING_SPIKE,
            QueryFamilyId.MIX_SHIFT,
            QueryFamilyId.RANK_SHIFT,
            QueryFamilyId.CONTRIBUTION_CHANGE,
            QueryFamilyId.OVERLAP_INTERSECTION_EXCLUSIVE,
            QueryFamilyId.CONCENTRATION,
            QueryFamilyId.DUPLICATE_NORMALIZATION_STALE,
            QueryFamilyId.GENERATED_SQL_FALLBACK,
        }
        composite_families = {
            QueryFamilyId.EXECUTIVE_SCORECARD,
            QueryFamilyId.EXECUTIVE_BRIEFING,
            QueryFamilyId.PRACTITIONER_INVESTIGATION,
            QueryFamilyId.MULTI_SCOPE_MATRIX,
            QueryFamilyId.ISSUE_CAUSE_COUNTERMEASURE_REVIEW,
            QueryFamilyId.CONTEXTUAL_FOLLOWUP,
        }
        delegated_families = semantic_families | generated_families | composite_families
        if self.mode in catalog_executable and any(
            query.family_id in delegated_families for query in self.queries
        ):
            raise ValueError("catalog execution modes do not accept delegated query families")
        if self.mode != AnalysisMode.HYBRID and any(
            query.family_id == QueryFamilyId.EXACT_AGGREGATE_PLUS_SEMANTIC for query in self.queries
        ):
            raise ValueError("exact_aggregate_plus_semantic requires hybrid mode")
        if self.delegated_family_id is not None:
            if self.delegated_family_id in generated_families:
                if self.mode != AnalysisMode.GENERATED:
                    raise ValueError("generated family requires generated mode")
            elif self.delegated_family_id in semantic_families:
                if self.mode != AnalysisMode.SEMANTIC:
                    raise ValueError("semantic family requires semantic mode")
            else:
                raise ValueError("delegated_family_id must reference a delegated family")
        return self


class LegacyIssuePlannerDiagnosticsV1(AnalysisContractModel):
    version: Literal[1] = 1
    status: Literal["fast_path", "valid", "repaired", "fallback"]
    attempt_count: int = Field(ge=0, le=2)
    candidate_family_count: int = Field(ge=0)
    catalog_family_count: int = Field(ge=0)
    prompt_chars: int = Field(ge=0)
    fallback_reason: (
        Literal[
            "input_invalid",
            "catalog_preparation_failed",
            "prompt_budget_exceeded",
            "repair_prompt_budget_exceeded",
            "attempts_exhausted",
            "partial_plan_salvaged",
        ]
        | None
    ) = None
    validation_error_code: (
        Literal[
            "llm_execution_failed",
            "response_json_invalid",
            "response_object_invalid",
            "plan_schema_invalid",
            "catalog_validation_failed",
            "question_constraint_unrepresented",
        ]
        | None
    ) = None
    plan_fingerprint: str | None = Field(default=None, max_length=96)


class AnalysisScopeV1(AnalysisContractModel):
    workspace_id: str
    dataset_key: Literal["common-master"] = "common-master"
    data_sources: tuple[AnalysisDataSource, ...] = (AnalysisDataSource.LEGACY_ISSUES,)
    module_keys: tuple[str, ...]
    revision_ids: tuple[str, ...]
    revision_by_module: dict[str, str]
    checklist_ids: tuple[str, ...] = ()
    retrieval_partition_ids: tuple[str, ...]
    source_count: int = Field(default=0, ge=0)
    source_counts: dict[AnalysisDataSource, int] = Field(default_factory=dict)
    filters: tuple[dict[str, Any], ...] = ()
    date_field: str | None = None


class AnalysisColumnV1(AnalysisContractModel):
    key: str
    label: str
    kind: Literal["dimension", "metric", "window", "record"]
    value_type: Literal["text", "number", "date", "percent", "boolean", "json"]
    field_key: str | None = None


class AnalysisCoverageV1(AnalysisContractModel):
    field_key: str
    label: str
    present_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    invalid_count: int = Field(default=0, ge=0)


class AnalysisResultV1(AnalysisContractModel):
    schema_version: Literal[1] = 1
    query_id: str
    title: str
    family_id: QueryFamilyId
    family_version: int = Field(default=1, ge=1)
    exactness: Exactness = Exactness.EXACT
    output_shape: str
    scope: AnalysisScopeV1
    population_unit: AnalysisCountingUnit | None = None
    counting_unit: AnalysisCountingUnit | None = None
    columns: tuple[AnalysisColumnV1, ...]
    rows: tuple[dict[str, Any], ...]
    totals: dict[str, Any] = Field(default_factory=dict)
    coverage: tuple[AnalysisCoverageV1, ...] = ()
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    execution_path: Literal["catalog"] = "catalog"

    @property
    def family_ref(self) -> str:
        return f"{self.family_id.value}@{self.family_version}"


class LegacyIssueAnalysisArtifactV1(AnalysisContractModel):
    type: Literal["legacy-issue-analysis"] = "legacy-issue-analysis"
    version: Literal[1] = 1
    mode: AnalysisMode
    title: str
    scope: AnalysisScopeV1
    results: tuple[AnalysisResultV1, ...]
    warnings: tuple[str, ...] = ()
    planner_diagnostics: LegacyIssuePlannerDiagnosticsV1 | None = None

    def to_payload(self) -> dict[str, Any]:
        if self.results and all(
            result.exactness == self.results[0].exactness for result in self.results
        ):
            exactness = self.results[0].exactness
        elif not self.results and self.mode == AnalysisMode.SEMANTIC:
            exactness = Exactness.SEMANTIC_EVIDENCE
        else:
            exactness = Exactness.MIXED
        scope: dict[str, Any] = {
            "dataset_key": self.scope.dataset_key,
            "data_sources": [source.value for source in self.scope.data_sources],
            "module_keys": list(self.scope.module_keys),
            "revision_ids": list(self.scope.revision_ids),
            "checklist_ids": list(self.scope.checklist_ids),
            "source_counts": {
                source.value: count for source, count in self.scope.source_counts.items()
            },
        }
        if len(self.scope.data_sources) == 1:
            scope["source_count"] = self.scope.source_count
        if self.scope.filters:
            scope["filters"] = list(self.scope.filters)
        if self.scope.date_field:
            scope["date_field"] = self.scope.date_field
        public_exactness = {
            Exactness.EXACT: "exact",
            Exactness.SEMANTIC_EVIDENCE: "literal_match",
            Exactness.MIXED: "literal_match",
        }
        bar_families = {
            QueryFamilyId.SINGLE_DISTRIBUTION,
            QueryFamilyId.SHARE,
            QueryFamilyId.TOP_BOTTOM_N,
            QueryFamilyId.TOP_N_WITHIN_PARENT,
            QueryFamilyId.HISTOGRAM,
            QueryFamilyId.PARETO,
            QueryFamilyId.CONCENTRATION,
        }

        def public_shape(result: AnalysisResultV1) -> str:
            if result.family_id in bar_families:
                return "bar"
            if result.output_shape in {
                "scalar",
                "table",
                "time_series",
                "crosstab",
                "detail",
            }:
                return result.output_shape
            return "table"

        payload = {
            "version": self.version,
            "mode": self.mode.value,
            "title": _bounded_public_text(self.title, 500),
            "exactness": public_exactness[exactness],
            "scope": scope,
            "queries": [
                _public_query_payload(
                    result,
                    exactness=public_exactness[result.exactness],
                    shape=public_shape(result),
                )
                for result in self.results
            ],
            "warnings": [_bounded_public_text(warning, 1_000) for warning in self.warnings],
        }
        if self.planner_diagnostics is not None:
            payload["planner_diagnostics"] = self.planner_diagnostics.model_dump(
                mode="json",
                exclude_none=True,
            )
        return payload


def _filter_shape(group: FilterGroupV1 | None, *, depth: int = 0) -> tuple[int, int]:
    if group is None:
        return 0, depth
    child_shapes = [_filter_shape(child, depth=depth + 1) for child in group.groups]
    count = len(group.conditions) + sum(shape[0] for shape in child_shapes)
    deepest = max((shape[1] for shape in child_shapes), default=depth + 1)
    return count, deepest


def _public_query_payload(
    result: AnalysisResultV1,
    *,
    exactness: str,
    shape: str,
) -> dict[str, Any]:
    rows, cell_clipped, rows_clipped = _bounded_public_rows(result.rows)
    totals: dict[str, str | int | float | None] = {}
    for key, value in result.totals.items():
        normalized, clipped = _public_cell(value)
        totals[key] = normalized
        cell_clipped = cell_clipped or clipped
    warnings = [_bounded_public_text(warning, 1_000) for warning in result.warnings]
    if cell_clipped:
        warnings.append("표시 한도를 초과한 셀 값을 잘랐습니다.")
    if rows_clipped:
        warnings.append("응답 크기 제한에 따라 일부 행만 표시합니다.")
    population_unit = result.population_unit or (
        AnalysisCountingUnit.CHECKLIST_ITEMS
        if result.scope.data_sources[0] == AnalysisDataSource.VEHICLE_CHECKLISTS
        else AnalysisCountingUnit.LEGACY_RECORDS
    )
    return {
        "id": result.query_id,
        "title": _bounded_public_text(result.title, 500),
        "family_id": result.family_id.value,
        "family_version": result.family_version,
        "data_source": result.scope.data_sources[0].value,
        "source_count": result.scope.source_count,
        "population_unit": population_unit.value,
        "counting_unit": (
            result.counting_unit.value if result.counting_unit is not None else None
        ),
        "coverage_scope": "filtered_population",
        "shape": shape,
        "exactness": exactness,
        "columns": [
            {
                "key": column.key,
                "label": _bounded_public_text(column.label, 500),
                "type": (
                    column.value_type
                    if column.value_type in {"text", "number", "date", "percent"}
                    else "text"
                ),
                "role": (
                    column.kind
                    if column.kind in {"dimension", "metric"}
                    else "metric"
                    if column.kind == "window"
                    else "dimension"
                ),
            }
            for column in result.columns
        ],
        "rows": rows,
        "totals": totals,
        "coverage": [
            {
                "field_key": coverage.field_key,
                "label": _bounded_public_text(coverage.label, 500),
                "present_count": coverage.present_count,
                "missing_count": coverage.missing_count,
                "invalid_count": coverage.invalid_count,
            }
            for coverage in result.coverage
        ],
        "warnings": list(dict.fromkeys(warnings)),
        "truncated": result.truncated or cell_clipped or rows_clipped,
    }


def _bounded_public_rows(
    rows: tuple[dict[str, Any], ...],
) -> tuple[list[dict[str, str | int | float | None]], bool, bool]:
    public_rows: list[dict[str, str | int | float | None]] = []
    used_bytes = 2
    cell_clipped = False
    rows_clipped = False
    for row in rows:
        public_row: dict[str, str | int | float | None] = {}
        for key, value in row.items():
            normalized, clipped = _public_cell(value)
            public_row[key] = normalized
            cell_clipped = cell_clipped or clipped
        encoded_row = json.dumps(
            public_row,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        separator_bytes = 2 if public_rows else 0
        if used_bytes + separator_bytes + len(encoded_row) > PUBLIC_QUERY_ROWS_MAX_BYTES:
            rows_clipped = True
            break
        public_rows.append(public_row)
        used_bytes += separator_bytes + len(encoded_row)
    return public_rows, cell_clipped, rows_clipped


def _public_cell(value: Any) -> tuple[str | int | float | None, bool]:
    if value is None:
        return None, False
    if isinstance(value, bool):
        return ("true" if value else "false"), False
    if isinstance(value, Decimal):
        normalized = int(value) if value == value.to_integral_value() else float(value)
        return normalized, False
    if isinstance(value, (int, float, str)):
        if isinstance(value, str):
            bounded = _bounded_public_text(value, PUBLIC_CELL_MAX_CHARS)
            return bounded, len(bounded) != len(value)
        return value, False
    if isinstance(value, (date, datetime)):
        return value.isoformat(), False
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    else:
        rendered = str(value)
    bounded = _bounded_public_text(rendered, PUBLIC_CELL_MAX_CHARS)
    return bounded, len(bounded) != len(rendered)


def _bounded_public_text(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else value[:max_chars]


__all__ = [
    "AnalysisColumnV1",
    "AnalysisCoverageV1",
    "AnalysisCountingUnit",
    "AnalysisDataSource",
    "AnalysisMode",
    "AnalysisPlanV1",
    "AnalysisResultV1",
    "AnalysisScopeV1",
    "ComparisonSpecV1",
    "DEFAULT_QUERY_LIMIT",
    "DimensionSpecV1",
    "Exactness",
    "FilterConditionV1",
    "FilterGroupV1",
    "FilterJunction",
    "FilterOperator",
    "LegacyIssueAnalysisArtifactV1",
    "LegacyIssuePlannerDiagnosticsV1",
    "MetricOperator",
    "MetricSpecV1",
    "QueryFamilyId",
    "QueryRequestV1",
    "RecordSetKind",
    "RecordSetSpecV1",
    "PUBLIC_CELL_MAX_CHARS",
    "PUBLIC_QUERY_ROWS_MAX_BYTES",
    "SortDirection",
    "SortSpecV1",
    "TimeGrain",
    "ValueMatchMode",
    "WindowOperator",
    "WindowSpecV1",
]
