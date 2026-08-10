from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from sqlalchemy.orm import Session

from ai_do_api.domains.patent.kipris import (
    KiprisError,
    PatentSearchJurisdictionPage,
    PatentSearchPage,
    PatentSearchResult,
)
from ai_do_api.domains.patent_prior_art import (
    PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID,
    PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID,
)
from ai_do_api.domains.patent_prior_art import pipeline, planning
from ai_do_api.domains.patent_prior_art.pipeline import (
    PatentPriorArtPipelineCancelled,
    PatentPriorArtTransientError,
    run_patent_prior_art,
)
from ai_do_api.domains.patent_prior_art.planning import (
    compile_provider_queries,
    preview_patent_prior_art_search,
)
from ai_do_api.domains.patent_prior_art.schemas import (
    PatentPriorArtSearchPlanDraft,
    PatentPriorArtSearchValues,
)
from ai_do_api.domains.ai.gateway import AiGatewayPolicyViolation
from ai_do_api.domains.retrieval.candidate_ranking import (
    MAX_QUERY_CHARS,
    CandidateRankingService,
)


_DB = cast(Session, None)
_INVENTION = (
    "복수의 센서 신호를 이용하여 열교환기와 송풍기의 작동 상태를 제어하고 "
    "에너지 사용량을 줄이는 통합 제어 기술이다."
)


def _values(values: list[str], source: str = "input_derived") -> PatentPriorArtSearchValues:
    return PatentPriorArtSearchValues(values=values, source=source)  # type: ignore[arg-type]


def _plan(
    *,
    categories: list[str] | None = None,
    keywords: list[str] | None = None,
    keywords_en: list[str] | None = None,
    ipc_codes: list[str] | None = None,
    cpc_codes: list[str] | None = None,
    applicants: list[str] | None = None,
    excluded_terms: list[str] | None = None,
    display_query: str = "",
) -> PatentPriorArtSearchPlanDraft:
    return PatentPriorArtSearchPlanDraft(
        category_ids=_values(categories or [], "user"),
        keywords_ko=_values(keywords or []),
        keywords_en=_values(keywords_en or []),
        ipc_codes=_values(ipc_codes or []),
        cpc_codes=_values(cpc_codes or []),
        applicants=_values(applicants or [], "user"),
        excluded_terms=_values(excluded_terms or []),
        display_query=display_query,
    )


def _raw_completion(text: str) -> SimpleNamespace:
    return SimpleNamespace(completion=SimpleNamespace(text=text))


def _completion(payload: dict[str, object]) -> SimpleNamespace:
    return _raw_completion(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _planning_payload(*, code: str = "B60H") -> dict[str, object]:
    return {
        "technology_summary": "입력된 기술의 기능 요소를 중심으로 한 검색 계획",
        "keywords_ko": ["열교환기", "송풍기", "통합 제어"],
        "keywords_en": ["heat exchanger", "blower control"],
        "ipc_codes": [code],
        "cpc_codes": [],
        "excluded_terms": [],
    }


def _patent(
    number: int,
    *,
    title: str = "Integrated thermal controller",
    abstract: str = "A controller operates a heat exchanger and blower using sensor signals.",
    applicants: tuple[str, ...] = (),
    jurisdiction: str = "KR",
) -> PatentSearchResult:
    return PatentSearchResult(
        canonical_number=f"{jurisdiction}{number}",
        publication_number=f"{jurisdiction}-{number}",
        application_number=f"APP-{number}",
        title=title,
        abstract=abstract,
        applicants=applicants,
        jurisdiction=jurisdiction,
        ipc_codes=("B60H1/00",),
        filing_date=date(2020, 1, 2),
        publication_date=date(2021, 2, 3),
        external_url=f"https://patents.example/{jurisdiction}{number}",
        provider_document_id=f"provider-{jurisdiction}-{number}",
    )


class _FakeKiprisClient:
    def __init__(self, results: list[PatentSearchResult], *, has_next: bool = False) -> None:
        self.results = results
        self.has_next = has_next
        self.calls: list[tuple[Any, int, int]] = []

    def search(self, criteria: Any, *, page: int, page_size: int) -> PatentSearchPage:
        self.calls.append((criteria, page, page_size))
        jurisdiction = criteria.countries[0]
        return PatentSearchPage(
            results=tuple(self.results),
            page=page,
            page_size=page_size,
            total_count=len(self.results) + (page_size if self.has_next else 0),
            jurisdictions=(
                PatentSearchJurisdictionPage(
                    jurisdiction=jurisdiction,
                    total_count=len(self.results),
                    returned_count=len(self.results),
                    has_next=self.has_next,
                ),
            ),
            has_next=self.has_next,
        )


def test_preview_executes_registered_workload_and_places_vehicle_anchor_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any, dict[str, Any]]] = []

    def fake_execute(
        workload_id: str, context: Any, _db: Session, **kwargs: Any
    ) -> SimpleNamespace:
        calls.append((workload_id, context, kwargs))
        return _completion(_planning_payload())

    monkeypatch.setattr(planning, "execute_llm", fake_execute)
    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=_INVENTION,
        category_ids=["vehicle"],
        jurisdictions=["KR", "US"],
    )

    assert calls[0][0] == PATENT_PRIOR_ART_SEARCH_PLAN_WORKLOAD_ID
    assert calls[0][1].app_id == "patent-prior-art"
    assert preview.source_queries[0].source_id == "category-vehicle-kr"
    assert "vehicle" in preview.source_queries[0].query_text.lower()
    compiled = compile_provider_queries(preview.plan, ["KR", "US"])
    assert compiled[0].purpose == "category_anchor"
    assert compiled[0].classification_codes == ("B60",)


