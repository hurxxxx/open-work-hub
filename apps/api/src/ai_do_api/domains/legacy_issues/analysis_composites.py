from __future__ import annotations

from collections.abc import Iterable

from ai_do_api.domains.legacy_issues.analysis_contracts import (
    AnalysisDataSource,
    AnalysisMode,
    AnalysisPlanV1,
    DimensionSpecV1,
    MetricOperator,
    MetricSpecV1,
    QueryFamilyId,
    QueryRequestV1,
    SortDirection,
    SortSpecV1,
    TimeGrain,
)
from ai_do_api.domains.legacy_issues.dataset_records import DatasetFieldDefinition


def build_standard_report_plan(
    *,
    fields: Iterable[DatasetFieldDefinition],
    routing_mode: AnalysisMode | None,
    data_sources: tuple[AnalysisDataSource, ...],
) -> AnalysisPlanV1 | None:
    """Expand the standard executive report into safe atomic catalog queries.

    This is the server-owned fallback for a report request when the LLM planner
    cannot produce a valid atomic plan. It intentionally uses only canonical,
    reusable fields and never creates filters or SQL from the question.
    """

    if data_sources != (AnalysisDataSource.LEGACY_ISSUES,):
        return None

    field_types = {field.key: field.field_type for field in fields if field.active}
    queries: list[QueryRequestV1] = [
        QueryRequestV1(
            query_id="report_total",
            family_id=QueryFamilyId.TOTAL_COUNT,
            metrics=(
                MetricSpecV1(
                    operator=MetricOperator.ISSUE_COUNT,
                    alias="issue_count",
                ),
            ),
        )
    ]

    if "severity_grade" in field_types:
        queries.append(
            QueryRequestV1(
                query_id="report_severity",
                family_id=QueryFamilyId.SEVERITY,
                metrics=(
                    MetricSpecV1(
                        operator=MetricOperator.ISSUE_COUNT,
                        alias="issue_count",
                    ),
                ),
                dimensions=(
                    DimensionSpecV1(
                        field_key="severity_grade",
                        alias="severity_grade",
                    ),
                ),
                sort=(
                    SortSpecV1(
                        key="issue_count",
                        direction=SortDirection.DESC,
                    ),
                ),
            )
        )

    if "vehicle_model" in field_types:
        queries.append(
            QueryRequestV1(
                query_id="report_top_vehicle_models",
                family_id=QueryFamilyId.TOP_BOTTOM_N,
                metrics=(
                    MetricSpecV1(
                        operator=MetricOperator.ISSUE_COUNT,
                        alias="issue_count",
                    ),
                ),
                dimensions=(
                    DimensionSpecV1(
                        field_key="vehicle_model",
                        alias="vehicle_model",
                    ),
                ),
                sort=(
                    SortSpecV1(
                        key="issue_count",
                        direction=SortDirection.DESC,
                    ),
                ),
                limit=10,
            )
        )

    if field_types.get("occurrence_date") == "date":
        queries.append(
            QueryRequestV1(
                query_id="report_occurrence_years",
                family_id=QueryFamilyId.TIME_SERIES,
                metrics=(
                    MetricSpecV1(
                        operator=MetricOperator.ISSUE_COUNT,
                        alias="issue_count",
                    ),
                ),
                dimensions=(
                    DimensionSpecV1(
                        field_key="occurrence_date",
                        alias="occurrence_year",
                        time_grain=TimeGrain.YEAR,
                    ),
                ),
                sort=(
                    SortSpecV1(
                        key="occurrence_year",
                        direction=SortDirection.ASC,
                    ),
                ),
            )
        )
        queries.append(_coverage_query("occurrence_date", query_id="report_date_coverage"))

    if "severity_grade" in field_types and len(queries) < 6:
        queries.append(
            _coverage_query(
                "severity_grade",
                query_id="report_severity_coverage",
            )
        )

    return AnalysisPlanV1(
        schema_version=1,
        mode=(
            AnalysisMode.HYBRID
            if routing_mode == AnalysisMode.HYBRID
            else AnalysisMode.ANALYTICS
        ),
        queries=tuple(queries[:6]),
    )


def _coverage_query(field_key: str, *, query_id: str) -> QueryRequestV1:
    return QueryRequestV1(
        query_id=query_id,
        family_id=QueryFamilyId.MISSING_POPULATED_RATE,
        metrics=(
            MetricSpecV1(
                operator=MetricOperator.PRESENT_COUNT,
                field_key=field_key,
                alias="present_count",
            ),
            MetricSpecV1(
                operator=MetricOperator.MISSING_COUNT,
                field_key=field_key,
                alias="missing_count",
            ),
        ),
    )


__all__ = ["build_standard_report_plan"]
