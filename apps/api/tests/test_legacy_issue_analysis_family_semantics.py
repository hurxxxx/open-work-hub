from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from ai_do_api.core.db import Base
from ai_do_api.domains.auth.models import OrgUnit, User, Workspace
from ai_do_api.domains.legacy_issues.analysis_catalog import (
    AnalysisCatalogError,
    FamilyExecutionKind,
    QUERY_FAMILY_CATALOG,
    build_analysis_field_catalog,
    validate_query_request,
)
from ai_do_api.domains.legacy_issues import analysis_sql
from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisMode,
    AnalysisPlanV1,
    AnalysisScopeV1,
    ComparisonSpecV1,
    DimensionSpecV1,
    FilterConditionV1,
    FilterGroupV1,
    FilterOperator,
    MetricOperator,
    MetricSpecV1,
    QueryFamilyId,
    QueryRequestV1,
    RecordSetSpecV1,
    SortDirection,
    SortSpecV1,
    TimeGrain,
    ValueMatchMode,
    WindowOperator,
    WindowSpecV1,
)
from ai_do_api.domains.legacy_issues.analysis_sql import (
    compile_analysis_query,
    execute_analysis_query,
)
from ai_do_api.domains.legacy_issues.dataset_records import (
    COMMON_MASTER_DATASET_KEY,
    COMMON_MASTER_FIELDS,
)
from ai_do_api.domains.legacy_issues.models import (
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from ai_do_api.domains.retrieval.models import RetrievalPartition


FIELDS = build_analysis_field_catalog(COMMON_MASTER_FIELDS)


def _condition(
    field_key: str,
    value: str,
    *,
    operator: FilterOperator = FilterOperator.EQ,
) -> FilterGroupV1:
    return FilterGroupV1(
        conditions=(
            FilterConditionV1(
                field_key=field_key,
                operator=operator,
                value=value,
            ),
        ),
    )


def _date_comparison(key: str, label: str, lower: str, upper: str) -> ComparisonSpecV1:
    return ComparisonSpecV1(
        key=key,
        label=label,
        filters=FilterGroupV1(
            conditions=(
                FilterConditionV1(
                    field_key="occurrence_date",
                    operator=FilterOperator.BETWEEN,
                    values=(lower, upper),
                ),
            ),
        ),
    )


@pytest.mark.parametrize(
    ("query_request", "message"),
    [
        pytest.param(
            QueryRequestV1(
                query_id="total-with-filter",
                family_id=QueryFamilyId.TOTAL_COUNT,
                filters=_condition("region_zone", "한국"),
            ),
            "total_count does not accept filters",
            id="total-count-with-filter",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="filtered-without-filter",
                family_id=QueryFamilyId.FILTERED_COUNT,
            ),
            "requires filters",
            id="filtered-count-without-filter",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="distinct-with-count",
                family_id=QueryFamilyId.DISTINCT_COUNT,
            ),
            "distinct_count requires exactly one distinct_count metric",
            id="distinct-count-wrong-metric",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="date-range-without-max",
                family_id=QueryFamilyId.DATE_RANGE_COVERAGE,
                metrics=(
                    MetricSpecV1(
                        operator=MetricOperator.MIN,
                        field_key="occurrence_date",
                        alias="first_date",
                    ),
                ),
            ),
            "requires metrics",
            id="date-range-missing-min-max-pair",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="histogram-without-bucket",
                family_id=QueryFamilyId.HISTOGRAM,
                dimensions=(DimensionSpecV1(field_key="introduced_revision_no"),),
            ),
            "histogram requires numeric_bucket_size",
            id="histogram-without-bucket",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="period-with-one-comparison",
                family_id=QueryFamilyId.PERIOD_COMPARE,
                comparisons=(
                    _date_comparison(
                        "current",
                        "현재",
                        "2025-01-01",
                        "2025-01-31",
                    ),
                ),
            ),
            "requires at least 2 comparisons",
            id="period-compare-with-one-comparison",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="period-without-date",
                family_id=QueryFamilyId.PERIOD_COMPARE,
                comparisons=(
                    ComparisonSpecV1(
                        key="korea",
                        label="한국",
                        filters=_condition("region_zone", "한국"),
                    ),
                    ComparisonSpecV1(
                        key="europe",
                        label="유럽",
                        filters=_condition("region_zone", "유럽"),
                    ),
                ),
            ),
            "requires date comparison filters",
            id="period-compare-without-date-filter",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="rolling-without-window",
                family_id=QueryFamilyId.ROLLING,
                dimensions=(
                    DimensionSpecV1(
                        field_key="occurrence_date",
                        alias="month",
                        time_grain=TimeGrain.MONTH,
                    ),
                ),
            ),
            "rolling requires a moving window",
            id="rolling-without-moving-window",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="cumulative-without-window",
                family_id=QueryFamilyId.CUMULATIVE,
                dimensions=(
                    DimensionSpecV1(
                        field_key="occurrence_date",
                        alias="month",
                        time_grain=TimeGrain.MONTH,
                    ),
                ),
            ),
            "requires windows",
            id="cumulative-without-cumulative-window",
        ),
        pytest.param(
            QueryRequestV1(
                query_id="ambiguous-rank-metric",
                family_id=QueryFamilyId.TOP_BOTTOM_N,
                dimensions=(DimensionSpecV1(field_key="vehicle_model"),),
                metrics=(
                    MetricSpecV1(alias="record_count"),
                    MetricSpecV1(
                        operator=MetricOperator.DISTINCT_COUNT,
                        field_key="issue_type",
                        alias="type_count",
                    ),
                ),
            ),
            "requires exactly one ranking metric",
            id="top-n-with-ambiguous-rank-metric",
        ),
    ],
)
def test_family_recipe_validation_rejects_invalid_requests(
    query_request: QueryRequestV1,
    message: str,
) -> None:
    with pytest.raises(AnalysisCatalogError, match=message):
        validate_query_request(query_request, fields=FIELDS)


