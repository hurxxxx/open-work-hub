"""Build a privacy-preserving, read-only Files RAG canary manifest.

The harness inventories an existing directory without uploading files or
calling Open Work Hub services.  Standard output and optional manifests contain only
aggregate statistics and SHA-256 identifiers; source names and bodies are
never serialized.

Dry-run inventory is the only connected mode today.  ``--execute-ingest`` is
reserved behind an explicit corpus argument so a future adapter cannot
accidentally turn an inventory command into an ingest.
"""

from __future__ import annotations

import argparse
import codecs
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import warnings
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Sequence

from open_work_hub_api.domains.document_processing.html_extractor import (
    HtmlExtractionError,
    extract_html_stream,
)

SCHEMA_VERSION = "open-work-hub.files-rag-readonly-manifest.v2"
MAX_SOURCE_BYTES = 120 * 1024 * 1024
MAX_OFFICE_ARCHIVE_ENTRIES = 1_000
MAX_OFFICE_ARCHIVE_UNCOMPRESSED_BYTES = 240 * 1024 * 1024
MAX_OFFICE_ARCHIVE_ENTRY_BYTES = 120 * 1024 * 1024
MAX_OFFICE_ARCHIVE_COMPRESSION_RATIO = 100
MAX_PDF_PAGES = 10_000
HASH_CHUNK_BYTES = 1024 * 1024
HTML_INSPECTION_MAX_CHARS = 4096

TEXT_EXTENSIONS = frozenset({"csv", "md", "rst", "text", "txt"})
HTML_EXTENSIONS = frozenset({"htm", "html"})
IMAGE_EXTENSIONS = frozenset({"jpeg", "jpg", "png", "tif", "tiff", "webp"})
OPENXML_MARKERS = {
    "docx": "word/document.xml",
    "pptx": "ppt/presentation.xml",
    "xlsx": "xl/workbook.xml",
    "xlsm": "xl/workbook.xml",
}
OLE_REQUIRED_STREAMS = {
    "doc": ("worddocument",),
    "ppt": ("powerpoint document",),
    "xls": ("workbook", "book"),
}
SUPPORTED_EXTENSIONS = frozenset(
    TEXT_EXTENSIONS
    | HTML_EXTENSIONS
    | IMAGE_EXTENSIONS
    | OPENXML_MARKERS.keys()
    | OLE_REQUIRED_STREAMS.keys()
    | {"pdf"}
)
EVALUATION_MODES = ("keyword", "semantic", "hybrid")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_EXTENSION_RE = re.compile(r"^[a-z0-9]{1,10}$")


class HarnessContractError(Exception):
    """A safe, stable error whose code may be printed without source data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FileExcluded(Exception):
    """A source file that must not become an ingest canary."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Candidate:
    path: Path
    source_id: str
    extension: str
    size_bytes: int
    device: int
    inode: int
    modified_ns: int


@dataclass(frozen=True)
class Inspection:
    candidate: Candidate
    content_sha256: str | None = None
    exclusion_reason: str | None = None


@dataclass(frozen=True)
class SourceTreeInspection:
    source_root: Path
    eligible: tuple[Inspection, ...]
    reason_counts: Counter[str]
    reason_bytes: Counter[str]
    extension_totals: dict[str, Counter[str]]
    regular_file_count: int
    regular_file_bytes: int

    @property
    def excluded_entry_count(self) -> int:
        return sum(self.reason_counts.values())


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _source_id(relative_path: Path) -> str:
    encoded = relative_path.as_posix().encode("utf-8", errors="surrogateescape")
    return _sha256_bytes(b"open-work-hub-files-source-v1\0" + encoded)


def _source_root_id(source_root: Path) -> str:
    encoded = os.fsencode(str(source_root))
    return _sha256_bytes(b"open-work-hub-files-source-root-v1\0" + encoded)


def _public_extension(path: Path) -> str:
    suffix = path.suffix.lower().removeprefix(".")
    if PUBLIC_EXTENSION_RE.fullmatch(suffix):
        return suffix
    return "other"