def test_preview_never_falls_back_after_core_blocks_external_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    violation = AiGatewayPolicyViolation(
        reason_code="external_transfer_blocked",
        task_kind="patent_prior_art_search_plan",
    )
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(violation),
    )
    monkeypatch.setattr(
        planning,
        "_fallback_plan_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("policy blocks must not use planning fallback")
        ),
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        preview_patent_prior_art_search(
            _DB,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            invention_text=_INVENTION,
            category_ids=["vehicle"],
            jurisdictions=["KR"],
        )

    assert exc_info.value is violation


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("unknown registered workload"),
        RuntimeError("configured workload route unavailable"),
    ],
)
def test_preview_propagates_registered_workload_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(
        planning,
        "_fallback_plan_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("gateway failures must not use planning fallback")
        ),
    )

    with pytest.raises(type(failure)) as exc_info:
        preview_patent_prior_art_search(
            _DB,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            invention_text=_INVENTION,
            category_ids=["vehicle"],
            jurisdictions=["KR"],
        )

    assert exc_info.value is failure


def test_preview_uses_fallback_only_after_an_invalid_completed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: _raw_completion("not-json"),
    )

    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=_INVENTION,
        category_ids=["vehicle"],
        jurisdictions=["KR"],
    )

    assert preview.technology_summary == _INVENTION
    assert preview.source_queries[0].source_id == "category-vehicle-kr"


def test_preview_preserves_public_thirty_value_plan_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reviewed_keywords = [f"reviewed-term-{index:02d}" for index in range(30)]
    payload = _planning_payload()
    payload["keywords_en"] = reviewed_keywords
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: _completion(payload),
    )

    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=_INVENTION,
        category_ids=[],
        jurisdictions=["KR"],
    )

    assert planning.MAX_PLAN_VALUES == 30
    assert preview.plan.keywords_en.values == reviewed_keywords
    assert len(preview.plan.keywords_en.values) == 30

    reviewed_applicants = [f"Applicant {index:02d}" for index in range(30)]
    compiled = compile_provider_queries(
        _plan(keywords=["technical term"], applicants=reviewed_applicants),
        ["KR"],
    )
    applicant_focus = [query for query in compiled if query.purpose == "applicant_focus"]
    assert applicant_focus and applicant_focus[0].applicants == tuple(reviewed_applicants)
    # Broad calls stay applicant-free so the full prior-art field is retrieved.
    assert all(query.applicants == () for query in compiled if query.purpose != "applicant_focus")


def test_compile_provider_queries_rejects_an_empty_plan() -> None:
    with pytest.raises(ValueError, match="search plan must include"):
        compile_provider_queries(_plan(), ["KR"])