def test_exact_aggregate_plus_semantic_is_only_valid_in_hybrid_mode() -> None:
    request = QueryRequestV1(
        query_id="exact-and-semantic",
        family_id=QueryFamilyId.EXACT_AGGREGATE_PLUS_SEMANTIC,
    )

    for mode in (AnalysisMode.ANALYTICS, AnalysisMode.METADATA):
        with pytest.raises(ValidationError, match="requires hybrid mode"):
            AnalysisPlanV1(mode=mode, queries=(request,))

    plan = AnalysisPlanV1(mode=AnalysisMode.HYBRID, queries=(request,))
    assert plan.queries == (request,)


def test_generated_families_are_delegated_instead_of_catalog_executed() -> None:
    generated_family_ids = {
        family_id
        for (family_id, version), descriptor in QUERY_FAMILY_CATALOG.items()
        if version == 1 and descriptor.execution_kind == FamilyExecutionKind.GENERATED
    }

    assert generated_family_ids
    for family_id in generated_family_ids:
        request = QueryRequestV1(
            query_id=f"invalid-{family_id.value}",
            family_id=family_id,
        )
        with pytest.raises(
            ValidationError,
            match="catalog execution modes do not accept delegated query families",
        ):
            AnalysisPlanV1(mode=AnalysisMode.ANALYTICS, queries=(request,))

        delegated = AnalysisPlanV1(
            mode=AnalysisMode.GENERATED,
            delegated_family_id=family_id,
        )
        assert delegated.delegated_family_id == family_id


