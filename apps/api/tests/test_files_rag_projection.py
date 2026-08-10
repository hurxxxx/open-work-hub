from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from open_work_hub_api.domains.document_processing import DocumentExtractBundle, EvidenceBlock
from open_work_hub_api.domains.files.models import (
    FileManagerCorpus,
    FileManagerFile,
    FileManagerFileSourceMetadata,
)
from open_work_hub_api.domains.files import rag_projection, rag_sync
from open_work_hub_api.domains.files.rag_projection import (
    FILES_MIN_STRUCTURED_TEXT_CHARS,
    FILES_OCR_POLICY_VERSION,
    MAX_FILES_RAG_SOURCE_BYTES,
    UnsupportedFileForRetrieval,
    build_file_rag_projection,
    detect_file_mime_type,
    extract_file_artifact,
    read_file_content,
    validate_office_archive,
)
from open_work_hub_api.domains.files.retrieval_contract import (
    files_retrieval_active_for_environment,
)
from open_work_hub_api.domains.files.source_access import FileManagerSourceAccessAdapter
from open_work_hub_api.domains.files.search_projection import build_file_search_document
from open_work_hub_api.domains.files.service import purge_file_retrieval_artifact
from open_work_hub_api.domains.rag.contracts import RagScopeKind, RagSyncOperation
from open_work_hub_api.domains.retrieval.projection_fencing import ProjectionEventRef
from open_work_hub_api.domains.search.projection_identity import ensure_search_document_identity


_FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


def _file(**overrides) -> FileManagerFile:
    values = {
        "id": "file-1",
        "workspace_id": "workspace-1",
        "folder_id": "folder-1",
        "owner_id": "user-1",
        "filename": "quarterly-plan.pptx",
        "content_type": "application/octet-stream",
        "size_bytes": 100,
        "storage_key": "files/workspace-1/file-1/quarterly-plan.pptx",
        "visibility": "workspace",
    }
    values.update(overrides)
    return FileManagerFile(**values)


def _pptx_signature() -> bytes:
    return _openxml_signature("ppt/presentation.xml")


