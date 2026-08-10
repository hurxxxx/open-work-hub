from open_alm_api.domains.legacy_issues.analysis_graph.report_guard import (
    build_source_markdown_fallback,
    sanitize_report_markdown,
    validate_report_markdown,
)


def test_report_guard_accepts_only_captured_numbers_and_citations() -> None:
    result = validate_report_markdown(
        "# 결빙 문제 요약\n\n총 12건입니다.\n\n대표 사례를 확인했습니다. [E1]",
        question="결빙 관련 문제를 보고해줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["total_count"],
                "rows": [{"total_count": 12}],
            }
        ],
        evidence=[{"evidence_id": "E1", "excerpt": "결빙 현상"}],
    )
    assert result.valid is True
    assert result.errors == ()


def test_report_guard_keeps_counts_percentages_and_percentage_points_distinct() -> None:
    source = [
        {
            "status": "succeeded",
            "columns": ["issue_count"],
            "rows": [{"issue_count": 25}],
        }
    ]

    assert validate_report_markdown(
        "# 결과\n\n확인된 문제는 25건입니다.",
        question="문제 건수",
        query_results=source,
        evidence=[],
    ).valid
    for unsupported in ("25%", "25%p"):
        result = validate_report_markdown(
            f"# 결과\n\n확인된 비율은 {unsupported}입니다.",
            question="문제 현황",
            query_results=source,
            evidence=[],
        )
        assert result.valid is False
        assert f"unsupported_number:{unsupported}" in result.errors

    rate_source = [
        {
            "status": "succeeded",
            "columns": ["coverage_rate"],
            "rows": [{"coverage_rate": 25}],
        }
    ]
    assert validate_report_markdown(
        "# 결과\n\n체크리스트 반영률은 25%입니다.",
        question="체크리스트 반영률",
        query_results=rate_source,
        evidence=[],
    ).valid
    result = validate_report_markdown(
        "# 결과\n\n체크리스트 반영 건수는 25건입니다.",
        question="체크리스트 반영 현황",
        query_results=rate_source,
        evidence=[],
    )
    assert result.valid is False
    assert "unsupported_number:25" in result.errors


def test_report_guard_rejects_unsupported_number_citation_and_internal_commentary() -> None:
    result = validate_report_markdown(
        "# 결과\n\n분석 과정에서 총 99건을 확인했습니다. [E9]",
        question="결빙 관련 문제를 보고해줘",
        query_results=[],
        evidence=[],
    )
    assert result.valid is False
    assert "internal_commentary:분석 과정" in result.errors
    assert "unsupported_number:99" in result.errors
    assert "unknown_citation:E9" in result.errors


def test_report_guard_allows_user_facing_calculation_limitations() -> None:
    result = validate_report_markdown(
        (
            "# 계산 불가 항목\n\n"
            "분석 과정에서 계산이 불가능한 항목은 추정하지 않았습니다."
        ),
        question="계산 불가 항목은 명시하고 추정하지 마",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["checklist_count"],
                "rows": [{"checklist_count": 1}],
            }
        ],
        evidence=[],
    )

    assert result.valid is True
    assert result.errors == ()


def test_report_guard_requires_a_table_only_when_the_user_requests_one() -> None:
    result = validate_report_markdown(
        "# 저반영 차종\n\nAB 차종의 반영률은 0%입니다.",
        question="반영률이 낮은 차종을 표로 정리해줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["vehicle_model", "coverage_rate"],
                "rows": [{"vehicle_model": "AB", "coverage_rate": 0}],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "missing_requested_table" in result.errors


def test_report_guard_rejects_no_sources_and_reviewed_claims_that_remain() -> None:
    no_sources = validate_report_markdown(
        "# 결과\n\n특별한 문제가 없습니다.",
        question="상태를 알려줘",
        query_results=[],
        evidence=[],
    )
    assert "no_captured_sources" in no_sources.errors

    reviewed = validate_report_markdown(
        "# 결과\n\n모든 차종에서 결빙이 증가했습니다.",
        question="결빙 문제를 보고해줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["total_count"],
                "rows": [{"total_count": 12}],
            }
        ],
        evidence=[],
        reviewed_unsupported_claims=["모든 차종에서 결빙이 증가했습니다."],
    )
    assert "reviewed_unsupported_claim" in reviewed.errors


