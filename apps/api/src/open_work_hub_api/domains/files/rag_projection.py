from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from io import BytesIO
import mimetypes
from pathlib import Path
import re
from typing import Any, Protocol
from urllib.parse import urlencode
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload, undefer

from open_work_hub_api.core.app_routes import (
    InternalAppLocation,
    app_entry_href,
    build_app_href,
)
from open_work_hub_api.domains.document_processing import (
    EvidenceBlock,
    UnsupportedDocumentType,
    extract_document,
)
from open_work_hub_api.domains.document_processing.html_extractor import (
    HtmlExtractionError,
    validate_html_signature,
)
from open_work_hub_api.domains.files import storage_adapter as file_storage
from open_work_hub_api.domains.files.external_projection import (
    external_source_title,
    refresh_safe_external_source_metadata,
    safe_external_source_metadata,
)
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.retrieval_contract import FILES_RAG_SOURCE_KIND
from open_work_hub_api.domains.rag.chunking import (
    build_contextual_index_text,
    split_korean_aware_text,
    split_korean_aware_text_spans,
)
from open_work_hub_api.domains.rag.contracts import (
    RagChunk,
    RagProjection,
    RagScopeKind,
    RagVectorSearchHit,
)
from open_work_hub_api.domains.source_access.resource_types import FILE_MANAGER_FILE_RESOURCE_TYPE