def _openxml_signature(marker: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        _write_deterministic_zip_entry(archive, "[Content_Types].xml", b"<Types />")
        _write_deterministic_zip_entry(archive, marker, b"<document />")
    return output.getvalue()


def _hostile_openxml_archive(marker: str) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        _write_deterministic_zip_entry(archive, "[Content_Types].xml", b"<Types />")
        _write_deterministic_zip_entry(archive, marker, b"<document />")
        _write_deterministic_zip_entry(
            archive,
            "payload.bin",
            b"x" * (2 * 1024 * 1024),
        )
    return output.getvalue()


def _write_deterministic_zip_entry(
    archive: ZipFile,
    filename: str,
    content: bytes,
) -> None:
    entry = ZipInfo(filename=filename, date_time=_FIXED_ZIP_TIMESTAMP)
    entry.compress_type = ZIP_DEFLATED
    archive.writestr(entry, content)


def test_openxml_fixture_uses_fixed_entry_timestamps() -> None:
    with ZipFile(BytesIO(_openxml_signature("word/document.xml"))) as archive:
        timestamps = {entry.date_time for entry in archive.infolist()}

    assert timestamps == {_FIXED_ZIP_TIMESTAMP}


def test_files_retrieval_activation_requires_partition_generation() -> None:
    assert (
        files_retrieval_active_for_environment(
            environment="development",
            env_profile="dev",
            rag_enabled=True,
            operator_enabled=True,
            partition_generation_ready=True,
        )
        is True
    )
    assert (
        files_retrieval_active_for_environment(
            environment="development",
            env_profile="dev",
            rag_enabled=True,
            operator_enabled=True,
        )
        is False
    )
    assert (
        files_retrieval_active_for_environment(
            environment="development",
            env_profile="dev",
            rag_enabled=True,
            partition_generation_ready=True,
        )
        is False
    )
    assert (
        files_retrieval_active_for_environment(
            environment="development",
            env_profile="dev",
            rag_enabled=False,
            operator_enabled=True,
            partition_generation_ready=True,
        )
        is False
    )
    assert (
        files_retrieval_active_for_environment(
            environment="production",
            env_profile="prod",
            rag_enabled=True,
            operator_enabled=True,
            partition_generation_ready=True,
        )
        is True
    )


def test_detect_file_mime_uses_server_observed_signature() -> None:
    assert (
        detect_file_mime_type(
            filename="renamed.bin",
            content=_pptx_signature(),
        )
        == "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )

    with pytest.raises(UnsupportedFileForRetrieval, match="invalid_zip_container"):
        detect_file_mime_type(filename="fake.pptx", content=b"PK\x03\x04broken")

    with pytest.raises(UnsupportedFileForRetrieval, match="unsupported_content_signature"):
        detect_file_mime_type(filename="payload.pdf", content=b"not a pdf")

    assert (
        detect_file_mime_type(
            filename="report.html",
            content=b"<!doctype html><html><body><p>report</p></body></html>",
        )
        == "text/html"
    )
    with pytest.raises(UnsupportedFileForRetrieval, match="html_signature_mismatch"):
        detect_file_mime_type(filename="disguised.html", content=b"ordinary plain text")


@pytest.mark.parametrize("marker", ["word/document.xml", "xl/workbook.xml"])
def test_openxml_preflight_rejects_extreme_compression_ratio(marker: str) -> None:
    content = _hostile_openxml_archive(marker)

    assert "openxmlformats" in detect_file_mime_type(filename="renamed.bin", content=content)
    with pytest.raises(
        UnsupportedFileForRetrieval,
        match="office_archive_compression_ratio_exceeded",
    ):
        validate_office_archive(content)


def test_zip_entry_limit_is_checked_from_eocd_before_member_materialization() -> None:
    content = bytearray(_pptx_signature())
    eocd_offset = content.rfind(b"PK\x05\x06")
    assert eocd_offset >= 0
    encoded_count = (1001).to_bytes(2, "little")
    content[eocd_offset + 8 : eocd_offset + 10] = encoded_count
    content[eocd_offset + 10 : eocd_offset + 12] = encoded_count

    with pytest.raises(
        UnsupportedFileForRetrieval,
        match="office_archive_entry_limit_exceeded",
    ):
        detect_file_mime_type(filename="hostile.pptx", content=bytes(content))


def test_pptx_artifact_skips_ocr_when_structured_text_is_sufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = _file()
    structured_text = "히터 시스템 정상 운전 절차입니다. " * 12
    structured_block = EvidenceBlock(
        document_id=file.id,
        block_id=f"{file.id}:slide:7:text:1",
        locator_kind="slide",
        locator_label="Slide 7",
        section_path="Slide 7",
        block_kind="text",
        text=structured_text,
    )
    monkeypatch.setattr(
        rag_projection,
        "extract_document",
        lambda **kwargs: DocumentExtractBundle(
            document_id=file.id,
            filename=kwargs["filename"],
            mime_type=kwargs["mime_type"],
            evidence_blocks=[structured_block],
        ),
    )
    rag_service = SimpleNamespace(
        ocr_provider_name="test-ocr",
        extract_text=lambda **kwargs: pytest.fail("sufficient native text must not call OCR"),
    )

    artifact = extract_file_artifact(
        file=file,
        content=_pptx_signature(),
        rag_service=rag_service,
    )
    projection = build_file_rag_projection(file=file, artifact=artifact)

    assert artifact.metadata["observed_mime_type"].endswith("presentationml.presentation")
    assert artifact.metadata["ocr_status"] == "skipped_structured_sufficient"
    assert artifact.metadata["ocr_provider"] is None
    assert artifact.metadata["ocr_attempted"] is False
    assert artifact.metadata["ocr_fallback_reason"] is None
    assert artifact.metadata["ocr_policy_version"] == FILES_OCR_POLICY_VERSION
    assert structured_text.strip() in artifact.text
    assert "owner:user-1" in projection.visibility_refs
    assert "workspace:workspace-1" in projection.visibility_refs
    assert projection.metadata["content_modality"] == "text"
    assert any(chunk.metadata["locator_label"] == "Slide 7" for chunk in projection.chunks)
    assert not any(chunk.metadata["locator_kind"] == "document_ocr" for chunk in projection.chunks)


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("procedure.docx", _openxml_signature("word/document.xml")),
        ("limits.xlsx", _openxml_signature("xl/workbook.xml")),
        ("overview.pptx", _pptx_signature()),
        ("manual.pdf", b"%PDF-1.7\n% native text document placeholder"),
    ],
    ids=("docx", "xlsx", "pptx", "pdf"),
)
def test_supported_documents_use_native_text_before_ocr(
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
    content: bytes,
) -> None:
    file = _file(filename=filename)
    native_text = "네이티브 문서 파서가 추출한 검색 가능한 본문입니다. " * 10
    monkeypatch.setattr(
        rag_projection,
        "extract_document",
        lambda **kwargs: DocumentExtractBundle(
            document_id=file.id,
            filename=kwargs["filename"],
            mime_type=kwargs["mime_type"],
            evidence_blocks=[
                EvidenceBlock(
                    document_id=file.id,
                    block_id=f"{file.id}:native:1",
                    locator_kind="document",
                    locator_label="Document",
                    section_path="Body",
                    block_kind="text",
                    text=native_text,
                )
            ],
            metadata={"native_marker": "preserved"},
        ),
    )

    artifact = extract_file_artifact(
        file=file,
        content=content,
        rag_service=SimpleNamespace(
            ocr_provider_name="test-ocr",
            extract_text=lambda **kwargs: pytest.fail(
                f"{filename} with sufficient native text must not call OCR"
            ),
        ),
    )

    assert artifact.metadata["parser"] == "document_processing"
    assert artifact.metadata["ocr_attempted"] is False
    assert artifact.metadata["ocr_status"] == "skipped_structured_sufficient"
    assert artifact.metadata["ocr_fallback_reason"] is None
    assert artifact.metadata["format_metadata"] == {"native_marker": "preserved"}