def _is_office_temporary(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name.startswith("~$")
        or name.startswith(".~lock.")
        or name.startswith(".tmp")
        or name.endswith((".tmp", ".temp", ".autosave"))
    )


def _is_html_companion_asset(relative_path: Path, extension: str) -> bool:
    if extension not in IMAGE_EXTENSIONS:
        return False
    parent_parts = {part.casefold() for part in relative_path.parts[:-1]}
    return "support" in parent_parts and bool(
        parent_parts & {"lib", "slwebview_files"}
    )


def _size_bucket(size_bytes: int) -> str:
    if size_bytes < 64 * 1024:
        return "tiny_lt_64k"
    if size_bytes < 1024 * 1024:
        return "small_64k_1m"
    if size_bytes < 10 * 1024 * 1024:
        return "medium_1m_10m"
    return "large_10m_120m"


def _record_exclusion(
    reason_counts: Counter[str],
    reason_bytes: Counter[str],
    reason: str,
    size_bytes: int,
) -> None:
    reason_counts[reason] += 1
    reason_bytes[reason] += max(0, size_bytes)


def _scan_source(
    source_root: Path,
) -> tuple[
    list[Candidate],
    Counter[str],
    Counter[str],
    dict[str, Counter[str]],
    int,
    int,
]:
    candidates: list[Candidate] = []
    reason_counts: Counter[str] = Counter()
    reason_bytes: Counter[str] = Counter()
    extension_totals: dict[str, Counter[str]] = defaultdict(Counter)
    regular_file_count = 0
    regular_file_bytes = 0

    def on_walk_error(_error: OSError) -> None:
        _record_exclusion(reason_counts, reason_bytes, "unreadable_directory", 0)

    for directory, directory_names, filenames in os.walk(
        source_root,
        topdown=True,
        followlinks=False,
        onerror=on_walk_error,
    ):
        directory_path = Path(directory)
        kept_directories: list[str] = []
        for directory_name in sorted(directory_names, key=os.fsencode):
            child = directory_path / directory_name
            try:
                child_stat = child.lstat()
            except OSError:
                _record_exclusion(reason_counts, reason_bytes, "unreadable_entry", 0)
                continue
            if stat.S_ISLNK(child_stat.st_mode):
                _record_exclusion(reason_counts, reason_bytes, "symlink_directory", 0)
                continue
            kept_directories.append(directory_name)
        directory_names[:] = kept_directories

        for filename in sorted(filenames, key=os.fsencode):
            path = directory_path / filename
            try:
                file_stat = path.lstat()
            except OSError:
                _record_exclusion(reason_counts, reason_bytes, "unreadable_entry", 0)
                continue
            if stat.S_ISLNK(file_stat.st_mode):
                _record_exclusion(reason_counts, reason_bytes, "symlink_file", 0)
                continue
            if not stat.S_ISREG(file_stat.st_mode):
                _record_exclusion(reason_counts, reason_bytes, "special_file", 0)
                continue

            extension = _public_extension(path)
            size_bytes = file_stat.st_size
            regular_file_count += 1
            regular_file_bytes += size_bytes
            extension_totals[extension]["file_count"] += 1
            extension_totals[extension]["bytes"] += size_bytes

            try:
                relative_path = path.relative_to(source_root)
            except ValueError:
                _record_exclusion(
                    reason_counts, reason_bytes, "source_boundary_changed", size_bytes
                )
                continue
            if _is_office_temporary(path):
                _record_exclusion(reason_counts, reason_bytes, "office_temporary_file", size_bytes)
                continue
            if _is_html_companion_asset(relative_path, extension):
                _record_exclusion(reason_counts, reason_bytes, "html_companion_asset", size_bytes)
                continue
            if extension not in SUPPORTED_EXTENSIONS:
                _record_exclusion(reason_counts, reason_bytes, "unsupported_extension", size_bytes)
                continue
            if size_bytes > MAX_SOURCE_BYTES:
                _record_exclusion(
                    reason_counts, reason_bytes, "source_size_limit_exceeded", size_bytes
                )
                continue
            candidates.append(
                Candidate(
                    path=path,
                    source_id=_source_id(relative_path),
                    extension=extension,
                    size_bytes=size_bytes,
                    device=file_stat.st_dev,
                    inode=file_stat.st_ino,
                    modified_ns=file_stat.st_mtime_ns,
                )
            )
    return (
        candidates,
        reason_counts,
        reason_bytes,
        extension_totals,
        regular_file_count,
        regular_file_bytes,
    )