def test_family_recipe_validation_accepts_valid_catalog_plans() -> None:
    requests = (
        QueryRequestV1(
            query_id="total",
            family_id=QueryFamilyId.TOTAL_COUNT,
        ),
        QueryRequestV1(
            query_id="filtered",
            family_id=QueryFamilyId.FILTERED_COUNT,
            filters=_condition("region_zone", "한국"),
        ),
        QueryRequestV1(
            query_id="distinct-models",
            family_id=QueryFamilyId.DISTINCT_COUNT,
            metrics=(
                MetricSpecV1(
                    operator=MetricOperator.DISTINCT_COUNT,
                    field_key="vehicle_model",
                    alias="model_count",
                ),
            ),
        ),
        QueryRequestV1(
            query_id="date-range",
            family_id=QueryFamilyId.DATE_RANGE_COVERAGE,
            metrics=(
                MetricSpecV1(
                    operator=MetricOperator.MIN,
                    field_key="occurrence_date",
                    alias="first_date",
                ),
                MetricSpecV1(
                    operator=MetricOperator.MAX,
                    field_key="occurrence_date",
                    alias="last_date",
                ),
            ),
        ),
        QueryRequestV1(
            query_id="revision-histogram",
            family_id=QueryFamilyId.HISTOGRAM,
            dimensions=(
                DimensionSpecV1(
                    field_key="introduced_revision_no",
                    numeric_bucket_size=1,
                ),
            ),
        ),
        QueryRequestV1(
            query_id="periods",
            family_id=QueryFamilyId.PERIOD_COMPARE,
            comparisons=(
                _date_comparison(
                    "previous",
                    "이전",
                    "2024-01-01",
                    "2024-12-31",
                ),
                _date_comparison(
                    "current",
                    "현재",
                    "2025-01-01",
                    "2025-12-31",
                ),
            ),
        ),
        QueryRequestV1(
            query_id="rolling",
            family_id=QueryFamilyId.ROLLING,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="month",
                    time_grain=TimeGrain.MONTH,
                ),
            ),
            windows=(
                WindowSpecV1(
                    operator=WindowOperator.MOVING_AVERAGE,
                    metric_alias="issue_count",
                    alias="moving_average",
                    preceding=3,
                ),
            ),
        ),
        QueryRequestV1(
            query_id="cumulative",
            family_id=QueryFamilyId.CUMULATIVE,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="month",
                    time_grain=TimeGrain.MONTH,
                ),
            ),
            windows=(
                WindowSpecV1(
                    operator=WindowOperator.CUMULATIVE_SUM,
                    metric_alias="issue_count",
                    alias="cumulative_count",
                ),
            ),
        ),
    )

    for request in requests:
        descriptor = validate_query_request(request, fields=FIELDS)
        plan = AnalysisPlanV1(mode=AnalysisMode.ANALYTICS, queries=(request,))
        assert descriptor.family_id == request.family_id
        assert plan.queries == (request,)


@pytest.fixture
def family_db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            OrgUnit.__table__,
            Workspace.__table__,
            User.__table__,
            RetrievalPartition.__table__,
            LegacyIssueDataRevision.__table__,
            LegacyIssueRecord.__table__,
        ],
    )
    with Session(engine) as session:
        rows = (
            ("서울", "A", "2025-03-05", "유형-A", "원인"),
            ("서울", "A", "2025-01-05", "유형-A", "원인"),
            ("서울", "A", "2025-02-05", "유형-A", "원인"),
            ("서울", "B", "2025-01-15", "유형-A", "원인"),
            ("부산", "C", "2025-03-15", "유형-A", "원인"),
            ("부산", "C", "2025-02-15", "유형-B", "원인"),
            ("부산", "D", "2025-01-25", "유형-B", None),
            ("유럽", "E", "2025-03-25", "유형-B", None),
            ("유럽", "E", "2025-02-25", "유형-C", None),
            ("유럽", "F", "2025-01-30", "유형-C", None),
        )
        session.add_all(
            LegacyIssueRecord(
                id=f"family-record-{index}",
                workspace_id="family-workspace",
                dataset_key=COMMON_MASTER_DATASET_KEY,
                module_key="aircon",
                revision_id="family-revision",
                stable_record_id=f"family-stable-{index}",
                field_values={
                    "region_zone": region,
                    "vehicle_model": vehicle_model,
                    "occurrence_date": occurrence_date,
                    "issue_type": issue_type,
                    "cause": cause,
                },
            )
            for index, (region, vehicle_model, occurrence_date, issue_type, cause) in enumerate(
                rows,
                start=1,
            )
        )
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def family_scope() -> AnalysisScopeV1:
    return AnalysisScopeV1(
        workspace_id="family-workspace",
        module_keys=("aircon",),
        revision_ids=("family-revision",),
        revision_by_module={"aircon": "family-revision"},
        retrieval_partition_ids=(),
        source_count=10,
    )