def test_html_artifact_uses_safe_structured_extraction_without_ocr() -> None:
    file = _file(filename="report.html", content_type="text/html")
    content = (
        "<!doctype html><html><head><title>시험 보고서</title></head><body>"
        "<h1>열관리 결과</h1>"
        f"<p>{'냉각 성능 검증 결과 정상 범위를 확인했습니다. ' * 8}</p>"
        "<table><tr><th>항목</th><th>결과</th></tr>"
        "<tr><td>냉각수 온도</td><td>82 C</td></tr></table>"
        "<script>외부 전송 실행 본문</script>"
        "</body></html>"
    ).encode()

    artifact = extract_file_artifact(
        file=file,
        content=content,
        rag_service=SimpleNamespace(
            ocr_provider_name="test-ocr",
            extract_text=lambda **kwargs: pytest.fail("HTML must never call OCR"),
        ),
    )
    projection = build_file_rag_projection(file=file, artifact=artifact)

    assert artifact.metadata["observed_mime_type"] == "text/html"
    assert artifact.metadata["parser"] == "document_processing"
    assert artifact.metadata["ocr_attempted"] is False
    assert artifact.metadata["format_metadata"]["format"] == "html"
    assert artifact.metadata["format_metadata"]["charset"] == "utf-8-sig"
    assert artifact.metadata["format_metadata"]["table_row_count"] == 2
    assert "외부 전송 실행 본문" not in artifact.text
    assert any(chunk.metadata["locator_kind"] == "table_row" for chunk in projection.chunks)


def test_html_artifact_rejects_helper_page_below_visible_text_minimum() -> None:
    file = _file(filename="iframe_history.html", content_type="text/html")

    with pytest.raises(
        UnsupportedFileForRetrieval,
        match="html_visible_text_below_minimum",
    ):
        extract_file_artifact(
            file=file,
            content=b"<!doctype html><html><body><p>history helper</p></body></html>",
            rag_service=SimpleNamespace(
                ocr_provider_name="test-ocr",
                extract_text=lambda **kwargs: pytest.fail("helper HTML must never call OCR"),
            ),
        )


def test_pptx_artifact_uses_ocr_fallback_when_structured_text_is_below_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = _file()
    structured_block = EvidenceBlock(
        document_id=file.id,
        block_id=f"{file.id}:slide:1:text:1",
        locator_kind="slide",
        locator_label="Slide 1",
        section_path="Slide 1",
        block_kind="text",
        text="히터 정상 온도는 80도입니다.",
    )
    monkeypatch.setattr(
        rag_projection,
        "extract_document",
        lambda **kwargs: DocumentExtractBundle(
            document_id=file.id,
            filename=kwargs["filename"],
            mime_type=kwargs["mime_type"],
            evidence_blocks=[structured_block],
        ),
    )
    calls: list[dict] = []

    def extract_text(**kwargs) -> str:
        calls.append(kwargs)
        return "히터 정상 온도는 80도입니다.\n비상 정지 압력은 12 bar 입니다."

    artifact = extract_file_artifact(
        file=file,
        content=_pptx_signature(),
        rag_service=SimpleNamespace(
            ocr_provider_name="test-ocr",
            extract_text=extract_text,
        ),
    )

    assert len(calls) == 1
    assert calls[0]["content_type"].endswith("presentationml.presentation")
    assert artifact.metadata["structured_chars"] == len(structured_block.text)
    assert artifact.metadata["ocr_attempted"] is True
    assert artifact.metadata["ocr_fallback_reason"] == "structured_text_below_minimum"
    assert artifact.metadata["ocr_min_structured_chars"] == FILES_MIN_STRUCTURED_TEXT_CHARS
    assert artifact.metadata["ocr_status"] == "enriched"
    assert artifact.metadata["ocr_provider"] == "test-ocr"
    assert "비상 정지 압력" in artifact.text
    assert any(block.locator_kind == "document_ocr" for block in artifact.blocks)