def test_compile_provider_queries_keeps_category_anchors_first_with_neutral_labels() -> None:
    compiled = compile_provider_queries(
        _plan(categories=["vehicle"], keywords=["thermal control"]),
        ["KR", "US"],
    )

    assert [query.purpose for query in compiled] == [
        "category_anchor",
        "category_anchor",
        "technical",
        "technical",
    ]
    assert [query.source_id for query in compiled] == [
        "category-vehicle-kr",
        "category-vehicle-us",
        "technical-kr",
        "technical-us",
    ]
    assert {query.source_label for query in compiled} == {"KIPRIS"}


def test_classification_without_explicit_applicant_never_adds_a_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: _completion(_planning_payload(code="B60H")),
    )
    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=_INVENTION,
        category_ids=[],
        jurisdictions=["KR"],
    )
    criteria = compile_provider_queries(preview.plan, ["KR"])[0].to_criteria()

    assert criteria.applicants == ()
    assert preview.plan.applicants.values == []


def test_unrelated_classification_gets_no_vehicle_context_unless_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: _completion(_planning_payload(code="H04L")),
    )
    unrelated = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=(
            "분산 노드 사이에서 암호화된 패킷을 라우팅하고 장애 시 경로를 전환하는 "
            "통신 프로토콜이며 H04L 분류를 대상으로 한다."
        ),
        category_ids=[],
        jurisdictions=["KR"],
    )
    unrelated_query = " ".join(item.query_text for item in unrelated.source_queries).lower()

    assert "vehicle" not in unrelated_query
    assert "자동차" not in unrelated_query
    assert "b60h" not in unrelated_query

    scoped = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=_INVENTION,
        category_ids=["vehicle"],
        jurisdictions=["KR"],
    )
    assert scoped.source_queries[0].source_id.startswith("category-vehicle")
    assert compile_provider_queries(scoped.plan, ["KR"])[0].classification_codes == ("B60",)


def test_only_explicit_applicant_values_reach_provider_criteria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: _completion(_planning_payload()),
    )
    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=f"{_INVENTION}\n출원인: 델타전자",
        category_ids=[],
        jurisdictions=["KR"],
    )
    compiled = compile_provider_queries(preview.plan, ["KR"])

    assert preview.plan.applicants.values == ["델타전자"]
    focus = [query for query in compiled if query.purpose == "applicant_focus"]
    assert focus and all(query.applicants == ("델타전자",) for query in focus)
    # The applicant filter is additive: broad calls never carry it.
    assert all(query.applicants == () for query in compiled if query.purpose != "applicant_focus")
    assert "ignored display text" not in compiled[0].query_text

    tampered_plan = preview.plan.model_copy(update={"display_query": "ignored display text"})
    assert all(
        "ignored display text" not in query.query_text
        for query in compile_provider_queries(tampered_plan, ["KR"])
    )


def test_document_applicants_add_focus_queries_without_narrowing_broad_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        planning,
        "execute_llm",
        lambda *_args, **_kwargs: _completion(_planning_payload()),
    )
    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=(
            f"{_INVENTION}\n"
            "1) 차량 메이커 : 폭스바겐, BMW 2) 공조 부품사 메이커 : 보그워너, 산덴, 한온시스템 등"
        ),
        category_ids=[],
        jurisdictions=["KR", "US"],
    )

    # Labelled makers become applicants (not keywords, not exclusions).
    assert preview.plan.applicants.values == [
        "폭스바겐",
        "BMW",
        "보그워너",
        "산덴",
        "한온시스템",
    ]

    compiled = compile_provider_queries(preview.plan, ["KR", "US"])
    broad = [q for q in compiled if q.purpose in {"category_anchor", "technical"}]
    focus = [q for q in compiled if q.purpose == "applicant_focus"]
    assert broad and all(q.applicants == () for q in broad)  # full prior-art coverage
    assert focus and all(q.applicants == tuple(preview.plan.applicants.values) for q in focus)
    assert {q.jurisdiction for q in focus} == {"KR", "US"}


