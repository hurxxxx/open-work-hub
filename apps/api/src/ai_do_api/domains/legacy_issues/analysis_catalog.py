from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping

from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisDataSource,
    FilterConditionV1,
    FilterGroupV1,
    FilterOperator,
    MetricOperator,
    QueryFamilyId,
    QueryRequestV1,
    ValueMatchMode,
    WindowOperator,
)
from ai_do_api.domains.legacy_issues.dataset_records import DatasetFieldDefinition


CATALOG_VERSION = 1
EXPECTED_QUERY_FAMILY_COUNT = 62


class AnalysisCatalogError(ValueError):
    pass


class FamilyExecutionKind(str, Enum):
    METADATA = "metadata"
    AGGREGATE = "aggregate"
    DETAIL = "detail"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    COMPOSITE = "composite"
    GENERATED = "generated"


ALL_METRICS = frozenset(MetricOperator)
COUNT_METRICS = frozenset(
    {
        MetricOperator.ISSUE_COUNT,
        MetricOperator.DISTINCT_COUNT,
        MetricOperator.PRESENT_COUNT,
        MetricOperator.MISSING_COUNT,
        MetricOperator.CONDITIONAL_RATE,
    }
)
NUMERIC_METRICS = frozenset(
    {
        MetricOperator.SUM,
        MetricOperator.AVG,
        MetricOperator.MIN,
        MetricOperator.MAX,
        MetricOperator.MEDIAN,
        MetricOperator.PERCENTILE,
    }
)


@dataclass(frozen=True, slots=True)
class QueryFamilyDescriptor:
    family_id: QueryFamilyId
    version: int
    category: str
    execution_kind: FamilyExecutionKind
    output_shape: str
    min_dimensions: int
    max_dimensions: int
    allowed_metrics: frozenset[MetricOperator]
    requires_time_dimension: bool = False
    supports_comparisons: bool = False
    supports_windows: bool = False
    required_metrics: frozenset[MetricOperator] = frozenset()
    required_windows: frozenset[WindowOperator] = frozenset()
    min_comparisons: int = 0
    requires_filters: bool = False
    requires_detail_fields: bool = False
    audiences: tuple[str, ...] = ("executive", "practitioner")
    purpose: str = ""
    recipe: str = ""

    @property
    def ref(self) -> str:
        return f"{self.family_id.value}@{self.version}"


@dataclass(frozen=True, slots=True)
class AnalysisFieldCapabilities:
    field: DatasetFieldDefinition
    filter_operators: frozenset[FilterOperator]
    metric_operators: frozenset[MetricOperator]
    groupable: bool
    time_bucketable: bool
    numeric_bucketable: bool


_NULL_FILTERS = frozenset({FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL})
_EQUALITY_FILTERS = frozenset(
    {
        FilterOperator.EQ,
        FilterOperator.NE,
        FilterOperator.IN,
        FilterOperator.NOT_IN,
        *_NULL_FILTERS,
    }
)
_TEXT_FILTERS = frozenset(
    {
        *_EQUALITY_FILTERS,
        FilterOperator.CONTAINS,
        FilterOperator.STARTS_WITH,
        FilterOperator.CONTAINS_ANY,
        FilterOperator.CONTAINS_ALL,
    }
)
_ORDERED_FILTERS = frozenset(
    {
        *_EQUALITY_FILTERS,
        FilterOperator.GT,
        FilterOperator.GTE,
        FilterOperator.LT,
        FilterOperator.LTE,
        FilterOperator.BETWEEN,
    }
)
_MULTI_FILTERS = frozenset(
    {
        *_EQUALITY_FILTERS,
        FilterOperator.CONTAINS_ANY,
        FilterOperator.CONTAINS_ALL,
    }
)


def field_capabilities(field: DatasetFieldDefinition) -> AnalysisFieldCapabilities:
    field_type = field.field_type
    if field.allow_multiple:
        filters = _MULTI_FILTERS
    elif field_type in {"text", "longText"}:
        filters = _TEXT_FILTERS
    elif field_type in {"number", "date"}:
        filters = _ORDERED_FILTERS
    else:
        filters = _EQUALITY_FILTERS

    metric_operators = {
        MetricOperator.DISTINCT_COUNT,
        MetricOperator.PRESENT_COUNT,
        MetricOperator.MISSING_COUNT,
    }
    if field_type == "number":
        metric_operators.update(NUMERIC_METRICS)
    elif field_type == "date":
        metric_operators.update({MetricOperator.MIN, MetricOperator.MAX})
    return AnalysisFieldCapabilities(
        field=field,
        filter_operators=filters,
        metric_operators=frozenset(metric_operators),
        groupable=True,
        time_bucketable=field_type == "date",
        numeric_bucketable=field_type == "number",
    )


def build_analysis_field_catalog(
    fields: Iterable[DatasetFieldDefinition],
) -> Mapping[str, AnalysisFieldCapabilities]:
    catalog: dict[str, AnalysisFieldCapabilities] = {}
    for field in fields:
        if not field.active:
            continue
        existing = catalog.get(field.key)
        if existing is not None and (
            existing.field.field_type != field.field_type
            or existing.field.allow_multiple != field.allow_multiple
        ):
            raise AnalysisCatalogError(f"conflicting analysis field definition: {field.key}")
        catalog[field.key] = field_capabilities(field)
    return MappingProxyType(catalog)


