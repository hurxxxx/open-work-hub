from open_alm_api.domains.legacy_issues.grounded_report import (
    render_grounded_legacy_issue_report,
)


def test_generated_planner_fallback_uses_business_scope_wording() -> None:
    report = render_grounded_legacy_issue_report(
        analysis_result={
            "version": 1,
            "mode": "generated",
            "exactness": "mixed",
            "scope": {"source_count": 10},
            "queries": [],
            "planner_diagnostics": {
                "status": "fallback",
                "fallback_reason": "attempts_exhausted",
            },
        },
        evidence=[],
        analysis_degraded=True,
    )

    assert "현재 보고서에 표시된 데이터 범위와 집계 항목만 포함합니다." in report
    assert "서버" not in report
    assert "원래 분석 계획" not in report
    assert "검증을 통과" not in report
    assert "보호된 대체 분석" not in report
    assert "표준 카탈로그" not in report


def test_salvaged_catalog_plan_does_not_expose_planner_process() -> None:
    report = render_grounded_legacy_issue_report(
        analysis_result={
            "version": 1,
            "mode": "analytics",
            "exactness": "exact",
            "scope": {"source_count": 10},
            "queries": [],
            "planner_diagnostics": {
                "status": "fallback",
                "fallback_reason": "partial_plan_salvaged",
            },
        },
        evidence=[],
        analysis_degraded=True,
    )

    assert "확인되지 않은 항목은 제외했으며 추정값을 사용하지 않았습니다." in report
    assert "서버" not in report
    assert "원래 계획" not in report
    assert "검증을 통과" not in report
    assert "planner" not in report
    assert "fallback" not in report


def test_data_quality_recommendation_names_only_fields_with_quality_issues() -> None:
    report = render_grounded_legacy_issue_report(
        analysis_result={
            "version": 1,
            "mode": "hybrid",
            "exactness": "exact",
            "scope": {"source_count": 10},
            "queries": [
                {
                    "id": "quality",
                    "family_id": "missing_populated_rate",
                    "columns": [],
                    "rows": [],
                    "coverage": [
                        {
                            "field_key": "severity",
                            "label": "중요도",
                            "present_count": 2,
                            "missing_count": 8,
                            "invalid_count": 0,
                        },
                        {
                            "field_key": "vehicle_model",
                            "label": "차종",
                            "present_count": 10,
                            "missing_count": 0,
                            "invalid_count": 0,
                        },
                    ],
                }
            ],
        },
        evidence=[],
    )

    recommendation = next(
        line for line in report.splitlines() if line.startswith("- 데이터 품질:")
    )
    assert "`중요도`" in recommendation
    assert "차종" not in recommendation