def _open_candidate(candidate: Candidate) -> BinaryIO:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate.path, flags)
    except OSError as error:
        raise FileExcluded("unreadable_file") from error
    stream = os.fdopen(descriptor, "rb")
    opened_stat = os.fstat(stream.fileno())
    identity = (
        opened_stat.st_dev,
        opened_stat.st_ino,
        opened_stat.st_size,
        opened_stat.st_mtime_ns,
    )
    expected = (
        candidate.device,
        candidate.inode,
        candidate.size_bytes,
        candidate.modified_ns,
    )
    if not stat.S_ISREG(opened_stat.st_mode) or identity != expected:
        stream.close()
        raise FileExcluded("source_changed_during_scan")
    return stream


def _validate_openxml(stream: BinaryIO, extension: str) -> None:
    stream.seek(0)
    try:
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_OFFICE_ARCHIVE_ENTRIES:
                raise FileExcluded("office_archive_entry_limit_exceeded")
            total_uncompressed = 0
            total_compressed = 0
            normalized_names: set[str] = set()
            for info in infos:
                normalized_name = info.filename.replace("\\", "/")
                parts = PurePosixPath(normalized_name).parts
                if (
                    normalized_name.startswith("/")
                    or any(part == ".." for part in parts)
                    or (parts and ":" in parts[0])
                ):
                    raise FileExcluded("unsafe_office_archive_path")
                normalized_names.add(normalized_name)
                if info.flag_bits & 0x1:
                    raise FileExcluded("encrypted_office_archive")
                if info.file_size > MAX_OFFICE_ARCHIVE_ENTRY_BYTES:
                    raise FileExcluded("office_archive_entry_size_limit_exceeded")
                total_uncompressed += info.file_size
                total_compressed += info.compress_size
                if total_uncompressed > MAX_OFFICE_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise FileExcluded("office_archive_uncompressed_limit_exceeded")
                if info.file_size and info.compress_size <= 0:
                    raise FileExcluded("office_archive_compression_ratio_exceeded")
                if (
                    info.compress_size
                    and info.file_size / info.compress_size > MAX_OFFICE_ARCHIVE_COMPRESSION_RATIO
                ):
                    raise FileExcluded("office_archive_compression_ratio_exceeded")
            if total_uncompressed and total_compressed <= 0:
                raise FileExcluded("office_archive_compression_ratio_exceeded")
            if (
                total_compressed
                and total_uncompressed / total_compressed > MAX_OFFICE_ARCHIVE_COMPRESSION_RATIO
            ):
                raise FileExcluded("office_archive_compression_ratio_exceeded")
            if OPENXML_MARKERS[extension] not in normalized_names:
                raise FileExcluded("office_container_type_mismatch")
            if archive.testzip() is not None:
                raise FileExcluded("corrupt_office_archive")
    except FileExcluded:
        raise
    except (EOFError, OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        raise FileExcluded("corrupt_office_archive") from error


def _ole_stream_names(ole: object) -> dict[str, object]:
    names: dict[str, object] = {}
    for parts in ole.listdir(streams=True, storages=False):  # type: ignore[attr-defined]
        normalized = "/".join(parts).casefold()
        names[normalized] = parts
    return names


def _validate_ole(stream: BinaryIO, extension: str, *, openxml_extension: bool = False) -> None:
    import olefile

    stream.seek(0)
    try:
        with olefile.OleFileIO(stream) as ole:
            names = _ole_stream_names(ole)
            encrypted_names = {"encryptedpackage", "encryptioninfo", "encryptedsummary"}
            if any(name.rsplit("/", 1)[-1] in encrypted_names for name in names):
                raise FileExcluded("encrypted_office_container")
            if openxml_extension:
                raise FileExcluded("office_container_type_mismatch")
            required = OLE_REQUIRED_STREAMS[extension]
            required_name = next(
                (name for name in names if name.rsplit("/", 1)[-1] in required),
                None,
            )
            if required_name is None:
                raise FileExcluded("office_container_type_mismatch")
            stream_ref = names[required_name]
            if extension == "doc":
                header = ole.openstream(stream_ref).read(12)
                if len(header) < 12:
                    raise FileExcluded("corrupt_office_container")
                fib_flags = int.from_bytes(header[10:12], "little")
                if fib_flags & 0x0100:
                    raise FileExcluded("encrypted_office_container")
            elif extension == "xls":
                workbook = ole.openstream(stream_ref)
                scanned = 0
                while scanned < 2 * 1024 * 1024:
                    record_header = workbook.read(4)
                    if not record_header:
                        break
                    if len(record_header) != 4:
                        raise FileExcluded("corrupt_office_container")
                    record_id = int.from_bytes(record_header[:2], "little")
                    record_size = int.from_bytes(record_header[2:], "little")
                    if record_id == 0x002F:
                        raise FileExcluded("encrypted_office_container")
                    if record_size > MAX_OFFICE_ARCHIVE_ENTRY_BYTES:
                        raise FileExcluded("corrupt_office_container")
                    payload = workbook.read(record_size)
                    if len(payload) != record_size:
                        raise FileExcluded("corrupt_office_container")
                    scanned += 4 + record_size
    except FileExcluded:
        raise
    except (EOFError, OSError, ValueError, olefile.OleFileError) as error:
        raise FileExcluded("corrupt_office_container") from error


def _validate_pdf(stream: BinaryIO) -> None:
    import fitz

    stream.seek(0)
    content = stream.read()
    try:
        document = fitz.open(stream=content, filetype="pdf")
        try:
            if document.needs_pass:
                raise FileExcluded("encrypted_pdf")
            page_count = document.page_count
            if page_count <= 0:
                raise FileExcluded("empty_pdf")
            if page_count > MAX_PDF_PAGES:
                raise FileExcluded("pdf_page_limit_exceeded")
            if document.is_repaired:
                raise FileExcluded("repaired_pdf_container")
            for page_number in range(page_count):
                document.load_page(page_number)
        finally:
            document.close()
    except FileExcluded:
        raise
    except Exception as error:  # noqa: BLE001 - PyMuPDF exposes broad parser errors.
        raise FileExcluded("corrupt_pdf") from error


def _validate_image(stream: BinaryIO, extension: str, head: bytes) -> None:
    from PIL import Image

    stripped = head.lstrip().lower()
    if stripped.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        raise FileExcluded("html_like_image")
    signature_matches = {
        "png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpg": head.startswith(b"\xff\xd8\xff"),
        "jpeg": head.startswith(b"\xff\xd8\xff"),
        "tif": head[:4] in {b"II*\x00", b"MM\x00*"},
        "tiff": head[:4] in {b"II*\x00", b"MM\x00*"},
        "webp": head.startswith(b"RIFF") and head[8:12] == b"WEBP",
    }
    if not signature_matches[extension]:
        raise FileExcluded("image_signature_mismatch")
    stream.seek(0)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                image.verify()
    except (
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise FileExcluded("corrupt_or_unsafe_image") from error


def _stream_decodes(stream: BinaryIO, encoding: str) -> bool:
    stream.seek(0)
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    try:
        while chunk := stream.read(HASH_CHUNK_BYTES):
            decoder.decode(chunk, final=False)
        decoder.decode(b"", final=True)
    except UnicodeDecodeError:
        return False
    return True


def _validate_text(stream: BinaryIO, head: bytes) -> None:
    if b"\x00" in head[:4096]:
        raise FileExcluded("binary_content_disguised_as_text")
    if not any(_stream_decodes(stream, encoding) for encoding in ("utf-8-sig", "cp949")):
        raise FileExcluded("unsupported_text_encoding")


def _validate_html(stream: BinaryIO) -> None:
    try:
        result = extract_html_stream(
            document_id="readonly-html-inspection",
            stream=stream,
            max_chars=HTML_INSPECTION_MAX_CHARS,
        )
    except HtmlExtractionError as error:
        raise FileExcluded("invalid_or_unsupported_html") from error
    if result.extracted_chars < 128:
        if result.truncation_reason == "time_limit":
            raise FileExcluded("html_parse_limit_exceeded")
        raise FileExcluded("html_visible_text_below_minimum")


def _validate_candidate_content(stream: BinaryIO, candidate: Candidate) -> None:
    stream.seek(0)
    head = stream.read(8192)
    extension = candidate.extension
    if extension in OPENXML_MARKERS:
        if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            _validate_ole(stream, extension, openxml_extension=True)
        if not head.startswith(b"PK\x03\x04"):
            raise FileExcluded("office_signature_mismatch")
        _validate_openxml(stream, extension)
        return
    if extension in OLE_REQUIRED_STREAMS:
        if not head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise FileExcluded("office_signature_mismatch")
        _validate_ole(stream, extension)
        return
    if extension == "pdf":
        if not head.startswith(b"%PDF-"):
            raise FileExcluded("pdf_signature_mismatch")
        _validate_pdf(stream)
        return
    if extension in IMAGE_EXTENSIONS:
        _validate_image(stream, extension, head)
        return
    if extension in TEXT_EXTENSIONS:
        _validate_text(stream, head)
        return
    if extension in HTML_EXTENSIONS:
        _validate_html(stream)
        return
    raise FileExcluded("unsupported_extension")


def _hash_stream(stream: BinaryIO) -> str:
    stream.seek(0)
    digest = hashlib.sha256()
    while chunk := stream.read(HASH_CHUNK_BYTES):
        digest.update(chunk)
    return digest.hexdigest()


def _inspect_candidate(candidate: Candidate) -> Inspection:
    try:
        with _open_candidate(candidate) as stream:
            _validate_candidate_content(stream, candidate)
            content_sha256 = _hash_stream(stream)
            final_stat = os.fstat(stream.fileno())
            identity = (
                final_stat.st_dev,
                final_stat.st_ino,
                final_stat.st_size,
                final_stat.st_mtime_ns,
            )
            expected = (
                candidate.device,
                candidate.inode,
                candidate.size_bytes,
                candidate.modified_ns,
            )
            if identity != expected:
                raise FileExcluded("source_changed_during_scan")
        return Inspection(candidate=candidate, content_sha256=content_sha256)
    except FileExcluded as error:
        return Inspection(candidate=candidate, exclusion_reason=error.reason)
    except Exception:  # noqa: BLE001 - source-specific details must never escape.
        return Inspection(candidate=candidate, exclusion_reason="inspection_error")


def inspect_source_tree(source: Path, *, workers: int = 4) -> SourceTreeInspection:
    """Inspect a source tree with the same fail-closed eligibility contract as the manifest."""

    if not 1 <= workers <= 32:
        raise HarnessContractError("invalid_harness_limits")
    try:
        source_root = source.resolve(strict=True)
    except OSError as error:
        raise HarnessContractError("invalid_source") from error
    if not source_root.is_dir():
        raise HarnessContractError("invalid_source")
    (
        candidates,
        reason_counts,
        reason_bytes,
        extension_totals,
        regular_file_count,
        regular_file_bytes,
    ) = _scan_source(source_root)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="files-rag-inventory") as pool:
        inspections = list(pool.map(_inspect_candidate, candidates))

    eligible: list[Inspection] = []
    for inspection in inspections:
        candidate = inspection.candidate
        if inspection.exclusion_reason is not None:
            _record_exclusion(
                reason_counts,
                reason_bytes,
                inspection.exclusion_reason,
                candidate.size_bytes,
            )
            continue
        eligible.append(inspection)
        extension_totals[candidate.extension]["eligible_file_count"] += 1
        extension_totals[candidate.extension]["eligible_bytes"] += candidate.size_bytes
    return SourceTreeInspection(
        source_root=source_root,
        eligible=tuple(eligible),
        reason_counts=reason_counts,
        reason_bytes=reason_bytes,
        extension_totals=extension_totals,
        regular_file_count=regular_file_count,
        regular_file_bytes=regular_file_bytes,
    )


def _validate_sha256(value: object) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise HarnessContractError("invalid_evaluation_input")
    return value


def _query_id(query: str) -> str:
    normalized = " ".join(query.split()).casefold()
    if not normalized:
        raise HarnessContractError("invalid_evaluation_input")
    return _sha256_bytes(b"open-work-hub-retrieval-eval-query-v1\0" + normalized.encode("utf-8"))


def _load_json(path: Path, error_code: str) -> object:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HarnessContractError(error_code) from error


def _ranking_metrics(returned: list[str], relevant: set[str], k: int) -> dict[str, float]:
    ranked = returned[:k]
    relevant_positions = [index for index, item in enumerate(ranked, start=1) if item in relevant]
    recall = len(set(ranked) & relevant) / len(relevant) if relevant else 0.0
    reciprocal_rank = 1.0 / relevant_positions[0] if relevant_positions else 0.0
    dcg = sum(1.0 / math.log2(position + 1) for position in relevant_positions)
    ideal_hits = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_hits + 1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0
    return {
        "mrr": round(reciprocal_rank, 6),
        "ndcg_at_k": round(ndcg, 6),
        "recall_at_k": round(recall, 6),
    }


def _build_evaluation(
    evaluation_input: Path | None,
    evaluation_results: Path | None,
) -> dict[str, object] | None:
    if evaluation_input is None:
        if evaluation_results is not None:
            raise HarnessContractError("evaluation_input_required")
        return None
    raw_input = _load_json(evaluation_input, "invalid_evaluation_input")
    if not isinstance(raw_input, dict) or not isinstance(raw_input.get("queries"), list):
        raise HarnessContractError("invalid_evaluation_input")
    k = raw_input.get("k", 10)
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 100:
        raise HarnessContractError("invalid_evaluation_input")

    queries: dict[str, dict[str, object]] = {}
    for item in raw_input["queries"]:
        if not isinstance(item, dict) or not isinstance(item.get("query"), str):
            raise HarnessContractError("invalid_evaluation_input")
        query_id = _query_id(item["query"])
        relevant_raw = item.get("relevant_source_ids")
        if not isinstance(relevant_raw, list):
            raise HarnessContractError("invalid_evaluation_input")
        relevant = {_validate_sha256(value) for value in relevant_raw}
        if not relevant or query_id in queries:
            raise HarnessContractError("invalid_evaluation_input")
        allowed_raw = item.get("allowed_source_ids")
        allowed: set[str] | None = None
        if allowed_raw is not None:
            if not isinstance(allowed_raw, list):
                raise HarnessContractError("invalid_evaluation_input")
            allowed = {_validate_sha256(value) for value in allowed_raw}
        queries[query_id] = {"relevant": relevant, "allowed": allowed}

    result_rows: dict[tuple[str, str], dict[str, object]] = {}
    if evaluation_results is not None:
        raw_results = _load_json(evaluation_results, "invalid_evaluation_results")
        if not isinstance(raw_results, dict) or not isinstance(raw_results.get("results"), list):
            raise HarnessContractError("invalid_evaluation_results")
        for item in raw_results["results"]:
            if not isinstance(item, dict):
                raise HarnessContractError("invalid_evaluation_results")
            query_id = item.get("query_id")
            mode = item.get("mode")
            returned_raw = item.get("returned_source_ids")
            latency_ms = item.get("latency_ms")
            if (
                not isinstance(query_id, str)
                or query_id not in queries
                or mode not in EVALUATION_MODES
                or not isinstance(returned_raw, list)
                or isinstance(latency_ms, bool)
                or not isinstance(latency_ms, (int, float))
                or not math.isfinite(latency_ms)
                or latency_ms < 0
            ):
                raise HarnessContractError("invalid_evaluation_results")
            returned = [_validate_sha256(value) for value in returned_raw]
            if len(returned) != len(set(returned)):
                raise HarnessContractError("invalid_evaluation_results")
            key = (query_id, mode)
            if key in result_rows:
                raise HarnessContractError("invalid_evaluation_results")
            result_rows[key] = {
                "returned": returned,
                "latency_ms": round(float(latency_ms), 3),
            }

    query_reports: list[dict[str, object]] = []
    aggregate_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for query_id in sorted(queries):
        relevant = queries[query_id]["relevant"]
        allowed = queries[query_id]["allowed"]
        assert isinstance(relevant, set)
        assert allowed is None or isinstance(allowed, set)
        modes: dict[str, object] = {}
        for mode in EVALUATION_MODES:
            result = result_rows.get((query_id, mode))
            if result is None:
                modes[mode] = None
                continue
            returned = result["returned"]
            assert isinstance(returned, list)
            metrics: dict[str, object] = {
                **_ranking_metrics(returned, relevant, k),
                "returned_count": len(returned[:k]),
                "latency_ms": result["latency_ms"],
                "acl_violation_count": (
                    None if allowed is None else sum(item not in allowed for item in returned[:k])
                ),
            }
            modes[mode] = metrics
            aggregate_rows[mode].append(metrics)
        query_reports.append(
            {
                "query_id": query_id,
                "relevant_count": len(relevant),
                "modes": modes,
            }
        )

    aggregate: dict[str, object] = {}
    for mode in EVALUATION_MODES:
        rows = aggregate_rows[mode]
        if not rows:
            aggregate[mode] = None
            continue
        acl_values = [row["acl_violation_count"] for row in rows]
        aggregate[mode] = {
            "evaluated_query_count": len(rows),
            "mean_recall_at_k": round(
                sum(float(row["recall_at_k"]) for row in rows) / len(rows), 6
            ),
            "mean_mrr": round(sum(float(row["mrr"]) for row in rows) / len(rows), 6),
            "mean_ndcg_at_k": round(sum(float(row["ndcg_at_k"]) for row in rows) / len(rows), 6),
            "mean_latency_ms": round(sum(float(row["latency_ms"]) for row in rows) / len(rows), 3),
            "acl_violation_count": (
                None if any(value is None for value in acl_values) else sum(acl_values)
            ),
        }
    return {
        "k": k,
        "query_count": len(query_reports),
        "queries": query_reports,
        "aggregate": aggregate,
    }


def build_manifest(
    source: Path,
    *,
    canaries_per_stratum: int = 2,
    workers: int = 4,
    evaluation_input: Path | None = None,
    evaluation_results: Path | None = None,
) -> dict[str, object]:
    if not 1 <= canaries_per_stratum <= 20 or not 1 <= workers <= 32:
        raise HarnessContractError("invalid_harness_limits")
    source_inspection = inspect_source_tree(source, workers=workers)
    source_root = source_inspection.source_root
    eligible = list(source_inspection.eligible)
    reason_counts = source_inspection.reason_counts
    reason_bytes = source_inspection.reason_bytes
    extension_totals = source_inspection.extension_totals
    regular_file_count = source_inspection.regular_file_count
    regular_file_bytes = source_inspection.regular_file_bytes

    strata: dict[tuple[str, str], list[Inspection]] = defaultdict(list)
    for inspection in eligible:
        candidate = inspection.candidate
        strata[(candidate.extension, _size_bucket(candidate.size_bytes))].append(inspection)

    stratum_reports: list[dict[str, object]] = []
    for (extension, size_bucket), items in sorted(strata.items()):
        ranked = sorted(
            items,
            key=lambda item: _sha256_bytes(
                b"open-work-hub-files-canary-v1\0"
                + item.candidate.source_id.encode("ascii")
                + (item.content_sha256 or "").encode("ascii")
            ),
        )
        canaries = [
            {
                "source_id": item.candidate.source_id,
                "content_sha256": item.content_sha256,
                "size_bytes": item.candidate.size_bytes,
            }
            for item in ranked[:canaries_per_stratum]
        ]
        stratum_reports.append(
            {
                "extension": extension,
                "size_bucket": size_bucket,
                "eligible_file_count": len(items),
                "eligible_bytes": sum(item.candidate.size_bytes for item in items),
                "canaries": canaries,
            }
        )

    eligible_rows = sorted(
        (
            item.candidate.source_id,
            item.content_sha256,
            item.candidate.size_bytes,
        )
        for item in eligible
    )
    eligible_set_sha256 = _sha256_bytes(_canonical_json(eligible_rows).encode("ascii"))
    extension_reports = [
        {
            "extension": extension,
            "file_count": totals["file_count"],
            "bytes": totals["bytes"],
            "eligible_file_count": totals["eligible_file_count"],
            "eligible_bytes": totals["eligible_bytes"],
        }
        for extension, totals in sorted(extension_totals.items())
    ]
    exclusion_reports = [
        {
            "reason": reason,
            "file_count": reason_counts[reason],
            "bytes": reason_bytes[reason],
        }
        for reason in sorted(reason_counts)
    ]
    evaluation = _build_evaluation(evaluation_input, evaluation_results)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "mode": "dry_run",
        "source_root_id": _source_root_id(source_root),
        "inventory": {
            "regular_file_count": regular_file_count,
            "regular_file_bytes": regular_file_bytes,
            "eligible_file_count": len(eligible),
            "eligible_bytes": sum(item.candidate.size_bytes for item in eligible),
            "excluded_entry_count": sum(reason_counts.values()),
            "excluded_bytes": sum(reason_bytes.values()),
            "eligible_content_set_sha256": eligible_set_sha256,
            "extensions": extension_reports,
            "exclusions": exclusion_reports,
        },
        "strata": stratum_reports,
        "evaluation": evaluation,
    }
    manifest["manifest_sha256"] = _sha256_bytes(_canonical_json(manifest).encode("ascii"))
    return manifest