def test_short_native_text_survives_failed_ocr_fallback_with_failure_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = _file()
    native_text = "짧지만 검색 가능한 네이티브 본문"
    monkeypatch.setattr(
        rag_projection,
        "extract_document",
        lambda **kwargs: DocumentExtractBundle(
            document_id=file.id,
            filename=kwargs["filename"],
            mime_type=kwargs["mime_type"],
            evidence_blocks=[
                EvidenceBlock(
                    document_id=file.id,
                    block_id=f"{file.id}:slide:1:text:1",
                    locator_kind="slide",
                    locator_label="Slide 1",
                    section_path="Slide 1",
                    block_kind="text",
                    text=native_text,
                )
            ],
        ),
    )

    def fail_ocr(**kwargs) -> str:
        raise TimeoutError("provider timeout must not leak into artifact metadata")

    artifact = extract_file_artifact(
        file=file,
        content=_pptx_signature(),
        rag_service=SimpleNamespace(
            ocr_provider_name="test-ocr",
            extract_text=fail_ocr,
        ),
    )

    assert native_text in artifact.text
    assert artifact.metadata["ocr_attempted"] is True
    assert artifact.metadata["ocr_fallback_reason"] == "structured_text_below_minimum"
    assert artifact.metadata["ocr_status"] == "failed:TimeoutError"
    assert artifact.metadata["ocr_provider"] == "test-ocr"
    assert not any(block.locator_kind == "document_ocr" for block in artifact.blocks)


def test_scanned_pdf_uses_ocr_as_primary_when_structured_text_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = _file(filename="scan.pdf")
    monkeypatch.setattr(
        rag_projection,
        "extract_document",
        lambda **kwargs: DocumentExtractBundle(
            document_id=file.id,
            filename=kwargs["filename"],
            mime_type=kwargs["mime_type"],
            evidence_blocks=[],
        ),
    )
    calls: list[dict] = []

    def extract_text(**kwargs) -> str:
        calls.append(kwargs)
        return "스캔 문서에서 추출한 점검 절차"

    artifact = extract_file_artifact(
        file=file,
        content=b"%PDF-1.7\n% scanned document placeholder",
        rag_service=SimpleNamespace(
            ocr_provider_name="test-ocr",
            extract_text=extract_text,
        ),
    )

    assert len(calls) == 1
    assert artifact.metadata["structured_chars"] == 0
    assert artifact.metadata["ocr_attempted"] is True
    assert artifact.metadata["ocr_fallback_reason"] == "structured_text_missing"
    assert artifact.metadata["ocr_status"] == "primary"
    assert artifact.metadata["parser"] == "ocr"
    assert artifact.blocks[0].locator_kind == "document_ocr"


def test_image_artifact_records_image_ocr_fallback_provenance() -> None:
    file = _file(filename="diagram.png")
    calls: list[dict] = []

    def extract_text(**kwargs) -> str:
        calls.append(kwargs)
        return "도면 이미지의 히터 배관 표기"

    artifact = extract_file_artifact(
        file=file,
        content=b"\x89PNG\r\n\x1a\nplaceholder",
        rag_service=SimpleNamespace(
            ocr_provider_name="test-ocr",
            extract_text=extract_text,
        ),
    )

    assert len(calls) == 1
    assert artifact.metadata["ocr_attempted"] is True
    assert artifact.metadata["ocr_fallback_reason"] == "image_source"
    assert artifact.metadata["ocr_status"] == "primary"
    assert artifact.metadata["ocr_provider"] == "test-ocr"


