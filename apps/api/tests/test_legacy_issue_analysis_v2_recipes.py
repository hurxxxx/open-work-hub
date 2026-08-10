from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from ai_do_api.domains.legacy_issues.analysis_v2.contracts import (
    AnalysisRoute,
    AnalysisRouteDecision,
    FallbackReason,
)
from ai_do_api.domains.legacy_issues.analysis_v2.recipes import (
    default_recipe_catalog,
)
from ai_do_api.domains.legacy_issues.analysis_v2.sql_policy import (
    SafeSqlPolicy,
    SafeSqlPolicyError,
)
from ai_do_api.domains.legacy_issues.analysis_v2.views import (
    CHECKLIST_ITEMS_VIEW_V1,
    CHECKLISTS_VIEW_V1,
    ISSUE_RECORDS_VIEW_V1,
)


def test_default_recipe_catalog_bootstrap_validates_versioned_recipe_families() -> None:
    catalog = default_recipe_catalog()

    assert {
        recipe.recipe_id for recipe in catalog.all()
    } >= {
        "issue_total",
        "issue_breakdown",
        "issue_matrix",
        "issue_cube",
        "issue_trend",
        "issue_checklist_coverage",
    }
    assert {recipe.version for recipe in catalog.all()} == {1}
    assert {
        recipe.counting_unit for recipe in catalog.all()
    } == {"issues", "checklists", "checklist_items", "mixed"}
    assert {
        view
        for recipe in catalog.all()
        for view in recipe.source_views
    } == {
        ISSUE_RECORDS_VIEW_V1,
        CHECKLISTS_VIEW_V1,
        CHECKLIST_ITEMS_VIEW_V1,
    }


def test_recipe_parameters_are_typed_and_never_interpolated_as_values() -> None:
    rendered = default_recipe_catalog().render(
        "issue_matrix",
        1,
        {
            "row_dimension": "vehicle_model",
            "column_dimension": "region_zone",
            "date_from": "2026-01-01",
            "vehicle_models": ["A차종", "B차종"],
            "limit": 25,
        },
    )

    assert "TRIM(i.vehicle_model)" in rendered.sql
    assert "AS row_value" in rendered.sql
    assert "TRIM(i.region_zone)" in rendered.sql
    assert "AS column_value" in rendered.sql
    assert "A차종" not in rendered.sql
    assert rendered.bindings == {
        "limit": 25,
        "date_from": date(2026, 1, 1),
        "vehicle_models_0": "A차종",
        "vehicle_models_1": "B차종",
    }
    assert rendered.validated_sql.referenced_views == (ISSUE_RECORDS_VIEW_V1,)


def test_contains_filter_escapes_sql_wildcards_as_literal_text() -> None:
    rendered = default_recipe_catalog().render(
        "issue_total",
        1,
        {"query_text": r"EVA_100%\\결빙"},
    )

    assert "ESCAPE" in rendered.sql
    assert rendered.bindings["query_text"] == r"%EVA\_100\%\\\\결빙%"


def test_ranked_summary_calculates_top_n_count_and_share_in_sql() -> None:
    rendered = default_recipe_catalog().render(
        "issue_ranked_summary",
        1,
        {
            "dimension": "vehicle_model",
            "top_n": 10,
            "regions": ["테스트-국내"],
        },
    )

    assert "TRIM(i.vehicle_model)" in rendered.sql
    assert "AS dimension_value" in rendered.sql
    assert "AS total_issue_count" in rendered.sql
    assert "AS cumulative_issue_count" in rendered.sql
    assert "AS cumulative_share" in rendered.sql
    assert "LIMIT %(top_n)s" in rendered.sql
    assert rendered.bindings == {
        "top_n": 10,
        "regions_0": "테스트-국내",
    }


def test_recipe_rendering_preserves_full_logical_arguments() -> None:
    rendered = default_recipe_catalog().render(
        "issue_matrix",
        1,
        {
            "row_dimension": "occurrence_stage",
            "column_dimension": "process_name",
            "date_from": "2024-01-01",
            "limit": 25,
        },
    )

    assert rendered.arguments == {
        "row_dimension": "occurrence_stage",
        "column_dimension": "process_name",
        "limit": 25,
        "date_from": date(2024, 1, 1),
    }
    assert rendered.bindings == {
        "limit": 25,
        "date_from": date(2024, 1, 1),
    }


def test_matrix_exposes_declared_row_and_overall_denominators() -> None:
    rendered = default_recipe_catalog().render(
        "issue_matrix",
        1,
        {
            "row_dimension": "occurrence_stage",
            "column_dimension": "process_name",
        },
    )

    assert "AS row_total_count" in rendered.sql
    assert "AS row_share" in rendered.sql
    assert "AS total_issue_count" in rendered.sql
    assert "AS overall_share" in rendered.sql


