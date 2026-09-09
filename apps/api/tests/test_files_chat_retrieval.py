from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from dev_accounts import auth_headers, dev_login

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy
from open_work_hub_api.domains.files import chat_retrieval
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.search import FileSearchRuntime, FileSearchUnavailable
from open_work_hub_api.domains.retrieval.contracts import RetrievalHit
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


def test_file_chat_evidence_raises_existing_unavailable_error_for_closed_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _closed_runtime(_db):
        raise FileSearchUnavailable("active_pair_missing")

    monkeypatch.setattr(
        chat_retrieval,
        "resolve_file_search_runtime",
        _closed_runtime,
    )

    with pytest.raises(FileSearchUnavailable, match="active_pair_missing"):
        chat_retrieval.query_file_chat_evidence(
            object(),  # type: ignore[arg-type]
            user=SimpleNamespace(),
            query="제동 제어 기준",
        )


def test_file_chat_evidence_uses_files_only_natural_language_hybrid_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FileSearchRuntime(
        keyword_client=object(),  # type: ignore[arg-type]
        rag_query_service=object(),  # type: ignore[arg-type]
        rag_collection="files-v1-active",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        chat_retrieval,
        "resolve_file_search_runtime",
        lambda _db: runtime,
    )

    def _query_retrieval(_db, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            hits=[],
            trace_id="files-chat-trace",
            latency_ms=17,
            profile=SimpleNamespace(backend_profiles={}),
        )

    monkeypatch.setattr(chat_retrieval, "query_retrieval", _query_retrieval)

    result = chat_retrieval.query_file_chat_evidence(
        object(),  # type: ignore[arg-type]
        user=SimpleNamespace(id="user-1"),
        query="접근 권한 관리 기준은 무엇인가요?",
        limit=3,
        conversation_id="conversation-1",
    )

    request = captured["request"]
    assert request.strategy.value == "hybrid"
    assert request.sources == ["keyword", "generic_rag"]
    assert request.source_kinds == ["files"]
    assert request.filters == {"keyword": {"entity_types": ["file"]}}
    assert request.top_k == chat_retrieval.MAX_FILE_CHAT_EVIDENCE_CANDIDATES
    assert request.answer_mode.value == "search-only"
    assert captured["source"] == "api.files.chat.evidence"
    assert captured["conversation_id"] == "conversation-1"
    assert captured["keyword_search_client"] is runtime.keyword_client
    assert captured["keyword_evaluation_entity_types"] == ("file",)
    # Retrieval maps this false value to the natural-language OR/30% BM25 policy.
    assert captured["keyword_strict_text_match"] is False
    assert captured["rag_allowed_unlisted_source_kinds"] == frozenset({"files"})
    assert captured["rag_query_service"] is runtime.rag_query_service
    assert captured["rag_collection"] == "files-v1-active"
    assert captured["partitioned_generation"] is True
    assert result.items == ()
    assert result.trace_id == "files-chat-trace"
    assert result.latency_ms == 17


def test_file_chat_evidence_fails_closed_for_low_confidence_rerank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FileSearchRuntime(
        keyword_client=object(),  # type: ignore[arg-type]
        rag_query_service=object(),  # type: ignore[arg-type]
        rag_collection="files-v1-active",
    )
    monkeypatch.setattr(
        chat_retrieval,
        "resolve_file_search_runtime",
        lambda _db: runtime,
    )
    monkeypatch.setattr(
        chat_retrieval,
        "query_retrieval",
        lambda _db, **_kwargs: SimpleNamespace(
            hits=[
                _retrieval_hit(
                    file_id="irrelevant-file",
                    filename="unrelated.pdf",
                    excerpt="대한민국과 관계없는 내용",
                )
            ],
            trace_id="low-confidence-trace",
            latency_ms=11,
            profile=SimpleNamespace(
                backend_profiles={
                    "rerank": {
                        "applied": False,
                        "degraded": True,
                        "score_semantics": "normalized_relevance",
                        "error_type": "LowConfidenceRerankScores",
                    }
                }
            ),
        ),
    )

    result = chat_retrieval.query_file_chat_evidence(
        object(),  # type: ignore[arg-type]
        user=SimpleNamespace(id="user-1"),
        query="대한민국의 수도는 어디야?",
    )

    assert result.items == ()
    assert result.trace_id == "low-confidence-trace"
    assert result.latency_ms == 11


