from __future__ import annotations

from types import SimpleNamespace

import pytest

from aidoo_api.domains.rag import application as rag_application
from aidoo_api.domains.rag.contracts import (
    RagAnswerMode,
    RagProjection,
    RagQueryRequest,
    RagQueryResponse,
)
from aidoo_api.domains.rag.grounded_answer import LlmGroundedAnswerSynthesizer
from aidoo_api.domains.rag.providers import RagProviderTransientError
from aidoo_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from aidoo_api.domains.rag.query_service import RagQueryService
from aidoo_api.domains.rag.service import RagService


def test_llm_grounded_answer_synthesizer_keeps_only_citation_backed_statements(monkeypatch) -> None:
    hit = SimpleNamespace(
        resource_id="doc-1",
        source_kind="manual",
        summary="Supplier repricing increased the budget risk.",
        title="Budget Review",
        citation="doc-1:0",
    )

    def _fake_complete_chat(*args, **kwargs):
        del args, kwargs
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"statements":['
                            '{"text":"예산 리스크가 상승했습니다.","citation_indexes":[1]},'
                            '{"text":"증거 없는 문장입니다.","citation_indexes":[]}'
                            '],"unsupported_claims":["확인되지 않은 주장"]}'
                        )
                    )
                )
            ]
        )
        return response, None, None

    monkeypatch.setattr(
        "aidoo_api.domains.rag.grounded_answer.complete_chat",
        _fake_complete_chat,
    )

    synthesizer = LlmGroundedAnswerSynthesizer(
        db=object(),
        workspace_id="ws-1",
        actor_user_id="user-1",
        principal_kind="user",
        principal_id="user-1",
        source="test.rag",
        conversation_id="conversation-1",
        agent_run_id="agent-run-1",
    )

    answer = synthesizer.synthesize(query="현재 리스크는?", hits=[hit], timeout_ms=1200)

    assert answer is not None
    assert answer.text == "예산 리스크가 상승했습니다."
    assert answer.citations[0].resource_id == "doc-1"
    assert answer.unsupported_claims == ["확인되지 않은 주장"]


def test_llm_grounded_answer_synthesizer_routes_through_llm_runtime(monkeypatch) -> None:
    captured: dict[str, object] = {}
    hit = SimpleNamespace(
        resource_id="doc-1",
        source_kind="manual",
        summary="Budget risk increased after supplier repricing.",
        title="Budget Review",
        citation="doc-1:0",
    )

    def _fake_complete_chat(context, db, *, messages, **kwargs):
        captured["context"] = context
        captured["db"] = db
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=(
                            '{"statements":['
                            '{"text":"예산 리스크가 상승했습니다.","citation_indexes":[1]}'
                            '],"unsupported_claims":[]}'
                        )
                    )
                )
            ]
        )
        return response, None, None

    monkeypatch.setattr(
        "aidoo_api.domains.rag.grounded_answer.complete_chat",
        _fake_complete_chat,
    )

    synthesizer = LlmGroundedAnswerSynthesizer(
        db=object(),
        workspace_id="ws-1",
        actor_user_id="user-1",
        principal_kind="user",
        principal_id="user-1",
        source="api.stream",
        conversation_id="conversation-1",
        agent_run_id="agent-run-1",
    )

    answer = synthesizer.synthesize(query="현재 리스크는?", hits=[hit], timeout_ms=1200)

    assert answer is not None
    context = captured["context"]
    kwargs = captured["kwargs"]
    assert context.task_kind == "rag_grounded_answer"
    assert context.source == "api.stream"
    assert context.workspace_id == "ws-1"
    assert context.actor_user_id == "user-1"
    assert context.principal_kind == "user"
    assert context.principal_id == "user-1"
    assert kwargs["agent_run_id"] == "agent-run-1"
    assert kwargs["conversation_id"] == "conversation-1"
    assert kwargs["timeout_seconds"] == pytest.approx(1.2)
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["temperature"] == 0
    assert kwargs["max_tokens"] == 1200


def test_workspace_rag_query_builds_llm_grounded_answer_synthesizer(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _StubQueryService:
        def query(self, request, *, post_filter, grounded_answer_synthesizer=None):
            del post_filter
            captured["request"] = request
            captured["grounded_answer_synthesizer"] = grounded_answer_synthesizer
            return RagQueryResponse(
                query=request.query,
                answer_mode=request.answer_mode,
                hits=[],
                grounded_answer=None,
                sources_used=[],
                query_profile={},
                latency_ms=0,
            )

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
        "resolve_workspace_enabled_app_ids",
        lambda db, workspace_id: {"ai", "docs"},
    )
    monkeypatch.setattr(rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test")
    monkeypatch.setattr(rag_application, "resolve_default_collection_name", lambda settings: "rag-test")
    monkeypatch.setattr(rag_application, "build_user_rag_post_filter", lambda db, user: lambda hit: True)

    response = rag_application.query_workspace_rag(
        db=object(),
        workspace=SimpleNamespace(id="ws-1"),
        user=SimpleNamespace(id="user-1"),
        query="budget risk",
        answer_mode=RagAnswerMode.GROUNDED_ANSWER,
        source_kinds=[],
        filters={},
        top_k=8,
        include_binary_hits=False,
        settings=SimpleNamespace(rag_enabled=True),
        query_service=_StubQueryService(),
        source="api.stream",
        principal_kind="user",
        principal_id="user-1",
        conversation_id="conversation-1",
        agent_run_id="agent-run-1",
    )

    assert response.answer_mode == RagAnswerMode.GROUNDED_ANSWER
    assert isinstance(captured["grounded_answer_synthesizer"], LlmGroundedAnswerSynthesizer)


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
        "resolve_workspace_enabled_app_ids",
        lambda db, workspace_id: {"ai", "docs"},
    )
    monkeypatch.setattr(rag_application, "ensure_default_collection_ready", lambda *args, **kwargs: "rag-test")
    monkeypatch.setattr(rag_application, "resolve_default_collection_name", lambda settings: "rag-test")
    monkeypatch.setattr(rag_application, "build_user_rag_post_filter", lambda db, user: lambda hit: True)

    with pytest.raises(rag_application.RagUnavailableError, match="RAG query is unavailable"):
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
        def synthesize(self, *, query: str, hits, timeout_ms: int | None = None):
            del query, hits, timeout_ms
            return None

    response = rag_query.query(
        RagQueryRequest(
            collection="rag-grounded-answer",
            workspace_id="ws-1",
            query="budget risk",
            answer_mode=RagAnswerMode.GROUNDED_ANSWER,
            source_kinds=["manual"],
        ),
        grounded_answer_synthesizer=_NullSynthesizer(),
    )

    assert response.hits
    assert response.grounded_answer is None
    assert response.query_profile["grounded_answer_degraded"] is True