def test_docx_adjacent_paragraphs_are_chunked_with_locator_ranges() -> None:
    file = _file(filename="procedure.docx")
    artifact = rag_projection.FileExtractionArtifact(
        content_checksum="a" * 64,
        text="document body",
        blocks=[
            EvidenceBlock(
                document_id=file.id,
                block_id=f"{file.id}:para{paragraph_number}",
                locator_kind="paragraph",
                locator_label=f"¶{paragraph_number}",
                section_path="Body",
                block_kind="text",
                text=f"단락 {paragraph_number} " + ("가" * 280),
            )
            for paragraph_number in range(1, 5)
        ],
        metadata={"parser": "document_processing"},
    )

    projection = build_file_rag_projection(file=file, artifact=artifact)

    assert len(projection.chunks) == 2
    assert projection.chunks[0].metadata == {
        "chunk_index": 0,
        "chunk_strategy": "files_paragraph_range_korean_v1",
        "locator_kind": "paragraph",
        "locator_label": "¶1–¶3",
        "locator_start_label": "¶1",
        "locator_end_label": "¶3",
        "section_path": "Body",
        "part_number": 1,
    }
    assert projection.chunks[1].metadata["locator_label"] == "¶3–¶4"
    assert projection.chunks[1].metadata["locator_start_label"] == "¶3"
    assert projection.chunks[1].metadata["locator_end_label"] == "¶4"
    assert all(len(chunk.text) <= 1_400 for chunk in projection.chunks)
    assert projection.metadata["chunking"] == {
        "strategy_version": "files-retrieval-chunk-v2",
        "hard_limit": 512,
        "generated_count": 2,
        "indexed_count": 2,
        "truncated": False,
    }


def test_docx_paragraph_ranges_do_not_cross_a_table_locator() -> None:
    file = _file(filename="procedure.docx")

    def paragraph(number: int) -> EvidenceBlock:
        return EvidenceBlock(
            document_id=file.id,
            block_id=f"{file.id}:para{number}",
            locator_kind="paragraph",
            locator_label=f"¶{number}",
            section_path="Body",
            block_kind="text",
            text=f"단락 {number} " + ("가" * 280),
        )

    table = EvidenceBlock(
        document_id=file.id,
        block_id=f"{file.id}:table1",
        locator_kind="table",
        locator_label="Table 1",
        section_path="Body",
        block_kind="table",
        text="table evidence",
    )
    artifact = rag_projection.FileExtractionArtifact(
        content_checksum="a" * 64,
        text="document body",
        blocks=[paragraph(1), paragraph(2), table, paragraph(3), paragraph(4)],
        metadata={"parser": "document_processing"},
    )

    projection = build_file_rag_projection(file=file, artifact=artifact)

    assert [chunk.metadata["locator_label"] for chunk in projection.chunks] == [
        "¶1–¶2",
        "Table 1",
        "¶3–¶4",
    ]


def test_file_projection_caps_chunks_and_records_explicit_truncation_metadata() -> None:
    file = _file(filename="many-locators.docx")
    artifact = rag_projection.FileExtractionArtifact(
        content_checksum="a" * 64,
        text="document body",
        blocks=[
            EvidenceBlock(
                document_id=file.id,
                block_id=f"{file.id}:block:{block_number}",
                locator_kind="document",
                locator_label=f"Block {block_number}",
                section_path="Body",
                block_kind="text",
                text=f"evidence {block_number}",
            )
            for block_number in range(1, 514)
        ],
        metadata={"parser": "document_processing"},
    )

    projection = build_file_rag_projection(file=file, artifact=artifact)
    repeated_projection = build_file_rag_projection(file=file, artifact=artifact)

    assert len(projection.chunks) == 512
    assert projection.chunks[-1].metadata["locator_label"] == "Block 512"
    assert projection.metadata["chunking"] == {
        "strategy_version": "files-retrieval-chunk-v2",
        "hard_limit": 512,
        "generated_count": 513,
        "indexed_count": 512,
        "truncated": True,
    }
    assert [chunk.model_dump() for chunk in repeated_projection.chunks] == [
        chunk.model_dump() for chunk in projection.chunks
    ]


def test_file_reader_closes_storage_response_and_enforces_declared_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StoredObject:
        closed = False
        released = False

        def stream(self, chunk_size: int):
            assert chunk_size > 0
            yield b"first"
            yield b"second"

        def close(self) -> None:
            self.closed = True

        def release_conn(self) -> None:
            self.released = True

    stored = StoredObject()
    monkeypatch.setattr(
        rag_projection.file_storage,
        "open_file_object",
        lambda storage_key: stored,
    )

    assert read_file_content(_file(filename="notes.txt", size_bytes=11)) == b"firstsecond"
    assert stored.closed is True
    assert stored.released is True

    with pytest.raises(UnsupportedFileForRetrieval, match="source_size_limit_exceeded"):
        read_file_content(_file(size_bytes=MAX_FILES_RAG_SOURCE_BYTES + 1))