def validate_query_request(
    request: QueryRequestV1,
    *,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> QueryFamilyDescriptor:
    descriptor = get_query_family_descriptor(request.family_id, request.family_version)
    dimension_count = len(request.dimensions)
    if not descriptor.min_dimensions <= dimension_count <= descriptor.max_dimensions:
        raise AnalysisCatalogError(
            f"{descriptor.ref} accepts {descriptor.min_dimensions}.."
            f"{descriptor.max_dimensions} dimensions"
        )
    if descriptor.requires_time_dimension and not any(
        dimension.time_grain is not None for dimension in request.dimensions
    ):
        raise AnalysisCatalogError(f"{descriptor.ref} requires a time dimension")
    if request.comparisons and not descriptor.supports_comparisons:
        raise AnalysisCatalogError(f"{descriptor.ref} does not support comparisons")
    if request.windows and not descriptor.supports_windows:
        raise AnalysisCatalogError(f"{descriptor.ref} does not support windows")
    metric_operators = {metric.operator for metric in request.metrics}
    missing_metrics = descriptor.required_metrics.difference(metric_operators)
    if missing_metrics:
        raise AnalysisCatalogError(
            f"{descriptor.ref} requires metrics: "
            f"{sorted(metric.value for metric in missing_metrics)}"
        )
    window_operators = {window.operator for window in request.windows}
    missing_windows = descriptor.required_windows.difference(window_operators)
    if missing_windows:
        raise AnalysisCatalogError(
            f"{descriptor.ref} requires windows: "
            f"{sorted(window.value for window in missing_windows)}"
        )
    if len(request.comparisons) < descriptor.min_comparisons:
        raise AnalysisCatalogError(
            f"{descriptor.ref} requires at least {descriptor.min_comparisons} comparisons"
        )
    if descriptor.requires_filters and request.filters is None and request.record_set is None:
        raise AnalysisCatalogError(f"{descriptor.ref} requires filters")
    if descriptor.requires_detail_fields and not request.detail_fields:
        raise AnalysisCatalogError(f"{descriptor.ref} requires detail_fields")

    for dimension in request.dimensions:
        capabilities = _require_field(fields, dimension.field_key)
        if not capabilities.groupable:
            raise AnalysisCatalogError(f"field is not groupable: {dimension.field_key}")
        if dimension.time_grain is not None and not capabilities.time_bucketable:
            raise AnalysisCatalogError(f"time grain requires a date field: {dimension.field_key}")
        if dimension.numeric_bucket_size is not None and not capabilities.numeric_bucketable:
            raise AnalysisCatalogError(
                f"numeric bucket requires a number field: {dimension.field_key}"
            )

    for metric in request.metrics:
        if metric.operator not in descriptor.allowed_metrics:
            raise AnalysisCatalogError(
                f"{descriptor.ref} does not allow metric: {metric.operator.value}"
            )
        if metric.field_key is not None:
            capabilities = _require_field(fields, metric.field_key)
            if metric.operator not in capabilities.metric_operators:
                raise AnalysisCatalogError(
                    f"{metric.operator.value} is incompatible with "
                    f"{metric.field_key}:{capabilities.field.field_type}"
                )
        _validate_filter_group(metric.condition, fields=fields)

    _validate_filter_group(request.filters, fields=fields)
    if request.record_set is not None:
        if descriptor.execution_kind not in {
            FamilyExecutionKind.AGGREGATE,
            FamilyExecutionKind.DETAIL,
        }:
            raise AnalysisCatalogError(
                f"{descriptor.ref} does not support a cohort re-entry record set"
            )
        if request.family_id == QueryFamilyId.TOTAL_COUNT:
            raise AnalysisCatalogError(
                "total_count does not accept a cohort re-entry record set; use filtered_count"
            )
        for field_key in request.record_set.key_fields:
            capabilities = _require_field(fields, field_key)
            if not capabilities.groupable or capabilities.field.allow_multiple:
                raise AnalysisCatalogError(
                    f"record-set key must be a single-value groupable field: {field_key}"
                )
            if (
                request.record_set.key_match_mode == ValueMatchMode.NORMALIZED
                and capabilities.field.field_type not in {"text", "longText", "select"}
            ):
                raise AnalysisCatalogError(
                    f"normalized record-set matching requires a text field: {field_key}"
                )
        _validate_filter_group(request.record_set.seed_filters, fields=fields)
    for comparison in request.comparisons:
        _validate_filter_group(comparison.filters, fields=fields)
    for field_key in request.detail_fields:
        _require_field(fields, field_key)

    metric_aliases = {metric.alias for metric in request.metrics}
    dimension_aliases = {dimension.alias or dimension.field_key for dimension in request.dimensions}
    available_aliases = metric_aliases | dimension_aliases
    comparison_aliases = {
        f"{comparison.key}__{metric.alias}"
        for comparison in request.comparisons
        for metric in request.metrics
    }
    if comparison_aliases.intersection(available_aliases):
        raise AnalysisCatalogError("comparison output aliases collide with query aliases")
    available_aliases.update(comparison_aliases)
    for window in request.windows:
        if window.metric_alias not in metric_aliases:
            raise AnalysisCatalogError(f"window metric alias is not defined: {window.metric_alias}")
        unknown_partition = set(window.partition_by).difference(dimension_aliases)
        if unknown_partition:
            raise AnalysisCatalogError(
                f"window partition aliases are not dimensions: {sorted(unknown_partition)}"
            )
        unknown_order = set(window.order_by).difference(available_aliases)
        if unknown_order:
            raise AnalysisCatalogError(
                f"window order aliases are not defined: {sorted(unknown_order)}"
            )
        available_aliases.add(window.alias)
    for sort in request.sort:
        if sort.key not in available_aliases and sort.key not in request.detail_fields:
            raise AnalysisCatalogError(f"sort alias is not defined: {sort.key}")
    _validate_family_semantics(request, fields=fields)
    return descriptor


def _validate_filter_group(
    group: FilterGroupV1 | None,
    *,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> None:
    if group is None:
        return
    for condition in group.conditions:
        _validate_filter_condition(condition, fields=fields)
    for child in group.groups:
        _validate_filter_group(child, fields=fields)


def _validate_filter_condition(
    condition: FilterConditionV1,
    *,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> None:
    capabilities = _require_field(fields, condition.field_key)
    if condition.operator not in capabilities.filter_operators:
        raise AnalysisCatalogError(
            f"{condition.operator.value} is incompatible with "
            f"{condition.field_key}:{capabilities.field.field_type}"
        )
    if condition.match_mode == ValueMatchMode.NORMALIZED:
        if capabilities.field.allow_multiple or capabilities.field.field_type not in {
            "text",
            "longText",
            "select",
        }:
            raise AnalysisCatalogError(
                f"normalized matching requires a single-value text field: {condition.field_key}"
            )
        if condition.operator in {
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }:
            raise AnalysisCatalogError(
                f"{condition.operator.value} does not support normalized matching"
            )


def _require_field(
    fields: Mapping[str, AnalysisFieldCapabilities],
    field_key: str,
) -> AnalysisFieldCapabilities:
    try:
        return fields[field_key]
    except KeyError as error:
        raise AnalysisCatalogError(f"unknown or inactive analysis field: {field_key}") from error


def _validate_family_semantics(
    request: QueryRequestV1,
    *,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> None:
    family_id = request.family_id
    metric_operators = {metric.operator for metric in request.metrics}

    if family_id == QueryFamilyId.TOTAL_COUNT:
        if request.filters is not None:
            raise AnalysisCatalogError("total_count does not accept filters")
        if metric_operators != {MetricOperator.ISSUE_COUNT} or len(request.metrics) != 1:
            raise AnalysisCatalogError("total_count requires exactly one issue_count metric")
    elif family_id == QueryFamilyId.FILTERED_COUNT:
        if metric_operators != {MetricOperator.ISSUE_COUNT} or len(request.metrics) != 1:
            raise AnalysisCatalogError("filtered_count requires exactly one issue_count metric")
    elif family_id == QueryFamilyId.DISTINCT_COUNT:
        if (
            len(request.metrics) != 1
            or request.metrics[0].operator != MetricOperator.DISTINCT_COUNT
        ):
            raise AnalysisCatalogError("distinct_count requires exactly one distinct_count metric")
    elif family_id == QueryFamilyId.DATE_RANGE_COVERAGE:
        _require_metric_pair_on_same_field(
            request,
            first=MetricOperator.MIN,
            second=MetricOperator.MAX,
            field_type="date",
            fields=fields,
        )
    elif family_id in {
        QueryFamilyId.FIELD_COVERAGE_CARDINALITY,
        QueryFamilyId.MISSING_POPULATED_RATE,
        QueryFamilyId.COMPLETENESS,
    }:
        _require_metrics_on_same_field(
            request,
            required={MetricOperator.PRESENT_COUNT, MetricOperator.MISSING_COUNT},
        )
    elif family_id == QueryFamilyId.NUMERIC_SUMMARY:
        _require_metrics_on_same_field(request)
        if any(
            metric.field_key is None or fields[metric.field_key].field.field_type != "number"
            for metric in request.metrics
        ):
            raise AnalysisCatalogError("numeric_summary requires one numeric field")
    elif family_id == QueryFamilyId.HISTOGRAM:
        if any(dimension.numeric_bucket_size is None for dimension in request.dimensions):
            raise AnalysisCatalogError("histogram requires numeric_bucket_size")
    elif family_id in {
        QueryFamilyId.TOP_BOTTOM_N,
        QueryFamilyId.TOP_N_WITHIN_PARENT,
    }:
        if len(request.metrics) != 1:
            raise AnalysisCatalogError(
                f"{family_id.value} requires exactly one ranking metric"
            )
        if request.sort and request.sort[0].key != request.metrics[0].alias:
            raise AnalysisCatalogError(
                f"{family_id.value} first sort must use the ranking metric"
            )
    elif family_id == QueryFamilyId.PARETO:
        if len(request.metrics) != 1:
            raise AnalysisCatalogError("pareto requires exactly one metric")
    elif family_id in {
        QueryFamilyId.PERIOD_COMPARE,
        QueryFamilyId.BEFORE_AFTER,
    }:
        if not any(
            _filter_group_uses_field_type(comparison.filters, field_type="date", fields=fields)
            for comparison in request.comparisons
        ):
            raise AnalysisCatalogError(f"{family_id.value} requires date comparison filters")
    elif family_id == QueryFamilyId.YOY_MOM:
        supported = {
            WindowOperator.LAG,
            WindowOperator.ABSOLUTE_CHANGE,
            WindowOperator.RATE_CHANGE,
        }
        if not any(window.operator in supported for window in request.windows):
            raise AnalysisCatalogError("yoy_mom requires a lag/change window")
    elif family_id == QueryFamilyId.ROLLING:
        moving = {
            WindowOperator.MOVING_AVERAGE,
            WindowOperator.MOVING_SUM,
        }
        if not any(window.operator in moving for window in request.windows):
            raise AnalysisCatalogError("rolling requires a moving window")
    elif family_id == QueryFamilyId.FIRST_LAST:
        _require_metric_pair_on_same_field(
            request,
            first=MetricOperator.MIN,
            second=MetricOperator.MAX,
            field_type="date",
            fields=fields,
        )
        if any(dimension.time_grain is not None for dimension in request.dimensions):
            raise AnalysisCatalogError("first_last groups by non-time dimensions")
    elif family_id == QueryFamilyId.SYMPTOM_CAUSE:
        _require_dimension_role(
            request,
            role="symptom",
            candidates={"symptom", "occurrence_type", "issue_type"},
        )
        _require_dimension_role(
            request,
            role="cause",
            candidates={"cause", "cause_type"},
        )
    elif family_id == QueryFamilyId.CAUSE_COUNTERMEASURE:
        _require_dimension_role(
            request,
            role="cause",
            candidates={"cause", "cause_type"},
        )
        _require_dimension_role(
            request,
            role="countermeasure",
            candidates={"countermeasure", "countermeasure_type", "action"},
        )
    elif family_id == QueryFamilyId.SUPPLIER_PART_PROCESS:
        available = {"supplier", "part_number", "process_name"}
        selected = {dimension.field_key for dimension in request.dimensions}
        if len(selected.intersection(available)) < 2:
            raise AnalysisCatalogError(
                "supplier_part_process requires at least two supplier/part/process dimensions"
            )
    elif family_id == QueryFamilyId.SEVERITY:
        _require_dimension_fields(request, {"severity_grade"})
    elif family_id == QueryFamilyId.APPLIED_BACKLOG:
        _require_dimension_fields(request, {"applied"})
    elif family_id == QueryFamilyId.MASTER_STATUS:
        _require_dimension_fields(request, {"evidence_legacy_issue"})


def _require_metrics_on_same_field(
    request: QueryRequestV1,
    *,
    required: set[MetricOperator] | None = None,
) -> None:
    operators = {metric.operator for metric in request.metrics}
    if required is not None and not required.issubset(operators):
        raise AnalysisCatalogError(
            f"family requires metrics: {sorted(operator.value for operator in required)}"
        )
    field_keys = {metric.field_key for metric in request.metrics}
    if None in field_keys or len(field_keys) != 1:
        raise AnalysisCatalogError("family metrics must reference the same field")


def _require_dimension_fields(
    request: QueryRequestV1,
    required: set[str],
) -> None:
    selected = {dimension.field_key for dimension in request.dimensions}
    missing = required.difference(selected)
    if missing:
        raise AnalysisCatalogError(
            f"{request.family_id.value} requires dimensions: {sorted(missing)}"
        )


def _require_dimension_role(
    request: QueryRequestV1,
    *,
    role: str,
    candidates: set[str],
) -> None:
    selected = {dimension.field_key for dimension in request.dimensions}
    if not selected.intersection(candidates):
        raise AnalysisCatalogError(f"{request.family_id.value} requires a {role} dimension")


def _require_metric_pair_on_same_field(
    request: QueryRequestV1,
    *,
    first: MetricOperator,
    second: MetricOperator,
    field_type: str,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> None:
    _require_metrics_on_same_field(request, required={first, second})
    field_key = request.metrics[0].field_key
    if field_key is None or fields[field_key].field.field_type != field_type:
        raise AnalysisCatalogError(f"family requires one {field_type} field")


def _filter_group_uses_field_type(
    group: FilterGroupV1,
    *,
    field_type: str,
    fields: Mapping[str, AnalysisFieldCapabilities],
) -> bool:
    if any(
        fields[condition.field_key].field.field_type == field_type for condition in group.conditions
    ):
        return True
    return any(
        _filter_group_uses_field_type(child, field_type=field_type, fields=fields)
        for child in group.groups
    )


def _descriptor(
    family_id: QueryFamilyId,
    *,
    category: str,
    execution_kind: FamilyExecutionKind = FamilyExecutionKind.AGGREGATE,
    output_shape: str = "table",
    dimensions: tuple[int, int] = (0, 4),
    metrics: frozenset[MetricOperator] = ALL_METRICS,
    time: bool = False,
    comparisons: bool = False,
    windows: bool = False,
    required_metrics: frozenset[MetricOperator] = frozenset(),
    required_windows: frozenset[WindowOperator] = frozenset(),
    min_comparisons: int = 0,
    requires_filters: bool = False,
    requires_detail_fields: bool = False,
    audiences: tuple[str, ...] = ("executive", "practitioner"),
) -> QueryFamilyDescriptor:
    purpose, recipe = _family_guidance(family_id, category=category)
    return QueryFamilyDescriptor(
        family_id=family_id,
        version=CATALOG_VERSION,
        category=category,
        execution_kind=execution_kind,
        output_shape=output_shape,
        min_dimensions=dimensions[0],
        max_dimensions=dimensions[1],
        allowed_metrics=metrics,
        requires_time_dimension=time,
        supports_comparisons=comparisons,
        supports_windows=windows,
        required_metrics=required_metrics,
        required_windows=required_windows,
        min_comparisons=min_comparisons,
        requires_filters=requires_filters,
        requires_detail_fields=requires_detail_fields,
        audiences=audiences,
        purpose=purpose,
        recipe=recipe,
    )


_FAMILY_PURPOSES: Mapping[QueryFamilyId, str] = MappingProxyType(
    {
        QueryFamilyId.FIELD_CATALOG: "분석 가능한 필드·타입·다중값 여부 조회",
        QueryFamilyId.VALUE_DOMAIN: "한 필드에 실제 존재하는 값과 빈도 조회",
        QueryFamilyId.SCOPE_INVENTORY: "현재 분석 대상 모듈·리비전·원천 범위 확인",
        QueryFamilyId.DATE_RANGE_COVERAGE: "날짜 필드의 최초·최종일과 입력 범위 확인",
        QueryFamilyId.FIELD_COVERAGE_CARDINALITY: "필드별 입력률·미입력률·고유값 수 확인",
        QueryFamilyId.ACTIVE_REVISION_FRESHNESS: "모듈별 유효 리비전과 최신성 확인",
        QueryFamilyId.TOTAL_COUNT: "필터 없는 전체 문제 건수",
        QueryFamilyId.FILTERED_COUNT: "지정 조건을 만족하는 문제 건수",
        QueryFamilyId.DISTINCT_COUNT: "특정 필드의 고유값 수",
        QueryFamilyId.MISSING_POPULATED_RATE: "특정 필드의 입력·미입력 건수와 비율",
        QueryFamilyId.NUMERIC_SUMMARY: "숫자 필드의 합계·평균·범위·백분위 요약",
        QueryFamilyId.DURATION_SUMMARY: "두 날짜 사이 소요기간 분포 요약",
        QueryFamilyId.SINGLE_DISTRIBUTION: "한 차원별 항목 수 또는 고유 개체 수 분포",
        QueryFamilyId.MULTIDIM_BREAKDOWN: "둘 이상 차원의 조합별 건수 분해",
        QueryFamilyId.SHARE: "차원별 건수와 전체 대비 구성비",
        QueryFamilyId.TOP_BOTTOM_N: (
            "모든 차원 조합을 하나의 전체 순위로 계산한 전역 상위 또는 하위 N개 그룹"
        ),
        QueryFamilyId.TOP_N_WITHIN_PARENT: (
            "각 부모 차원 조합마다 별도로 계산한 하위 그룹 Top N"
        ),
        QueryFamilyId.CROSSTAB: "두 개 이상 범주의 교차 분포",
        QueryFamilyId.HISTOGRAM: "숫자 필드를 일정 구간으로 나눈 분포",
        QueryFamilyId.TIME_SERIES: "일·주·월·분기·연도별 추이",
        QueryFamilyId.PERIOD_COMPARE: "두 기간의 동일 지표 비교",
        QueryFamilyId.ABSOLUTE_CHANGE: "직전 또는 비교 기간 대비 절대 증감",
        QueryFamilyId.RATE_CHANGE: "직전 또는 비교 기간 대비 증감률",
        QueryFamilyId.YOY_MOM: "전년·전월·전분기 대비 변화",
        QueryFamilyId.ROLLING: "이동 기간 합계 또는 평균",
        QueryFamilyId.CUMULATIVE: "시간 순 누적 건수 또는 누적값",
        QueryFamilyId.FIRST_LAST: "그룹별 최초·최종 발생 시점",
        QueryFamilyId.EMERGING_DECLINING_SPIKE: "신규·감소·급증 그룹 탐색",
        QueryFamilyId.COHORT_COMPARE: "명시한 둘 이상 집단의 동일 지표 비교",
        QueryFamilyId.BENCHMARK: "선택 집단을 전체 또는 기준 집단과 비교",
        QueryFamilyId.BEFORE_AFTER: "기준일 전후의 지표 비교",
        QueryFamilyId.MIX_SHIFT: "기간·집단 사이 구성비 변화",
        QueryFamilyId.RANK_SHIFT: "기간·집단 사이 순위 변화",
        QueryFamilyId.CONTRIBUTION_CHANGE: "전체 증감에 기여한 그룹과 기여량",
        QueryFamilyId.OVERLAP_INTERSECTION_EXCLUSIVE: "집단 간 교집합·합집합·한정 집합",
        QueryFamilyId.PARETO: "상위 그룹과 누적 기여율을 이용한 Pareto 분석",
        QueryFamilyId.CONCENTRATION: "문제가 일부 차종·권역·유형에 집중되는 정도",
        QueryFamilyId.CONDITIONAL_RATE: "분모 집단에서 조건을 만족하는 비율",
        QueryFamilyId.CATEGORICAL_ASSOCIATION: "두 범주 필드의 조건부 비율·연관 분포",
        QueryFamilyId.SYMPTOM_CAUSE: "현상과 원인 범주의 조합 분포",
        QueryFamilyId.CAUSE_COUNTERMEASURE: "원인과 개선대책 범주의 조합 분포",
        QueryFamilyId.SUPPLIER_PART_PROCESS: "협력사·부품·공정 축의 기여 분포",
        QueryFamilyId.SEVERITY: "중요도·등급별 건수와 고위험 비율",
        QueryFamilyId.APPLIED_BACKLOG: "적용 여부별 완료·미적용 잔여 현황",
        QueryFamilyId.MASTER_STATUS: "마스터 상태별 등재·대기·제외 현황",
        QueryFamilyId.EVIDENCE_COVERAGE: "근거 필드와 첨부의 보유·누락 현황",
        QueryFamilyId.COMPLETENESS: "업무 필드의 입력 완전성",
        QueryFamilyId.INVALID_VALUES: "선언 타입과 맞지 않는 값의 규모",
        QueryFamilyId.DUPLICATE_NORMALIZATION_STALE: "중복·표기 변형·장기 미갱신 후보",
        QueryFamilyId.DETAIL_LIST: "조건을 만족하는 개별 레코드 목록",
        QueryFamilyId.GROUP_DRILLDOWN: "집계 그룹에서 원본 레코드로 상세 조회",
        QueryFamilyId.REPRESENTATIVE_RECORDS: "집계 결과를 설명하는 대표 레코드",
        QueryFamilyId.SEMANTIC_SIMILAR: "자유 텍스트 의미가 유사한 과거 사례",
        QueryFamilyId.EXACT_AGGREGATE_PLUS_SEMANTIC: "정확 통계와 의미 근거를 함께 요청",
        QueryFamilyId.ATTACHMENT_EVIDENCE: "첨부 원문에서 관련 근거 탐색",
        QueryFamilyId.EXECUTIVE_SCORECARD: "핵심 수치·추이·위험·집중도를 묶은 요약",
        QueryFamilyId.EXECUTIVE_BRIEFING: "경영진 질문을 여러 정확 통계와 근거로 분해",
        QueryFamilyId.PRACTITIONER_INVESTIGATION: "실무 원인 조사에 필요한 분포·상세·근거 결합",
        QueryFamilyId.MULTI_SCOPE_MATRIX: "권역·기간·차종 등 여러 범위 축의 복합 비교",
        QueryFamilyId.ISSUE_CAUSE_COUNTERMEASURE_REVIEW: "문제·원인·대책 흐름의 복합 검토",
        QueryFamilyId.CONTEXTUAL_FOLLOWUP: "직전 대화의 범위·필터를 이어받은 후속 분석",
        QueryFamilyId.GENERATED_SQL_FALLBACK: "기존 원자 쿼리 패밀리로 표현할 수 없는 읽기 전용 분석",
    }
)

_CATEGORY_RECIPES: Mapping[str, str] = MappingProxyType(
    {
        "metadata": "메타데이터 또는 coverage 연산을 사용하고 추측한 값은 만들지 않는다.",
        "scalar": "dimension 없이 호환 metric과 필요한 filter만 선택한다.",
        "distribution": "1~4 dimensions와 issue_count를 선택하고 필요하면 rank/share window를 추가한다.",
        "time": "date field에 time_grain을 지정하고 시간순 window 또는 comparison을 사용한다.",
        "comparison": "comparison filters로 2~4 집단을 정의하고 같은 metric을 비교한다.",
        "association": "범주 dimensions와 count/rate/share를 사용하며 인과로 표현하지 않는다.",
        "quality": "대상 상태 필드와 count/rate/coverage를 조합한다.",
        "detail": "detail_fields와 filter를 지정하고 최대 200행만 요청한다.",
        "semantic": "query node를 만들지 말고 plan mode를 semantic으로 선택한다.",
        "hybrid": "plan mode를 hybrid로 두고 정확 통계용 atomic query node만 만든다.",
        "composite": "이 ID를 단일 실행하지 말고 2~6개의 atomic query node로 분해한다.",
        "generated": "query node를 만들지 말고 mode=generated를 선택한다.",
    }
)

_FAMILY_RECIPE_OVERRIDES: Mapping[QueryFamilyId, str] = MappingProxyType(
    {
        QueryFamilyId.DATE_RANGE_COVERAGE: "date field에 MIN과 MAX metric을 함께 사용한다.",
        QueryFamilyId.FIELD_COVERAGE_CARDINALITY: "PRESENT_COUNT, MISSING_COUNT, DISTINCT_COUNT를 사용한다.",
        QueryFamilyId.DISTINCT_COUNT: "대상 field_key를 가진 DISTINCT_COUNT 하나를 사용한다.",
        QueryFamilyId.SINGLE_DISTRIBUTION: (
            "dimension 하나와 목적에 맞는 count metric을 사용한다. 고유 개체의 "
            "그룹별 수는 DISTINCT_COUNT와 해당 개체 field_key를 사용한다."
        ),
        QueryFamilyId.MISSING_POPULATED_RATE: "PRESENT_COUNT와 MISSING_COUNT를 같은 필드에 사용한다.",
        QueryFamilyId.NUMERIC_SUMMARY: "number field에 AVG/MIN/MAX와 필요한 percentile을 사용한다.",
        QueryFamilyId.DURATION_SUMMARY: "두 날짜의 파생 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.SHARE: "dimension과 metric을 선택하고 PERCENT_OF_TOTAL window를 사용한다.",
        QueryFamilyId.TOP_BOTTOM_N: (
            "모든 dimensions의 완전한 tuple을 하나의 전역 모집단으로 정렬하고 "
            "limit=N을 적용한다. 부모별 partition을 만들지 않는다."
        ),
        QueryFamilyId.TOP_N_WITHIN_PARENT: (
            "질문이 각 부모 그룹마다 별도 N개를 요구할 때만 parent dimensions 뒤에 "
            "child dimension을 두고 limit=N을 지정한다. 서버가 각 parent tuple별 "
            "rank<=N을 적용하며 전역 복합 차원 Top N에는 사용하지 않는다."
        ),
        QueryFamilyId.CROSSTAB: "서로 다른 범주 dimensions를 2개 이상 사용한다.",
        QueryFamilyId.HISTOGRAM: "number dimension에 numeric_bucket_size를 지정한다.",
        QueryFamilyId.ABSOLUTE_CHANGE: "시간순 LAG 또는 비교 집단 값의 차이를 사용한다.",
        QueryFamilyId.RATE_CHANGE: "시간순 RATE_CHANGE window를 사용하고 0 분모는 제외한다.",
        QueryFamilyId.YOY_MOM: "date time_grain과 LAG/증감 window를 사용하고 월 YoY=12, 분기 YoY=4처럼 lag_offset을 지정한다.",
        QueryFamilyId.ROLLING: "MOVING_SUM 또는 MOVING_AVERAGE와 preceding을 지정한다.",
        QueryFamilyId.CUMULATIVE: "시간순 CUMULATIVE_SUM window를 사용한다.",
        QueryFamilyId.PARETO: "dimension과 metric을 지정한다. 서버가 내림차순 구성비와 누적 기여율을 계산한다.",
        QueryFamilyId.CONDITIONAL_RATE: "CONDITIONAL_RATE metric의 condition과 명시적 분모 filter를 사용한다.",
        QueryFamilyId.DETAIL_LIST: "detail_fields와 filter를 지정하고 limit은 200 이하로 둔다.",
        QueryFamilyId.GROUP_DRILLDOWN: "상위 집계의 동일 filter를 유지한 채 detail_fields를 선택한다.",
        QueryFamilyId.EXACT_AGGREGATE_PLUS_SEMANTIC: "mode=hybrid; catalog query는 정확 집계만 담고 의미검색은 서버가 별도 실행한다.",
        QueryFamilyId.EMERGING_DECLINING_SPIKE: "시계열 보간과 임계값 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.MIX_SHIFT: "비교 집단별 구성비 파생 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.RANK_SHIFT: "비교 집단별 순위 파생 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.CONTRIBUTION_CHANGE: "비교값 차이와 기여율 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.OVERLAP_INTERSECTION_EXCLUSIVE: "교집합·배타 집합 파생 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.CONCENTRATION: "집중도 지수 또는 누적 점유율 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.DUPLICATE_NORMALIZATION_STALE: "정규화·중복·경과일 파생 계산이 필요하므로 mode=generated를 선택하고 query node를 만들지 않는다.",
        QueryFamilyId.REPRESENTATIVE_RECORDS: "대표성은 의미 관련도로 판단하므로 query node 없이 mode=semantic을 선택한다.",
        QueryFamilyId.GENERATED_SQL_FALLBACK: "다른 catalog family로 표현할 수 없을 때만 mode=generated로 선택한다.",
    }
)


def _family_guidance(
    family_id: QueryFamilyId,
    *,
    category: str,
) -> tuple[str, str]:
    try:
        purpose = _FAMILY_PURPOSES[family_id]
        recipe = _FAMILY_RECIPE_OVERRIDES.get(
            family_id,
            _CATEGORY_RECIPES[category],
        )
    except KeyError as error:
        raise AnalysisCatalogError(
            f"analysis family guidance is missing: {family_id.value}"
        ) from error
    return purpose, recipe


def _build_descriptors() -> tuple[QueryFamilyDescriptor, ...]:
    metadata = (
        _descriptor(
            QueryFamilyId.FIELD_CATALOG,
            category="metadata",
            execution_kind=FamilyExecutionKind.METADATA,
            output_shape="field_catalog",
            dimensions=(0, 0),
            metrics=COUNT_METRICS,
        ),
        _descriptor(
            QueryFamilyId.VALUE_DOMAIN,
            category="metadata",
            output_shape="value_domain",
            dimensions=(1, 1),
            metrics=COUNT_METRICS,
        ),
        _descriptor(
            QueryFamilyId.SCOPE_INVENTORY,
            category="metadata",
            execution_kind=FamilyExecutionKind.METADATA,
            output_shape="scope",
            dimensions=(0, 0),
            metrics=COUNT_METRICS,
        ),
        _descriptor(
            QueryFamilyId.DATE_RANGE_COVERAGE,
            category="metadata",
            output_shape="scalar",
            dimensions=(0, 0),
        ),
        _descriptor(
            QueryFamilyId.FIELD_COVERAGE_CARDINALITY,
            category="metadata",
            output_shape="scalar",
            dimensions=(0, 0),
            metrics=COUNT_METRICS,
        ),
        _descriptor(
            QueryFamilyId.ACTIVE_REVISION_FRESHNESS,
            category="metadata",
            execution_kind=FamilyExecutionKind.METADATA,
            output_shape="scope",
            dimensions=(0, 0),
            metrics=COUNT_METRICS,
        ),
    )

    scalar_ids = (
        QueryFamilyId.TOTAL_COUNT,
        QueryFamilyId.FILTERED_COUNT,
        QueryFamilyId.DISTINCT_COUNT,
        QueryFamilyId.MISSING_POPULATED_RATE,
        QueryFamilyId.NUMERIC_SUMMARY,
        QueryFamilyId.DURATION_SUMMARY,
    )
    scalar = tuple(
        _descriptor(
            family_id,
            category="scalar",
            execution_kind=(
                FamilyExecutionKind.GENERATED
                if family_id == QueryFamilyId.DURATION_SUMMARY
                else FamilyExecutionKind.AGGREGATE
            ),
            output_shape="scalar",
            dimensions=(0, 0),
            metrics=(
                frozenset({MetricOperator.ISSUE_COUNT})
                if family_id in {QueryFamilyId.TOTAL_COUNT, QueryFamilyId.FILTERED_COUNT}
                else NUMERIC_METRICS
                if family_id == QueryFamilyId.NUMERIC_SUMMARY
                else ALL_METRICS
            ),
            requires_filters=family_id == QueryFamilyId.FILTERED_COUNT,
        )
        for family_id in scalar_ids
    )

    distribution_ids = (
        QueryFamilyId.SINGLE_DISTRIBUTION,
        QueryFamilyId.MULTIDIM_BREAKDOWN,
        QueryFamilyId.SHARE,
        QueryFamilyId.TOP_BOTTOM_N,
        QueryFamilyId.TOP_N_WITHIN_PARENT,
        QueryFamilyId.CROSSTAB,
        QueryFamilyId.HISTOGRAM,
    )
    distribution = tuple(
        _descriptor(
            family_id,
            category="distribution",
            output_shape="crosstab" if family_id == QueryFamilyId.CROSSTAB else "table",
            dimensions=(
                (2, 4)
                if family_id == QueryFamilyId.CROSSTAB
                else (1, 1)
                if family_id
                in {
                    QueryFamilyId.SINGLE_DISTRIBUTION,
                    QueryFamilyId.HISTOGRAM,
                }
                else (1, 4)
                if family_id == QueryFamilyId.SHARE
                else (2, 4)
                if family_id
                in {
                    QueryFamilyId.MULTIDIM_BREAKDOWN,
                    QueryFamilyId.TOP_N_WITHIN_PARENT,
                }
                else (1, 4)
            ),
            windows=family_id
            in {
                QueryFamilyId.SHARE,
            },
            required_metrics=(
                frozenset({MetricOperator.ISSUE_COUNT})
                if family_id
                in {
                    QueryFamilyId.MULTIDIM_BREAKDOWN,
                    QueryFamilyId.CROSSTAB,
                    QueryFamilyId.HISTOGRAM,
                }
                else frozenset()
            ),
        )
        for family_id in distribution_ids
    )

    time_ids = (
        QueryFamilyId.TIME_SERIES,
        QueryFamilyId.PERIOD_COMPARE,
        QueryFamilyId.ABSOLUTE_CHANGE,
        QueryFamilyId.RATE_CHANGE,
        QueryFamilyId.YOY_MOM,
        QueryFamilyId.ROLLING,
        QueryFamilyId.CUMULATIVE,
        QueryFamilyId.FIRST_LAST,
        QueryFamilyId.EMERGING_DECLINING_SPIKE,
    )
    time = tuple(
        _descriptor(
            family_id,
            category="time",
            execution_kind=(
                FamilyExecutionKind.GENERATED
                if family_id == QueryFamilyId.EMERGING_DECLINING_SPIKE
                else FamilyExecutionKind.AGGREGATE
            ),
            output_shape=(
                "table"
                if family_id
                in {
                    QueryFamilyId.PERIOD_COMPARE,
                    QueryFamilyId.FIRST_LAST,
                }
                else "time_series"
            ),
            dimensions=(
                (0, 3)
                if family_id == QueryFamilyId.FIRST_LAST
                else (0, 4)
                if family_id == QueryFamilyId.PERIOD_COMPARE
                else (1, 4)
            ),
            metrics=(
                frozenset({MetricOperator.MIN, MetricOperator.MAX})
                if family_id == QueryFamilyId.FIRST_LAST
                else ALL_METRICS
            ),
            time=family_id
            not in {
                QueryFamilyId.FIRST_LAST,
                QueryFamilyId.PERIOD_COMPARE,
            },
            comparisons=family_id
            in {
                QueryFamilyId.PERIOD_COMPARE,
            },
            windows=family_id
            not in {
                QueryFamilyId.FIRST_LAST,
                QueryFamilyId.EMERGING_DECLINING_SPIKE,
            },
            required_windows=(
                frozenset({WindowOperator.ABSOLUTE_CHANGE})
                if family_id == QueryFamilyId.ABSOLUTE_CHANGE
                else frozenset({WindowOperator.RATE_CHANGE})
                if family_id == QueryFamilyId.RATE_CHANGE
                else frozenset({WindowOperator.CUMULATIVE_SUM})
                if family_id == QueryFamilyId.CUMULATIVE
                else frozenset()
            ),
            min_comparisons=2 if family_id == QueryFamilyId.PERIOD_COMPARE else 0,
        )
        for family_id in time_ids
    )

    comparison_ids = (
        QueryFamilyId.COHORT_COMPARE,
        QueryFamilyId.BENCHMARK,
        QueryFamilyId.BEFORE_AFTER,
        QueryFamilyId.MIX_SHIFT,
        QueryFamilyId.RANK_SHIFT,
        QueryFamilyId.CONTRIBUTION_CHANGE,
        QueryFamilyId.OVERLAP_INTERSECTION_EXCLUSIVE,
    )
    comparison = tuple(
        _descriptor(
            family_id,
            category="comparison",
            execution_kind=(
                FamilyExecutionKind.GENERATED
                if family_id
                in {
                    QueryFamilyId.MIX_SHIFT,
                    QueryFamilyId.RANK_SHIFT,
                    QueryFamilyId.CONTRIBUTION_CHANGE,
                    QueryFamilyId.OVERLAP_INTERSECTION_EXCLUSIVE,
                }
                else FamilyExecutionKind.AGGREGATE
            ),
            dimensions=(0, 4),
            comparisons=family_id
            not in {
                QueryFamilyId.MIX_SHIFT,
                QueryFamilyId.RANK_SHIFT,
                QueryFamilyId.CONTRIBUTION_CHANGE,
                QueryFamilyId.OVERLAP_INTERSECTION_EXCLUSIVE,
            },
            windows=family_id
            not in {
                QueryFamilyId.MIX_SHIFT,
                QueryFamilyId.RANK_SHIFT,
                QueryFamilyId.CONTRIBUTION_CHANGE,
                QueryFamilyId.OVERLAP_INTERSECTION_EXCLUSIVE,
            },
            min_comparisons=(
                2
                if family_id
                in {
                    QueryFamilyId.COHORT_COMPARE,
                    QueryFamilyId.BENCHMARK,
                    QueryFamilyId.BEFORE_AFTER,
                }
                else 0
            ),
        )
        for family_id in comparison_ids
    )

    association_ids = (
        QueryFamilyId.PARETO,
        QueryFamilyId.CONCENTRATION,
        QueryFamilyId.CONDITIONAL_RATE,
        QueryFamilyId.CATEGORICAL_ASSOCIATION,
        QueryFamilyId.SYMPTOM_CAUSE,
        QueryFamilyId.CAUSE_COUNTERMEASURE,
        QueryFamilyId.SUPPLIER_PART_PROCESS,
    )
    association = tuple(
        _descriptor(
            family_id,
            category="association",
            execution_kind=(
                FamilyExecutionKind.GENERATED
                if family_id
                in {
                    QueryFamilyId.CONCENTRATION,
                }
                else FamilyExecutionKind.AGGREGATE
            ),
            dimensions=(
                (2, 4)
                if family_id
                in {
                    QueryFamilyId.CATEGORICAL_ASSOCIATION,
                    QueryFamilyId.SYMPTOM_CAUSE,
                    QueryFamilyId.CAUSE_COUNTERMEASURE,
                }
                else (1, 4)
            ),
            windows=family_id not in {QueryFamilyId.PARETO, QueryFamilyId.CONCENTRATION},
            required_metrics=(
                frozenset({MetricOperator.CONDITIONAL_RATE})
                if family_id == QueryFamilyId.CONDITIONAL_RATE
                else frozenset()
            ),
        )
        for family_id in association_ids
    )

    quality_ids = (
        QueryFamilyId.SEVERITY,
        QueryFamilyId.APPLIED_BACKLOG,
        QueryFamilyId.MASTER_STATUS,
        QueryFamilyId.EVIDENCE_COVERAGE,
        QueryFamilyId.COMPLETENESS,
        QueryFamilyId.INVALID_VALUES,
        QueryFamilyId.DUPLICATE_NORMALIZATION_STALE,
    )
    quality = tuple(
        _descriptor(
            family_id,
            category="quality",
            execution_kind=(
                FamilyExecutionKind.METADATA
                if family_id
                in {
                    QueryFamilyId.EVIDENCE_COVERAGE,
                    QueryFamilyId.INVALID_VALUES,
                }
                else FamilyExecutionKind.GENERATED
                if family_id == QueryFamilyId.DUPLICATE_NORMALIZATION_STALE
                else FamilyExecutionKind.AGGREGATE
            ),
            dimensions=(
                (1, 4)
                if family_id
                in {
                    QueryFamilyId.INVALID_VALUES,
                    QueryFamilyId.SEVERITY,
                    QueryFamilyId.APPLIED_BACKLOG,
                    QueryFamilyId.MASTER_STATUS,
                }
                else (0, 4)
            ),
            comparisons=family_id
            not in {
                QueryFamilyId.EVIDENCE_COVERAGE,
                QueryFamilyId.INVALID_VALUES,
                QueryFamilyId.DUPLICATE_NORMALIZATION_STALE,
            },
            windows=family_id
            not in {
                QueryFamilyId.EVIDENCE_COVERAGE,
                QueryFamilyId.INVALID_VALUES,
                QueryFamilyId.DUPLICATE_NORMALIZATION_STALE,
            },
        )
        for family_id in quality_ids
    )

    detail = (
        _descriptor(
            QueryFamilyId.DETAIL_LIST,
            category="detail",
            execution_kind=FamilyExecutionKind.DETAIL,
            output_shape="detail",
            dimensions=(0, 4),
            metrics=COUNT_METRICS,
            audiences=("practitioner",),
        ),
        _descriptor(
            QueryFamilyId.GROUP_DRILLDOWN,
            category="detail",
            execution_kind=FamilyExecutionKind.DETAIL,
            output_shape="detail",
            dimensions=(1, 4),
            metrics=COUNT_METRICS,
            requires_filters=True,
            requires_detail_fields=True,
            audiences=("practitioner",),
        ),
        _descriptor(
            QueryFamilyId.REPRESENTATIVE_RECORDS,
            category="detail",
            execution_kind=FamilyExecutionKind.SEMANTIC,
            output_shape="evidence",
            dimensions=(0, 4),
            metrics=COUNT_METRICS,
        ),
        _descriptor(
            QueryFamilyId.SEMANTIC_SIMILAR,
            category="semantic",
            execution_kind=FamilyExecutionKind.SEMANTIC,
            output_shape="evidence",
            dimensions=(0, 4),
            metrics=COUNT_METRICS,
        ),
        _descriptor(
            QueryFamilyId.EXACT_AGGREGATE_PLUS_SEMANTIC,
            category="hybrid",
            execution_kind=FamilyExecutionKind.HYBRID,
            output_shape="hybrid",
            dimensions=(0, 4),
        ),
        _descriptor(
            QueryFamilyId.ATTACHMENT_EVIDENCE,
            category="semantic",
            execution_kind=FamilyExecutionKind.SEMANTIC,
            output_shape="evidence",
            dimensions=(0, 4),
            metrics=COUNT_METRICS,
        ),
    )

    composite_ids = (
        QueryFamilyId.EXECUTIVE_SCORECARD,
        QueryFamilyId.EXECUTIVE_BRIEFING,
        QueryFamilyId.PRACTITIONER_INVESTIGATION,
        QueryFamilyId.MULTI_SCOPE_MATRIX,
        QueryFamilyId.ISSUE_CAUSE_COUNTERMEASURE_REVIEW,
        QueryFamilyId.CONTEXTUAL_FOLLOWUP,
    )
    composite = tuple(
        _descriptor(
            family_id,
            category="composite",
            execution_kind=FamilyExecutionKind.COMPOSITE,
            output_shape="report",
            dimensions=(0, 4),
            comparisons=True,
            windows=True,
            audiences=(
                ("practitioner",)
                if family_id == QueryFamilyId.PRACTITIONER_INVESTIGATION
                else ("executive", "practitioner")
            ),
        )
        for family_id in composite_ids
    )
    generated = (
        _descriptor(
            QueryFamilyId.GENERATED_SQL_FALLBACK,
            category="generated",
            execution_kind=FamilyExecutionKind.GENERATED,
            output_shape="table",
            dimensions=(0, 4),
        ),
    )
    return (
        *metadata,
        *scalar,
        *distribution,
        *time,
        *comparison,
        *association,
        *quality,
        *detail,
        *composite,
        *generated,
    )


def compile_analysis_catalog() -> Mapping[tuple[QueryFamilyId, int], QueryFamilyDescriptor]:
    descriptors = _build_descriptors()
    if len(descriptors) != EXPECTED_QUERY_FAMILY_COUNT:
        raise AnalysisCatalogError(
            f"analysis catalog must contain {EXPECTED_QUERY_FAMILY_COUNT} families"
        )
    compiled: dict[tuple[QueryFamilyId, int], QueryFamilyDescriptor] = {}
    for descriptor in descriptors:
        key = (descriptor.family_id, descriptor.version)
        if key in compiled:
            raise AnalysisCatalogError(f"duplicate analysis family: {descriptor.ref}")
        if descriptor.version < 1:
            raise AnalysisCatalogError(f"invalid analysis family version: {descriptor.ref}")
        if not 0 <= descriptor.min_dimensions <= descriptor.max_dimensions <= 4:
            raise AnalysisCatalogError(f"invalid dimension range: {descriptor.ref}")
        if not descriptor.allowed_metrics:
            raise AnalysisCatalogError(f"analysis family has no metrics: {descriptor.ref}")
        if not descriptor.required_metrics.issubset(descriptor.allowed_metrics):
            raise AnalysisCatalogError(
                f"analysis family requires disallowed metrics: {descriptor.ref}"
            )
        if descriptor.required_windows and not descriptor.supports_windows:
            raise AnalysisCatalogError(
                f"analysis family requires unsupported windows: {descriptor.ref}"
            )
        if descriptor.min_comparisons and not descriptor.supports_comparisons:
            raise AnalysisCatalogError(
                f"analysis family requires unsupported comparisons: {descriptor.ref}"
            )
        if not descriptor.purpose or not descriptor.recipe:
            raise AnalysisCatalogError(f"analysis family guidance is missing: {descriptor.ref}")
        compiled[key] = descriptor
    registered_ids = {family_id for family_id, version in compiled if version == CATALOG_VERSION}
    if registered_ids != set(QueryFamilyId):
        missing = sorted(family.value for family in set(QueryFamilyId).difference(registered_ids))
        extra = sorted(family.value for family in registered_ids.difference(set(QueryFamilyId)))
        raise AnalysisCatalogError(f"analysis family mismatch: missing={missing}, extra={extra}")
    return MappingProxyType(compiled)


QUERY_FAMILY_CATALOG = compile_analysis_catalog()


def analysis_catalog_payload(
    *,
    fields: Iterable[DatasetFieldDefinition],
    detailed_family_ids: Iterable[QueryFamilyId] | None = None,
    compact: bool = False,
) -> dict[str, object]:
    """Return the compact, data-free planner contract for the active catalog."""

    field_catalog = build_analysis_field_catalog(fields)
    descriptors = tuple(QUERY_FAMILY_CATALOG.values())
    if detailed_family_ids is None:
        detailed_ids = {descriptor.family_id for descriptor in descriptors}
    else:
        detailed_ids = set(detailed_family_ids)
    details = [
        _family_detail_payload(descriptor)
        for descriptor in descriptors
        if descriptor.family_id in detailed_ids
    ]
    field_payload = [
        _field_payload(capabilities, compact=compact) for capabilities in field_catalog.values()
    ]
    if not compact:
        return {
            "version": CATALOG_VERSION,
            "data_sources": _data_source_payload(),
            "families": details,
            "fields": field_payload,
        }

    capability_profiles: dict[
        tuple[str, bool, tuple[str, ...], tuple[str, ...], bool, bool],
        dict[str, object],
    ] = {}
    for capabilities in field_catalog.values():
        profile_key = (
            capabilities.field.field_type,
            capabilities.field.allow_multiple,
            tuple(sorted(operator.value for operator in capabilities.filter_operators)),
            tuple(sorted(operator.value for operator in capabilities.metric_operators)),
            capabilities.time_bucketable,
            capabilities.numeric_bucketable,
        )
        capability_profiles.setdefault(
            profile_key,
            {
                "type": capabilities.field.field_type,
                "allow_multiple": capabilities.field.allow_multiple,
                "filters": list(profile_key[2]),
                "metrics": list(profile_key[3]),
                "time_bucketable": capabilities.time_bucketable,
                "numeric_bucketable": capabilities.numeric_bucketable,
            },
        )
    return {
        "version": CATALOG_VERSION,
        "data_sources": _data_source_payload(),
        "family_index": [
            {
                "id": descriptor.family_id.value,
                "version": descriptor.version,
                "category": descriptor.category,
                "execution_kind": descriptor.execution_kind.value,
                "purpose": descriptor.purpose,
            }
            for descriptor in descriptors
        ],
        "family_details": details,
        "field_rules": list(capability_profiles.values()),
        "fields": field_payload,
    }


def _data_source_payload() -> list[dict[str, object]]:
    return [
        {
            "id": AnalysisDataSource.LEGACY_ISSUES.value,
            "purpose": "과거차 문제점 마스터의 유효 리비전 레코드",
            "counting_unit": "문제점 레코드",
        },
        {
            "id": AnalysisDataSource.VEHICLE_CHECKLISTS.value,
            "purpose": ("차량·모듈별 최신 체크리스트의 독립 수정값과 진행 상태"),
            "counting_unit": (
                "issue_count는 체크리스트 항목; 체크리스트 수는 checklist_id distinct_count"
            ),
            "counting_units": [
                {
                    "id": "checklist_items",
                    "metric": "issue_count",
                    "entity": "최신 체크리스트 안의 항목 행",
                },
                {
                    "id": "checklists",
                    "metric": "distinct_count(checklist_id)",
                    "entity": "차량·모듈별 최신 체크리스트 문서",
                },
            ],
            "metadata_fields": [
                "checklist_id",
                "checklist_vehicle_code",
                "checklist_vehicle_name",
                "checklist_status",
                "checklist_module",
                "checklist_source_revision_no",
                "checklist_updated_date",
            ],
        },
    ]


def _family_detail_payload(descriptor: QueryFamilyDescriptor) -> dict[str, object]:
    return {
        "id": descriptor.family_id.value,
        "version": descriptor.version,
        "category": descriptor.category,
        "execution_kind": descriptor.execution_kind.value,
        "shape": descriptor.output_shape,
        "purpose": descriptor.purpose,
        "recipe": descriptor.recipe,
        "dimensions": {
            "min": descriptor.min_dimensions,
            "max": descriptor.max_dimensions,
            "requires_time": descriptor.requires_time_dimension,
        },
        "metrics": sorted(metric.value for metric in descriptor.allowed_metrics),
        "supports_comparisons": descriptor.supports_comparisons,
        "supports_windows": descriptor.supports_windows,
        "requirements": {
            "metrics": sorted(metric.value for metric in descriptor.required_metrics),
            "windows": sorted(window.value for window in descriptor.required_windows),
            "min_comparisons": descriptor.min_comparisons,
            "filters": descriptor.requires_filters,
            "detail_fields": descriptor.requires_detail_fields,
        },
        "audiences": list(descriptor.audiences),
    }


def _field_payload(
    capabilities: AnalysisFieldCapabilities,
    *,
    compact: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "key": capabilities.field.key,
        "label_ko": capabilities.field.label_ko,
        "label_en": capabilities.field.label_en,
        "aliases": list(capabilities.field.aliases),
        "group_key": capabilities.field.group_key,
        "type": capabilities.field.field_type,
        "allow_multiple": capabilities.field.allow_multiple,
        "options": list(capabilities.field.options),
        "source": capabilities.field.source,
        "module_key": capabilities.field.module_key,
    }
    if not compact:
        payload.update(
            {
                "filters": sorted(operator.value for operator in capabilities.filter_operators),
                "metrics": sorted(operator.value for operator in capabilities.metric_operators),
                "time_bucketable": capabilities.time_bucketable,
                "numeric_bucketable": capabilities.numeric_bucketable,
            }
        )
    return payload


def get_query_family_descriptor(
    family_id: QueryFamilyId,
    version: int = CATALOG_VERSION,
) -> QueryFamilyDescriptor:
    try:
        return QUERY_FAMILY_CATALOG[(family_id, version)]
    except KeyError as error:
        raise AnalysisCatalogError(
            f"unknown analysis family: {family_id.value}@{version}"
        ) from error


__all__ = [
    "AnalysisCatalogError",
    "AnalysisFieldCapabilities",
    "CATALOG_VERSION",
    "EXPECTED_QUERY_FAMILY_COUNT",
    "FamilyExecutionKind",
    "QUERY_FAMILY_CATALOG",
    "QueryFamilyDescriptor",
    "analysis_catalog_payload",
    "build_analysis_field_catalog",
    "compile_analysis_catalog",
    "field_capabilities",
    "get_query_family_descriptor",
    "validate_query_request",
]