FILES_EXTRACTION_PARSER_VERSION = "files-retrieval-v2"
FILES_OCR_POLICY_VERSION = "files-native-first-v1"
FILES_MIN_STRUCTURED_TEXT_CHARS = 128
FILES_RAG_CHUNKING_STRATEGY_VERSION = "files-retrieval-chunk-v2"
MAX_FILES_RAG_CHUNKS = 512
MAX_FILES_RAG_SOURCE_BYTES = 120 * 1024 * 1024
MAX_FILES_RAG_EXTRACTED_CHARS = 240_000
MAX_OFFICE_ARCHIVE_ENTRIES = 1_000
MAX_OFFICE_ARCHIVE_UNCOMPRESSED_BYTES = 240 * 1024 * 1024
MAX_OFFICE_ARCHIVE_ENTRY_BYTES = 120 * 1024 * 1024
MAX_OFFICE_ARCHIVE_COMPRESSION_RATIO = 100
_READ_CHUNK_BYTES = 1024 * 1024
_TEXT_SUFFIXES = {".csv", ".md", ".rst", ".text", ".txt"}
_HTML_SUFFIXES = {".htm", ".html"}
SUPPORTED_FILES_RAG_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".htm",
    ".html",
    ".jpeg",
    ".jpg",
    ".md",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rst",
    ".text",
    ".tif",
    ".tiff",
    ".webp",
    ".xls",
    ".xlsm",
    ".xlsx",
    ".txt",
}
_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}
_OCR_ENRICHMENT_MIME_TYPES = {
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_MIME_BY_OFFICE_MARKER = {
    "ppt/presentation.xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    "word/document.xml": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "xl/workbook.xml": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}
_OPENXML_MIME_TYPES = frozenset(_MIME_BY_OFFICE_MARKER.values())
_MIME_BY_OLE_SUFFIX = {
    ".doc": "application/msword",
    ".ppt": "application/vnd.ms-powerpoint",
    ".xls": "application/vnd.ms-excel",
}
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


class UnsupportedFileForRetrieval(ValueError):
    pass


class FileExtractionRuntime(Protocol):
    @property
    def ocr_provider_name(self) -> str | None: ...

    def extract_text(
        self,
        *,
        content: bytes,
        content_type: str | None = None,
        workspace_id: str | None = None,
        resource_type: str | None = None,
        source_kind: str | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class FileExtractionArtifact:
    content_checksum: str
    text: str
    blocks: list[EvidenceBlock]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class _FileChunkingResult:
    chunks: list[RagChunk]
    generated_count: int

    @property
    def truncated(self) -> bool:
        return self.generated_count > len(self.chunks)


def load_file_rag_projection(
    db: Session,
    *,
    file_id: str,
    rag_service: FileExtractionRuntime,
) -> RagProjection | None:
    file = db.scalar(
        select(FileManagerFile)
        .options(
            joinedload(FileManagerFile.owner),
            joinedload(FileManagerFile.source_metadata),
            joinedload(FileManagerFile.workspace),
            undefer(FileManagerFile.extraction_text),
            undefer(FileManagerFile.extraction_blocks),
            undefer(FileManagerFile.extraction_metadata),
        )
        .where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    if file is None:
        return None

    artifact = _cached_artifact(file)
    if artifact is None:
        try:
            content = read_file_content(file)
            artifact = extract_file_artifact(file=file, content=content, rag_service=rag_service)
        except UnsupportedFileForRetrieval as error:
            _mark_extraction_unsupported_if_active(db, file_id=file.id, reason=str(error))
            return None
        except Exception as error:
            setattr(error, "retrieval_failure_phase", "extraction")
            raise
        if not _store_artifact_if_active(db, file_id=file.id, artifact=artifact):
            return None
    return build_file_rag_projection(
        file=file,
        artifact=artifact,
        workspace_slug=file.workspace.key,
    )


def workspace_file_resource_ids(db: Session, workspace: Any) -> list[str]:
    return list(
        db.scalars(
            select(FileManagerFile.id)
            .where(
                FileManagerFile.workspace_id == workspace.id,
                FileManagerFile.deleted_at.is_(None),
            )
            .order_by(FileManagerFile.created_at.asc(), FileManagerFile.id.asc())
        )
    )


def read_file_content(file: FileManagerFile) -> bytes:
    if file.size_bytes > MAX_FILES_RAG_SOURCE_BYTES:
        raise UnsupportedFileForRetrieval("source_size_limit_exceeded")
    obj = file_storage.open_file_object(file.storage_key)
    content = bytearray()
    try:
        for chunk in obj.stream(_READ_CHUNK_BYTES):
            content.extend(chunk)
            if len(content) > MAX_FILES_RAG_SOURCE_BYTES:
                raise UnsupportedFileForRetrieval("source_size_limit_exceeded")
    finally:
        obj.close()
        obj.release_conn()
    return bytes(content)


def extract_file_artifact(
    *,
    file: FileManagerFile,
    content: bytes,
    rag_service: FileExtractionRuntime,
) -> FileExtractionArtifact:
    if not content:
        raise UnsupportedFileForRetrieval("empty_source")
    checksum = hashlib.sha256(content).hexdigest()
    observed_mime = detect_file_mime_type(filename=file.filename, content=content)
    if observed_mime in _OPENXML_MIME_TYPES:
        validate_office_archive(content)
    blocks: list[EvidenceBlock] = []
    parser_name = "ocr"
    structured_error: str | None = None
    format_metadata: dict[str, object] = {}

    if observed_mime == "text/html":
        try:
            bundle = extract_document(
                document_id=file.id,
                filename=_canonical_filename(file.filename, observed_mime),
                mime_type=observed_mime,
                content=content,
            )
        except UnsupportedDocumentType as error:
            raise UnsupportedFileForRetrieval("html_parse_failed") from error
        blocks.extend(bundle.evidence_blocks)
        format_metadata = dict(bundle.metadata)
        parser_name = "document_processing"
    elif observed_mime.startswith("text/"):
        text = _decode_plain_text(content)
        if text:
            blocks.append(
                EvidenceBlock(
                    document_id=file.id,
                    block_id=f"{file.id}:text:1",
                    locator_kind="document",
                    locator_label="Document",
                    section_path="Body",
                    block_kind="text",
                    text=text[:MAX_FILES_RAG_EXTRACTED_CHARS],
                )
            )
        parser_name = "plain_text"
    elif observed_mime not in _IMAGE_MIME_TYPES:
        try:
            bundle = extract_document(
                document_id=file.id,
                filename=_canonical_filename(file.filename, observed_mime),
                mime_type=observed_mime,
                content=content,
            )
        except UnsupportedDocumentType as error:
            structured_error = error.__class__.__name__
        else:
            blocks.extend(bundle.evidence_blocks)
            format_metadata = dict(bundle.metadata)
            parser_name = "document_processing"

    structured_text = _normalized_blocks_text(blocks)
    structured_chars = sum(len(block.text.strip()) for block in blocks)
    if observed_mime == "text/html" and structured_chars < FILES_MIN_STRUCTURED_TEXT_CHARS:
        raise UnsupportedFileForRetrieval("html_visible_text_below_minimum")
    ocr_status = "not_required"
    ocr_provider = None
    ocr_novel_text = ""
    ocr_attempted = False
    ocr_fallback_reason: str | None = None
    if observed_mime in _IMAGE_MIME_TYPES:
        ocr_fallback_reason = "image_source"
    elif observed_mime in _OCR_ENRICHMENT_MIME_TYPES:
        if not structured_text:
            ocr_fallback_reason = "structured_text_missing"
        elif structured_chars < FILES_MIN_STRUCTURED_TEXT_CHARS:
            ocr_fallback_reason = "structured_text_below_minimum"
        else:
            ocr_status = "skipped_structured_sufficient"

    if ocr_fallback_reason is not None:
        ocr_attempted = True
        ocr_provider = rag_service.ocr_provider_name
        try:
            ocr_text = rag_service.extract_text(
                content=content,
                content_type=observed_mime,
                workspace_id=file.workspace_id,
                resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
                source_kind=FILES_RAG_SOURCE_KIND,
            )
        except Exception as error:  # noqa: BLE001 - structured extraction may safely degrade
            ocr_status = f"failed:{error.__class__.__name__}"
            if not structured_text:
                raise
        else:
            if structured_text:
                ocr_novel_text = novel_ocr_text(
                    structured_text=structured_text,
                    ocr_text=ocr_text,
                    max_chars=max(
                        MAX_FILES_RAG_EXTRACTED_CHARS - len(structured_text),
                        0,
                    ),
                )
            else:
                ocr_novel_text = ocr_text.strip()[:MAX_FILES_RAG_EXTRACTED_CHARS]
            if ocr_novel_text:
                blocks.append(
                    EvidenceBlock(
                        document_id=file.id,
                        block_id=f"{file.id}:ocr:1",
                        locator_kind="document_ocr",
                        locator_label="OCR supplement",
                        section_path="OCR supplement",
                        block_kind="ocr_text",
                        text=ocr_novel_text,
                    )
                )
                ocr_status = "enriched" if structured_text else "primary"
                parser_name = f"{parser_name}+ocr" if structured_text else "ocr"
            else:
                ocr_status = "no_novel_text"

    text = _normalized_blocks_text(blocks)[:MAX_FILES_RAG_EXTRACTED_CHARS]
    if not text:
        raise UnsupportedFileForRetrieval("no_extractable_text")
    return FileExtractionArtifact(
        content_checksum=checksum,
        text=text,
        blocks=blocks,
        metadata={
            "parser": parser_name,
            "parser_version": FILES_EXTRACTION_PARSER_VERSION,
            "declared_mime_type": file.content_type,
            "observed_mime_type": observed_mime,
            "structured_error_code": structured_error,
            "structured_chars": structured_chars,
            **({"format_metadata": format_metadata} if format_metadata else {}),
            "ocr_provider": ocr_provider,
            "ocr_status": ocr_status,
            "ocr_attempted": ocr_attempted,
            "ocr_fallback_reason": ocr_fallback_reason,
            "ocr_min_structured_chars": FILES_MIN_STRUCTURED_TEXT_CHARS,
            "ocr_policy_version": FILES_OCR_POLICY_VERSION,
            "ocr_novel_chars": len(ocr_novel_text),
        },
    )


def build_file_rag_projection(
    *,
    file: FileManagerFile,
    artifact: FileExtractionArtifact,
    workspace_slug: str | None = None,
) -> RagProjection:
    chunking_result = _chunk_file_evidence(file=file, blocks=artifact.blocks)
    chunks = chunking_result.chunks
    corpus = file.corpus
    if corpus is not None and corpus.access_scope_kind == "company":
        scope_kind = RagScopeKind.COMPANY
        workspace_id = None
        visibility_refs = ["company_public"]
    elif corpus is not None:
        scope_kind = RagScopeKind.WORKSPACE
        workspace_id = corpus.managed_workspace_id
        visibility_refs = [f"workspace:{corpus.managed_workspace_id}"]
    else:
        scope_kind = RagScopeKind.WORKSPACE
        workspace_id = file.workspace_id
        visibility_refs = [f"owner:{file.owner_id}"]
        if file.visibility == "workspace":
            visibility_refs.append(f"workspace:{file.workspace_id}")
    return RagProjection(
        scope_kind=scope_kind,
        workspace_id=workspace_id,
        resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
        resource_id=file.id,
        source_kind=FILES_RAG_SOURCE_KIND,
        title=external_source_title(file),
        summary=_summary(artifact.text),
        text_content=artifact.text,
        owner_label=(
            file.owner.display_name or file.owner.full_name if file.owner is not None else None
        ),
        visibility_refs=visibility_refs,
        metadata={
            "origin_ref": _file_deep_link(file, workspace_slug=workspace_slug),
            "content_modality": "text",
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": file.size_bytes,
            "visibility": file.visibility,
            "corpus_id": file.corpus_id,
            "managed_workspace_id": (
                corpus.managed_workspace_id if corpus is not None else file.workspace_id
            ),
            "folder_id": file.folder_id,
            "content_checksum": artifact.content_checksum,
            **safe_external_source_metadata(file),
            **artifact.metadata,
            "chunking": {
                "strategy_version": FILES_RAG_CHUNKING_STRATEGY_VERSION,
                "hard_limit": MAX_FILES_RAG_CHUNKS,
                "generated_count": chunking_result.generated_count,
                "indexed_count": len(chunks),
                "truncated": chunking_result.truncated,
            },
        },
        chunks=chunks,
    )


def evidence_blocks_to_chunks(
    *,
    file: FileManagerFile,
    blocks: list[EvidenceBlock],
) -> list[RagChunk]:
    return _chunk_file_evidence(file=file, blocks=blocks).chunks


def _chunk_file_evidence(
    *,
    file: FileManagerFile,
    blocks: list[EvidenceBlock],
) -> _FileChunkingResult:
    generated_chunks = _generate_file_chunks(file=file, blocks=blocks)
    return _FileChunkingResult(
        chunks=generated_chunks[:MAX_FILES_RAG_CHUNKS],
        generated_count=len(generated_chunks),
    )


def _generate_file_chunks(
    *,
    file: FileManagerFile,
    blocks: list[EvidenceBlock],
) -> list[RagChunk]:
    grouped: dict[tuple[str, str, str], tuple[int, list[EvidenceBlock]]] = {}
    paragraph_runs: list[tuple[int, list[EvidenceBlock]]] = []
    current_paragraph_run: list[EvidenceBlock] = []
    current_paragraph_start = 0

    def flush_paragraph_run() -> None:
        nonlocal current_paragraph_run
        if current_paragraph_run:
            paragraph_runs.append((current_paragraph_start, current_paragraph_run))
            current_paragraph_run = []

    for block_index, block in enumerate(blocks):
        if block.locator_kind == "paragraph":
            if (
                current_paragraph_run
                and current_paragraph_run[-1].section_path != block.section_path
            ):
                flush_paragraph_run()
            if not current_paragraph_run:
                current_paragraph_start = block_index
            current_paragraph_run.append(block)
            continue

        flush_paragraph_run()
        key = (block.locator_kind, block.locator_label, block.section_path)
        if key not in grouped:
            grouped[key] = (block_index, [])
        grouped[key][1].append(block)
    flush_paragraph_run()

    work_units: list[tuple[int, str, list[EvidenceBlock]]] = [
        (start_index, "paragraph", run) for start_index, run in paragraph_runs
    ]
    work_units.extend(
        (start_index, "locator", locator_blocks) for start_index, locator_blocks in grouped.values()
    )

    chunks: list[RagChunk] = []
    for _, unit_kind, locator_blocks in sorted(work_units, key=lambda item: item[0]):
        if unit_kind == "paragraph":
            chunks.extend(
                _paragraph_blocks_to_chunks(
                    file=file,
                    blocks=locator_blocks,
                    chunk_index_start=len(chunks),
                )
            )
            continue

        first_block = locator_blocks[0]
        locator_kind = first_block.locator_kind
        locator_label = first_block.locator_label
        section_path = first_block.section_path
        body = "\n\n".join(block.text.strip() for block in locator_blocks if block.text.strip())
        for part_number, piece in enumerate(split_korean_aware_text(body), start=1):
            chunk_index = len(chunks)
            chunks.append(
                RagChunk(
                    chunk_id=f"{file.id}:{locator_kind}:{chunk_index}",
                    text=piece,
                    summary=_summary(piece),
                    index_text=build_contextual_index_text(
                        title=external_source_title(file),
                        page_title=locator_label,
                        section_path=[section_path],
                        body=piece,
                    ),
                    metadata={
                        "chunk_index": chunk_index,
                        "chunk_strategy": "files_locator_korean_v1",
                        "locator_kind": locator_kind,
                        "locator_label": locator_label,
                        "section_path": section_path,
                        "part_number": part_number,
                    },
                )
            )
    return chunks


def _paragraph_blocks_to_chunks(
    *,
    file: FileManagerFile,
    blocks: list[EvidenceBlock],
    chunk_index_start: int,
) -> list[RagChunk]:
    body_parts: list[str] = []
    paragraph_offsets: list[tuple[int, int, EvidenceBlock]] = []
    cursor = 0
    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if body_parts:
            cursor += 2
        start = cursor
        body_parts.append(text)
        cursor += len(text)
        paragraph_offsets.append((start, cursor, block))
    if not body_parts:
        return []

    body = "\n\n".join(body_parts)
    chunks: list[RagChunk] = []
    for part_number, span in enumerate(split_korean_aware_text_spans(body), start=1):
        covered_blocks = [
            block
            for start, end, block in paragraph_offsets
            if start < span.end and end > span.start
        ]
        if not covered_blocks:
            continue
        first_block = covered_blocks[0]
        last_block = covered_blocks[-1]
        locator_label = _locator_range_label(
            first_block.locator_label,
            last_block.locator_label,
        )
        chunk_index = chunk_index_start + len(chunks)
        chunks.append(
            RagChunk(
                chunk_id=f"{file.id}:paragraph:{chunk_index}",
                text=span.text,
                summary=_summary(span.text),
                index_text=build_contextual_index_text(
                    title=external_source_title(file),
                    page_title=locator_label,
                    section_path=[first_block.section_path],
                    body=span.text,
                ),
                metadata={
                    "chunk_index": chunk_index,
                    "chunk_strategy": "files_paragraph_range_korean_v1",
                    "locator_kind": "paragraph",
                    "locator_label": locator_label,
                    "locator_start_label": first_block.locator_label,
                    "locator_end_label": last_block.locator_label,
                    "section_path": first_block.section_path,
                    "part_number": part_number,
                },
            )
        )
    return chunks


def _locator_range_label(start_label: str, end_label: str) -> str:
    if start_label == end_label:
        return start_label
    return f"{start_label}–{end_label}"


def detect_file_mime_type(*, filename: str, content: bytes) -> str:
    head = content[:32]
    suffix = Path(filename).suffix.lower()
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] in {b"II*\x00", b"MM\x00*"}:
        return "image/tiff"
    if head.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"PK\x03\x04"):
        _validate_zip_directory_header(content)
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
        except (BadZipFile, OSError) as error:
            raise UnsupportedFileForRetrieval("invalid_zip_container") from error
        for marker, mime_type in _MIME_BY_OFFICE_MARKER.items():
            if marker in names:
                return mime_type
        raise UnsupportedFileForRetrieval("unsupported_zip_container")
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1") and suffix in _MIME_BY_OLE_SUFFIX:
        return _MIME_BY_OLE_SUFFIX[suffix]
    try:
        validate_html_signature(content)
    except HtmlExtractionError as error:
        if suffix in _HTML_SUFFIXES:
            raise UnsupportedFileForRetrieval("html_signature_mismatch") from error
    else:
        return "text/html"
    if suffix in _TEXT_SUFFIXES:
        _decode_plain_text(content)
        return mimetypes.guess_type(filename)[0] or "text/plain"
    raise UnsupportedFileForRetrieval("unsupported_content_signature")


def validate_office_archive(content: bytes) -> None:
    """Reject hostile OpenXML containers before any entry is decompressed."""

    _validate_zip_directory_header(content)
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
    except (BadZipFile, OSError) as error:
        raise UnsupportedFileForRetrieval("invalid_zip_container") from error
    if len(infos) > MAX_OFFICE_ARCHIVE_ENTRIES:
        raise UnsupportedFileForRetrieval("office_archive_entry_limit_exceeded")
    total_uncompressed = 0
    total_compressed = 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise UnsupportedFileForRetrieval("encrypted_office_archive")
        if info.file_size > MAX_OFFICE_ARCHIVE_ENTRY_BYTES:
            raise UnsupportedFileForRetrieval("office_archive_entry_size_limit_exceeded")
        total_uncompressed += info.file_size
        total_compressed += info.compress_size
        if total_uncompressed > MAX_OFFICE_ARCHIVE_UNCOMPRESSED_BYTES:
            raise UnsupportedFileForRetrieval("office_archive_uncompressed_limit_exceeded")
    if total_uncompressed and total_compressed <= 0:
        raise UnsupportedFileForRetrieval("office_archive_compression_ratio_exceeded")
    if (
        total_compressed
        and total_uncompressed / total_compressed > MAX_OFFICE_ARCHIVE_COMPRESSION_RATIO
    ):
        raise UnsupportedFileForRetrieval("office_archive_compression_ratio_exceeded")


def _validate_zip_directory_header(content: bytes) -> None:
    search_start = max(0, len(content) - 65_557)
    search_end = len(content)
    eocd_offset = -1
    while search_end > search_start:
        candidate = content.rfind(b"PK\x05\x06", search_start, search_end)
        if candidate < 0:
            break
        if candidate + 22 <= len(content):
            comment_length = int.from_bytes(content[candidate + 20 : candidate + 22], "little")
            if candidate + 22 + comment_length == len(content):
                eocd_offset = candidate
                break
        search_end = candidate
    if eocd_offset < 0:
        raise UnsupportedFileForRetrieval("invalid_zip_container")
    disk_number = int.from_bytes(content[eocd_offset + 4 : eocd_offset + 6], "little")
    central_directory_disk = int.from_bytes(content[eocd_offset + 6 : eocd_offset + 8], "little")
    disk_entries = int.from_bytes(content[eocd_offset + 8 : eocd_offset + 10], "little")
    total_entries = int.from_bytes(content[eocd_offset + 10 : eocd_offset + 12], "little")
    if disk_number or central_directory_disk or disk_entries != total_entries:
        raise UnsupportedFileForRetrieval("unsupported_multidisk_zip_container")
    if total_entries > MAX_OFFICE_ARCHIVE_ENTRIES or total_entries == 0xFFFF:
        raise UnsupportedFileForRetrieval("office_archive_entry_limit_exceeded")
    central_directory_size = int.from_bytes(content[eocd_offset + 12 : eocd_offset + 16], "little")
    central_directory_offset = int.from_bytes(
        content[eocd_offset + 16 : eocd_offset + 20], "little"
    )
    central_directory_end = central_directory_offset + central_directory_size
    if central_directory_end != eocd_offset:
        raise UnsupportedFileForRetrieval("invalid_zip_container")
    cursor = central_directory_offset
    observed_entries = 0
    while cursor < central_directory_end:
        if cursor + 46 > central_directory_end or content[cursor : cursor + 4] != b"PK\x01\x02":
            raise UnsupportedFileForRetrieval("invalid_zip_container")
        filename_length = int.from_bytes(content[cursor + 28 : cursor + 30], "little")
        extra_length = int.from_bytes(content[cursor + 30 : cursor + 32], "little")
        comment_length = int.from_bytes(content[cursor + 32 : cursor + 34], "little")
        cursor += 46 + filename_length + extra_length + comment_length
        observed_entries += 1
        if observed_entries > MAX_OFFICE_ARCHIVE_ENTRIES:
            raise UnsupportedFileForRetrieval("office_archive_entry_limit_exceeded")
    if cursor != central_directory_end or observed_entries != total_entries:
        raise UnsupportedFileForRetrieval("invalid_zip_container")


def novel_ocr_text(
    *,
    structured_text: str,
    ocr_text: str,
    max_chars: int = MAX_FILES_RAG_EXTRACTED_CHARS,
) -> str:
    structured_tokens = {token.casefold() for token in _TOKEN_RE.findall(structured_text)}
    novel_lines: list[str] = []
    chars = 0
    for raw_line in ocr_text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue
        tokens = {token.casefold() for token in _TOKEN_RE.findall(line)}
        novel = tokens - structured_tokens
        novel_chars = sum(len(token) for token in novel)
        if not novel or (novel_chars < 6 and len(novel) < 2):
            continue
        remaining = max_chars - chars
        if remaining <= 0:
            break
        clipped = line[:remaining]
        novel_lines.append(clipped)
        chars += len(clipped) + 1
    return "\n".join(novel_lines).strip()


def mark_file_extraction_failed(
    db: Session,
    *,
    file_id: str,
    error_code: str,
) -> None:
    db.execute(
        update(FileManagerFile)
        .where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_(None),
        )
        .values(
            extraction_status="failed",
            extraction_error_code=error_code[:120],
            extracted_at=datetime.now(UTC).replace(tzinfo=None),
        )
        .execution_options(synchronize_session=False)
    )


def purge_deleted_file_retrieval_artifact(db: Session, *, file_id: str) -> None:
    """Defensively enforce retention after a delete worker completes."""

    db.execute(
        update(FileManagerFile)
        .where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_not(None),
        )
        .values(
            extraction_status="pending",
            extraction_content_checksum=None,
            extraction_text=None,
            extraction_blocks=[],
            extraction_metadata={},
            extraction_error_code=None,
            extracted_at=None,
        )
        .execution_options(synchronize_session=False)
    )