def test_file_keyword_acl_covers_owner_workspace_member_and_admin() -> None:
    adapter = FileManagerSourceAccessAdapter()

    def policy(role: str | None):
        return SimpleNamespace(
            user=SimpleNamespace(id="user-1"),
            workspace_role=role,
            _keyword_acl_clause=lambda field, value: (field, value),
            _keyword_entity_branch=lambda entity_type, clauses: (entity_type, clauses),
        )

    member_branch = adapter.keyword_acl_branches(policy("member"))[0]
    assert member_branch == (
        "file",
        [("owner_user_id", "user-1"), ("visibility", "workspace")],
    )

    admin_branch = adapter.keyword_acl_branches(policy("admin"))[0]
    assert admin_branch == (
        "file",
        [
            ("owner_user_id", "user-1"),
            ("visibility", ["private", "workspace"]),
        ],
    )


def test_file_keyword_projection_uses_same_resource_identity_as_rag() -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    file = _file(
        extraction_status="ready",
        extraction_content_checksum="a" * 64,
        extraction_text="히터 시스템 비상 정지 압력은 12 bar 입니다.",
        extraction_metadata={"parser_version": "files-retrieval-v1"},
        updated_at=now,
    )

    document = build_file_search_document(
        workspace=SimpleNamespace(id="workspace-1", key="engineering"),
        file=file,
    )

    assert document["entity_type"] == "file"
    assert document["entity_id"] == file.id
    assert document["metadata"]["resource_type"] == "file_manager_file"
    assert document["metadata"]["resource_id"] == file.id
    assert document["metadata"]["source_kind"] == "files"
    assert document["visibility"] == "workspace"
    assert document["deep_link"].startswith("/w/engineering/files?")
    assert "비상 정지 압력" in document["body"]
    ensure_search_document_identity(
        document,
        workspace_id="workspace-1",
        allowed_entity_types=("file",),
        expected_entity_id=file.id,
        context="file projection test",
    )


def test_external_source_typed_metadata_is_searchable_without_private_source_fields() -> None:
    now = datetime(2026, 8, 4, 9, 30)
    file = _file(
        corpus_id="corpus-1",
        extraction_status="ready",
        extraction_content_checksum="a" * 64,
        extraction_text="냉각 성능 검증 결과",
        extraction_metadata={"parser": "test"},
        updated_at=now,
    )
    file.source_metadata = FileManagerFileSourceMetadata(
        file_id=file.id,
        corpus_id="corpus-1",
        external_id="private-upstream-id",
        external_id_sha256="b" * 64,
        source_kind="external_repository",
        source_id="private-source-id",
        source_id_sha256="c" * 64,
        source_version="private-revision",
        source_uri="private://internal/locator",
        title="냉각 성능 기술 보고서",
        author="홍길동",
        authored_at=datetime(2026, 8, 1),
        department="연구개발팀",
        document_type="기술보고서",
        source_updated_at=now,
        content_checksum="d" * 64,
        raw_metadata={"private_secret": "must-not-project"},
        acl_resolved=True,
    )
    artifact = rag_projection.FileExtractionArtifact(
        content_checksum="a" * 64,
        text="냉각 성능 검증 결과",
        blocks=[
            EvidenceBlock(
                document_id=file.id,
                block_id=f"{file.id}:text:1",
                locator_kind="document",
                locator_label="Document",
                section_path="Body",
                block_kind="text",
                text="냉각 성능 검증 결과",
            )
        ],
        metadata={"parser": "test"},
    )

    keyword = build_file_search_document(
        workspace=SimpleNamespace(id="workspace-1", key="engineering"),
        file=file,
    )
    vector = build_file_rag_projection(file=file, artifact=artifact)

    assert keyword["title"] == "냉각 성능 기술 보고서"
    assert keyword["metadata"]["origin_source_kind"] == "external_repository"
    assert keyword["metadata"]["author"] == "홍길동"
    assert keyword["metadata"]["department"] == "연구개발팀"
    assert keyword["metadata"]["document_type"] == "기술보고서"
    assert keyword["date_markers"]["authored_at"] == "2026-08-01T00:00:00"
    assert {target["label"] for target in keyword["targets"]} >= {
        "external_repository",
        "홍길동",
        "연구개발팀",
        "기술보고서",
    }
    assert vector.title == "냉각 성능 기술 보고서"
    assert vector.metadata["origin_source_kind"] == "external_repository"
    assert "냉각 성능 기술 보고서" in vector.chunks[0].index_text
    projected = repr({"keyword": keyword, "vector": vector.model_dump(mode="json")})
    assert "private-upstream-id" not in projected
    assert "private-source-id" not in projected
    assert "private-revision" not in projected
    assert "private://internal/locator" not in projected
    assert "must-not-project" not in projected