def _assert_output_outside_source(source: Path, output: Path) -> Path:
    try:
        source_root = source.resolve(strict=True)
        resolved_output = output.resolve(strict=False)
    except OSError as error:
        raise HarnessContractError("invalid_manifest_output") from error
    if resolved_output == source_root or source_root in resolved_output.parents:
        raise HarnessContractError("manifest_output_inside_source")
    if not resolved_output.parent.is_dir():
        raise HarnessContractError("invalid_manifest_output")
    return resolved_output


def _write_manifest(source: Path, output: Path, manifest: dict[str, object]) -> None:
    resolved_output = _assert_output_outside_source(source, output)
    payload = (_canonical_json(manifest) + "\n").encode("ascii")
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=resolved_output.parent,
            prefix=f".{resolved_output.name}.",
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, resolved_output)
        temporary_name = None
    except OSError as error:
        raise HarnessContractError("manifest_write_failed") from error
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--canaries-per-stratum", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--evaluation-input", type=Path)
    parser.add_argument("--evaluation-results", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="inventory only (the default; accepted for explicit runbooks)",
    )
    mode.add_argument("--execute-ingest", action="store_true")
    parser.add_argument("--corpus-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.execute_ingest:
            if not args.corpus_id:
                raise HarnessContractError("ingest_scope_required")
            raise HarnessContractError("ingest_adapter_not_connected")
        if args.corpus_id:
            raise HarnessContractError("ingest_flag_required")
        if args.manifest_out is not None:
            _assert_output_outside_source(args.source, args.manifest_out)
        manifest = build_manifest(
            args.source,
            canaries_per_stratum=args.canaries_per_stratum,
            workers=args.workers,
            evaluation_input=args.evaluation_input,
            evaluation_results=args.evaluation_results,
        )
        if args.manifest_out is not None:
            _write_manifest(args.source, args.manifest_out, manifest)
        print(_canonical_json(manifest))
        return 0
    except HarnessContractError as error:
        print(_canonical_json({"status": "error", "code": error.code}))
        return 2
    except Exception:  # noqa: BLE001 - never leak source names/content through tracebacks.
        print(_canonical_json({"status": "error", "code": "unexpected_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