def _cached_artifact(file: FileManagerFile) -> FileExtractionArtifact | None:
    if (
        file.extraction_status != "ready"
        or not file.extraction_content_checksum
        or not file.extraction_text
        or not file.extraction_blocks
    ):
        return None
    try:
        blocks = [EvidenceBlock(**dict(item)) for item in file.extraction_blocks]
    except (TypeError, ValueError):
        return None
    return FileExtractionArtifact(
        content_checksum=file.extraction_content_checksum,
        text=file.extraction_text,
        blocks=blocks,
        metadata=dict(file.extraction_metadata or {}),
    )


def _store_artifact_if_active(
    db: Session,
    *,
    file_id: str,
    artifact: FileExtractionArtifact,
) -> bool:
    result = db.execute(
        update(FileManagerFile)
        .where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_(None),
        )
        .values(
            extraction_status="ready",
            extraction_content_checksum=artifact.content_checksum,
            extraction_text=artifact.text,
            extraction_blocks=[block.to_dict() for block in artifact.blocks],
            extraction_metadata=dict(artifact.metadata),
            extraction_error_code=None,
            extracted_at=datetime.now(UTC).replace(tzinfo=None),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def _mark_extraction_unsupported_if_active(
    db: Session,
    *,
    file_id: str,
    reason: str,
) -> bool:
    result = db.execute(
        update(FileManagerFile)
        .where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_(None),
        )
        .values(
            extraction_status="unsupported",
            extraction_content_checksum=None,
            extraction_text=None,
            extraction_blocks=[],
            extraction_metadata={
                "parser_version": FILES_EXTRACTION_PARSER_VERSION,
                "unsupported_reason": reason[:120],
            },
            extraction_error_code=reason[:120],
            extracted_at=datetime.now(UTC).replace(tzinfo=None),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


def _normalized_blocks_text(blocks: list[EvidenceBlock]) -> str:
    lines = [
        f"[{block.locator_label}] {block.text.strip()}" for block in blocks if block.text.strip()
    ]
    return "\n".join(lines).strip()


def _decode_plain_text(content: bytes) -> str:
    if b"\x00" in content[:4096]:
        raise UnsupportedFileForRetrieval("binary_content_disguised_as_text")
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    raise UnsupportedFileForRetrieval("unsupported_text_encoding")


def _canonical_filename(filename: str, mime_type: str) -> str:
    suffix_by_mime = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "text/html": ".html",
    }
    suffix = suffix_by_mime.get(mime_type)
    if suffix is None:
        return filename
    return f"{Path(filename).stem}{suffix}"


def _summary(text: str, *, max_chars: int = 240) -> str | None:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _file_deep_link(
    file: FileManagerFile,
    *,
    workspace_slug: str | None = None,
) -> str:
    query = {"file": file.id}
    if file.folder_id:
        query["folder"] = file.folder_id
    if workspace_slug:
        return build_app_href(
            InternalAppLocation(
                route_id="files.root",
                workspace_slug=workspace_slug,
                query_params=query,
            )
        )
    return f"{app_entry_href('files')}?{urlencode(sorted(query.items()))}"


def hydrate_file_rag_hits_from_source(
    db: Session,
    *,
    hits: Sequence[RagVectorSearchHit],
) -> list[RagVectorSearchHit]:
    """Hydrate Files response scope from PostgreSQL without granting access.

    The vector payload is only a candidate envelope. The RAG query service
    invokes this before its final source-owned ACL pass, so stale workspace,
    visibility, and origin metadata cannot flow into grounding or citations.
    """

    file_ids = tuple(
        dict.fromkeys(
            hit.projection.resource_id
            for hit in hits
            if hit.projection.resource_type == FILE_MANAGER_FILE_RESOURCE_TYPE
        )
    )
    files_by_id = (
        {
            file.id: file
            for file in db.scalars(
                select(FileManagerFile)
                .options(
                    joinedload(FileManagerFile.corpus),
                    joinedload(FileManagerFile.source_metadata),
                    joinedload(FileManagerFile.workspace),
                )
                .where(
                    FileManagerFile.id.in_(file_ids),
                    FileManagerFile.deleted_at.is_(None),
                )
            )
        }
        if file_ids
        else {}
    )

    hydrated: list[RagVectorSearchHit] = []
    for hit in hits:
        projection = hit.projection
        if projection.resource_type != FILE_MANAGER_FILE_RESOURCE_TYPE:
            hydrated.append(hit)
            continue
        file = files_by_id.get(projection.resource_id)
        if file is None:
            continue
        corpus = file.corpus
        if corpus is not None and corpus.access_scope_kind == "company":
            scope_kind = RagScopeKind.COMPANY
            workspace_id = None
            visibility_refs = ["company_public"]
            access_scope_kind = "company"
            managed_workspace_id = corpus.managed_workspace_id
        elif corpus is not None:
            scope_kind = RagScopeKind.WORKSPACE
            workspace_id = corpus.managed_workspace_id
            visibility_refs = [f"workspace:{corpus.managed_workspace_id}"]
            access_scope_kind = "workspace"
            managed_workspace_id = corpus.managed_workspace_id
        else:
            scope_kind = RagScopeKind.WORKSPACE
            workspace_id = file.workspace_id
            visibility_refs = [f"owner:{file.owner_id}"]
            if file.visibility == "workspace":
                visibility_refs.append(f"workspace:{file.workspace_id}")
            access_scope_kind = "workspace"
            managed_workspace_id = file.workspace_id

        metadata = refresh_safe_external_source_metadata(
            dict(projection.metadata),
            file=file,
        )
        metadata.update(
            {
                "origin_ref": _file_deep_link(
                    file,
                    # Resource visibility may be company-wide, but the file
                    # still has one owning workspace route context.
                    workspace_slug=file.workspace.key,
                ),
                "filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": file.size_bytes,
                "visibility": (access_scope_kind if corpus is not None else file.visibility),
                "corpus_id": file.corpus_id,
                "access_scope_kind": access_scope_kind,
                "managed_workspace_id": managed_workspace_id,
                "folder_id": file.folder_id,
            }
        )
        fresh_projection = projection.model_copy(
            update={
                "retrieval_partition_id": file.retrieval_partition_id,
                "scope_kind": scope_kind,
                "workspace_id": workspace_id,
                "title": external_source_title(file),
                "visibility_refs": visibility_refs,
                "metadata": metadata,
            }
        )
        hydrated.append(hit.model_copy(update={"projection": fresh_projection}))
    return hydrated


__all__ = [
    "FILES_EXTRACTION_PARSER_VERSION",
    "FILES_MIN_STRUCTURED_TEXT_CHARS",
    "FILES_OCR_POLICY_VERSION",
    "FILES_RAG_SOURCE_KIND",
    "MAX_FILES_RAG_CHUNKS",
    "SUPPORTED_FILES_RAG_SUFFIXES",
    "FileExtractionArtifact",
    "FileExtractionRuntime",
    "UnsupportedFileForRetrieval",
    "validate_office_archive",
    "build_file_rag_projection",
    "detect_file_mime_type",
    "evidence_blocks_to_chunks",
    "extract_file_artifact",
    "hydrate_file_rag_hits_from_source",
    "load_file_rag_projection",
    "mark_file_extraction_failed",
    "novel_ocr_text",
    "purge_deleted_file_retrieval_artifact",
    "read_file_content",
    "workspace_file_resource_ids",
]