def test_large_extraction_artifacts_are_deferred_and_purged_on_soft_delete() -> None:
    assert FileManagerFile.extraction_text.property.deferred is True
    assert FileManagerFile.extraction_blocks.property.deferred is True
    assert FileManagerFile.extraction_metadata.property.deferred is True
    file = _file(
        extraction_status="ready",
        extraction_content_checksum="a" * 64,
        extraction_text="민감한 히터 설계 본문",
        extraction_blocks=[{"text": "민감한 히터 설계 본문"}],
        extraction_metadata={"parser": "document_processing"},
        extraction_error_code="old-error",
        extracted_at=datetime.now(UTC).replace(tzinfo=None),
    )

    purge_file_retrieval_artifact(file)

    assert file.extraction_status == "pending"
    assert file.extraction_content_checksum is None
    assert file.extraction_text is None
    assert file.extraction_blocks == []
    assert file.extraction_metadata == {}
    assert file.extraction_error_code is None
    assert file.extracted_at is None


def test_file_retrieval_hook_obeys_named_activation_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []
    projection_events: list[dict] = []
    monkeypatch.setattr(
        rag_sync,
        "enqueue_rag_sync_job",
        lambda db, **kwargs: calls.append(("rag", kwargs)),
    )
    monkeypatch.setattr(
        rag_sync,
        "enqueue_file_search_index_by_id",
        lambda db, **kwargs: calls.append(("search", kwargs)),
    )
    monkeypatch.setattr(
        rag_sync,
        "get_settings",
        lambda: SimpleNamespace(rag_enabled=True),
    )
    envelope = rag_sync._FileProjectionEnvelope(
        retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        scope_kind=RagScopeKind.WORKSPACE,
        workspace_id="workspace-1",
    )
    projection_event = ProjectionEventRef(
        event_sequence=1,
        resource_type="file_manager_file",
        resource_id="file-1",
        projection_version=1,
        retrieval_partition_id=envelope.retrieval_partition_id,
        change_kind="delete",
        desired_state="deleted",
        content_checksum=None,
        visibility_checksum=None,
        diagnostic_workspace_id="workspace-1",
    )
    monkeypatch.setattr(
        rag_sync,
        "_resolve_file_projection_envelope",
        lambda db, *, file: envelope,
    )
    monkeypatch.setattr(
        rag_sync,
        "record_projection_event",
        lambda db, **kwargs: projection_events.append(kwargs) or projection_event,
    )

    file = _file()
    monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", False)
    rag_sync.enqueue_file_retrieval_sync(
        SimpleNamespace(),
        file=file,
        operation=RagSyncOperation.UPSERT,
    )
    assert calls == []
    assert projection_events == [
        {
            "resource_type": "file_manager_file",
            "resource_id": file.id,
            "retrieval_partition_id": envelope.retrieval_partition_id,
            "change_kind": rag_sync.RetrievalProjectionChangeKind.CONTENT,
            "desired_state": rag_sync.RetrievalProjectionDesiredState.ACTIVE,
            "content_checksum": file.extraction_content_checksum,
            "diagnostic_workspace_id": file.workspace_id,
        }
    ]

    monkeypatch.setattr(rag_sync, "FILES_RETRIEVAL_ACTIVE", True)
    rag_sync.enqueue_file_retrieval_sync(
        SimpleNamespace(),
        file=file,
        operation=RagSyncOperation.DELETE,
    )

    assert calls[0] == (
        "search",
        {
            "file_id": file.id,
            "operation": "delete",
            "projection_event": projection_event,
        },
    )
    assert calls[1][0] == "rag"
    assert calls[1][1]["resource_type"] == "file_manager_file"
    assert calls[1][1]["operation"] == RagSyncOperation.DELETE
    assert calls[1][1]["projection_event"] == projection_event
    assert len(projection_events) == 2


