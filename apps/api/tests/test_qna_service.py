from __future__ import annotations

import asyncio
from types import SimpleNamespace

from open_alm_api.core.llm_adapters import StreamChunk
from open_alm_api.domains.qna import service
from open_alm_api.domains.rag.contracts import (
    RagAnswerMode,
    RagGroundedAnswer,
    RagQueryHit,
    RagQueryResponse,
    RagScopeKind,
)


def test_normalize_attachment_names_strips_path_fragments_and_dedupes() -> None:
    assert service.normalize_attachment_names(
        [
            "IMG_160944.png",
            "/IMG_160944.png",
            r"C:\temp\report.pdf",
            "folder/report.pdf?download=1",
            "folder/report.pdf",
        ]
    ) == ["IMG_160944.png", "report.pdf"]


def test_qna_url_lookup_answer_distinguishes_welfare_mall_urls() -> None:
    answer = service.build_qna_url_lookup_answer(
        query="복지몰 주소는?",
        hits=[
            _qna_hit(
                resource_id="notice-1",
                title="복지포인트 제도 도입 [안내]",
                excerpt=(
                    "※ 복지카드 온라인 신청 URL "
                    "1) 신한은행 다드림 LOVE카드 : https://shcard.io/OPEN ALM "
                    "2) 신한은행 다드림 RPM+ Platinum# 카드 : "
                    "https://shcard.io/OPEN ALMRPM "
                    "※ 복지몰 URL : https://open-alm.ezwel.com "
                    "→ 본인인증 완료시 카드 자동 연동"
                ),
                score=0.69,
            ),
            _qna_hit(
                resource_id="notice-2",
                title="LG복지몰 & 제주신화월드 이용 [안내]",
                excerpt=(
                    "1) LG복지몰 : https://well.lglifecare.com/auth/login "
                    "초기 ID : 사번(대문자) / PW : 생년월일 6자리 "
                    "2) 제주신화월드 : https://shorturl.at/bQXrH "
                    "LG복지몰 바로가기 https://well.lglifecare.com/auth/login접속"
                ),
                score=0.1,
            ),
        ],
    )

    assert answer is not None
    assert "복지몰: https://open-alm.ezwel.com" in answer.text
    assert "LG복지몰: https://well.lglifecare.com/auth/login" in answer.text
    assert "https://shcard.io/OPEN ALM" not in answer.text
    assert "https://shcard.io/OPEN ALMRPM" not in answer.text
    assert "https://shorturl.at/bQXrH" not in answer.text
    assert answer.unsupported_claims == []
    assert [citation.resource_id for citation in answer.citations] == [
        "notice-1",
        "notice-2",
    ]


def test_qna_url_lookup_answer_filters_by_specific_url_label() -> None:
    answer = service.build_qna_url_lookup_answer(
        query="LG복지몰 주소는?",
        hits=[
            _qna_hit(
                resource_id="notice-1",
                title="복지포인트 제도 도입 [안내]",
                excerpt="※ 복지몰 URL : https://open-alm.ezwel.com",
                score=0.69,
            ),
            _qna_hit(
                resource_id="notice-2",
                title="LG복지몰 & 제주신화월드 이용 [안내]",
                excerpt="1) LG복지몰 : https://well.lglifecare.com/auth/login",
                score=0.1,
            ),
        ],
    )

    assert answer is not None
    assert "https://well.lglifecare.com/auth/login" in answer.text
    assert "https://open-alm.ezwel.com" not in answer.text
    assert [citation.resource_id for citation in answer.citations] == ["notice-2"]


def test_ask_question_rejects_degraded_grounded_answer(monkeypatch) -> None:
    default_answer = RagGroundedAnswer(
        text="건강검진, 예방접종 등 - 질병치료 목적 외 한방 약제비...",
        citations=[],
        sources_used=["qna_doc"],
    )
    hit = _qna_hit(
        resource_id="welfare-1",
        title="복지제도 기준",
        excerpt=(
            "가족수당 지원 : 3개월 이상 근속자 중 부모, 배우자, 자녀 요건에 따라 지급 "
            "건강검진 : 정기검진 1회/년, 종합검진은 40세 이상자 및 10년 이상 근속자 대상"
        ),
        score=0.7,
    )

    def fake_query_company_rag(*args, **kwargs):
        return RagQueryResponse(
            query="복지제도 정리해줘",
            answer_mode=RagAnswerMode.GROUNDED_ANSWER,
            hits=[hit],
            grounded_answer=default_answer,
            sources_used=["qna_doc"],
            query_profile={"grounded_answer_degraded": True},
        )

    monkeypatch.setattr(
        service.rag_application,
        "query_company_rag",
        fake_query_company_rag,
    )
    monkeypatch.setattr(
        service.rag_application,
        "resolve_ai_gateway_workspace_id",
        lambda db, user: "ws-1",
    )

    try:
        service.ask_question(
            None,
            user=object(),
            question="복지제도 정리해줘",
        )
    except service.QnaAnswerGenerationError:
        pass
    else:
        raise AssertionError("degraded Q&A answers must not fall back to excerpts")