def test_report_guard_does_not_treat_hierarchical_heading_numbers_as_claims() -> None:
    result = validate_report_markdown(
        (
            "# 결빙 문제 보고서\n\n"
            "## 2. 문제 유형\n\n"
            "### 2.1 제어 로직\n\n"
            "확인된 사례를 요약했습니다. [E1]"
        ),
        question="결빙 문제를 보고해줘",
        query_results=[],
        evidence=[{"evidence_id": "E1", "excerpt": "저온 제어 로직 오류"}],
    )

    assert result.valid is True
    assert result.errors == ()


def test_report_guard_accepts_bounded_calculations_dates_and_row_ordinals() -> None:
    result = validate_report_markdown(
        (
            "# 차종별 현황\n\n"
            "| 순위 | 차종 | 비중 |\n"
            "| --- | --- | --- |\n"
            "| 1 | CV | 3.98% |\n\n"
            "2024.11 기준 결과입니다."
        ),
        question="차종별 비중을 알려줘",
        query_results=[
                {
                    "status": "succeeded",
                    "recipe_id": "issue_breakdown",
                    "columns": ["vehicle_model", "issue_count", "occurrence_date"],
                "rows": [
                    {
                        "vehicle_model": "CV",
                        "issue_count": 39,
                        "issue_share": 3.98,
                        "occurrence_date": "2024-11-25",
                    },
                    {
                        "vehicle_model": "ALL",
                        "issue_count": 979,
                        "occurrence_date": "2024-11-25",
                        },
                    ],
                },
                {
                    "status": "succeeded",
                    "recipe_id": "issue_total",
                    "columns": ["issue_count"],
                    "rows": [{"issue_count": 979}],
                },
            ],
        evidence=[],
    )

    assert result.valid is True
    assert result.errors == ()


def test_report_guard_accepts_signed_deltas_prefix_shares_and_percentage_points() -> None:
    result = validate_report_markdown(
        (
            "# 기간 비교\n\n"
            "2023년 3건에서 2024년 2건으로 -1건(-33.33%) 감소했습니다.\n\n"
            "중요도 A 비중은 66.67%에서 50%로 -16.67%p 변했습니다.\n\n"
            "상위 5개 유형 25건은 전체 35건의 71.4%입니다."
        ),
        question="2023년과 2024년을 비교해줘",
        query_results=[
            {
                "status": "succeeded",
                "recipe_id": "issue_breakdown",
                "columns": ["issue_type", "issue_count"],
                "rows": [
                    {"issue_type": "A", "issue_count": 9},
                    {"issue_type": "B", "issue_count": 6},
                    {"issue_type": "C", "issue_count": 4},
                    {"issue_type": "D", "issue_count": 3},
                    {"issue_type": "E", "issue_count": 3},
                    {"issue_type": "기타", "issue_count": 10},
                ],
            },
            {
                "status": "succeeded",
                "recipe_id": "issue_period_comparison",
                "columns": ["year", "issue_count", "severity_a_count"],
                "rows": [
                    {"year": 2023, "issue_count": 3, "severity_a_count": 2},
                    {"year": 2024, "issue_count": 2, "severity_a_count": 1},
                ],
            },
        ],
        evidence=[],
    )

    assert result.valid is True
    assert result.errors == ()


