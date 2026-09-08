from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, event, select

from dev_accounts import auth_headers, content_headers, dev_login

from open_work_hub_api.core.db import get_engine, get_session_factory
from open_work_hub_api.domains.auth.models import CompanyAppControl, User
from open_work_hub_api.domains.auth.app_access_models import AppAccessPolicy, AppUserGrant
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.models import (
    FileManagerFile,
    FileManagerFileSourceMetadata,
)
from open_work_hub_api.domains.files import search as file_search
from open_work_hub_api.domains.files.external_projection import safe_external_source_metadata
from open_work_hub_api.domains.files.router import require_file_search_runtime
from open_work_hub_api.domains.files.search import FileSearchRuntime
from open_work_hub_api.domains.files.search_projection import build_file_search_document
from open_work_hub_api.domains.rag.contracts import RagChunk, RagProjection, RagScopeKind
from open_work_hub_api.domains.rag.providers.fake import FakeEmbeddingClient, FakeVectorIndexClient
from open_work_hub_api.domains.rag.query_service import RagQueryService
from open_work_hub_api.domains.rag.service import RagService
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordSearchHit,
    KeywordSearchQuery,
    KeywordSearchResult,
)
from open_work_hub_api.domains.retrieval.runtime_binding import (
    PartitionedRetrievalRuntimeUnavailable,
)


_FILES_SEARCH_PATH = "/api/v1/files/search"


class _KeywordBackend:
    def __init__(
        self,
        document: dict[str, object] | list[tuple[dict[str, object], float]],
    ) -> None:
        self.documents = [(document, 17.25)] if isinstance(document, dict) else list(document)
        self.last_query: KeywordSearchQuery | None = None

    def index_exists(self) -> bool:
        return True

    def open_point_in_time(self, *, keep_alive: str = "1m") -> str:
        assert keep_alive == "1m"
        return "files-search-pit"

    def close_point_in_time(self, point_in_time_id: str) -> None:
        assert point_in_time_id == "files-search-pit"

    def search(self, query: KeywordSearchQuery) -> KeywordSearchResult:
        self.last_query = query
        return KeywordSearchResult(
            hits=tuple(
                KeywordSearchHit(
                    document=document,
                    score=score,
                    sort_values=(score, str(document["entity_id"])),
                )
                for document, score in self.documents
            )
        )


class _RecordingVectorBackend(FakeVectorIndexClient):
    def __init__(self) -> None:
        super().__init__()
        self.last_query = None
        self.result_counts: list[int] = []

    def query(self, *, request, timeout_seconds=None):
        self.last_query = request
        result = super().query(request=request, timeout_seconds=timeout_seconds)
        self.result_counts.append(len(result))
        return result


def test_file_search_runtime_binds_the_validated_partitioned_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = SimpleNamespace(
        keyword_search_client=object(),
        rag_query_service=object(),
        rag_collection="files-v1-release",
    )
    monkeypatch.setattr(file_search, "FILES_RETRIEVAL_ACTIVE", True)
    monkeypatch.setattr(
        file_search,
        "resolve_partitioned_files_query_runtime",
        lambda db: expected,
    )

    runtime = file_search.resolve_file_search_runtime(object())

    assert runtime.keyword_client is expected.keyword_search_client
    assert runtime.rag_query_service is expected.rag_query_service
    assert runtime.rag_collection == "files-v1-release"


def test_file_search_runtime_maps_generation_failure_without_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(file_search, "FILES_RETRIEVAL_ACTIVE", True)

    def _fail_closed(db):
        del db
        raise PartitionedRetrievalRuntimeUnavailable(reason="release_cohort_mismatch")

    monkeypatch.setattr(file_search, "resolve_partitioned_files_query_runtime", _fail_closed)

    with pytest.raises(file_search.FileSearchUnavailable, match="release_cohort_mismatch"):
        file_search.resolve_file_search_runtime(object())


def test_files_search_fails_closed_before_partitioned_generations_are_active(
    client: TestClient,
) -> None:
    session = dev_login(client, "administrator")

    response = client.post(
        _FILES_SEARCH_PATH,
        headers=auth_headers(session["token"]),
        json={"query": "접근 권한 관리", "strategy": "hybrid"},
    )

    assert response.status_code == 503, response.text
    assert response.json()["code"] == "files.search_unavailable"


@pytest.mark.parametrize("strategy", ("keyword", "semantic", "hybrid"))
def test_files_search_returns_200_empty_for_healthy_active_empty_generation(
    client: TestClient,
    strategy: str,
) -> None:
    session = dev_login(client, "administrator")
    vector_backend = _RecordingVectorBackend()
    rag_query_service = RagQueryService(
        vector_index=vector_backend,
        embedding_client=FakeEmbeddingClient(dimensions=32),
        rerank_client=None,
        query_timeout_ms=5_000,
    )
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=_KeywordBackend([]),
        rag_query_service=rag_query_service,
        rag_collection="files-empty-active-generation",
    )
    try:
        response = client.post(
            _FILES_SEARCH_PATH,
            headers=auth_headers(session["token"]),
            json={"query": "아직 없는 문서", "strategy": strategy},
        )
    finally:
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert response.status_code == 200, response.text
    assert response.json()["hits"] == []
    assert response.json()["has_more"] is False