def test_document_competitor_names_are_not_excluded_from_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _planning_payload()
    # The model keeps trying to exclude competitors (Korean and English, any case)
    # and document-meta words. Auto-generated exclusions are dropped wholesale.
    payload["excluded_terms"] = [
        "보그워너",
        "BorgWarner",
        "bogwarner",
        "BMW",
        "benchmarking",
        "산덴",
    ]
    monkeypatch.setattr(planning, "execute_llm", lambda *_args, **_kwargs: _completion(payload))
    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=f"{_INVENTION}\n경쟁사 : 보그워너, 산덴",
        category_ids=[],
        jurisdictions=["KR"],
    )

    # Competitors surface as applicants; no model-proposed exclusion is kept.
    assert "보그워너" in preview.plan.applicants.values
    assert "산덴" in preview.plan.applicants.values
    assert preview.plan.excluded_terms.values == []

    # No competitor name is ever NOT-ed out of a compiled provider query.
    for query in compile_provider_queries(preview.plan, ["KR"]):
        assert "NOT" not in query.query_text
        for name in ("보그워너", "산덴", "BorgWarner", "bogwarner", "BMW"):
            assert name not in query.query_text


def test_applicant_focus_queries_never_displace_broad_coverage() -> None:
    compiled = compile_provider_queries(
        _plan(keywords=["열교환기"], applicants=[f"Maker {index}" for index in range(3)]),
        ["KR", "US", "EP", "JP", "CN", "WO"],
    )

    assert len(compiled) <= planning.MAX_COMPILED_QUERIES
    technical = [q for q in compiled if q.purpose == "technical"]
    assert len(technical) == 6  # broad coverage guaranteed for every jurisdiction


def test_build_display_query_deduplicates_per_jurisdiction_repeats() -> None:
    compiled = compile_provider_queries(
        _plan(categories=["vehicle"], keywords=["thermal control"]),
        ["KR", "US", "JP"],
    )

    lines = planning.build_display_query(compiled).split("\n")
    # Three jurisdictions reuse the same two expressions (category + technical);
    # the display collapses the repeats instead of printing each six times.
    assert lines == list(dict.fromkeys(lines))
    assert len(lines) == 2


def test_classification_codes_are_capped_to_a_focused_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _planning_payload()
    # Model enumerates a whole subclass — 25 sequential H05B3 groups.
    enumerated = [f"H05B3/{group:02d}" for group in range(0, 50, 2)]
    payload["ipc_codes"] = enumerated
    payload["cpc_codes"] = enumerated
    monkeypatch.setattr(planning, "execute_llm", lambda *_args, **_kwargs: _completion(payload))
    preview = preview_patent_prior_art_search(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        invention_text=_INVENTION,
        category_ids=[],
        jurisdictions=["KR"],
    )

    assert 0 < len(preview.plan.ipc_codes.values) <= planning.MAX_CLASSIFICATION_CODES
    assert 0 < len(preview.plan.cpc_codes.values) <= planning.MAX_CLASSIFICATION_CODES


def test_cjk_phrases_are_not_quoted_in_provider_queries() -> None:
    compiled = compile_provider_queries(
        _plan(keywords=["필름형 수가열히터"], keywords_en=["vehicle heater"]),
        ["KR"],
    )
    query = compiled[0].query_text

    # KIPRIS returns zero hits for a quoted CJK phrase, so it must stay unquoted...
    assert "필름형 수가열히터" in query
    assert '"필름형 수가열히터"' not in query
    # ...while an ASCII phrase is still quoted so it stays a single token.
    assert '"vehicle heater"' in query


def test_cpc_is_lexical_context_but_never_a_kipris_ipc_filter() -> None:
    compiled = compile_provider_queries(
        _plan(
            keywords=["packet routing"],
            ipc_codes=["H04L12/58"],
            cpc_codes=["H04L67/10"],
        ),
        ["KR"],
    )
    criteria = compiled[0].to_criteria()

    assert criteria.classification_codes == ("H04L12/58",)
    assert "H04L67/10" in criteria.query