def test_cube_keeps_three_dimensions_in_each_atomic_result_row() -> None:
    rendered = default_recipe_catalog().render(
        "issue_cube",
        1,
        {
            "row_dimension": "occurrence_stage",
            "column_dimension": "process_name",
            "detail_dimension": "vehicle_model",
        },
    )

    assert "TRIM(i.occurrence_stage)" in rendered.sql
    assert "AS row_value" in rendered.sql
    assert "TRIM(i.process_name)" in rendered.sql
    assert "AS column_value" in rendered.sql
    assert "TRIM(i.vehicle_model)" in rendered.sql
    assert "AS detail_value" in rendered.sql
    assert "AS combination_total_count" in rendered.sql
    assert "AS detail_share" in rendered.sql
    assert "AS total_issue_count" in rendered.sql
    assert "AS overall_share" in rendered.sql


def test_supplier_part_hotspots_exposes_composite_share_and_missing_flags() -> None:
    rendered = default_recipe_catalog().render(
        "issue_supplier_part_hotspots",
        1,
        {"limit": 8},
    )

    assert "AS supplier_missing" in rendered.sql
    assert "AS part_number_missing" in rendered.sql
    assert "AS supplier_missing_issue_count" in rendered.sql
    assert "AS supplier_missing_share" in rendered.sql
    assert "AS total_issue_count" in rendered.sql
    assert "AS combination_share" in rendered.sql
    assert "AS cumulative_issue_count" in rendered.sql
    assert "AS cumulative_share" in rendered.sql
    assert rendered.arguments["limit"] == 8


def test_breakdown_marks_missing_dimension_values_explicitly() -> None:
    rendered = default_recipe_catalog().render(
        "issue_breakdown",
        1,
        {"dimension": "supplier"},
    )

    assert "AS dimension_missing" in rendered.sql
    assert "AS issue_share" in rendered.sql
    assert "'미입력'" in rendered.sql


def test_detail_recipe_supports_exact_group_filters_and_missing_values() -> None:
    rendered = default_recipe_catalog().render(
        "issue_details",
        1,
        {
            "suppliers": ["두원공조"],
            "part_number_missing": True,
            "occurrence_stages": ["MP"],
            "process_names": ["조립"],
            "cause_types": ["설계"],
            "limit": 2,
        },
    )

    assert "i.part_number" in rendered.sql
    assert "i.supplier IN (%(suppliers_0)s)" in rendered.sql
    assert "i.part_number IS NULL" in rendered.sql
    assert "i.occurrence_stage IN (%(occurrence_stages_0)s)" in rendered.sql
    assert "i.process_name IN (%(process_names_0)s)" in rendered.sql
    assert "i.cause_type IN (%(cause_types_0)s)" in rendered.sql
    assert rendered.bindings == {
        "suppliers_0": "두원공조",
        "occurrence_stages_0": "MP",
        "process_names_0": "조립",
        "cause_types_0": "설계",
        "limit": 2,
    }


def test_checklist_coverage_counts_linked_issues_without_duplicate_inflation() -> None:
    rendered = default_recipe_catalog().render(
        "issue_checklist_coverage",
        1,
        {"dimension": "vehicle_model"},
    )

    bounded_count = (
        "COUNT(DISTINCT CASE WHEN NOT ci.stable_issue_id IS NULL "
        "THEN i.issue_id END)"
    )
    assert rendered.sql.count(bounded_count) == 2
    assert "COUNT(DISTINCT ci.source_issue_id)" not in rendered.sql


def test_checklist_coverage_prioritizes_high_issue_count_when_rates_tie() -> None:
    rendered = default_recipe_catalog().render(
        "issue_checklist_coverage",
        1,
        {"dimension": "vehicle_model", "sort_direction": "ASC"},
    )

    assert (
        "ORDER BY coverage_rate ASC, issue_count DESC, dimension_value"
        in rendered.sql
    )
    assert "AS unlinked_issue_count" in rendered.sql
    assert "AS total_issue_count" in rendered.sql
    assert "AS issue_share" in rendered.sql
    definitions = {
        item.name: item for item in rendered.recipe.metrics
    }
    assert definitions["coverage_rate"].denominator_column == "issue_count"
    assert definitions["issue_share"].denominator_column == "total_issue_count"


def test_checklist_item_breakdown_exposes_linked_and_unlinked_items() -> None:
    rendered = default_recipe_catalog().render(
        "checklist_item_breakdown",
        1,
        {"dimension": "module_key"},
    )

    assert "AS linked_item_count" in rendered.sql
    assert "AS unlinked_item_count" in rendered.sql
    assert "AS linkage_rate" in rendered.sql


