from __future__ import annotations

from open_alm_api.domains.ai_graph.contracts import AiGraphNodeSpec, AiGraphSpec


LEGACY_ISSUE_ANALYSIS_GRAPH_ID = "legacy_issues.analysis"
LEGACY_ISSUE_ANALYSIS_GRAPH_VERSION = "2.0.0"


def legacy_issue_analysis_graph_spec() -> AiGraphSpec:
    """Return the versioned topology shared by API dispatch and the worker."""

    return AiGraphSpec(
        graph_id=LEGACY_ISSUE_ANALYSIS_GRAPH_ID,
        graph_version=LEGACY_ISSUE_ANALYSIS_GRAPH_VERSION,
        nodes=(
            _node("interpret", "사용자 요청과 분석 의도를 구조화한다."),
            _node(
                "analyze_data",
                "레시피 우선 SQL과 의미 검색으로 근거를 수집한다.",
                depends_on=("interpret",),
            ),
            _node(
                "choose_output",
                "일반 답변과 보고서 작성 경로를 선택한다.",
                depends_on=("analyze_data",),
                routes={"answer": "answer_draft", "report": "report_template"},
            ),
            _node(
                "answer_draft",
                "수집된 근거만 사용해 간결한 답변을 만든다.",
            ),
            _node(
                "persist_answer",
                "일반 답변과 사용 근거를 저장한다.",
                depends_on=("answer_draft",),
            ),
            _node(
                "report_template",
                "요청과 근거에 맞는 동적 보고서 목차를 만든다.",
            ),
            _node(
                "quantitative_analyst",
                "정형 집계 결과를 검토한다.",
                depends_on=("report_template",),
                required=False,
            ),
            _node(
                "evidence_analyst",
                "사례 근거와 정성 패턴을 검토한다.",
                depends_on=("report_template",),
                required=False,
            ),
            _node(
                "checklist_analyst",
                "차량 체크리스트 근거를 검토한다.",
                depends_on=("report_template",),
                required=False,
            ),
            _node(
                "report_draft",
                "병렬 분석 결과를 하나의 보고서 초안으로 합친다.",
                depends_on=(
                    "quantitative_analyst",
                    "evidence_analyst",
                    "checklist_analyst",
                ),
            ),
            _node(
                "grounding_review",
                "초안의 사실성·인용·내부 코멘트를 검토한다.",
                depends_on=("report_draft",),
            ),
            _node(
                "report_finalize",
                "검토 결과를 반영해 사용자용 보고서를 만든다.",
                depends_on=("grounding_review",),
            ),
            _node(
                "validate_report",
                "최종 보고서를 서버 규칙으로 검증한다.",
                depends_on=("report_finalize",),
                routes={"accept": "persist_report", "correct": "report_correction"},
            ),
            _node(
                "persist_report",
                "검증된 보고서와 출처 데이터를 저장한다.",
            ),
            _node(
                "report_correction",
                "검증 오류를 한 번만 교정한다.",
            ),
            _node(
                "validate_correction",
                "교정본을 재검증한다.",
                depends_on=("report_correction",),
                routes={
                    "accept": "persist_corrected_report",
                    "fallback": "persist_source_fallback",
                },
            ),
            _node(
                "persist_corrected_report",
                "검증을 통과한 교정 보고서를 저장한다.",
            ),
            _node(
                "persist_source_fallback",
                "검증 실패 시 캡처된 근거만으로 안전한 보고서를 저장한다.",
            ),
        ),
    )


def _node(
    node_id: str,
    purpose: str,
    *,
    depends_on: tuple[str, ...] = (),
    required: bool = True,
    routes: dict[str, str | None] | None = None,
) -> AiGraphNodeSpec:
    return AiGraphNodeSpec(
        node_id=node_id,
        purpose=purpose,
        depends_on=depends_on,
        required=required,
        routes=routes or {},
    )


__all__ = [
    "LEGACY_ISSUE_ANALYSIS_GRAPH_ID",
    "LEGACY_ISSUE_ANALYSIS_GRAPH_VERSION",
    "legacy_issue_analysis_graph_spec",
]