def test_reviewed_applicants_do_not_reorder_platform_ranking() -> None:
    candidates = [
        _patent(1, applicants=("Company Alpha",)),
        _patent(2, applicants=("Company Beta",)),
        _patent(3, applicants=("Company Gamma",)),
    ]

    class FixedRankingService:
        def rank(self, request: Any) -> Any:
            profile = CandidateRankingService().rank(request).profile
            return SimpleNamespace(
                candidates=tuple(
                    SimpleNamespace(
                        candidate=request.candidates[index],
                        rank=index + 1,
                        score=score,
                    )
                    for index, score in enumerate((1.0, 0.7, 0.0))
                ),
                profile=profile,
            )

    ranked, profile = pipeline._rank_candidates(
        cast(Any, FixedRankingService()),
        invention_text=_INVENTION,
        technology_summary="센서 기반 열관리 제어",
        search_plan=_plan(
            keywords=["열교환기", "송풍기"],
            applicants=["Company Beta"],
        ),
        candidates=candidates,
        max_candidates=3,
    )

    assert [item.result.publication_number for item in ranked] == ["KR-1", "KR-2", "KR-3"]
    assert [item.rank for item in ranked] == [1, 2, 3]
    assert "applicant_boost_applied" not in profile
    assert "applicant_boost_count" not in profile


def test_reviewed_plan_terms_precede_long_invention_in_ranking_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "execute_llm",
        lambda *_args, **_kwargs: _raw_completion("not-json"),
    )

    class RecordingRankingService(CandidateRankingService):
        query = ""

        def rank(self, request: Any) -> Any:
            self.query = request.query
            return super().rank(request)

    ranker = RecordingRankingService()
    run_patent_prior_art(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        title="ranking query order",
        invention_text="원문 전용 표식 " + ("아주 긴 발명 설명 " * 400),
        jurisdictions=["KR"],
        search_plan=_plan(
            keywords=["검토   키워드"],
            keywords_en=["reviewed   keyword"],
            ipc_codes=["b60h 1/00"],
            cpc_codes=["h04l 67/10"],
            applicants=["Applicant Never Rank"],
            excluded_terms=["Excluded Never Rank"],
            display_query="Display Never Rank",
        ),
        technology_summary="검토   기술 요약",
        max_candidates=1,
        kipris_client=cast(Any, _FakeKiprisClient([_patent(1)])),
        ranking_service=ranker,
    )

    expected_prefix = "\n".join(
        (
            "검토 키워드",
            "reviewed keyword",
            "B60H1/00",
            "H04L67/10",
            "검토 기술 요약",
        )
    )
    platform_visible_query = ranker.query[:MAX_QUERY_CHARS]
    assert ranker.query.startswith(f"{expected_prefix}\n원문 전용 표식")
    assert all(term in platform_visible_query for term in expected_prefix.splitlines())
    assert "Applicant Never Rank" not in ranker.query
    assert "Excluded Never Rank" not in ranker.query
    assert "Display Never Rank" not in ranker.query


def test_run_uses_registered_assessment_and_builds_neutral_deterministic_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workload_ids: list[str] = []

    def fake_execute(
        workload_id: str, _context: Any, _db: Session, **kwargs: Any
    ) -> SimpleNamespace:
        workload_ids.append(workload_id)
        request = json.loads(kwargs["messages"][1]["content"])
        return _completion(
            {
                "items": [
                    {
                        "candidate_id": item["candidate_id"],
                        "relevance_band": "high",
                        "summary": "센서 기반 제어 구성과 열교환기 작동 요소가 대응합니다.",
                        "match_reasons": ["센서 신호", "열교환기 제어"],
                    }
                    for item in request["candidates"]
                ]
            }
        )

    monkeypatch.setattr(pipeline, "execute_llm", fake_execute)
    result = run_patent_prior_art(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        title="선행기술 조사",
        invention_text=_INVENTION,
        jurisdictions=["KR"],
        search_plan=_plan(keywords=["열교환기", "송풍기"]),
        technology_summary="센서 기반 열관리 제어",
        max_candidates=5,
        kipris_client=cast(Any, _FakeKiprisClient([_patent(1)])),
        ranking_service=CandidateRankingService(),
    )
    assert workload_ids == [PATENT_PRIOR_ART_CANDIDATE_ASSESSMENT_WORKLOAD_ID]
    assert result.result_json == pipeline.serialise_result_payload(result.result_payload)
    assert "## 1. 과제 개요" in result.report_markdown
    assert "## 5. 후보별 요지시트" in result.report_markdown
    assert "## 9. 출처·한계 및 고지" in result.report_markdown
    assert "semantic_provider" not in result.ranking_profile
    assert "rerank_provider" not in result.ranking_profile


