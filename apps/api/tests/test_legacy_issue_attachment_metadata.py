from io import BytesIO
from types import SimpleNamespace

from fastapi import UploadFile
from fastapi.responses import StreamingResponse
import pytest
from starlette.exceptions import HTTPException

from open_alm_api.domains.auth.models import utcnow_naive
from open_alm_api.domains.legacy_issues import attachment_indexing
from open_alm_api.domains.legacy_issues.dataset_records import (
    DATASET_ATTACHMENT_MAX_BYTES,
    DATASET_ATTACHMENT_DESCRIPTION_MAX_CHARS,
    LegacyIssueDatasetDefinition,
    _copy_dataset_attachment_ai_chunk,
    _copy_dataset_attachment_for_revision,
    copy_dataset_revision_records,
    dataset_attachment_content_headers,
    normalize_attachment_description,
)
from open_alm_api.domains.legacy_issues.attachment_indexing import (
    _CHUNK_OVERLAP_CHARS,
    AttachmentExtractionArtifact,
    _attachment_summary_source_text,
    _build_attachment_chunks,
    _build_attachment_summary_chunk,
    _sanitize_attachment_summary,
    _split_text,
)
from open_alm_api.domains.legacy_issues.ai_search import build_legacy_issue_search_terms
from open_alm_api.domains.legacy_issues.models import (
    LegacyIssueAiChunk,
    LegacyIssueAttachment,
    LegacyIssueDataRevision,
    LegacyIssueRecord,
)
from open_alm_api.domains.legacy_issues.router import (
    LegacyIssueAssistantMatchedChunkItem,
    LegacyIssueAttachmentUpdateRequest,
)


def test_normalize_attachment_description_compacts_human_context() -> None:
    assert normalize_attachment_description("  symptom photo\n\nafter repair  ") == (
        "symptom photo after repair"
    )
    assert normalize_attachment_description("   ") is None
    assert normalize_attachment_description(None) is None

    long_description = "x" * (DATASET_ATTACHMENT_DESCRIPTION_MAX_CHARS + 10)
    assert len(normalize_attachment_description(long_description) or "") == (
        DATASET_ATTACHMENT_DESCRIPTION_MAX_CHARS
    )


def test_dataset_attachment_upload_limit_is_one_gibibyte() -> None:
    assert DATASET_ATTACHMENT_MAX_BYTES == 1024 * 1024 * 1024