def test_report_guard_rejects_incorrect_top_group_sum_despite_dense_sources() -> None:
    result = validate_report_markdown(
        "# 상위 차종\n\n상위 10개 차종은 238건으로 전체 979건의 24.3%입니다.",
        question="전체 차종별 상위 그룹 비중",
        query_results=[
            {
                "status": "succeeded",
                "recipe_id": "issue_breakdown",
                "columns": ["vehicle_model", "issue_count"],
                "rows": [
                    {"vehicle_model": "CV", "issue_count": 39},
                    {"vehicle_model": "KA4 PE", "issue_count": 34},
                    {"vehicle_model": "OV1", "issue_count": 29},
                    {"vehicle_model": "SG2 EV", "issue_count": 28},
                    {"vehicle_model": "OV", "issue_count": 22},
                    {"vehicle_model": "AX", "issue_count": 20},
                    {"vehicle_model": "SW", "issue_count": 20},
                    {"vehicle_model": "NX4", "issue_count": 19},
                    {"vehicle_model": "UM", "issue_count": 19},
                    {"vehicle_model": "RB", "issue_count": 18},
                ],
            },
            {
                "status": "succeeded",
                "recipe_id": "issue_total",
                "columns": ["issue_count"],
                "rows": [{"issue_count": 979}],
            },
            {
                "status": "succeeded",
                "recipe_id": "issue_matrix",
                "columns": ["vehicle_model", "issue_type", "issue_count"],
                "rows": [
                    {
                        "vehicle_model": "KA4 PE",
                        "issue_type": None,
                        "issue_count": 512,
                    }
                ],
            },
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "unsupported_number:238" in result.errors
    assert "unsupported_number:24.3%" in result.errors


def test_report_guard_does_not_treat_result_row_count_as_business_count() -> None:
    result = validate_report_markdown(
        "# 제외 현황\n\n계산에서 제외된 문제는 전체 11건입니다.",
        question="날짜가 없는 제외 건수를 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "recipe_id": "issue_details",
                "columns": ["issue_id"],
                "rows": [{"issue_id": f"issue-{index}"} for index in range(11)],
                "row_count": 11,
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "unsupported_number:11" in result.errors


def test_report_guard_does_not_mix_unrelated_queries_for_a_ratio() -> None:
    result = validate_report_markdown(
        "# 공정 편중\n\n조립 공정의 행 기준 비중은 15.02%입니다.",
        question="발생 단계와 공정별 행 기준 비중을 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "recipe_id": "issue_matrix",
                "columns": ["row_value", "column_value", "issue_count"],
                "rows": [
                    {
                        "row_value": "MP",
                        "column_value": "조립",
                        "issue_count": 147,
                    }
                ],
            },
            {
                "status": "succeeded",
                "recipe_id": "issue_total",
                "columns": ["issue_count"],
                "rows": [{"issue_count": 979}],
            },
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "unsupported_number:15.02%" in result.errors


def test_report_guard_uses_explicit_query_share_instead_of_arbitrary_ratio() -> None:
    result = validate_report_markdown(
        "# 상위 조합\n\n상위 조합 누적 비중은 94.79%입니다.",
        question="상위 조합의 전체 대비 비중을 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "recipe_id": "issue_supplier_part_hotspots",
                "columns": [
                    "issue_count",
                    "total_issue_count",
                    "combination_share",
                    "cumulative_share",
                ],
                "rows": [
                    {
                        "issue_count": 653,
                        "total_issue_count": 979,
                        "combination_share": 66.7,
                        "cumulative_share": 66.7,
                    },
                    {
                        "issue_count": 274,
                        "total_issue_count": 979,
                        "combination_share": 27.99,
                        "cumulative_share": 94.69,
                    },
                ],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "unsupported_number:94.79%" in result.errors


def test_report_guard_accepts_query_parameter_dates() -> None:
    result = validate_report_markdown(
        "# 분석 범위\n\n2010년부터 2024년까지 35건입니다.",
        question="기간별 현황",
        query_results=[
            {
                "status": "succeeded",
                "params": {
                    "date_from": "2010-01-01",
                    "date_to": "2024-12-31",
                },
                "columns": ["issue_count"],
                "rows": [{"issue_count": 35}],
            }
        ],
        evidence=[],
    )

    assert result.valid is True
    assert result.errors == ()


def test_report_guard_rejects_internal_source_identifiers_without_scanning_hash() -> None:
    result = validate_report_markdown(
        "# 결과\n\n내부 조회 `analysis-4ce9aa8f802de919`에서 979건입니다.",
        question="전체 건수",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["issue_count"],
                "rows": [{"issue_count": 979}],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "internal_source_reference" in result.errors
    assert all("4" not in error for error in result.errors if error.startswith("unsupported"))


def test_report_guard_rejects_internal_recipe_source_labels() -> None:
    result = validate_report_markdown(
        "# 결과\n\n총 2건입니다. (Source: `issue_breakdown`)",
        question="전체 건수",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["issue_count"],
                "rows": [{"issue_count": 2}],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "internal_source_reference" in result.errors


def test_report_guard_rejects_internal_metadata_and_speculative_scope() -> None:
    result = validate_report_markdown(
        (
            "# 한계 사항\n\n"
            "원자료는 `truncated: true`이며 21개 항목은 특정 차종의 것으로 보입니다."
        ),
        question="체크리스트 항목 수를 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["checklist_item_count"],
                "rows": [{"checklist_item_count": 21}],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "internal_source_metadata" in result.errors
    assert "unsupported_speculation" in result.errors


def test_source_fallback_uses_only_available_source_families() -> None:
    markdown = build_source_markdown_fallback(
        title="결빙 문제 보고서",
        question="결빙 문제를 보고해줘",
        query_results=[
            {
                "status": "succeeded",
                "recipe_id": "count",
                "columns": ["vehicle_model", "count"],
                "rows": [{"vehicle_model": "A", "count": 3}],
            }
        ],
        evidence=[
            {
                "evidence_id": "E1",
                "title": "사례 1",
                "excerpt": "저온 조건에서 결빙",
            }
        ],
    )
    assert "# 결빙 문제 보고서" in markdown
    assert "| A | 3 |" in markdown
    assert "사례 1 [E1]" in markdown
    assert "체크리스트" not in markdown


def test_source_fallback_preserves_capability_limit_without_dumping_tables() -> None:
    markdown = build_source_markdown_fallback(
        title="대응 소요기간 보고서",
        question="최종 대책일까지 평균을 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "source_label": "관련 없는 대형 집계",
                "columns": ["issue_count"],
                "rows": [{"issue_count": index} for index in range(100)],
            }
        ],
        evidence=[],
        capability_limitations=["최종 대책일 컬럼이 없어 계산할 수 없습니다."],
    )

    assert "최종 대책일 컬럼이 없어 계산할 수 없습니다." in markdown
    assert "관련 없는 대형 집계" not in markdown
    assert "| issue_count |" not in markdown


def test_source_fallback_prioritizes_distinct_decision_tables_over_query_order() -> None:
    repeated_breakdown = {
        "status": "succeeded",
        "recipe_id": "checklist_item_breakdown",
        "source_label": "차량 체크리스트 항목 분포",
        "recipe_arguments": {"dimension": "module_key", "limit": 100},
        "columns": ["dimension_value", "checklist_item_count"],
        "rows": [{"dimension_value": "heat-exchanger", "checklist_item_count": 21}],
    }
    markdown = build_source_markdown_fallback(
        title="검토 누락 위험 보고서",
        question="차량 체크리스트 반영이 낮은 차종을 비교해줘",
        query_results=[
            repeated_breakdown,
            repeated_breakdown,
            {
                "status": "succeeded",
                "recipe_id": "checklist_total",
                "source_label": "차량 체크리스트 문서 수",
                "columns": ["checklist_count"],
                "rows": [{"checklist_count": 1}],
            },
            {
                "status": "succeeded",
                "recipe_id": "checklist_item_total",
                "source_label": "차량 체크리스트 항목 수",
                "columns": ["checklist_item_count"],
                "rows": [{"checklist_item_count": 21}],
            },
            {
                "status": "succeeded",
                "recipe_id": "checklist_status_summary",
                "source_label": "차량 체크리스트 완료 현황",
                "columns": ["checklist_count", "draft_count"],
                "rows": [{"checklist_count": 1, "draft_count": 1}],
            },
            {
                "status": "succeeded",
                "recipe_id": "issue_checklist_coverage",
                "source_label": "과거차 문제점 체크리스트 반영 범위",
                "recipe_arguments": {
                    "dimension": "vehicle_model",
                    "limit": 100,
                    "sort_direction": "ASC",
                },
                "columns": [
                    "dimension_value",
                    "issue_count",
                    "coverage_rate",
                    "total_issue_count",
                ],
                "rows": [
                    {
                        "dimension_value": "CV",
                        "issue_count": 39,
                        "coverage_rate": 0,
                        "total_issue_count": 979,
                    }
                ],
            },
        ],
        evidence=[],
        max_query_tables=5,
    )

    assert markdown.count("차량 체크리스트 항목 분포") == 1
    assert "과거차 문제점 체크리스트 반영 범위 (기준: 차종)" in markdown
    assert "| 구분 | 문제점 건수 | 문제점 반영률(%) | 전체 문제점 건수 |" in markdown
    assert "| CV | 39 | 0 | 979 |" in markdown


def test_source_fallback_prioritizes_cross_tab_and_labels_its_dimensions() -> None:
    markdown = build_source_markdown_fallback(
        title="공정 편중 보고서",
        question="발생 단계와 공정별 문제 분포를 교차 분석해줘",
        query_results=[
            *[
                {
                    "status": "succeeded",
                    "recipe_id": "issue_breakdown",
                    "source_label": "과거차 문제점 단일 기준 분포",
                    "recipe_arguments": {"dimension": dimension, "limit": 200},
                    "columns": ["dimension_value", "issue_count"],
                    "rows": [{"dimension_value": value, "issue_count": count}],
                }
                for dimension, value, count in (
                    ("vehicle_model", "CV", 39),
                    ("module_key", "aircon", 141),
                    ("cause_type", "설계", 500),
                    ("occurrence_stage", "MP", 147),
                    ("process_name", "미입력", 905),
                )
            ],
            {
                "status": "succeeded",
                "recipe_id": "issue_matrix",
                "source_label": "과거차 문제점 복합 기준 교차 집계",
                "recipe_arguments": {
                    "row_dimension": "occurrence_stage",
                    "column_dimension": "process_name",
                    "limit": 500,
                },
                "columns": [
                    "row_value",
                    "column_value",
                    "issue_count",
                    "row_total_count",
                    "row_share",
                ],
                "rows": [
                    {
                        "row_value": "MP",
                        "column_value": "미입력",
                        "issue_count": 107,
                        "row_total_count": 147,
                        "row_share": 72.79,
                    }
                ],
            },
        ],
        evidence=[],
        max_query_tables=5,
    )

    assert "과거차 문제점 복합 기준 교차 집계 (행: 발생 단계 · 열: 공정)" in markdown
    assert "| 행 기준 | 열 기준 | 문제점 건수 | 행 전체 건수 | 행 기준 비중(%) |" in markdown
    assert "| MP | 미입력 | 107 | 147 | 72.79 |" in markdown


def test_evidence_number_can_be_cited_within_the_same_markdown_list_item() -> None:
    result = validate_report_markdown(
        (
            "# 사례\n\n"
            "- **E1 사례**\n"
            "  - 발생일: 2025-10-28\n"
            "  - 확인 근거: 사례 원문 [E1]\n"
        ),
        question="발생일을 알려줘",
        query_results=[],
        evidence=[
            {
                "evidence_id": "E1",
                "title": "사례",
                "excerpt": "발생일 2025-10-28",
            }
        ],
    )

    assert result.valid is True


def test_query_metric_cannot_be_misattributed_to_semantic_evidence() -> None:
    result = validate_report_markdown(
        "# 결과\n\nCV 문제는 39건입니다. [E1]",
        question="차종별 문제를 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["vehicle_model", "issue_count"],
                "rows": [{"vehicle_model": "CV", "issue_count": 39}],
            }
        ],
        evidence=[
            {
                "evidence_id": "E1",
                "title": "개별 사례",
                "excerpt": "CV의 결빙 사례",
            }
        ],
    )

    assert result.valid is False
    assert "citation_source_mismatch" in result.errors


def test_sql_only_draft_scope_must_be_disclosed() -> None:
    query_results = [
        {
            "status": "succeeded",
            "columns": ["issue_count"],
            "rows": [{"issue_count": 1}],
        }
    ]
    source_revisions = [
        {
            "revision_id": "revision-draft",
            "status": "draft",
            "module_key": "aircon",
        }
    ]

    undisclosed = validate_report_markdown(
        "# 결과\n\n문제 이력은 1건입니다.",
        question="문제 이력이 있어?",
        query_results=query_results,
        evidence=[],
        source_revisions=source_revisions,
    )
    disclosed = validate_report_markdown(
        "# 결과\n\n작성 중 초안 데이터 기준으로 문제 이력은 1건입니다.",
        question="문제 이력이 있어?",
        query_results=query_results,
        evidence=[],
        source_revisions=source_revisions,
    )

    assert "draft_status_omitted" in undisclosed.errors
    assert disclosed.valid is True


def test_query_limit_is_not_accepted_as_a_business_count() -> None:
    result = validate_report_markdown(
        "# 결과\n\n제외 건수는 11건입니다.",
        question="제외 건수를 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "recipe_arguments": {"limit": 11},
                "columns": ["vehicle_model"],
                "rows": [{"vehicle_model": "CV"}],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "unsupported_number:11" in result.errors


def test_table_ordinal_requires_an_explicit_rank_header() -> None:
    result = validate_report_markdown(
        (
            "# 결과\n\n"
            "| 제외 건수 | 설명 |\n"
            "| --- | --- |\n"
            "| 11 | 확인 불가 |\n"
        ),
        question="제외 건수를 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["vehicle_model"],
                "rows": [{"vehicle_model": f"차종-{index}"} for index in range(11)],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "unsupported_number:11" in result.errors


def test_report_guard_rejects_metrics_mixed_across_dimension_rows() -> None:
    result = validate_report_markdown(
        "# 저반영 차종\n\n- OV1: 29건, 반영률 0%",
        question="반영률이 낮은 차종을 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": [
                    "dimension_value",
                    "issue_count",
                    "coverage_rate",
                ],
                "rows": [
                    {
                        "dimension_value": "CV",
                        "issue_count": 39,
                        "coverage_rate": 0,
                    },
                    {
                        "dimension_value": "OV1",
                        "issue_count": 29,
                        "coverage_rate": 6.9,
                    },
                ],
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "cross_row_numeric_mix" in result.errors


def test_row_guard_accepts_numbers_embedded_in_the_same_detail_record() -> None:
    result = validate_report_markdown(
        "# 대표 사례\n\n- CV: 초기 구동 RPM을 600에서 1500으로 변경했습니다.",
        question="대표 사례와 대책을 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "columns": ["vehicle_model", "countermeasure"],
                "rows": [
                    {
                        "vehicle_model": "CV",
                        "countermeasure": "초기 구동 RPM 변경 (600 → 1500)",
                    }
                ],
            }
        ],
        evidence=[],
    )

    assert result.valid is True


def test_safe_sanitizer_removes_only_lines_with_rejected_literals() -> None:
    markdown = sanitize_report_markdown(
        (
            "# 결과\n\n"
            "- 공정 미입력 비중은 92.44%입니다.\n"
            "- 잘못 계산한 근사치는 16%입니다.\n"
            "- 나머지 설명은 유지합니다."
        ),
        errors=["unsupported_number:16%"],
    )

    assert "92.44%" in markdown
    assert "16%" not in markdown
    assert "나머지 설명은 유지합니다." in markdown


def test_limited_vehicle_rows_cannot_support_an_all_vehicle_claim() -> None:
    result = validate_report_markdown(
        "# 결과\n\n모든 분석 대상 차종의 반영률은 0%입니다.",
        question="반영률이 낮은 차종을 알려줘",
        query_results=[
            {
                "status": "succeeded",
                "recipe_arguments": {
                    "dimension": "vehicle_model",
                    "limit": 50,
                },
                "columns": ["dimension_value", "coverage_rate"],
                "rows": [
                    {
                        "dimension_value": f"차종-{index}",
                        "coverage_rate": 0,
                    }
                    for index in range(50)
                ],
                "row_count": 50,
            }
        ],
        evidence=[],
    )

    assert result.valid is False
    assert "universal_claim_on_limited_result" in result.errors