def test_time_series_defaults_to_chronological_order(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="monthly",
            family_id=QueryFamilyId.TIME_SERIES,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="month",
                    time_grain=TimeGrain.MONTH,
                ),
            ),
        ),
        scope=family_scope,
    )

    assert [row["month"] for row in result.rows] == [
        "2025-01",
        "2025-02",
        "2025-03",
    ]
    assert [row["issue_count"] for row in result.rows] == [4, 3, 3]


def test_time_series_limit_does_not_drop_later_time_buckets(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    family_db.add_all(
        LegacyIssueRecord(
            id=f"long-series-record-{year}",
            workspace_id="family-workspace",
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id="family-revision",
            stable_record_id=f"long-series-stable-{year}",
            field_values={
                "region_zone": "서울",
                "vehicle_model": "A",
                "occurrence_date": f"{year}-01-01",
                "issue_type": "유형-A",
                "cause": "원인",
            },
        )
        for year in range(2010, 2022)
    )
    family_db.commit()

    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="yearly",
            family_id=QueryFamilyId.TIME_SERIES,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="year",
                    time_grain=TimeGrain.YEAR,
                ),
            ),
            limit=10,
        ),
        scope=family_scope,
    )

    assert [row["year"] for row in result.rows] == [
        *(str(year) for year in range(2010, 2022)),
        "2025",
    ]
    assert result.truncated is False


def test_time_series_chronological_sort_keeps_full_default_range(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    family_db.add_all(
        LegacyIssueRecord(
            id=f"sorted-series-record-{year}",
            workspace_id="family-workspace",
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id="family-revision",
            stable_record_id=f"sorted-series-stable-{year}",
            field_values={
                "region_zone": "서울",
                "vehicle_model": "A",
                "occurrence_date": f"{year}-01-01",
                "issue_type": "유형-A",
                "cause": "원인",
            },
        )
        for year in range(2010, 2022)
    )
    family_db.commit()

    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="yearly",
            family_id=QueryFamilyId.TIME_SERIES,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="year",
                    time_grain=TimeGrain.YEAR,
                ),
            ),
            sort=(SortSpecV1(key="year", direction=SortDirection.ASC),),
        ),
        scope=family_scope,
    )

    assert [row["year"] for row in result.rows] == [
        *(str(year) for year in range(2010, 2022)),
        "2025",
    ]
    assert result.truncated is False


def test_time_series_explicit_time_sort_applies_latest_n_limit(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    family_db.add_all(
        LegacyIssueRecord(
            id=f"latest-series-record-{year}",
            workspace_id="family-workspace",
            dataset_key=COMMON_MASTER_DATASET_KEY,
            module_key="aircon",
            revision_id="family-revision",
            stable_record_id=f"latest-series-stable-{year}",
            field_values={
                "region_zone": "서울",
                "vehicle_model": "A",
                "occurrence_date": f"{year}-01-01",
                "issue_type": "유형-A",
                "cause": "원인",
            },
        )
        for year in range(2010, 2022)
    )
    family_db.commit()

    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="latest-years",
            family_id=QueryFamilyId.TIME_SERIES,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="year",
                    time_grain=TimeGrain.YEAR,
                ),
            ),
            sort=(SortSpecV1(key="year", direction=SortDirection.DESC),),
            limit=10,
        ),
        scope=family_scope,
    )

    assert [row["year"] for row in result.rows] == [
        "2025",
        "2021",
        "2020",
        "2019",
        "2018",
        "2017",
        "2016",
        "2015",
        "2014",
        "2013",
    ]
    assert result.truncated is True