def test_assessment_never_falls_back_after_core_blocks_external_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    violation = AiGatewayPolicyViolation(
        reason_code="external_transfer_blocked",
        task_kind="patent_prior_art_candidate_assessment",
    )
    monkeypatch.setattr(
        pipeline,
        "execute_llm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(violation),
    )
    monkeypatch.setattr(
        pipeline,
        "_fallback_assessment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("policy blocks must not use assessment fallback")
        ),
    )

    with pytest.raises(AiGatewayPolicyViolation) as exc_info:
        run_patent_prior_art(
            _DB,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            title="blocked",
            invention_text=_INVENTION,
            jurisdictions=["KR"],
            search_plan=_plan(keywords=["열교환기"]),
            technology_summary="센서 기반 열관리 제어",
            max_candidates=5,
            kipris_client=cast(Any, _FakeKiprisClient([_patent(1)])),
            ranking_service=CandidateRankingService(),
        )

    assert exc_info.value is violation


@pytest.mark.parametrize(
    "failure",
    [
        ValueError("unknown registered workload"),
        RuntimeError("configured workload route unavailable"),
    ],
)
def test_assessment_propagates_registered_workload_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "execute_llm",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )
    monkeypatch.setattr(
        pipeline,
        "_fallback_assessment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("gateway failures must not use assessment fallback")
        ),
    )

    with pytest.raises(type(failure)) as exc_info:
        run_patent_prior_art(
            _DB,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            title="unavailable workload",
            invention_text=_INVENTION,
            jurisdictions=["KR"],
            search_plan=_plan(keywords=["열교환기"]),
            technology_summary="센서 기반 열관리 제어",
            max_candidates=5,
            kipris_client=cast(Any, _FakeKiprisClient([_patent(1)])),
            ranking_service=CandidateRankingService(),
        )

    assert exc_info.value is failure


def test_provider_calls_and_ranker_input_are_strictly_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "execute_llm",
        lambda *_args, **_kwargs: _raw_completion("not-json"),
    )
    provider = _FakeKiprisClient([_patent(index) for index in range(1, 151)], has_next=True)

    class RecordingRankingService(CandidateRankingService):
        def __init__(self) -> None:
            super().__init__()
            self.candidate_counts: list[int] = []

        def rank(self, request: Any) -> Any:
            self.candidate_counts.append(len(request.candidates))
            return super().rank(request)

    ranker = RecordingRankingService()
    jurisdictions = ["KR", "US", "EP", "WO", "CN", "JP"]
    run_patent_prior_art(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        title="bounded",
        invention_text=_INVENTION,
        jurisdictions=jurisdictions,
        search_plan=_plan(
            categories=["vehicle"],
            keywords=["열교환기", "송풍기"],
            ipc_codes=["B60H"],
        ),
        max_pages_per_query=2,
        max_candidates=17,
        kipris_client=cast(Any, provider),
        ranking_service=ranker,
    )

    assert len(provider.calls) == 12
    assert len(provider.calls) <= planning.MAX_COMPILED_QUERIES * 2
    assert {call[0].countries[0] for call in provider.calls} == set(jurisdictions)
    assert all(1 <= call[2] <= 30 for call in provider.calls)
    assert ranker.candidate_counts == [17]


def test_only_provider_timeout_is_exposed_as_retryable() -> None:
    class TimeoutClient:
        def search(self, *_args: Any, **_kwargs: Any) -> None:
            try:
                raise httpx.ReadTimeout("provider timeout")
            except httpx.ReadTimeout as error:
                raise KiprisError("provider unavailable") from error

    with pytest.raises(PatentPriorArtTransientError):
        run_patent_prior_art(
            _DB,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            title="timeout",
            invention_text=_INVENTION,
            jurisdictions=["KR"],
            search_plan=_plan(keywords=["열교환기"]),
            kipris_client=cast(Any, TimeoutClient()),
            ranking_service=CandidateRankingService(),
        )


def test_mixed_provider_errors_are_not_exposed_as_retryable() -> None:
    class MixedFailureClient:
        def search(self, criteria: Any, **_kwargs: Any) -> None:
            if criteria.countries == ("KR",):
                raise KiprisError("provider rejected the permanent query")
            try:
                raise httpx.ReadTimeout("provider timeout")
            except httpx.ReadTimeout as error:
                raise KiprisError("provider unavailable") from error

    with pytest.raises(KiprisError, match="permanent query"):
        run_patent_prior_art(
            _DB,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            title="mixed provider failure",
            invention_text=_INVENTION,
            jurisdictions=["KR", "US"],
            search_plan=_plan(keywords=["열교환기"]),
            kipris_client=cast(Any, MixedFailureClient()),
            ranking_service=CandidateRankingService(),
        )