def test_streamed_qna_answer_uses_search_hits_as_final_citations() -> None:
    response = RagQueryResponse(
        query="복지제도 정리해줘",
        answer_mode=RagAnswerMode.SEARCH_ONLY,
        hits=[
            _qna_hit(
                resource_id="welfare-1",
                title="복지제도 기준",
                excerpt="기숙사, 학자금, 통근버스, 건강검진을 지원한다.",
                score=0.7,
            )
        ],
    )

    grounded = service._with_qna_answer(
        service._as_qna_grounded_response(response),
        RagGroundedAnswer(
            text="복지제도는 기숙사, 학자금, 통근버스, 건강검진 지원으로 구성됩니다.",
            citations=service._qna_citations_from_hits(response.hits),
            unsupported_claims=[],
            sources_used=["qna_doc"],
        ),
        query_profile_flag="qna_streamed_answer",
    )

    assert grounded.answer_mode == RagAnswerMode.GROUNDED_ANSWER
    assert grounded.grounded_answer is not None
    assert grounded.grounded_answer.citations[0].resource_id == "welfare-1"
    assert grounded.query_profile["qna_streamed_answer"] is True


def test_stream_question_answer_emits_content_deltas_and_final_response(monkeypatch) -> None:
    hit = _qna_hit(
        resource_id="welfare-1",
        title="복지제도 기준",
        excerpt="기숙사, 학자금, 통근버스, 건강검진을 지원한다.",
        score=0.7,
    )
    captured: dict[str, object] = {}

    def fake_search_question_evidence(*args, **kwargs):
        captured["top_k"] = kwargs["top_k"]
        return RagQueryResponse(
            query=kwargs["question"],
            answer_mode=RagAnswerMode.SEARCH_ONLY,
            hits=[hit],
            query_profile={"returned_hit_count": 1},
        )

    async def fake_stream_llm(workload_id, context, db, **kwargs):
        captured["workload_id"] = workload_id
        captured["context"] = context
        captured["kwargs"] = kwargs
        captured["db"] = db
        yield StreamChunk(kind="content", text="복지제도는 "), object(), object()
        yield StreamChunk(kind="content", text="건강검진을 지원합니다."), object(), object()
        yield StreamChunk(kind="done", finish_reason="stop"), object(), object()

    monkeypatch.setattr(
        service,
        "search_question_evidence",
        fake_search_question_evidence,
    )
    monkeypatch.setattr(
        service,
        "stream_llm",
        fake_stream_llm,
    )
    monkeypatch.setattr(
        service.rag_application,
        "resolve_ai_gateway_workspace_id",
        lambda db, user: "ws-1",
    )

    async def collect_events():
        return [
            event
            async for event in service.stream_question_answer(
                None,
                user=SimpleNamespace(id="user-1"),
                question="복지제도 정리해줘",
                top_k=20,
            )
        ]

    events = asyncio.run(collect_events())

    assert captured["top_k"] == 20
    assert [event.text for event in events if isinstance(event, service.QnaAnswerDelta)] == [
        "복지제도는 ",
        "건강검진을 지원합니다.",
    ]
    completed = next(event for event in events if isinstance(event, service.QnaAnswerCompleted))
    assert completed.response.answer_mode == RagAnswerMode.GROUNDED_ANSWER
    assert completed.response.grounded_answer is not None
    assert completed.response.grounded_answer.text == "복지제도는 건강검진을 지원합니다."
    assert completed.response.grounded_answer.citations[0].resource_id == "welfare-1"
    assert captured["workload_id"] == "rag_grounded_answer"
    context_pack = captured["kwargs"]["context_pack"]
    assert captured["context"].app_id == "rag"
    assert context_pack.context_strategy == "rag_grounded_answer_stream_evidence"
    assert context_pack.source_kinds == ("qna_doc",)
    assert context_pack.sensitivity_labels == ("internal",)
    assert context_pack.content_origin == "internal_context"


def _qna_hit(
    *,
    resource_id: str,
    title: str,
    excerpt: str,
    score: float,
) -> RagQueryHit:
    return RagQueryHit(
        scope_kind=RagScopeKind.COMPANY,
        source_kind="qna_doc",
        resource_type="qna_document",
        resource_id=resource_id,
        workspace_id=None,
        title=title,
        summary=excerpt,
        excerpt=excerpt,
        score=score,
    )