def test_file_chat_evidence_keeps_only_calibrated_relevant_hits() -> None:
    relevant = _retrieval_hit(
        file_id="relevant-file",
        filename="relevant.pdf",
        excerpt="질문에 직접 답하는 근거",
        methods=["semantic", "cross_encoder"],
        score=0.8,
    )
    low_relevance = _retrieval_hit(
        file_id="low-file",
        filename="low.pdf",
        excerpt="무관한 근거",
        methods=["semantic", "cross_encoder"],
        score=0.000001,
    )

    filtered = chat_retrieval._filter_file_chat_relevance(
        [relevant, low_relevance],
        rerank_profile={
            "applied": True,
            "degraded": False,
            "score_semantics": "normalized_relevance",
        },
    )

    assert filtered == [relevant]


@pytest.mark.parametrize(
    "rerank_profile",
    [
        None,
        {},
        {
            "applied": True,
            "degraded": False,
            "score_semantics": "unknown",
        },
        {
            "applied": False,
            "degraded": True,
            "score_semantics": "normalized_relevance",
            "error_type": "InvalidRerankScores",
        },
        {
            "applied": False,
            "degraded": True,
            "score_semantics": "normalized_relevance",
            "error_type": "UninformativeRerankScores",
        },
    ],
)
def test_file_chat_evidence_rejects_uncalibrated_rerank_profiles(
    rerank_profile: object,
) -> None:
    hit = _retrieval_hit(
        file_id="candidate-file",
        filename="candidate.pdf",
        excerpt="후보 근거",
    )

    assert (
        chat_retrieval._filter_file_chat_relevance(
            [hit],
            rerank_profile=rerank_profile,
        )
        == []
    )


def test_file_chat_evidence_hydrates_source_metadata_and_bounds_context(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded = _upload_company_file(
        client,
        corpus_name="Chat evidence hydration",
        filename="source-fresh-policy.pdf",
    )

    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.login_id == "administrator"))
        file = db.get(FileManagerFile, uploaded["id"])
        assert user is not None and file is not None
        file.filename = "renamed-source-fresh-policy.pdf"
        db.commit()

        _stub_retrieval(
            monkeypatch,
            hits=[
                _retrieval_hit(
                    file_id=file.id,
                    filename="stale-index-name.pdf",
                    excerpt="근거 " + ("x" * 3_000),
                    locator="Slide 7",
                    methods=[
                        "bm25",
                        "semantic",
                        "dense_vector",
                        "rrf",
                        "cross_encoder",
                    ],
                )
            ],
        )

        result = chat_retrieval.query_file_chat_evidence(
            db,
            user=user,
            query="근거를 알려줘",
        )

    assert len(result.items) == 1
    item = result.items[0]
    assert item.file_id == uploaded["id"]
    assert item.filename == "renamed-source-fresh-policy.pdf"
    assert item.locator == "Slide 7"
    assert len(item.excerpt) == chat_retrieval.MAX_FILE_CHAT_EVIDENCE_EXCERPT_CHARS
    assert item.methods == (
        "bm25",
        "semantic",
        "dense_vector",
        "rrf",
        "cross_encoder",
    )