def test_attachment_content_headers_download_with_non_ascii_attachment_filename() -> None:
    headers = dataset_attachment_content_headers("과거차 점검결과(전장).pptx")

    response = StreamingResponse(
        iter([b"deck"]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers=headers,
    )

    content_disposition = response.headers["content-disposition"]
    assert content_disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in content_disposition
    assert "%EA%B3%BC%EA%B1%B0%EC%B0%A8" in content_disposition
    assert "과거차" not in content_disposition


def test_attachment_update_request_tracks_partial_patch_fields() -> None:
    primary_only = LegacyIssueAttachmentUpdateRequest(is_primary=True)
    assert "is_primary" in primary_only.model_fields_set
    assert "description" not in primary_only.model_fields_set

    clear_description = LegacyIssueAttachmentUpdateRequest(description=None)
    assert "is_primary" not in clear_description.model_fields_set
    assert "description" in clear_description.model_fields_set

    description_and_primary = LegacyIssueAttachmentUpdateRequest(
        description="원인 분석",
        is_primary=True,
    )
    assert description_and_primary.model_fields_set == {"description", "is_primary"}


def test_direct_attachment_paths_reject_disabled_compressor_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import router as legacy_router

    attachment = SimpleNamespace(record_id="record-1")

    monkeypatch.setattr(
        legacy_router,
        "get_dataset_definition",
        lambda dataset_key: SimpleNamespace(key=dataset_key),
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_attachment",
        lambda *_args, **_kwargs: attachment,
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_record",
        lambda *_args, **_kwargs: SimpleNamespace(module_key="compressor-electric"),
    )
    monkeypatch.setattr(legacy_router, "_compressor_enabled", lambda: False)
    monkeypatch.setattr(
        legacy_router,
        "enqueue_legacy_issue_attachment_index_job",
        lambda *_args, **_kwargs: pytest.fail("disabled attachment must not be reindexed"),
    )
    monkeypatch.setattr(
        legacy_router,
        "open_dataset_attachment_content",
        lambda *_args, **_kwargs: pytest.fail("disabled attachment must not be opened"),
    )

    for action in (
        lambda: legacy_router.retry_legacy_issue_dataset_attachment_index(
            "legacy-common-master",
            "attachment-1",
            db=SimpleNamespace(),
            current_user=SimpleNamespace(id="user-1"),
            current_workspace=SimpleNamespace(id="workspace-1"),
        ),
        lambda: legacy_router.open_legacy_issue_dataset_attachment(
            "legacy-common-master",
            "attachment-1",
            db=SimpleNamespace(),
            current_workspace=SimpleNamespace(id="workspace-1"),
        ),
    ):
        with pytest.raises(HTTPException) as error:
            action()
        assert error.value.status_code == 404
        assert error.value.detail.code == "legacy_issues.module_not_found"


def test_attachment_patch_uses_record_revision_editor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import router as legacy_router

    attachment = _attachment_for_revision("published-revision")
    events: list[str] = []

    def require_attachment_editor(_db, *, dataset_key, revision_id, **_kwargs):
        assert dataset_key == "legacy_issue.common-master.aircon"
        assert revision_id == "published-revision"
        events.append("authorize")
        return _published_revision_for_attachment_editor()

    def fake_set_primary(_db, _definition, *, attachment_id, is_primary, **_kwargs):
        assert attachment_id == attachment.id
        events.append("set_primary")
        attachment.is_primary = is_primary
        return attachment

    def fake_update_description(_db, _definition, *, attachment_id, description, **_kwargs):
        assert attachment_id == attachment.id
        events.append("update_description")
        attachment.description = description
        return attachment

    class FakeDb:
        def commit(self) -> None:
            events.append("commit")

    monkeypatch.setattr(
        legacy_router,
        "get_dataset_definition",
        lambda dataset_key: SimpleNamespace(key=dataset_key),
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_attachment",
        lambda *_args, **_kwargs: attachment,
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_record",
        lambda *_args, **_kwargs: SimpleNamespace(
            module_key="aircon",
            revision_id="published-revision",
        ),
    )
    monkeypatch.setattr(
        legacy_router,
        "require_record_revision_editor",
        require_attachment_editor,
    )
    monkeypatch.setattr(
        legacy_router,
        "set_dataset_attachment_primary",
        fake_set_primary,
    )
    monkeypatch.setattr(
        legacy_router,
        "update_dataset_attachment_description",
        fake_update_description,
    )
    monkeypatch.setattr(
        legacy_router,
        "get_legacy_issue_settings",
        lambda: SimpleNamespace(ai_attachment_index_enabled=False),
    )

    response = legacy_router.update_legacy_issue_dataset_attachment(
        "common-master",
        attachment.id,
        LegacyIssueAttachmentUpdateRequest(
            description="원인 분석",
            is_primary=True,
        ),
        FakeDb(),
        SimpleNamespace(id="user-1"),
        SimpleNamespace(id="workspace-1"),
    )

    assert response.is_primary is True
    assert response.description == "원인 분석"
    assert events == ["authorize", "set_primary", "update_description", "commit"]


@pytest.mark.anyio
async def test_attachment_upload_uses_record_revision_editor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import router as legacy_router

    attachment = _attachment_for_revision("published-revision")
    events: list[str] = []

    class FakeDb:
        def commit(self) -> None:
            events.append("commit")

    monkeypatch.setattr(
        legacy_router,
        "get_dataset_definition",
        lambda dataset_key: SimpleNamespace(key=dataset_key),
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_record",
        lambda *_args, **_kwargs: SimpleNamespace(
            module_key="aircon",
            revision_id="published-revision",
        ),
    )

    def require_attachment_editor(_db, *, dataset_key, revision_id, **_kwargs):
        assert dataset_key == "legacy_issue.common-master.aircon"
        assert revision_id == "published-revision"
        events.append("authorize")
        return _published_revision_for_attachment_editor()

    monkeypatch.setattr(
        legacy_router,
        "require_record_revision_editor",
        require_attachment_editor,
    )

    def fake_upload(_db, _definition, *, upload, **_kwargs):
        assert upload.content == b"evidence"
        events.append("upload")
        return attachment

    monkeypatch.setattr(legacy_router, "upload_dataset_attachment", fake_upload)
    monkeypatch.setattr(
        legacy_router,
        "get_legacy_issue_settings",
        lambda: SimpleNamespace(ai_attachment_index_enabled=False),
    )

    response = await legacy_router.upload_legacy_issue_dataset_attachment(
        "common-master",
        "record-1",
        file=UploadFile(filename="evidence.pptx", file=BytesIO(b"evidence")),
        db=FakeDb(),
        current_user=SimpleNamespace(id="user-1"),
        current_workspace=SimpleNamespace(id="workspace-1"),
    )

    assert response.id == attachment.id
    assert events == ["authorize", "upload", "commit"]


def test_attachment_delete_uses_record_revision_editor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import router as legacy_router

    attachment = _attachment_for_revision("published-revision")
    events: list[str] = []

    class FakeDb:
        def commit(self) -> None:
            events.append("commit")

    monkeypatch.setattr(
        legacy_router,
        "get_dataset_definition",
        lambda dataset_key: SimpleNamespace(key=dataset_key),
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_attachment",
        lambda *_args, **_kwargs: attachment,
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_record",
        lambda *_args, **_kwargs: SimpleNamespace(
            module_key="aircon",
            revision_id="published-revision",
        ),
    )

    def require_attachment_editor(_db, *, dataset_key, revision_id, **_kwargs):
        assert dataset_key == "legacy_issue.common-master.aircon"
        assert revision_id == "published-revision"
        events.append("authorize")
        return _published_revision_for_attachment_editor()

    monkeypatch.setattr(
        legacy_router,
        "require_record_revision_editor",
        require_attachment_editor,
    )
    monkeypatch.setattr(
        legacy_router,
        "delete_legacy_issue_attachment_index_data",
        lambda *_args, **_kwargs: events.append("delete_index"),
    )
    monkeypatch.setattr(
        legacy_router,
        "delete_dataset_attachment",
        lambda *_args, **_kwargs: events.append("delete_attachment"),
    )

    response = legacy_router.delete_legacy_issue_dataset_attachment(
        "common-master",
        attachment.id,
        db=FakeDb(),
        current_user=SimpleNamespace(id="user-1"),
        current_workspace=SimpleNamespace(id="workspace-1"),
    )

    assert response.status_code == 204
    assert events == ["authorize", "delete_index", "delete_attachment", "commit"]


def test_attachment_index_retry_uses_record_revision_editor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from open_alm_api.domains.legacy_issues import router as legacy_router

    attachment = _attachment_for_revision("published-revision")
    events: list[str] = []

    class FakeDb:
        def commit(self) -> None:
            events.append("commit")

    monkeypatch.setattr(
        legacy_router,
        "get_dataset_definition",
        lambda dataset_key: SimpleNamespace(key=dataset_key),
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_attachment",
        lambda *_args, **_kwargs: attachment,
    )
    monkeypatch.setattr(
        legacy_router,
        "get_dataset_record",
        lambda *_args, **_kwargs: SimpleNamespace(
            module_key="aircon",
            revision_id="published-revision",
        ),
    )

    def require_attachment_editor(_db, *, dataset_key, revision_id, **_kwargs):
        assert dataset_key == "legacy_issue.common-master.aircon"
        assert revision_id == "published-revision"
        events.append("authorize")

    monkeypatch.setattr(
        legacy_router,
        "require_record_revision_editor",
        require_attachment_editor,
    )
    monkeypatch.setattr(
        legacy_router,
        "enqueue_legacy_issue_attachment_index_job",
        lambda *_args, **_kwargs: events.append("enqueue"),
    )

    response = legacy_router.retry_legacy_issue_dataset_attachment_index(
        "common-master",
        attachment.id,
        db=FakeDb(),
        current_user=SimpleNamespace(id="user-1"),
        current_workspace=SimpleNamespace(id="workspace-1"),
    )

    assert response.id == attachment.id
    assert events == ["authorize", "enqueue", "commit"]


def _attachment_for_revision(revision_id: str | None) -> LegacyIssueAttachment:
    return LegacyIssueAttachment(
        id="attachment-1",
        workspace_id="workspace-1",
        dataset_key="common-master",
        revision_id=revision_id,
        stable_record_id="stable-1",
        record_id="record-1",
        filename="evidence.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description=None,
        storage_key="legacy-issues/test/evidence.pptx",
        is_primary=False,
        index_status="not_indexed",
        index_error=None,
        index_version="legacy_issue_attachment_index.v1",
        chunk_count=0,
        artifact_count=0,
        ai_summary=None,
        ai_summary_status="not_summarized",
        ai_summary_error=None,
        ai_summary_model=None,
        ai_summary_version="legacy_issue_attachment_summary.v1",
        ai_summarized_at=None,
        uploaded_by_id="user-1",
        created_at=utcnow_naive(),
    )


def _published_revision_for_attachment_editor() -> LegacyIssueDataRevision:
    return LegacyIssueDataRevision(
        id="published-revision",
        workspace_id="workspace-1",
        dataset_key="legacy_issue.common-master.aircon",
        status="published",
    )


def test_attachment_search_terms_keep_korean_keywords_and_codes() -> None:
    terms = build_legacy_issue_search_terms("공조 불로위 저단 소음 발생 HTR PIPE 벌지부")

    assert {"공조", "불로위", "저단", "소음", "발생", "htr", "pipe", "벌지부"} <= set(terms)
    assert "불로" in terms
    assert "로위" in terms


def test_assistant_matched_chunk_accepts_legacy_rows_without_attachment_fields() -> None:
    item = LegacyIssueAssistantMatchedChunkItem(
        chunk_id="chunk-1",
        chunk_key="summary",
        chunk_kind="record_summary",
        excerpt="summary",
        methods=["keyword"],
        score=1.0,
    )

    assert item.attachment_id is None
    assert item.attachment_filename is None


def test_attachment_chunk_split_keeps_overlap_for_long_paragraphs() -> None:
    text = "".join(f"{index:03d}" for index in range(300))

    chunks = _split_text(text, max_chars=300)

    assert len(chunks) > 2
    assert chunks[1].startswith(chunks[0][-_CHUNK_OVERLAP_CHARS:])


def test_attachment_ai_summary_chunk_is_searchable() -> None:
    definition = LegacyIssueDatasetDefinition(
        key="past_vehicle_body",
        table_model=LegacyIssueRecord,
        title_ko="의장 과거차 문제점",
        title_en="Legacy Issues",
        hierarchy_ko=("과거차문제점",),
        hierarchy_en=("Legacy Issues",),
        fields=(),
    )
    record = LegacyIssueRecord(
        id="record-1",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="revision-1",
        stable_record_id="stable-1",
        field_values={"problem": "BLOWER FAN 진동 및 소음"},
    )
    attachment = LegacyIssueAttachment(
        id="attachment-1",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="revision-1",
        stable_record_id="stable-1",
        record_id=record.id,
        filename="blower-noise.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description="소음 원인 분석",
        storage_key="legacy-issues/test/blower-noise.pptx",
    )

    chunk = _build_attachment_summary_chunk(
        definition=definition,
        record=record,
        attachment=attachment,
        summary="저단 운전 조건에서 BLOWER FAN 진동 소음이 발생하며 모터 고정부 확인 필요",
        now=utcnow_naive(),
    )

    assert chunk.chunk_kind == "attachment_summary"
    assert chunk.attachment_artifact_type == "ai_summary"
    assert "BLOWER FAN" in chunk.search_text
    assert {"blower", "fan", "진동", "소음"} <= set(chunk.search_terms or [])


def test_draft_attachment_copy_preserves_index_and_summary_metadata() -> None:
    now = utcnow_naive()
    source = LegacyIssueAttachment(
        id="source-attachment",
        workspace_id="workspace-1",
        dataset_key="past_vehicle_body",
        revision_id="published-revision",
        stable_record_id="stable-1",
        record_id="published-record",
        filename="indexed.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description="원인 분석",
        storage_key="legacy-issues/test/indexed.pptx",
        is_primary=True,
        index_status="indexed",
        indexed_at=now,
        index_version="legacy_issue_attachment_index.v2",
        chunk_count=3,
        artifact_count=2,
        ai_summary="# 문서 추출 색인 카드",
        ai_summary_status="summarized",
        ai_summary_model="legacy/model-id",
        ai_summary_version="legacy_issue_attachment_summary.v2",
        ai_summarized_at=now,
        uploaded_by_id="user-1",
        created_at=now,
    )

    copied = _copy_dataset_attachment_for_revision(
        source,
        workspace_id="workspace-1",
        dataset_key="past_vehicle_body",
        target_revision_id="draft-revision",
        target_record_id="draft-record",
        stable_record_id="stable-1",
    )

    assert copied.id != source.id
    assert copied.revision_id == "draft-revision"
    assert copied.record_id == "draft-record"
    assert copied.storage_key == source.storage_key
    assert copied.index_status == "indexed"
    assert copied.indexed_at == now
    assert copied.chunk_count == 3
    assert copied.artifact_count == 2
    assert copied.ai_summary == "# 문서 추출 색인 카드"
    assert copied.ai_summary_status == "summarized"
    assert copied.ai_summary_model == "legacy/model-id"
    assert copied.ai_summarized_at == now


def test_draft_attachment_copy_resets_in_flight_index_states() -> None:
    source = LegacyIssueAttachment(
        id="source-attachment",
        workspace_id="workspace-1",
        dataset_key="past_vehicle_body",
        revision_id="published-revision",
        stable_record_id="stable-1",
        record_id="published-record",
        filename="processing.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description=None,
        storage_key="legacy-issues/test/processing.pptx",
        index_status="processing",
        chunk_count=2,
        artifact_count=1,
        ai_summary="pending output",
        ai_summary_status="pending",
    )

    copied = _copy_dataset_attachment_for_revision(
        source,
        workspace_id="workspace-1",
        dataset_key="past_vehicle_body",
        target_revision_id="draft-revision",
        target_record_id="draft-record",
        stable_record_id="stable-1",
    )

    assert copied.index_status == "not_indexed"
    assert copied.indexed_at is None
    assert copied.chunk_count == 0
    assert copied.artifact_count == 0
    assert copied.ai_summary is None
    assert copied.ai_summary_status == "not_summarized"
    assert copied.ai_summarized_at is None


def test_draft_attachment_chunk_copy_retargets_attachment_metadata() -> None:
    now = utcnow_naive()
    source_attachment = LegacyIssueAttachment(
        id="source-attachment",
        workspace_id="workspace-1",
        dataset_key="past_vehicle_body",
        revision_id="published-revision",
        stable_record_id="stable-1",
        record_id="published-record",
        filename="indexed.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description="원본 설명",
        storage_key="legacy-issues/test/indexed.pptx",
    )
    target_attachment = LegacyIssueAttachment(
        id="target-attachment",
        workspace_id="workspace-1",
        dataset_key="past_vehicle_body",
        revision_id="draft-revision",
        stable_record_id="stable-1",
        record_id="draft-record",
        filename="indexed.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description="원본 설명",
        storage_key="legacy-issues/test/indexed.pptx",
    )
    source_chunk = LegacyIssueAiChunk(
        id="source-chunk",
        workspace_id="workspace-1",
        dataset_key="past_vehicle_body",
        revision_id="published-revision",
        record_id="published-record",
        stable_record_id="stable-1",
        attachment_id="source-attachment",
        attachment_filename="indexed.pptx",
        attachment_artifact_type="ai_summary",
        chunk_key="attachment:source-attachment:ai_summary",
        chunk_kind="attachment_summary",
        field_label="첨부파일 AI 추출 키워드",
        field_value="키워드",
        search_text="indexed.pptx 키워드",
        search_terms=["indexed", "키워드"],
        embedding_vector="[0.1,0.2]",
        embedding_model="embedding-model",
        embedding_dimensions=2,
        embedding_status="embedded",
        evidence_metadata={
            "attachment_id": "source-attachment",
            "attachment_filename": "indexed.pptx",
            "attachment_description": "원본 설명",
        },
        created_at=now,
        updated_at=now,
    )

    copied = _copy_dataset_attachment_ai_chunk(
        source_chunk,
        source_attachment=source_attachment,
        target_attachment=target_attachment,
    )

    assert copied.id != source_chunk.id
    assert copied.revision_id == "draft-revision"
    assert copied.record_id == "draft-record"
    assert copied.attachment_id == "target-attachment"
    assert copied.chunk_key == "attachment:target-attachment:ai_summary"
    assert copied.embedding_vector == "[0.1,0.2]"
    assert copied.search_terms == ["indexed", "키워드"]
    assert copied.evidence_metadata["attachment_id"] == "target-attachment"


def test_draft_attachment_projection_copy_flushes_attachment_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = LegacyIssueDatasetDefinition(
        key="past_vehicle_body",
        table_model=LegacyIssueRecord,
        title_ko="의장 과거차 문제점",
        title_en="Legacy Issues",
        hierarchy_ko=("과거차문제점",),
        hierarchy_en=("Legacy Issues",),
        fields=(),
    )
    source_record = LegacyIssueRecord(
        id="source-record",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="published-revision",
        stable_record_id="stable-1",
        field_values={"problem": "소음"},
    )
    source_attachment = LegacyIssueAttachment(
        id="source-attachment",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="published-revision",
        stable_record_id="stable-1",
        record_id=source_record.id,
        filename="indexed.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description=None,
        storage_key="legacy-issues/test/indexed.pptx",
        index_status="indexed",
        chunk_count=3,
        artifact_count=2,
        ai_summary_status="summarized",
        ai_summary="# 문서 추출 색인 카드",
    )
    events: list[str] = []

    class FakeSession:
        last_attachment: LegacyIssueAttachment | None = None

        def scalars(self, _statement):
            return [source_record]

        def add(self, row):
            if isinstance(row, LegacyIssueAttachment):
                self.last_attachment = row
                events.append("add_attachment")

        def get(self, model, revision_id):
            assert model is LegacyIssueDataRevision
            return SimpleNamespace(
                id=revision_id,
                workspace_id="workspace-1",
                base_revision_id=None,
                retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
            )

        def flush(self, rows=None):
            if rows and self.last_attachment is not None and rows == [self.last_attachment]:
                events.append("flush_attachment")
            else:
                events.append("flush")

    def fake_list_dataset_attachments(*_args, **_kwargs):
        return [source_attachment]

    def fake_copy_projection(_db, *, target_attachment, **_kwargs):
        assert target_attachment.id
        assert events[-1] == "flush_attachment"
        events.append("copy_projection")

    monkeypatch.setattr(
        "open_alm_api.domains.legacy_issues.dataset_records.list_dataset_attachments",
        fake_list_dataset_attachments,
    )
    monkeypatch.setattr(
        "open_alm_api.domains.legacy_issues.dataset_records._copy_dataset_attachment_index_projection",
        fake_copy_projection,
    )

    copy_dataset_revision_records(
        FakeSession(),
        definition,
        workspace=SimpleNamespace(id="workspace-1"),
        source_revision=SimpleNamespace(
            id="published-revision",
            workspace_id="workspace-1",
            base_revision_id=None,
            retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        ),
        target_revision=SimpleNamespace(
            id="draft-revision",
            workspace_id="workspace-1",
            base_revision_id=None,
            retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        ),
    )

    assert "copy_projection" in events


@pytest.mark.parametrize(
    ("source_status", "indexing_enabled", "expected_queue_count", "expected_target_status"),
    [
        ("pending", True, 1, "pending"),
        ("processing", True, 1, "pending"),
        ("pending", False, 0, "not_indexed"),
        ("failed", True, 0, "failed"),
        ("not_indexed", True, 0, "not_indexed"),
    ],
)
def test_draft_attachment_copy_requeues_in_flight_indexing(
    monkeypatch: pytest.MonkeyPatch,
    source_status: str,
    indexing_enabled: bool,
    expected_queue_count: int,
    expected_target_status: str,
) -> None:
    definition = LegacyIssueDatasetDefinition(
        key="past_vehicle_body",
        table_model=LegacyIssueRecord,
        title_ko="의장 과거차 문제점",
        title_en="Legacy Issues",
        hierarchy_ko=("과거차문제점",),
        hierarchy_en=("Legacy Issues",),
        fields=(),
    )
    source_record = LegacyIssueRecord(
        id="source-record",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="published-revision",
        stable_record_id="stable-1",
        field_values={"problem": "소음"},
    )
    source_attachment = LegacyIssueAttachment(
        id="source-attachment",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="published-revision",
        stable_record_id="stable-1",
        record_id=source_record.id,
        filename="processing.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description=None,
        storage_key="legacy-issues/test/processing.pptx",
        index_status=source_status,
    )
    queued: list[tuple[LegacyIssueAttachment, str]] = []

    class FakeSession:
        target_attachment: LegacyIssueAttachment | None = None

        def scalars(self, _statement):
            return [source_record]

        def add(self, row):
            if isinstance(row, LegacyIssueAttachment):
                self.target_attachment = row

        def get(self, model, revision_id):
            assert model is LegacyIssueDataRevision
            return SimpleNamespace(
                id=revision_id,
                workspace_id="workspace-1",
                base_revision_id=None,
                retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
            )

        @staticmethod
        def flush(_rows=None):
            return None

    monkeypatch.setattr(
        "open_alm_api.domains.legacy_issues.dataset_records.list_dataset_attachments",
        lambda *_args, **_kwargs: [source_attachment],
    )
    monkeypatch.setattr(
        "open_alm_api.domains.legacy_issues.settings.get_legacy_issue_settings",
        lambda: SimpleNamespace(ai_attachment_index_enabled=indexing_enabled),
    )

    def fake_enqueue(_db, *, attachment, trigger, **_kwargs):
        attachment.index_status = "pending"
        queued.append((attachment, trigger))
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr(
        attachment_indexing,
        "enqueue_legacy_issue_attachment_index_job",
        fake_enqueue,
    )

    db = FakeSession()
    copy_dataset_revision_records(
        db,
        definition,
        workspace=SimpleNamespace(id="workspace-1"),
        source_revision=SimpleNamespace(
            id="published-revision",
            workspace_id="workspace-1",
            base_revision_id=None,
            retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        ),
        target_revision=SimpleNamespace(
            id="draft-revision",
            workspace_id="workspace-1",
            base_revision_id=None,
            retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        ),
    )

    assert len(queued) == expected_queue_count
    target_attachment = queued[0][0] if queued else db.target_attachment
    assert target_attachment is not None
    assert target_attachment.revision_id == "draft-revision"
    assert target_attachment.record_id != source_record.id
    assert target_attachment.index_status == expected_target_status
    if queued:
        assert queued[0][1] == "draft_copy_inflight"


def test_attachment_text_chunks_skip_internal_extraction_errors() -> None:
    definition = LegacyIssueDatasetDefinition(
        key="past_vehicle_body",
        table_model=LegacyIssueRecord,
        title_ko="의장 과거차 문제점",
        title_en="Legacy Issues",
        hierarchy_ko=("과거차문제점",),
        hierarchy_en=("Legacy Issues",),
        fields=(),
    )
    record = LegacyIssueRecord(
        id="record-1",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="revision-1",
        stable_record_id="stable-1",
        field_values={"problem": "창문 서리 발생"},
    )
    attachment = LegacyIssueAttachment(
        id="attachment-1",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="revision-1",
        stable_record_id="stable-1",
        record_id=record.id,
        filename="blower-noise.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description=None,
        storage_key="legacy-issues/test/blower-noise.pptx",
    )

    chunks = _build_attachment_chunks(
        definition=definition,
        record=record,
        attachment=attachment,
        artifacts=[
            AttachmentExtractionArtifact(
                artifact_kind="vision_error",
                text="Vision extraction failed for blower-noise.pptx: vision_ocr_disabled",
            ),
            AttachmentExtractionArtifact(
                artifact_kind="ocr_text",
                text="ABC-123 장치 저속 작동 시 이상음 발생",
            ),
        ],
        now=utcnow_naive(),
    )

    assert len(chunks) == 1
    assert chunks[0].attachment_artifact_type == "ocr_text"
    assert "vision_ocr_disabled" not in chunks[0].search_text


def test_attachment_ai_summary_source_uses_attachment_text_not_related_row_fields() -> None:
    definition = LegacyIssueDatasetDefinition(
        key="past_vehicle_body",
        table_model=LegacyIssueRecord,
        title_ko="의장 과거차 문제점",
        title_en="Legacy Issues",
        hierarchy_ko=("과거차문제점",),
        hierarchy_en=("Legacy Issues",),
        fields=(),
    )
    record = LegacyIssueRecord(
        id="record-1",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="revision-1",
        stable_record_id="stable-1",
        field_values={"problem": "창문 서리 발생"},
    )
    attachment = LegacyIssueAttachment(
        id="attachment-1",
        workspace_id="workspace-1",
        dataset_key=definition.key,
        revision_id="revision-1",
        stable_record_id="stable-1",
        record_id=record.id,
        filename="blower-noise.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        size_bytes=123,
        description=None,
        storage_key="legacy-issues/test/blower-noise.pptx",
    )

    source_text = _attachment_summary_source_text(
        definition=definition,
        record=record,
        attachment=attachment,
        artifacts=[
            AttachmentExtractionArtifact(
                artifact_kind="ocr_text",
                text="ABC-123 장치 저속 작동 시 이상음 발생",
            ),
            AttachmentExtractionArtifact(
                artifact_kind="vision_error",
                text="Vision extraction failed for blower-noise.pptx: endpoint unavailable",
            ),
        ],
        chunks=[],
        limit=8000,
    )

    assert "ABC-123 장치" in source_text
    assert "창문 서리 발생" not in source_text
    assert "endpoint unavailable" not in source_text


def test_attachment_ai_summary_sanitizer_removes_ungrounded_undefined_term_explanations() -> None:
    summary = """# 요약
* **ABC**: 제조사 또는 부품명 약어 (원문 정의 없음)
* **SYS**: System Name (원문 정의 없음, 문맥상 시스템명)
* **MODEL-X**: 원문에서 정의된 뜻 없음 (원문 표기 유지)
* OVERALL: 기존 40.7 -> 오일도포 37.9 (평균 6.0dB ↓)
* **비고**: 평균 6.0dB ↓ (A열 관련), 평균 3.2dB ↓ (B열 관련)
* **표 데이터의 평균값 주석**: 표 하단 값은 A열 항목을 나타내는 것으로 보입니다.
* **원인 문구**: 접촉면 마찰에 의한 이상음
"""

    sanitized = _sanitize_attachment_summary(summary)

    assert "* **ABC**: (원문 정의 없음)" in sanitized
    assert "* **SYS**: (원문 정의 없음)" in sanitized
    assert "System Name" not in sanitized
    assert "제조사 또는 부품명" not in sanitized
    assert "* **MODEL-X**: (원문 정의 없음)" in sanitized
    assert "40.7 -> 오일도포 37.9 (평균" not in sanitized
    assert "(A열 관련)" not in sanitized
    assert "* **비고**: 평균 6.0dB ↓, 평균 3.2dB ↓" in sanitized
    assert "어떤 항목과 연결되는지는 변환 텍스트만으로 확정하지 않습니다" in sanitized
    assert "* **원인 문구**: 접촉면 마찰에 의한 이상음" in sanitized


def test_attachment_ai_summary_uses_gateway_with_internal_app_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        attachment_indexing,
        "get_legacy_issue_settings",
        lambda: SimpleNamespace(
            ai_attachment_summary_model="local-summary-model",
            ai_attachment_summary_max_tokens=512,
        ),
    )

    def fake_execute(workload_id, context, db, **kwargs):
        captured["workload_id"] = workload_id
        captured["context"] = context
        captured["db"] = db
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            completion=SimpleNamespace(
                text="* 원문 핵심 문구: 접촉면 마찰",
                model="local-model",
            )
        )

    monkeypatch.setattr(
        attachment_indexing,
        "execute_llm",
        fake_execute,
    )
    db = object()

    summary, model = attachment_indexing._generate_attachment_ai_summary(
        db,
        attachment=_attachment_for_revision("revision-1"),
        source_text="ABC-123 접촉면 마찰",
    )

    context = captured["context"]
    kwargs = captured["kwargs"]
    assert captured["db"] is db
    assert captured["workload_id"] == attachment_indexing.LEGACY_ISSUE_ATTACHMENT_SUMMARY_TASK_KIND
    assert context.app_id == "legacy-issues"
    assert context.workspace_id == "workspace-1"
    assert context.principal_kind == "system"
    assert kwargs["max_tokens"] == 512
    assert kwargs["context_pack"].content_origin == "internal_context"
    assert kwargs["context_pack"].sensitivity_labels == ("internal",)
    assert kwargs["context_pack"].source_kinds == ("legacy_issue_attachment",)
    assert "접촉면 마찰" in summary
    assert model == "local-model"