def test_time_series_hard_cap_preserves_latest_buckets_in_chronological_order(
    monkeypatch: pytest.MonkeyPatch,
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    family_db.add_all(
        (
            LegacyIssueRecord(
                id="hard-cap-april",
                workspace_id="family-workspace",
                dataset_key=COMMON_MASTER_DATASET_KEY,
                module_key="aircon",
                revision_id="family-revision",
                stable_record_id="hard-cap-april",
                field_values={"occurrence_date": "2025-04-01"},
            ),
            LegacyIssueRecord(
                id="hard-cap-may",
                workspace_id="family-workspace",
                dataset_key=COMMON_MASTER_DATASET_KEY,
                module_key="aircon",
                revision_id="family-revision",
                stable_record_id="hard-cap-may",
                field_values={"occurrence_date": "2025-05-01"},
            ),
        )
    )
    family_db.commit()
    monkeypatch.setattr(analysis_sql, "AGGREGATE_RESULT_LIMIT", 3)

    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="bounded-months",
            family_id=QueryFamilyId.TIME_SERIES,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="month",
                    time_grain=TimeGrain.MONTH,
                ),
            ),
        ),
        scope=family_scope,
    )

    assert [row["month"] for row in result.rows] == [
        "2025-03",
        "2025-04",
        "2025-05",
    ]
    assert result.truncated is True


def test_filtered_distribution_reports_query_population_and_filtered_coverage(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="january-regions",
            family_id=QueryFamilyId.SINGLE_DISTRIBUTION,
            dimensions=(DimensionSpecV1(field_key="region_zone"),),
            filters=FilterGroupV1(
                conditions=(
                    FilterConditionV1(
                        field_key="occurrence_date",
                        operator=FilterOperator.BETWEEN,
                        values=("2025-01-01", "2025-01-31"),
                    ),
                ),
            ),
        ),
        scope=family_scope,
    )

    assert result.scope.source_count == 10
    assert result.totals["population_count"] == 4
    coverage_by_field = {item.field_key: item for item in result.coverage}
    assert coverage_by_field["region_zone"].present_count == 4
    assert coverage_by_field["occurrence_date"].present_count == 4


def test_metric_alias_cannot_overwrite_canonical_population_totals() -> None:
    with pytest.raises(ValidationError, match="reserved for population metadata"):
        QueryRequestV1(
            query_id="distinct-types",
            family_id=QueryFamilyId.DISTINCT_COUNT,
            metrics=(
                MetricSpecV1(
                    operator=MetricOperator.DISTINCT_COUNT,
                    field_key="issue_type",
                    alias="source_count",
                ),
            ),
        )


def test_lag_offset_is_bound_into_compiled_sql(family_scope: AnalysisScopeV1) -> None:
    compiled = compile_analysis_query(
        QueryRequestV1(
            query_id="lagged",
            family_id=QueryFamilyId.TIME_SERIES,
            dimensions=(
                DimensionSpecV1(
                    field_key="occurrence_date",
                    alias="month",
                    time_grain=TimeGrain.MONTH,
                ),
            ),
            windows=(
                WindowSpecV1(
                    operator=WindowOperator.LAG,
                    metric_alias="issue_count",
                    alias="previous_count",
                    lag_offset=7,
                ),
            ),
        ),
        scope=family_scope,
        dialect_name="postgresql",
    )
    rendered = compiled.statement.compile(dialect=postgresql.dialect())

    assert "lag(" in str(rendered).lower()
    assert 7 in rendered.params.values()


def test_top_n_within_parent_applies_limit_per_parent(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="top-model-per-region",
            family_id=QueryFamilyId.TOP_N_WITHIN_PARENT,
            dimensions=(
                DimensionSpecV1(field_key="region_zone", alias="region"),
                DimensionSpecV1(field_key="vehicle_model", alias="model"),
            ),
            limit=1,
        ),
        scope=family_scope,
    )

    assert {
        (row["region"], row["model"], row["issue_count"], row["within_parent_rank"])
        for row in result.rows
    } == {
        ("부산", "C", 2, 1),
        ("서울", "A", 3, 1),
        ("유럽", "E", 2, 1),
    }


def test_top_n_within_parent_hard_cap_preserves_each_parent_first(
    monkeypatch: pytest.MonkeyPatch,
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    monkeypatch.setattr(analysis_sql, "AGGREGATE_RESULT_LIMIT", 3)

    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="balanced-top-models",
            family_id=QueryFamilyId.TOP_N_WITHIN_PARENT,
            dimensions=(
                DimensionSpecV1(field_key="region_zone", alias="region"),
                DimensionSpecV1(field_key="vehicle_model", alias="model"),
            ),
            limit=2,
        ),
        scope=family_scope,
    )

    assert {row["region"] for row in result.rows} == {"부산", "서울", "유럽"}
    assert {row["within_parent_rank"] for row in result.rows} == {1}
    assert result.truncated is True