def test_file_keyword_projection_is_enqueued_when_extraction_is_prepared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(
        rag_sync,
        "enqueue_file_search_index_by_id",
        lambda db, **kwargs: calls.append(kwargs),
    )

    projection_event = ProjectionEventRef(
        event_sequence=2,
        resource_type="file_manager_file",
        resource_id="file-1",
        projection_version=2,
        retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        change_kind="content",
        desired_state="active",
        content_checksum="a" * 64,
        visibility_checksum=None,
        diagnostic_workspace_id="workspace-1",
    )
    file = _file(extraction_content_checksum="a" * 64)
    rag_sync.mark_file_projection_prepared(
        SimpleNamespace(get=lambda model, file_id, **kwargs: file if file_id == file.id else None),
        file_id="file-1",
        projection_event=projection_event,
    )

    assert calls == [
        {
            "file_id": "file-1",
            "operation": "upsert",
            "projection_event": projection_event,
        }
    ]


def test_file_extraction_checksum_change_advances_projection_before_backend_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file = _file(extraction_content_checksum="b" * 64)
    db = SimpleNamespace(get=lambda model, file_id, **kwargs: file if file_id == file.id else None)
    search_calls: list[dict] = []
    rag_calls: list[dict] = []
    monkeypatch.setattr(
        rag_sync,
        "enqueue_file_search_index_by_id",
        lambda db, **kwargs: search_calls.append(kwargs),
    )
    monkeypatch.setattr(
        rag_sync,
        "enqueue_file_retrieval_sync",
        lambda db, **kwargs: rag_calls.append(kwargs),
    )
    stale_event = ProjectionEventRef(
        event_sequence=1,
        resource_type="file_manager_file",
        resource_id=file.id,
        projection_version=1,
        retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        change_kind="content",
        desired_state="active",
        content_checksum=None,
        visibility_checksum=None,
        diagnostic_workspace_id=file.workspace_id,
    )

    rag_sync.mark_file_projection_prepared(
        db,
        file_id=file.id,
        projection_event=stale_event,
    )

    assert search_calls == []
    assert rag_calls == [
        {
            "file": file,
            "operation": RagSyncOperation.UPSERT,
        }
    ]


def test_rag_delete_completion_only_purges_artifacts_without_duplicate_search_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purged: list[str] = []
    monkeypatch.setattr(
        rag_sync,
        "purge_deleted_file_retrieval_artifact",
        lambda db, *, file_id: purged.append(file_id),
    )
    monkeypatch.setattr(
        rag_sync,
        "enqueue_file_search_index_by_id",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("the source delete event already owns the fenced keyword delete")
        ),
    )

    rag_sync.mark_file_projection_deleted(SimpleNamespace(), file_id="file-1")

    assert purged == ["file-1"]


def test_company_corpus_projection_uses_company_candidate_scope() -> None:
    file = _file(corpus_id="corpus-1")
    file.corpus = FileManagerCorpus(
        id="corpus-1",
        name="Company corpus",
        managed_workspace_id="workspace-1",
        access_scope_kind="company",
        retrieval_partition_id="a3b6638a-7547-45f8-81f2-973bfa6080d6",
        created_by_id="user-1",
    )
    artifact = rag_projection.FileExtractionArtifact(
        content_checksum="a" * 64,
        text="company evidence",
        blocks=[
            EvidenceBlock(
                document_id=file.id,
                block_id=f"{file.id}:text:1",
                locator_kind="document",
                locator_label="Document",
                section_path="Document",
                block_kind="text",
                text="company evidence",
            )
        ],
        metadata={"parser": "test"},
    )

    projection = build_file_rag_projection(file=file, artifact=artifact)

    assert projection.scope_kind == RagScopeKind.COMPANY
    assert projection.workspace_id is None
    assert projection.visibility_refs == ["company_public"]
    assert projection.metadata["managed_workspace_id"] == "workspace-1"


def test_vector_provider_failure_does_not_overwrite_ready_extraction_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []
    monkeypatch.setattr(
        rag_sync,
        "mark_file_extraction_failed",
        lambda db, **kwargs: calls.append(kwargs),
    )

    rag_sync.mark_file_projection_failed(
        SimpleNamespace(),
        file_id="file-1",
        error="embedding provider unavailable",
        phase="rag",
    )
    assert calls == []

    rag_sync.mark_file_projection_failed(
        SimpleNamespace(),
        file_id="file-1",
        error="document parser failed",
        phase="extraction",
    )
    assert calls == [
        {
            "file_id": "file-1",
            "error_code": "extraction:document parser failed",
        }
    ]