def test_lexical_snippet_bounds_pathological_unbroken_source_text() -> None:
    source_text = f"{'x' * 240_000} needle {'y' * 240_000}"

    snippet = file_search._lexical_snippet(source_text, query="needle")

    assert len(snippet.text) <= file_search.MAX_FILE_SEARCH_SNIPPET_CHARS
    assert "needle" in snippet.text
    assert len(snippet.highlights) == 1
    highlight = snippet.highlights[0]
    assert snippet.text[highlight.start : highlight.end] == "needle"


def test_lexical_snippet_bounds_query_token_and_highlight_work() -> None:
    source_text = " ".join(["needle"] * 10_000)
    query = " ".join([f"needle-{index}" for index in range(1_000)])

    snippet = file_search._lexical_snippet(source_text, query=query)

    assert len(snippet.text) <= file_search.MAX_FILE_SEARCH_SNIPPET_CHARS
    assert len(snippet.highlights) <= file_search.MAX_FILE_SEARCH_HIGHLIGHTS


def test_low_confidence_semantic_fallback_uses_query_anchored_source_snippet() -> None:
    hit = SimpleNamespace(
        resource_id="file-1",
        score=0.016,
        methods=["dense_vector", "rrf"],
        excerpt="unrelated footer",
        summary="",
    )
    source = file_search._FileSearchSource(
        file_id="file-1",
        filename="policy.pdf",
        folder_id=None,
        content_type="application/pdf",
        size_bytes=100,
        updated_at=datetime.now(UTC),
    )

    result = file_search._file_search_hit(
        hit=hit,
        file=source,
        extraction_text="도입부 " + "일반 내용 " * 60 + "마약류 대책 협의회 개최",
        query="마약 처벌",
        rank=1,
    )

    assert "마약류 대책" in result.snippet.text
    assert "unrelated footer" not in result.snippet.text


def test_low_confidence_fallback_loads_source_text_for_only_filtered_page_hits() -> None:
    hits = [
        SimpleNamespace(resource_id="semantic", methods=["dense_vector", "rrf"]),
        SimpleNamespace(resource_id="keyword", methods=["bm25", "rrf"]),
    ]

    assert file_search._snippet_extraction_file_ids(
        hits,
        rerank_profile={"error_type": "LowConfidenceRerankScores"},
    ) == ["semantic", "keyword"]
    assert file_search._snippet_extraction_file_ids(
        hits,
        rerank_profile={"applied": True},
    ) == ["keyword"]


def test_file_search_metadata_filters_use_indexes_and_authoritative_source_state() -> None:
    request = file_search.FileSearchRequest(
        query="냉각",
        source_kind=" external_repository ",
        author="홍길동",
        department="연구 개발팀",
        document_type="기술보고서",
        authored_from="2026-08-01T00:00:00+09:00",
        authored_to="2026-08-03T00:00:00+09:00",
    )
    filters = file_search._file_search_retrieval_filters(request)

    assert len(filters["keyword"]["target_refs"]) == 4
    assert filters["keyword"]["target_ref_match"] == "all"
    assert filters["keyword"]["date_filters"][0]["field"] == "authored_at"
    assert filters["rag"] == {
        "metadata.origin_source_kind_filter": "external_repository",
        "metadata.author_filter": "홍길동",
        "metadata.department_filter": "연구 개발팀",
        "metadata.document_type_filter": "기술보고서",
        "metadata.authored_at": {
            "gte": datetime(2026, 7, 31, 15),
            "lte": datetime(2026, 8, 2, 15),
        },
    }

    file = FileManagerFile(
        id="file-filtered",
        owner_id="user-1",
        filename="report.pdf",
        content_type="application/pdf",
        size_bytes=10,
        storage_key="files/file-filtered/report.pdf",
        visibility="company",
    )
    file.source_metadata = FileManagerFileSourceMetadata(
        file_id=file.id,
        corpus_id="corpus-1",
        external_id="external-1",
        external_id_sha256="a" * 64,
        source_kind="external_repository",
        source_id="document-1",
        source_id_sha256="b" * 64,
        content_checksum="c" * 64,
        author="홍길동",
        department="연구   개발팀",
        document_type="기술보고서",
        authored_at=datetime(2026, 8, 2),
        raw_metadata={},
        acl_resolved=True,
    )

    assert file_search._file_source_matches_request(file, request=request)
    assert not file_search._file_source_matches_request(
        file,
        request=request.model_copy(update={"department": "품질팀"}),
    )


def test_file_search_rejects_inverted_authored_range() -> None:
    with pytest.raises(ValueError, match="authored_from"):
        file_search.FileSearchRequest(
            query="냉각",
            authored_from="2026-08-03T00:00:00Z",
            authored_to="2026-08-01T00:00:00Z",
        )


def test_file_search_relevance_filters_normalized_rerank_tail() -> None:
    hits = [
        SimpleNamespace(score=0.9, methods=["cross_encoder"]),
        SimpleNamespace(score=0.001, methods=["cross_encoder"]),
        SimpleNamespace(score=0.0009, methods=["cross_encoder"]),
    ]

    filtered = file_search._filter_file_search_relevance(
        hits,
        strategy=file_search.FileSearchStrategy.HYBRID,
        rerank_profile={
            "applied": True,
            "score_semantics": "normalized_relevance",
        },
    )

    assert filtered == hits[:2]