def test_top_bottom_n_with_multiple_dimensions_applies_one_global_limit(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="global-region-models",
            family_id=QueryFamilyId.TOP_BOTTOM_N,
            dimensions=(
                DimensionSpecV1(field_key="region_zone", alias="region"),
                DimensionSpecV1(field_key="vehicle_model", alias="model"),
            ),
            limit=3,
        ),
        scope=family_scope,
    )

    assert result.rows == (
        {"region": "서울", "model": "A", "issue_count": 3},
        {"region": "부산", "model": "C", "issue_count": 2},
        {"region": "유럽", "model": "E", "issue_count": 2},
    )


def test_exhaustive_distribution_does_not_treat_soft_limit_as_top_n(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="all-regions",
            family_id=QueryFamilyId.SINGLE_DISTRIBUTION,
            dimensions=(DimensionSpecV1(field_key="region_zone"),),
            limit=1,
        ),
        scope=family_scope,
    )

    assert {row["region_zone"] for row in result.rows} == {"서울", "부산", "유럽"}
    assert result.truncated is False


def test_pareto_computes_ordered_and_cumulative_shares(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="issue-type-pareto",
            family_id=QueryFamilyId.PARETO,
            dimensions=(DimensionSpecV1(field_key="issue_type"),),
        ),
        scope=family_scope,
    )

    assert [row["issue_type"] for row in result.rows] == ["유형-A", "유형-B", "유형-C"]
    assert [row["issue_count"] for row in result.rows] == [5, 3, 2]
    assert [row["share"] for row in result.rows] == pytest.approx([50.0, 30.0, 20.0])
    assert [row["cumulative_share"] for row in result.rows] == pytest.approx([50.0, 80.0, 100.0])


def test_first_last_uses_min_and_max_dates_per_group(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="first-last-by-region",
            family_id=QueryFamilyId.FIRST_LAST,
            dimensions=(DimensionSpecV1(field_key="region_zone", alias="region"),),
            metrics=(
                MetricSpecV1(
                    operator=MetricOperator.MIN,
                    field_key="occurrence_date",
                    alias="first_occurrence",
                ),
                MetricSpecV1(
                    operator=MetricOperator.MAX,
                    field_key="occurrence_date",
                    alias="last_occurrence",
                ),
            ),
        ),
        scope=family_scope,
    )

    rows_by_region = {row["region"]: row for row in result.rows}
    assert rows_by_region["서울"]["first_occurrence"] == "2025-01-05"
    assert rows_by_region["서울"]["last_occurrence"] == "2025-03-05"
    assert rows_by_region["부산"]["first_occurrence"] == "2025-01-25"
    assert rows_by_region["부산"]["last_occurrence"] == "2025-03-15"
    assert rows_by_region["유럽"]["first_occurrence"] == "2025-01-30"
    assert rows_by_region["유럽"]["last_occurrence"] == "2025-03-25"


def test_missing_populated_rate_reports_counts_and_percentages(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="cause-coverage",
            family_id=QueryFamilyId.MISSING_POPULATED_RATE,
            metrics=(
                MetricSpecV1(
                    operator=MetricOperator.PRESENT_COUNT,
                    field_key="cause",
                    alias="present_count",
                ),
                MetricSpecV1(
                    operator=MetricOperator.MISSING_COUNT,
                    field_key="cause",
                    alias="missing_count",
                ),
            ),
        ),
        scope=family_scope,
    )

    assert result.rows == (
        {
            "present_count": 6,
            "missing_count": 4,
            "present_rate": pytest.approx(60.0),
            "missing_rate": pytest.approx(40.0),
        },
    )


