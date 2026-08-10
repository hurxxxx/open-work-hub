from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_do_api.domains.rag import application as rag_application
from ai_do_api.domains.rag.contracts import (
    RagAnswerMode,
    RagProjection,
    RagQueryRequest,
)
from ai_do_api.domains.rag import grounded_answer
from ai_do_api.domains.rag.grounded_answer import LlmGroundedAnswerSynthesizer
from ai_do_api.domains.rag.grounded_answer_assembly import GroundedAnswerAssembler
from ai_do_api.domains.rag.providers import RagProviderTransientError
from ai_do_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from ai_do_api.domains.rag.query_service import RagQueryService
from ai_do_api.domains.rag.service import RagService


def test_workspace_rag_query_wraps_provider_failures_as_unavailable(monkeypatch) -> None:
    class _FailingQueryService:
        def query(self, request, *, post_filter, grounded_answer_synthesizer=None):
            del request, post_filter, grounded_answer_synthesizer
            raise RagProviderTransientError("provider unavailable")

    monkeypatch.setattr(
        rag_application,
        "list_workspace_rag_sources",
        lambda *args, **kwargs: [
            {
                "source_kind": "manual",
                "resource_type": "docs_native_doc",
                "label": "Docs / Manual",
                "app_id": "docs",
            }
        ],
    )
    monkeypatch.setattr(
        rag_application,
        "resolve_workspace_runtime_enabled_app_ids",
        lambda db, workspace_id: {"chatbot", "docs"},
    )
    monkeypatch.setattr(
        rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test"
    )
    monkeypatch.setattr(
        rag_application, "resolve_default_collection_name", lambda settings: "rag-test"
    )
    monkeypatch.setattr(
        rag_application,
        "build_user_rag_post_filter",
        lambda db, user, **kwargs: lambda hit: True,
    )

    with pytest.raises(rag_application.RagUnavailableError) as exc_info:
        rag_application.query_workspace_rag(
            db=object(),
            workspace=SimpleNamespace(id="ws-1"),
            user=SimpleNamespace(id="user-1"),
            query="budget risk",
            answer_mode=RagAnswerMode.SEARCH_ONLY,
            source_kinds=[],
            filters={},
            top_k=8,
            include_binary_hits=False,
            settings=SimpleNamespace(rag_enabled=True),
            query_service=_FailingQueryService(),
        )
    assert exc_info.value.code == "rag.query_unavailable"
    assert exc_info.value.params["reason"] == "provider unavailable"


def test_query_service_marks_grounded_answer_as_degraded_when_synthesizer_returns_none() -> None:
    vector_index = FakeVectorIndexClient()
    embedding_client = FakeEmbeddingClient()
    rag_service = RagService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )
    rag_query = RagQueryService(
        vector_index=vector_index,
        embedding_client=embedding_client,
    )

    rag_service.sync_projection(
        RagProjection(
            workspace_id="ws-1",
            resource_type="doc",
            resource_id="doc-1",
            source_kind="manual",
            title="Budget Review",
            summary="Quarterly budget risk and spending review",
            text_content="Budget risk increased after supplier repricing.",
            visibility_refs=["workspace:ws-1"],
        ),
        collection="rag-grounded-answer",
    )

    class _NullSynthesizer:
        timeout_ms: int | None = -1

        def synthesize(self, *, query: str, hits, timeout_ms: int | None = None):
            del query, hits
            self.timeout_ms = timeout_ms
            return None

    synthesizer = _NullSynthesizer()
    response = rag_query.query(
        RagQueryRequest(
            collection="rag-grounded-answer",
            workspace_id="ws-1",
            query="budget risk",
            answer_mode=RagAnswerMode.GROUNDED_ANSWER,
            source_kinds=["manual"],
        ),
        grounded_answer_synthesizer=synthesizer,
    )

    assert response.hits
    assert response.grounded_answer is not None
    assert "Budget risk increased" in response.grounded_answer.text
    assert response.query_profile["grounded_answer_degraded"] is True
    assert synthesizer.timeout_ms is None