def test_recipe_parameter_schema_rejects_unknown_or_unallowlisted_values() -> None:
    catalog = default_recipe_catalog()

    with pytest.raises(ValidationError):
        catalog.render(
            "issue_breakdown",
            1,
            {"dimension": "workspace_id"},
        )
    with pytest.raises(ValidationError):
        catalog.render(
            "issue_total",
            1,
            {"question_specific_override": "anything"},
        )


def test_recipe_first_decision_requires_explicit_fallback_gap() -> None:
    with pytest.raises(ValidationError):
        AnalysisRouteDecision(
            route=AnalysisRoute.SAFE_SQL,
            confidence=0.8,
            rationale="generated SQL",
        )

    decision = AnalysisRouteDecision(
        route=AnalysisRoute.SAFE_SQL,
        fallback_reason=FallbackReason.UNSUPPORTED_JOIN,
        confidence=0.8,
        rationale="No versioned recipe exposes the required relationship.",
    )

    assert decision.fallback_reason == FallbackReason.UNSUPPORTED_JOIN


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("DELETE FROM legacy_issue_analysis.issue_records_v1", "safe_sql_select_only"),
        ("SELECT * FROM legacy_issue_analysis.issue_records_v1", "safe_sql_wildcard"),
        ("SELECT issue_id FROM legacy_issue_records", "safe_sql_qualified_view"),
        ("SELECT email FROM public.users", "safe_sql_view_not_allowed"),
        (
            "SELECT pg_sleep(10), i.issue_id "
            "FROM legacy_issue_analysis.issue_records_v1 AS i",
            "safe_sql_function_not_allowed",
        ),
        (
            "SELECT i.issue_id FROM legacy_issue_analysis.issue_records_v1 AS i "
            "WHERE i.issue_id IN (SELECT source_issue_id FROM "
            "legacy_issue_analysis.vehicle_checklist_items_v1)",
            "safe_sql_subquery_not_allowed",
        ),
        (
            "SELECT i.issue_id FROM legacy_issue_analysis.issue_records_v1 AS i -- leak",
            "safe_sql_comment_not_allowed",
        ),
    ],
)
def test_safe_sql_policy_rejects_non_allowlisted_shapes(sql: str, reason: str) -> None:
    with pytest.raises(SafeSqlPolicyError, match=reason):
        SafeSqlPolicy().validate(sql)


def test_safe_sql_policy_accepts_parameterized_select_on_versioned_view() -> None:
    validated = SafeSqlPolicy().validate(
        "SELECT i.vehicle_model, COUNT(DISTINCT i.issue_id) AS issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i "
        "WHERE i.occurrence_date >= :date_from "
        "GROUP BY i.vehicle_model ORDER BY issue_count DESC",
        parameters={"date_from": date(2026, 1, 1)},
    )

    assert validated.parameter_names == ("date_from",)
    assert validated.referenced_views == (ISSUE_RECORDS_VIEW_V1,)
    assert len(validated.fingerprint) == 64


def test_safe_sql_policy_accepts_only_the_approved_issue_checklist_join_key() -> None:
    validated = SafeSqlPolicy().validate(
        "SELECT i.vehicle_model, "
        "COUNT(DISTINCT ci.source_issue_id) AS linked_issue_count "
        "FROM legacy_issue_analysis.issue_records_v1 AS i "
        "LEFT JOIN legacy_issue_analysis.vehicle_checklist_items_v1 AS ci "
        "ON ci.stable_issue_id = i.stable_issue_id "
        "GROUP BY i.vehicle_model"
    )

    assert validated.referenced_views == (
        ISSUE_RECORDS_VIEW_V1,
        CHECKLIST_ITEMS_VIEW_V1,
    )


@pytest.mark.parametrize(
    ("join_condition", "reason"),
    [
        ("1 = 1", "safe_sql_join_condition_not_allowed"),
        (
            "ci.vehicle_model = i.vehicle_model",
            "safe_sql_join_key_not_allowed",
        ),
        (
            "ci.stable_issue_id = i.stable_issue_id OR 1 = 1",
            "safe_sql_join_condition_not_allowed",
        ),
        (
            "ci.stable_issue_id = i.stable_issue_id "
            "AND ci.vehicle_model = i.vehicle_model",
            "safe_sql_join_condition_not_allowed",
        ),
    ],
)
def test_safe_sql_policy_rejects_unapproved_or_cartesian_join_conditions(
    join_condition: str,
    reason: str,
) -> None:
    sql = (
        "SELECT i.issue_id, ci.checklist_item_id "
        "FROM legacy_issue_analysis.issue_records_v1 AS i "
        "LEFT JOIN legacy_issue_analysis.vehicle_checklist_items_v1 AS ci "
        f"ON {join_condition}"
    )

    with pytest.raises(SafeSqlPolicyError, match=reason):
        SafeSqlPolicy().validate(sql)