def test_normalized_text_filter_handles_spacing_and_contains_any(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    family_db.add_all(
        (
            LegacyIssueRecord(
                id="normalized-record-1",
                workspace_id="family-workspace",
                dataset_key=COMMON_MASTER_DATASET_KEY,
                module_key="aircon",
                revision_id="family-revision",
                stable_record_id="normalized-stable-1",
                field_values={"symptom": "냉매밸브 작동 불량"},
            ),
            LegacyIssueRecord(
                id="normalized-record-2",
                workspace_id="family-workspace",
                dataset_key=COMMON_MASTER_DATASET_KEY,
                module_key="aircon",
                revision_id="family-revision",
                stable_record_id="normalized-stable-2",
                field_values={"symptom": "냉매 밸브 소음"},
            ),
            LegacyIssueRecord(
                id="normalized-record-3",
                workspace_id="family-workspace",
                dataset_key=COMMON_MASTER_DATASET_KEY,
                module_key="aircon",
                revision_id="family-revision",
                stable_record_id="normalized-stable-3",
                field_values={"symptom": "냉매 펌프 소음"},
            ),
        )
    )
    family_db.commit()

    result = execute_analysis_query(
        family_db,
        QueryRequestV1(
            query_id="normalized-symptom-count",
            family_id=QueryFamilyId.FILTERED_COUNT,
            filters=FilterGroupV1(
                conditions=(
                    FilterConditionV1(
                        field_key="symptom",
                        operator=FilterOperator.CONTAINS_ANY,
                        match_mode=ValueMatchMode.NORMALIZED,
                        values=("냉매 밸브", "압축기 밸브"),
                    ),
                ),
            ),
        ),
        scope=family_scope,
    )

    assert result.rows == ({"issue_count": 2},)


def test_cohort_reentry_analyzes_other_records_for_seed_entities(
    family_db: Session,
    family_scope: AnalysisScopeV1,
) -> None:
    request = QueryRequestV1(
        query_id="other-issues-for-seed-models",
        family_id=QueryFamilyId.SINGLE_DISTRIBUTION,
        dimensions=(DimensionSpecV1(field_key="issue_type"),),
        record_set=RecordSetSpecV1(
            key_fields=("vehicle_model",),
            seed_filters=_condition("issue_type", "유형-C"),
            exclude_seed_matches=True,
        ),
    )

    result = execute_analysis_query(
        family_db,
        request,
        scope=family_scope,
    )
    rendered = compile_analysis_query(
        request,
        scope=family_scope,
        dialect_name="postgresql",
    ).statement.compile(dialect=postgresql.dialect())

    assert result.rows == ({"issue_type": "유형-B", "issue_count": 1},)
    assert "cohort_seed_records" in str(rendered)
    assert "visible_records" in str(rendered)
    assert "유형-C" in rendered.params.values()


def test_record_set_is_orthogonal_to_filtered_count_and_rejects_total_count() -> None:
    record_set = RecordSetSpecV1(
        key_fields=("vehicle_model",),
        seed_filters=_condition("issue_type", "유형-C"),
    )
    request = QueryRequestV1(
        query_id="seed-model-record-count",
        family_id=QueryFamilyId.FILTERED_COUNT,
        record_set=record_set,
    )

    assert validate_query_request(request, fields=FIELDS).family_id == (
        QueryFamilyId.FILTERED_COUNT
    )
    with pytest.raises(AnalysisCatalogError, match="use filtered_count"):
        validate_query_request(
            QueryRequestV1(
                query_id="invalid-total",
                family_id=QueryFamilyId.TOTAL_COUNT,
                record_set=record_set,
            ),
            fields=FIELDS,
        )


def test_normalized_matching_rejects_non_text_fields() -> None:
    request = QueryRequestV1(
        query_id="invalid-normalized-number",
        family_id=QueryFamilyId.FILTERED_COUNT,
        filters=FilterGroupV1(
            conditions=(
                FilterConditionV1(
                    field_key="introduced_revision_no",
                    operator=FilterOperator.EQ,
                    match_mode=ValueMatchMode.NORMALIZED,
                    value=1,
                ),
            ),
        ),
    )

    with pytest.raises(AnalysisCatalogError, match="single-value text"):
        validate_query_request(request, fields=FIELDS)