def test_file_search_relevance_keeps_only_best_low_confidence_fallback() -> None:
    hits = [
        SimpleNamespace(score=0.032, methods=["rrf"]),
        SimpleNamespace(score=0.031, methods=["rrf"]),
    ]

    filtered = file_search._filter_file_search_relevance(
        hits,
        strategy=file_search.FileSearchStrategy.SEMANTIC,
        rerank_profile={
            "applied": False,
            "score_semantics": "normalized_relevance",
            "error_type": "LowConfidenceRerankScores",
        },
    )

    assert filtered == hits[:1]


def test_hybrid_file_search_low_confidence_prefers_semantic_leader() -> None:
    fused_leader = SimpleNamespace(
        resource_id="keyword-leader",
        score=0.032,
        methods=["bm25", "dense_vector", "rrf"],
        metadata={"retrieval": {"backend_ranks": {"keyword": 1, "generic_rag": 3}}},
    )
    semantic_leader = SimpleNamespace(
        resource_id="semantic-leader",
        score=0.031,
        methods=["dense_vector", "rrf"],
        metadata={"retrieval": {"backend_ranks": {"generic_rag": 1}}},
    )
    tail = SimpleNamespace(
        resource_id="tail",
        score=0.030,
        methods=["bm25", "dense_vector", "rrf"],
        metadata={"retrieval": {"backend_ranks": {"keyword": 2, "generic_rag": 2}}},
    )

    filtered = file_search._filter_file_search_relevance(
        [fused_leader, semantic_leader, tail],
        strategy=file_search.FileSearchStrategy.HYBRID,
        rerank_profile={
            "applied": False,
            "score_semantics": "normalized_relevance",
            "error_type": "LowConfidenceRerankScores",
        },
    )

    assert filtered == [semantic_leader]


@pytest.mark.parametrize(
    ("strategy", "profile"),
    [
        (
            file_search.FileSearchStrategy.KEYWORD,
            {"applied": True, "score_semantics": "normalized_relevance"},
        ),
        (
            file_search.FileSearchStrategy.HYBRID,
            {"applied": True, "score_semantics": "unknown"},
        ),
    ],
)
def test_file_search_relevance_does_not_guess_uncalibrated_score_meaning(
    strategy: file_search.FileSearchStrategy,
    profile: dict[str, object],
) -> None:
    hits = [SimpleNamespace(score=0.0001, methods=["cross_encoder"])]

    assert (
        file_search._filter_file_search_relevance(
            hits,
            strategy=strategy,
            rerank_profile=profile,
        )
        == hits
    )


def test_keyword_file_search_returns_ranked_source_fresh_snippet(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": "File search corpus"},
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
        files={"file": ("access-control.txt", b"source", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()

    prefix = [f"prefix-{index}" for index in range(70)]
    suffix = [f"suffix-{index}" for index in range(70)]
    extraction_text = " ".join([*prefix, "접근제어", *suffix])
    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "a" * 64
        file.extraction_text = extraction_text
        file.extraction_blocks = [{"text": extraction_text}]
        file.extraction_metadata = {"parser": "plain_text"}
        file.updated_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()
        db.refresh(file)
        document = build_file_search_document(file=file)
        document["retrieval_partition_id"] = str(file.retrieval_partition_id)
        document["projection_version"] = 1

    keyword_backend = _KeywordBackend(document)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=None,
        rag_collection=None,
    )
    try:
        response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                "query": "접근제어 suffix-0",
                "strategy": "keyword",
                "page": 1,
                "page_size": 10,
            },
        )
    finally:
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["strategy"] == "keyword"
    assert payload["page"] == 1
    assert payload["page_size"] == 10
    assert payload["has_more"] is False
    assert len(payload["hits"]) == 1
    hit = payload["hits"][0]
    assert hit["rank"] == 1
    assert hit["file_id"] == uploaded["id"]
    assert hit["filename"] == "access-control.txt"
    assert hit["score"] == 17.25
    assert hit["methods"] == ["bm25"]
    snippet_tokens = hit["snippet"]["text"].split()
    assert len(snippet_tokens) == 101
    assert snippet_tokens[0] == "prefix-20"
    assert snippet_tokens[-1] == "suffix-49"
    assert len(hit["snippet"]["highlights"]) == 2

    assert keyword_backend.last_query is not None
    assert keyword_backend.last_query.entity_types == ("file",)
    assert keyword_backend.last_query.retrieval_partition_ids == (corpus["retrieval_partition_id"],)
    assert keyword_backend.last_query.text_operator == "and"
    assert keyword_backend.last_query.text_minimum_should_match is None