def test_one_failing_jurisdiction_does_not_sink_the_whole_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline, "execute_llm", lambda *_args, **_kwargs: _raw_completion("not-json")
    )

    class PartialFailureClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, criteria: Any, *, page: int, page_size: int) -> PatentSearchPage:
            country = criteria.countries[0]
            self.calls.append(country)
            if country == "WO":
                raise KiprisError("provider rejected the WO query")
            results = (_patent(1, jurisdiction=country),)
            return PatentSearchPage(
                results=results,
                page=page,
                page_size=page_size,
                total_count=len(results),
                jurisdictions=(
                    PatentSearchJurisdictionPage(
                        jurisdiction=country,
                        total_count=len(results),
                        returned_count=len(results),
                        has_next=False,
                    ),
                ),
                has_next=False,
            )

    client = PartialFailureClient()
    result = run_patent_prior_art(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        title="partial failure",
        invention_text=_INVENTION,
        jurisdictions=["KR", "WO"],
        search_plan=_plan(keywords=["열교환기"]),
        max_candidates=5,
        kipris_client=cast(Any, client),
        ranking_service=CandidateRankingService(),
    )

    assert "WO" in client.calls  # the failing jurisdiction was attempted
    assert result.candidates  # KR results survived the WO failure
    assert all(candidate.jurisdiction == "KR" for candidate in result.candidates)
    failed_queries = [query for query in result.executed_queries if query.status == "failed"]
    assert [(query.jurisdiction, query.failure_code) for query in failed_queries] == [
        ("WO", "provider_unavailable")
    ]
    assert "KIPRIS/WO" in result.report_markdown
    assert "실패(누락)" in result.report_markdown


def test_search_stage_deadline_finishes_with_partial_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline, "execute_llm", lambda *_args, **_kwargs: _raw_completion("not-json")
    )
    monotonic_values = iter((100.0, 100.0, 700.0))
    monkeypatch.setattr(pipeline.time, "monotonic", lambda: next(monotonic_values))

    class DeadlineClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search(self, criteria: Any, *, page: int, page_size: int) -> PatentSearchPage:
            country = criteria.countries[0]
            self.calls.append(country)
            result = _patent(1, jurisdiction=country)
            return PatentSearchPage(
                results=(result,),
                page=page,
                page_size=page_size,
                total_count=1,
                jurisdictions=(
                    PatentSearchJurisdictionPage(
                        jurisdiction=country,
                        total_count=1,
                        returned_count=1,
                        has_next=False,
                    ),
                ),
                has_next=False,
            )

    client = DeadlineClient()
    result = run_patent_prior_art(
        _DB,
        workspace_id="workspace-1",
        actor_user_id="user-1",
        title="deadline partial",
        invention_text=_INVENTION,
        jurisdictions=["KR", "US"],
        search_plan=_plan(keywords=["열교환기"]),
        max_candidates=5,
        kipris_client=cast(Any, client),
        ranking_service=CandidateRankingService(),
    )

    assert pipeline.MAX_SEARCH_STAGE_SECONDS == 600
    assert client.calls == ["KR"]
    assert result.candidates
    assert [
        (query.jurisdiction, query.status, query.failure_code) for query in result.executed_queries
    ] == [
        ("KR", "succeeded", None),
        ("US", "failed", "provider_timeout"),
    ]


def test_cancellation_callback_stops_before_provider_access() -> None:
    provider = _FakeKiprisClient([_patent(1)])

    with pytest.raises(PatentPriorArtPipelineCancelled):
        run_patent_prior_art(
            _DB,
            workspace_id="workspace-1",
            actor_user_id="user-1",
            title="cancelled",
            invention_text=_INVENTION,
            jurisdictions=["KR"],
            search_plan=_plan(keywords=["열교환기"]),
            cancel_callback=lambda: True,
            kipris_client=cast(Any, provider),
            ranking_service=CandidateRankingService(),
        )

    assert provider.calls == []