def test_file_chat_evidence_filters_candidate_after_app_admission_revoke(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded = _upload_company_file(
        client,
        corpus_name="Company chat evidence",
        filename="private-source.txt",
    )
    dev_login(client, "delivery-hub-member")

    with get_session_factory()() as db:
        user = db.scalar(
            select(User).where(User.email == "delivery-hub-member@open-work-hub.local")
        )
        assert user is not None
        policy = db.get(AppAccessPolicy, "files")
        assert policy is not None
        policy.audience = "selected"
        db.commit()
        _stub_retrieval(
            monkeypatch,
            hits=[
                _retrieval_hit(
                    file_id=uploaded["id"],
                    filename="private-source.txt",
                    excerpt="PRIVATE-SOURCE-CONTEXT",
                )
            ],
        )

        result = chat_retrieval.query_file_chat_evidence(
            db,
            user=user,
            query="secret",
        )

    assert result.items == ()


def test_file_chat_evidence_rechecks_acl_after_hydration(
    client: TestClient,
    in_memory_object_storage: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uploaded = _upload_company_file(
        client,
        corpus_name="Concurrent chat evidence revoke",
        filename="revoked-evidence.txt",
    )
    _stub_retrieval(
        monkeypatch,
        hits=[
            _retrieval_hit(
                file_id=uploaded["id"],
                filename="revoked-evidence.txt",
                excerpt="CONCURRENT-REVOKE-SECRET",
            )
        ],
    )
    original_loader = chat_retrieval._load_file_chat_sources
    revoke_triggered = False

    def _load_then_revoke(db, file_ids):
        nonlocal revoke_triggered
        sources = original_loader(db, file_ids)
        with get_session_factory().begin() as revoke_db:
            user = revoke_db.scalar(select(User).where(User.login_id == "administrator"))
            assert user is not None
            files_service.delete_file(
                revoke_db,
                user=user,
                file_id=uploaded["id"],
            )
        revoke_triggered = True
        return sources

    monkeypatch.setattr(
        chat_retrieval,
        "_load_file_chat_sources",
        _load_then_revoke,
    )

    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.login_id == "administrator"))
        assert user is not None
        result = chat_retrieval.query_file_chat_evidence(
            db,
            user=user,
            query="revoked evidence",
        )

    assert revoke_triggered is True
    assert result.items == ()


def _upload_company_file(
    client: TestClient,
    *,
    corpus_name: str,
    filename: str,
) -> dict[str, object]:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": corpus_name},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()
    upload_response = client.post(
        "/api/v1/files/upload",
        headers=headers,
        data={
            "visibility": "company",
            "company_admin_read_acknowledged": True,
            "corpus_id": corpus["id"],
        },
        files={"file": (filename, b"source", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    return upload_response.json()


def _stub_retrieval(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hits: list[RetrievalHit],
) -> None:
    monkeypatch.setattr(
        chat_retrieval,
        "resolve_file_search_runtime",
        lambda _db: FileSearchRuntime(
            keyword_client=object(),  # type: ignore[arg-type]
            rag_query_service=object(),  # type: ignore[arg-type]
            rag_collection="files-v1-active",
        ),
    )
    monkeypatch.setattr(
        chat_retrieval,
        "query_retrieval",
        lambda _db, **_kwargs: SimpleNamespace(
            hits=hits,
            trace_id="trace-files-chat",
            latency_ms=3,
            profile=SimpleNamespace(
                backend_profiles={
                    "rerank": {
                        "applied": True,
                        "degraded": False,
                        "score_semantics": "normalized_relevance",
                    }
                }
            ),
        ),
    )


def _retrieval_hit(
    *,
    file_id: str,
    filename: str,
    excerpt: str,
    locator: str | None = None,
    methods: list[str] | None = None,
    score: float = 0.8,
) -> RetrievalHit:
    return RetrievalHit(
        source="generic_rag",
        source_kind="files",
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id=file_id,
        title=filename,
        excerpt=excerpt,
        citation=f"{file_id}:text:0",
        methods=methods or ["semantic", "dense_vector", "cross_encoder"],
        score=score,
        metadata={"locator_label": locator} if locator else {},
    )