def test_keyword_file_search_drops_a_file_deleted_after_page_source_load(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": "Concurrent delete search corpus"},
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
        files={"file": ("revoked-result.txt", b"source", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    secret_text = "CONCURRENT-DELETE-SECRET access control evidence"

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "d" * 64
        file.extraction_text = secret_text
        file.extraction_blocks = [{"text": secret_text}]
        file.extraction_metadata = {"parser": "plain_text"}
        db.commit()
        db.refresh(file)
        document = build_file_search_document(file=file)
        document["retrieval_partition_id"] = str(file.retrieval_partition_id)
        document["projection_version"] = 1

    keyword_backend = _KeywordBackend(document)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=None,
        rag_collection=None,
    )
    delete_triggered = False

    def delete_before_extraction_query(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        nonlocal delete_triggered
        if delete_triggered or "file_manager_files.extraction_text" not in statement:
            return
        delete_triggered = True
        with get_session_factory().begin() as revoke_db:
            user = revoke_db.scalar(select(User).where(User.login_id == "administrator"))
            assert user is not None
            files_service.delete_file(
                revoke_db,
                user=user,
                file_id=uploaded["id"],
            )

    event.listen(get_engine(), "before_cursor_execute", delete_before_extraction_query)
    try:
        response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={"query": "access control", "strategy": "keyword"},
        )
    finally:
        event.remove(get_engine(), "before_cursor_execute", delete_before_extraction_query)
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert delete_triggered is True
    assert response.status_code == 200, response.text
    assert response.json()["hits"] == []
    assert secret_text not in response.text


def test_keyword_file_search_refills_page_after_concurrent_revoke_and_recomputes_has_more(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": "Concurrent revoke refill corpus"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()

    documents: list[tuple[dict[str, object], float]] = []
    uploaded_ids: list[str] = []
    for index, score in enumerate((30.0, 20.0, 10.0)):
        upload_response = client.post(
            "/api/v1/files/upload",
            headers=headers,
            data={
                "visibility": "company",
                "company_admin_read_acknowledged": True,
                "corpus_id": corpus["id"],
            },
            files={
                "file": (
                    f"concurrent-refill-{index}.txt",
                    f"access control evidence {index}".encode(),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201, upload_response.text
        uploaded = upload_response.json()
        uploaded_ids.append(uploaded["id"])
        with get_session_factory()() as db:
            file = db.get(FileManagerFile, uploaded["id"])
            assert file is not None
            file.extraction_status = "ready"
            file.extraction_content_checksum = str(index + 1) * 64
            file.extraction_text = f"access control evidence {index}"
            file.extraction_blocks = [{"text": file.extraction_text}]
            file.extraction_metadata = {"parser": "plain_text"}
            db.commit()
            db.refresh(file)
            document = build_file_search_document(file=file)
            document["retrieval_partition_id"] = str(file.retrieval_partition_id)
            document["projection_version"] = 1
        documents.append((document, score))

    keyword_backend = _KeywordBackend(documents)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=None,
        rag_collection=None,
    )
    delete_triggered = False

    def delete_top_hit_before_extraction_query(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        nonlocal delete_triggered
        if delete_triggered or "file_manager_files.extraction_text" not in statement:
            return
        delete_triggered = True
        with get_session_factory().begin() as revoke_db:
            user = revoke_db.scalar(select(User).where(User.login_id == "administrator"))
            assert user is not None
            files_service.delete_file(
                revoke_db,
                user=user,
                file_id=uploaded_ids[0],
            )

    event.listen(get_engine(), "before_cursor_execute", delete_top_hit_before_extraction_query)
    try:
        response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                "query": "access control",
                "strategy": "keyword",
                "page": 1,
                "page_size": 2,
            },
        )
    finally:
        event.remove(get_engine(), "before_cursor_execute", delete_top_hit_before_extraction_query)
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert delete_triggered is True
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [hit["file_id"] for hit in payload["hits"]] == uploaded_ids[1:]
    assert [hit["rank"] for hit in payload["hits"]] == [1, 2]
    assert payload["has_more"] is False


def test_keyword_file_search_recomputes_has_more_after_off_page_revoke(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": "Concurrent off-page revoke corpus"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()

    documents: list[tuple[dict[str, object], float]] = []
    uploaded_ids: list[str] = []
    for index, score in enumerate((30.0, 20.0, 10.0)):
        upload_response = client.post(
            "/api/v1/files/upload",
            headers=headers,
            data={
                "visibility": "company",
                "company_admin_read_acknowledged": True,
                "corpus_id": corpus["id"],
            },
            files={
                "file": (
                    f"concurrent-off-page-{index}.txt",
                    f"access control evidence {index}".encode(),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201, upload_response.text
        uploaded = upload_response.json()
        uploaded_ids.append(uploaded["id"])
        with get_session_factory()() as db:
            file = db.get(FileManagerFile, uploaded["id"])
            assert file is not None
            file.extraction_status = "ready"
            file.extraction_content_checksum = str(index + 4) * 64
            file.extraction_text = f"access control evidence {index}"
            file.extraction_blocks = [{"text": file.extraction_text}]
            file.extraction_metadata = {"parser": "plain_text"}
            db.commit()
            db.refresh(file)
            document = build_file_search_document(file=file)
            document["retrieval_partition_id"] = str(file.retrieval_partition_id)
            document["projection_version"] = 1
        documents.append((document, score))

    keyword_backend = _KeywordBackend(documents)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=None,
        rag_collection=None,
    )
    delete_triggered = False

    def delete_off_page_hit_before_extraction_query(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        nonlocal delete_triggered
        if delete_triggered or "file_manager_files.extraction_text" not in statement:
            return
        delete_triggered = True
        with get_session_factory().begin() as revoke_db:
            user = revoke_db.scalar(select(User).where(User.login_id == "administrator"))
            assert user is not None
            files_service.delete_file(
                revoke_db,
                user=user,
                file_id=uploaded_ids[2],
            )

    event.listen(get_engine(), "before_cursor_execute", delete_off_page_hit_before_extraction_query)
    try:
        response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                "query": "access control",
                "strategy": "keyword",
                "page": 1,
                "page_size": 2,
            },
        )
    finally:
        event.remove(
            get_engine(),
            "before_cursor_execute",
            delete_off_page_hit_before_extraction_query,
        )
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert delete_triggered is True
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [hit["file_id"] for hit in payload["hits"]] == uploaded_ids[:2]
    assert [hit["rank"] for hit in payload["hits"]] == [1, 2]
    assert payload["has_more"] is False


def test_keyword_file_search_drops_hits_when_app_is_disabled_after_page_source_load(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    dev_login(client, "delivery-hub-admin")

    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": "Concurrent transfer search corpus"},
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
        files={"file": ("moved-result.txt", b"source", "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()
    secret_text = "CONCURRENT-TRANSFER-SECRET access control evidence"

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "e" * 64
        file.extraction_text = secret_text
        file.extraction_blocks = [{"text": secret_text}]
        file.extraction_metadata = {"parser": "plain_text"}
        db.commit()
        db.refresh(file)
        document = build_file_search_document(file=file)
        document["retrieval_partition_id"] = str(file.retrieval_partition_id)
        document["projection_version"] = 1

    keyword_backend = _KeywordBackend(document)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=None,
        rag_collection=None,
    )
    revoke_triggered = False

    def revoke_before_extraction_query(
        _connection,
        _cursor,
        statement: str,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        nonlocal revoke_triggered
        if revoke_triggered or "file_manager_files.extraction_text" not in statement:
            return
        revoke_triggered = True
        with get_session_factory().begin() as revoke_db:
            control = revoke_db.get(CompanyAppControl, "files")
            assert control is not None
            control.enabled = False

    event.listen(get_engine(), "before_cursor_execute", revoke_before_extraction_query)
    try:
        response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={"query": "access control", "strategy": "keyword"},
        )
    finally:
        event.remove(get_engine(), "before_cursor_execute", revoke_before_extraction_query)
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert revoke_triggered is True
    assert response.status_code == 200, response.text
    assert response.json()["hits"] == []
    assert secret_text not in response.text


def test_keyword_file_search_pages_over_a_bounded_deterministic_ranking(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": "Paged file search corpus"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()

    scores = [5.0, 8.0, 8.0, 2.0]
    documents: list[tuple[dict[str, object], float]] = []
    expected_scores: dict[str, float] = {}
    for index, score in enumerate(scores):
        upload_response = client.post(
            "/api/v1/files/upload",
            headers=headers,
            data={
                "visibility": "company",
                "company_admin_read_acknowledged": True,
                "corpus_id": corpus["id"],
            },
            files={
                "file": (
                    f"paged-{index}.txt",
                    f"common evidence {index}".encode(),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201, upload_response.text
        uploaded = upload_response.json()
        with get_session_factory()() as db:
            file = db.get(FileManagerFile, uploaded["id"])
            assert file is not None
            file.extraction_status = "ready"
            file.extraction_content_checksum = str(index) * 64
            file.extraction_text = f"common evidence {index}"
            file.extraction_blocks = [{"text": file.extraction_text}]
            file.extraction_metadata = {"parser": "plain_text"}
            db.commit()
            db.refresh(file)
            document = build_file_search_document(file=file)
            document["retrieval_partition_id"] = str(file.retrieval_partition_id)
            document["projection_version"] = 1
        documents.append((document, score))
        expected_scores[uploaded["id"]] = score

    keyword_backend = _KeywordBackend(documents)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=None,
        rag_collection=None,
    )
    try:
        first_response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={"query": "common", "strategy": "keyword", "page_size": 2},
        )
        second_response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                "query": "common",
                "strategy": "keyword",
                "page": 2,
                "page_size": 2,
            },
        )
    finally:
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    first = first_response.json()
    second = second_response.json()
    expected_ids = sorted(expected_scores, key=lambda file_id: (-expected_scores[file_id], file_id))
    assert [hit["file_id"] for hit in first["hits"]] == expected_ids[:2]
    assert [hit["rank"] for hit in first["hits"]] == [1, 2]
    assert first["has_more"] is True
    assert [hit["file_id"] for hit in second["hits"]] == expected_ids[2:]
    assert [hit["rank"] for hit in second["hits"]] == [3, 4]
    assert second["has_more"] is False
    assert keyword_backend.last_query is not None
    assert keyword_backend.last_query.size == file_search.MAX_FILE_SEARCH_RANKED_RESULTS


@pytest.mark.parametrize("strategy", ("keyword", "semantic", "hybrid"))
def test_file_search_has_more_matches_final_authorized_window_for_each_strategy(
    client: TestClient,
    in_memory_object_storage: None,
    strategy: str,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": f"Paged {strategy} search corpus"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()

    documents: list[tuple[dict[str, object], float]] = []
    projections: list[RagProjection] = []
    uploaded_ids: set[str] = set()
    for index, score in enumerate((30.0, 20.0, 10.0)):
        content = f"common semantic access evidence {index}"
        upload_response = client.post(
            "/api/v1/files/upload",
            headers=headers,
            data={
                "visibility": "company",
                "company_admin_read_acknowledged": True,
                "corpus_id": corpus["id"],
            },
            files={
                "file": (
                    f"paged-{strategy}-{index}.txt",
                    content.encode(),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 201, upload_response.text
        uploaded = upload_response.json()
        uploaded_ids.add(uploaded["id"])
        with get_session_factory()() as db:
            file = db.get(FileManagerFile, uploaded["id"])
            assert file is not None
            file.extraction_status = "ready"
            file.extraction_content_checksum = str(index + 4) * 64
            file.extraction_text = content
            file.extraction_blocks = [{"text": content}]
            file.extraction_metadata = {"parser": "plain_text"}
            db.commit()
            db.refresh(file)
            document = build_file_search_document(file=file)
            document["retrieval_partition_id"] = str(file.retrieval_partition_id)
            document["projection_version"] = 1
            projections.append(
                RagProjection(
                    retrieval_partition_id=str(file.retrieval_partition_id),
                    projection_version=1,
                    scope_kind=RagScopeKind.COMPANY,
                    resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                    resource_id=file.id,
                    source_kind="files",
                    title=file.filename,
                    summary=content,
                    text_content=content,
                    visibility_refs=["company_public"],
                    metadata={"filename": file.filename, "content_modality": "text"},
                    chunks=[
                        RagChunk(
                            chunk_id=f"{file.id}:text:0",
                            text=content,
                            summary=content,
                            index_text=content,
                        )
                    ],
                )
            )
        documents.append((document, score))

    vector_backend = _RecordingVectorBackend()
    embedding_backend = FakeEmbeddingClient(dimensions=32)
    rag_collection = f"files-page-contract-{strategy}"
    rag_service = RagService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        default_collection=rag_collection,
    )
    for projection in projections:
        rag_service.sync_projection(projection, collection=rag_collection)
    rag_query_service = RagQueryService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        rerank_client=None,
        query_timeout_ms=5_000,
    )
    keyword_backend = _KeywordBackend(documents)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=rag_query_service,
        rag_collection=rag_collection,
    )
    try:
        first_response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                "query": "common semantic access",
                "strategy": strategy,
                "page": 1,
                "page_size": 2,
            },
        )
        second_response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                "query": "common semantic access",
                "strategy": strategy,
                "page": 2,
                "page_size": 2,
            },
        )
    finally:
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    first = first_response.json()
    second = second_response.json()
    assert len(first["hits"]) == 2
    assert first["has_more"] is True
    assert [hit["rank"] for hit in first["hits"]] == [1, 2]
    assert len(second["hits"]) == 1
    assert second["has_more"] is False
    assert [hit["rank"] for hit in second["hits"]] == [3]
    assert {hit["file_id"] for hit in [*first["hits"], *second["hits"]]} == uploaded_ids


@pytest.mark.parametrize("strategy", ("semantic", "hybrid"))
def test_external_authored_range_reaches_fake_semantic_and_hybrid_backends(
    client: TestClient,
    in_memory_object_storage: None,
    strategy: str,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": f"External date filter {strategy}"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()
    content = "thermal source filter evidence"
    upload_response = client.post(
        "/api/v1/files/upload",
        headers=headers,
        data={
            "visibility": "company",
            "company_admin_read_acknowledged": True,
            "corpus_id": corpus["id"],
        },
        files={"file": ("external-report.txt", content.encode(), "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "a" * 64
        file.extraction_text = content
        file.extraction_blocks = [{"text": content}]
        file.extraction_metadata = {"parser": "plain_text"}
        file.source_metadata = FileManagerFileSourceMetadata(
            file_id=file.id,
            corpus_id=corpus["id"],
            external_id="external-report",
            external_id_sha256="b" * 64,
            source_kind="external_repository",
            source_id="document-1",
            source_id_sha256="c" * 64,
            title="External thermal report",
            author="홍길동",
            authored_at=datetime(2026, 8, 2),
            department="연구개발팀",
            document_type="기술보고서",
            source_updated_at=datetime(2026, 8, 2),
            content_checksum="a" * 64,
            raw_metadata={},
            acl_resolved=True,
        )
        db.commit()
        db.refresh(file)
        document = build_file_search_document(file=file)
        document["retrieval_partition_id"] = str(file.retrieval_partition_id)
        document["projection_version"] = 1
        projection = RagProjection(
            retrieval_partition_id=str(file.retrieval_partition_id),
            projection_version=1,
            scope_kind=RagScopeKind.COMPANY,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=file.id,
            source_kind="files",
            title="External thermal report",
            summary=content,
            text_content=content,
            visibility_refs=["company_public"],
            metadata={
                "filename": file.filename,
                "content_modality": "text",
                **safe_external_source_metadata(file),
            },
            chunks=[
                RagChunk(
                    chunk_id=f"{file.id}:text:0",
                    text=content,
                    summary=content,
                    index_text=content,
                )
            ],
        )

    vector_backend = _RecordingVectorBackend()
    embedding_backend = FakeEmbeddingClient(dimensions=32)
    rag_collection = f"files-external-date-filter-{strategy}"
    RagService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        default_collection=rag_collection,
    ).sync_projection(projection, collection=rag_collection)
    rag_query_service = RagQueryService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        rerank_client=None,
        query_timeout_ms=5_000,
    )
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=_KeywordBackend(document),
        rag_query_service=rag_query_service,
        rag_collection=rag_collection,
    )
    base_request = {
        "query": "thermal source filter evidence",
        "strategy": strategy,
        "source_kind": "external_repository",
        "author": "홍길동",
        "department": "연구개발팀",
        "document_type": "기술보고서",
    }
    try:
        included = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                **base_request,
                "authored_from": "2026-08-02T00:00:00Z",
                "authored_to": "2026-08-02T00:00:00Z",
            },
        )
        excluded = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={**base_request, "authored_from": "2026-08-03T00:00:00Z"},
        )
    finally:
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert included.status_code == 200, included.text
    assert [hit["file_id"] for hit in included.json()["hits"]] == [uploaded["id"]]
    assert excluded.status_code == 200, excluded.text
    assert excluded.json()["hits"] == []
    assert vector_backend.result_counts == [1, 0]


def test_hybrid_file_search_rechecks_user_admission_without_reindexing(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    session = dev_login(client, "administrator")
    headers = auth_headers(session["token"])
    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=headers,
        json={"name": "Company knowledge corpus"},
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
        files={
            "file": (
                "thermal-controller.txt",
                "서비스 장애 진단 사양".encode(),
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        file.extraction_status = "ready"
        file.extraction_content_checksum = "b" * 64
        file.extraction_text = "서비스 장애 진단 사양"
        file.extraction_blocks = [{"text": file.extraction_text}]
        file.extraction_metadata = {"parser": "plain_text"}
        db.commit()
        db.refresh(file)
        document = build_file_search_document(file=file)
        document["retrieval_partition_id"] = str(file.retrieval_partition_id)
        document["projection_version"] = 1

        projection = RagProjection(
            retrieval_partition_id=str(file.retrieval_partition_id),
            projection_version=1,
            scope_kind=RagScopeKind.COMPANY,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=file.id,
            source_kind="files",
            title=file.filename,
            summary="서비스 장애 진단 사양",
            text_content="서비스 장애 진단 사양",
            visibility_refs=["company_public"],
            metadata={"filename": file.filename, "content_modality": "text"},
            chunks=[
                RagChunk(
                    chunk_id=f"{file.id}:text:0",
                    text="서비스 장애 진단 사양",
                    summary="열관리 제어기",
                    index_text="서비스 장애 진단 사양",
                )
            ],
        )

    vector_backend = _RecordingVectorBackend()
    embedding_backend = FakeEmbeddingClient(dimensions=32)
    rag_collection = "files-company-dedup"
    RagService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        default_collection=rag_collection,
    ).sync_projection(projection, collection=rag_collection)
    rag_query_service = RagQueryService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        rerank_client=None,
        query_timeout_ms=5_000,
    )

    observer_session = dev_login(client, "delivery-hub-member")
    other_headers = auth_headers(observer_session["token"])
    _set_files_user_admission([observer_session["user"]["id"]])

    keyword_backend = _KeywordBackend(document)
    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=rag_query_service,
        rag_collection=rag_collection,
    )
    try:
        company_response = client.post(
            "/api/v1/files/search",
            headers=other_headers,
            json={
                "query": "열관리 제어기",
                "strategy": "hybrid",
                "page": 1,
                "page_size": 10,
            },
        )
        _set_files_user_admission([])
        denied_response = client.post(
            "/api/v1/files/search",
            headers=other_headers,
            json={"query": "열관리 제어기", "strategy": "hybrid"},
        )
        response = client.post(
            _FILES_SEARCH_PATH,
            headers=headers,
            json={
                "query": "열관리 제어기",
                "strategy": "hybrid",
                "page": 1,
                "page_size": 10,
            },
        )
    finally:
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert company_response.status_code == 200, company_response.text
    company_payload = company_response.json()
    assert len(company_payload["hits"]) == 1
    assert company_payload["hits"][0]["file_id"] == uploaded["id"]
    assert denied_response.status_code == 403, denied_response.text
    assert denied_response.json()["code"] == "files.app_disabled"
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["hits"]) == 1
    assert payload["hits"][0]["file_id"] == uploaded["id"]
    assert keyword_backend.last_query is not None
    assert keyword_backend.last_query.text_operator == "and"
    assert keyword_backend.last_query.text_minimum_should_match is None
    assert vector_backend.last_query is not None
    assert projection.retrieval_partition_id in vector_backend.last_query.retrieval_partition_ids
    assert vector_backend.result_counts == [1, 1]
    assert {"bm25", "dense_vector", "rrf"} <= set(payload["hits"][0]["methods"])


def test_company_user_grant_changes_reuse_projections_and_revoke_download_capabilities(
    client: TestClient,
    in_memory_object_storage: None,
) -> None:
    source_session = dev_login(client, "administrator")
    source_headers = auth_headers(source_session["token"])
    target_session = dev_login(client, "delivery-hub-member")
    target_headers = auth_headers(target_session["token"])

    corpus_response = client.post(
        "/api/v1/files/corpora",
        headers=source_headers,
        json={"name": "Company user admission search corpus"},
    )
    assert corpus_response.status_code == 201, corpus_response.text
    corpus = corpus_response.json()
    content = "통합 서비스의 장애 복구 진단 기준"
    upload_response = client.post(
        "/api/v1/files/upload",
        headers=source_headers,
        data={
            "visibility": "company",
            "company_admin_read_acknowledged": True,
            "corpus_id": corpus["id"],
        },
        files={"file": ("controller-transfer.txt", content.encode(), "text/plain")},
    )
    assert upload_response.status_code == 201, upload_response.text
    uploaded = upload_response.json()

    with get_session_factory()() as db:
        file = db.get(FileManagerFile, uploaded["id"])
        assert file is not None
        stable_partition_id = str(file.retrieval_partition_id)
        file.extraction_status = "ready"
        file.extraction_content_checksum = "c" * 64
        file.extraction_text = content
        file.extraction_blocks = [{"text": content}]
        file.extraction_metadata = {"parser": "plain_text"}
        db.commit()
        db.refresh(file)
        stale_keyword_document = build_file_search_document(
            file=file,
        )
        stale_keyword_document["retrieval_partition_id"] = stable_partition_id
        stale_keyword_document["projection_version"] = 1
        stale_vector_projection = RagProjection(
            retrieval_partition_id=stable_partition_id,
            projection_version=1,
            scope_kind=RagScopeKind.COMPANY,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            resource_id=file.id,
            source_kind="files",
            title=file.filename,
            summary=content,
            text_content=content,
            visibility_refs=["company_public"],
            metadata={"filename": file.filename, "content_modality": "text"},
            chunks=[
                RagChunk(
                    chunk_id=f"{file.id}:text:0",
                    text=content,
                    summary=content,
                    index_text=content,
                )
            ],
        )

    vector_backend = _RecordingVectorBackend()
    embedding_backend = FakeEmbeddingClient(dimensions=32)
    rag_collection = "files-user-admission"
    RagService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        default_collection=rag_collection,
    ).sync_projection(stale_vector_projection, collection=rag_collection)
    rag_query_service = RagQueryService(
        vector_index=vector_backend,
        embedding_client=embedding_backend,
        rerank_client=None,
        query_timeout_ms=5_000,
    )
    keyword_backend = _KeywordBackend(stale_keyword_document)

    _set_files_user_admission([])
    denied_before_grant = client.get(
        f"/api/v1/files/{uploaded['id']}/download", headers=target_headers
    )
    assert denied_before_grant.status_code == 403, denied_before_grant.text
    _set_files_user_admission([target_session["user"]["id"]])

    client.app.dependency_overrides[require_file_search_runtime] = lambda: FileSearchRuntime(
        keyword_client=keyword_backend,
        rag_query_service=rag_query_service,
        rag_collection=rag_collection,
    )
    try:
        source_search = client.post(
            _FILES_SEARCH_PATH,
            headers=source_headers,
            json={"query": "절전 복귀", "strategy": "hybrid"},
        )
        target_search = client.post(
            "/api/v1/files/search",
            headers=target_headers,
            json={"query": "절전 복귀", "strategy": "hybrid"},
        )
    finally:
        client.app.dependency_overrides.pop(require_file_search_runtime, None)

    assert source_search.status_code == 200, source_search.text
    assert [hit["file_id"] for hit in source_search.json()["hits"]] == [uploaded["id"]]
    assert target_search.status_code == 200, target_search.text
    assert [hit["file_id"] for hit in target_search.json()["hits"]] == [uploaded["id"]]
    assert {"bm25", "dense_vector", "rrf"} <= set(target_search.json()["hits"][0]["methods"])

    source_download = client.get(
        f"/api/v1/files/{uploaded['id']}/download",
        headers=source_headers,
    )
    assert source_download.status_code == 200, source_download.text
    target_download = client.get(
        f"/api/v1/files/{uploaded['id']}/download",
        headers=target_headers,
    )
    assert target_download.status_code == 200, target_download.text
    content_url = target_download.json()["url"]
    content_response = client.get(
        content_url,
        headers=content_headers(target_session["token"], content_url),
    )
    assert content_response.status_code == 200
    assert content_response.content == content.encode()

    _set_files_user_admission([])
    denied_content = client.get(
        content_url, headers=content_headers(target_session["token"], content_url)
    )
    assert denied_content.status_code == 403, denied_content.text
    denied_download = client.get(f"/api/v1/files/{uploaded['id']}/download", headers=target_headers)
    assert denied_download.status_code == 403, denied_download.text

    with get_session_factory()() as db:
        moved_file = db.get(FileManagerFile, uploaded["id"])
        assert moved_file is not None
        assert moved_file.corpus_id == corpus["id"]
        assert moved_file.visibility == "company"
        assert str(moved_file.retrieval_partition_id) == stable_partition_id
    stored_projection = vector_backend.snapshot_projection(
        collection=rag_collection,
        chunk_id=f"{uploaded['id']}:text:0",
    )
    assert stored_projection is not None
    assert stored_projection.scope_kind == RagScopeKind.COMPANY
    assert stored_projection.retrieval_partition_id == stable_partition_id
    assert "workspace_id" not in stale_keyword_document


def _set_files_user_admission(user_ids: list[str]) -> None:
    with get_session_factory().begin() as db:
        policy = db.get(AppAccessPolicy, "files")
        assert policy is not None
        policy.audience = "selected"
        db.execute(delete(AppUserGrant).where(AppUserGrant.app_id == "files"))
        db.add_all(AppUserGrant(app_id="files", user_id=user_id) for user_id in user_ids)