def test_grounded_answer_assembler_accepts_provider_schema_drift() -> None:
    answer = GroundedAnswerAssembler().assemble(
        raw_content=(
            '{"statements":[{"text":"복지제도 요약","citation_indexes":["1"],'
            '"confidence":0.9}],"unsupported_claims":[],"notes":"ignored"}'
        ),
        hits=[_hit()],
    )

    assert answer is not None
    assert answer.text == "복지제도 요약"
    assert [citation.resource_id for citation in answer.citations] == ["doc-1"]


def test_grounded_answer_stream_prompt_returns_plain_markdown_contract() -> None:
    messages = GroundedAnswerAssembler().build_stream_messages(
        query="복지제도 정리해줘",
        hits=[_hit()],
    )

    assert messages[0]["role"] == "system"
    assert "plain Markdown answer text only" in messages[0]["content"]
    assert "not JSON" in messages[0]["content"]
    assert "Do not include a separate sources" in messages[0]["content"]
    assert '<evidence index="1">' in messages[1]["content"]


def test_llm_grounded_answer_uses_task_token_budget(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_execute_llm(workload_id, context, db, **kwargs):
        captured["workload_id"] = workload_id
        captured["context"] = context
        captured["kwargs"] = kwargs
        captured["db"] = db
        completion = SimpleNamespace(
            text='{"statements":[{"text":"복지제도 요약","citation_indexes":[1]}],'
            '"unsupported_claims":[]}',
            finish_reason="stop",
        )
        return SimpleNamespace(completion=completion)

    monkeypatch.setattr(
        grounded_answer,
        "execute_llm",
        fake_execute_llm,
    )
    synthesizer = _llm_synthesizer()

    answer = synthesizer.synthesize(query="복지제도 정리해줘", hits=[_hit()])

    assert answer is not None
    assert answer.text == "복지제도 요약"
    assert captured["workload_id"] == "rag_grounded_answer"
    assert captured["context"].app_id == "rag"
    context_pack = captured["kwargs"]["context_pack"]
    assert context_pack.context_strategy == "rag_grounded_answer_evidence"
    assert context_pack.source_kinds == ("qna_doc",)
    assert context_pack.sensitivity_labels == ("internal",)
    assert context_pack.content_origin == "internal_context"
    assert captured["kwargs"].get("max_tokens") is None
    assert captured["kwargs"].get("timeout_seconds") is None


def test_llm_grounded_answer_rejects_truncated_completion(monkeypatch) -> None:
    def fake_execute_llm(workload_id, context, db, **kwargs):
        del workload_id, context, db, kwargs
        completion = SimpleNamespace(
            text='{"statements":[{"text":"잘린 답변","citation_indexes":[1]}]',
            finish_reason="length",
        )
        return SimpleNamespace(completion=completion)

    monkeypatch.setattr(
        grounded_answer,
        "execute_llm",
        fake_execute_llm,
    )
    synthesizer = _llm_synthesizer()

    with pytest.raises(ValueError, match="did not finish cleanly"):
        synthesizer.synthesize(query="복지제도 정리해줘", hits=[_hit()])


def _llm_synthesizer() -> LlmGroundedAnswerSynthesizer:
    return LlmGroundedAnswerSynthesizer(
        db=object(),
        workspace_id="ws-1",
        actor_user_id="user-1",
        principal_kind="user",
        principal_id="user-1",
        source="api.qna.ask",
    )


def _hit():
    return SimpleNamespace(
        source_kind="qna_doc",
        resource_type="qna_document",
        resource_id="doc-1",
        workspace_id="ws-1",
        title="복지제도 기준",
        summary="복지제도 기준",
        excerpt="건강검진, 가족수당, 경조비, 장기근속 포상",
        score=0.9,
        citation="[첨부: 복지제도.pdf] [p.1]",
    )
