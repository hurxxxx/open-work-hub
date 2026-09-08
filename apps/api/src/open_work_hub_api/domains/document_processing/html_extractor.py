from __future__ import annotations

import codecs
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import BytesIO
from typing import BinaryIO

from .contracts import (
    _MAX_EXTRACT_SECONDS,
    _MAX_EXTRACTED_CHARS,
    DocumentExtractBundle,
    EvidenceBlock,
    UnsupportedDocumentType,
)

_HTML_READ_CHUNK_BYTES = 64 * 1024
_HTML_SIGNATURE_BYTES = 8192
_MAX_HTML_BLOCKS = 20_000
_MAX_HTML_NESTING = 256
_MAX_HTML_TABLE_CELLS = 100_000
_HTML_SIGNATURE_RE = re.compile(
    rb"<(?:!doctype\s+html\b|html\b|head\b|body\b|title\b|meta\b|h[1-6]\b|"
    rb"table\b|article\b|section\b|main\b|div\b|p\b)",
    re.IGNORECASE,
)
_HTML_META_CHARSET_RE = re.compile(
    rb"<meta\b[^>]{0,2048}?\bcharset\s*=\s*[\"']?\s*([a-zA-Z0-9._:+-]+)",
    re.IGNORECASE,
)
_HTML_META_CONTENT_RE = re.compile(
    rb"<meta\b[^>]{0,2048}?\bcontent\s*=\s*[\"'][^\"']{0,2048}?"
    rb"charset\s*=\s*([a-zA-Z0-9._:+-]+)",
    re.IGNORECASE,
)
_ACTIVE_OR_NONVISIBLE_TAGS = frozenset(
    {
        "applet",
        "audio",
        "canvas",
        "embed",
        "iframe",
        "noscript",
        "object",
        "script",
        "style",
        "svg",
        "template",
        "video",
    }
)
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
_LOOSE_TEXT_BOUNDARIES = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "dd",
        "div",
        "dl",
        "dt",
        "footer",
        "header",
        "hr",
        "main",
        "nav",
        "pre",
        "section",
    }
)
_HEADING_TAGS = frozenset({f"h{level}" for level in range(1, 7)})
_SAFE_DECLARED_ENCODINGS = frozenset(
    {
        "ascii",
        "cp1252",
        "cp949",
        "euc_kr",
        "iso8859-1",
        "shift_jis",
        "utf-8",
        "utf-8-sig",
    }
)


class HtmlExtractionError(UnsupportedDocumentType):
    """A safe HTML parsing failure suitable for source-level classification."""


@dataclass(frozen=True)
class HtmlExtractionResult:
    evidence_blocks: list[EvidenceBlock]
    charset: str
    input_bytes: int
    extracted_chars: int
    peak_pending_chars: int
    table_row_count: int
    truncated: bool
    truncation_reason: str | None
    elapsed_ms: int

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "format": "html",
            "charset": self.charset,
            "input_bytes": self.input_bytes,
            "extracted_chars": self.extracted_chars,
            "peak_pending_chars": self.peak_pending_chars,
            "block_count": len(self.evidence_blocks),
            "table_row_count": self.table_row_count,
            "truncated": self.truncated,
            "truncation_reason": self.truncation_reason,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass
class _Capture:
    tag: str
    kind: str
    label: str
    section_path: str
    parts: list[str] = field(default_factory=list)
    pending_chars: int = 0


@dataclass
class _Table:
    number: int
    row_number: int = 0


@dataclass
class _Row:
    table: _Table
    cells: list[str] = field(default_factory=list)
    pending_chars: int = 0


@dataclass
class _Cell:
    parts: list[str] = field(default_factory=list)
    pending_chars: int = 0


class _StopHtmlParsing(Exception):
    pass


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _canonical_declared_encoding(value: bytes) -> str | None:
    try:
        requested = value.decode("ascii").strip()
        canonical = codecs.lookup(requested).name
    except (LookupError, UnicodeDecodeError):
        return None
    aliases = {
        "euc-kr": "euc_kr",
        "iso8859-1": "iso8859-1",
        "ks-c-5601-1987": "cp949",
        "ms949": "cp949",
        "shift-jis": "shift_jis",
        "utf-8-sig": "utf-8-sig",
        "windows-1252": "cp1252",
    }
    canonical = aliases.get(canonical, canonical)
    return canonical if canonical in _SAFE_DECLARED_ENCODINGS else None


def _encoding_candidates(head: bytes) -> list[str]:
    candidates: list[str] = []
    if head.startswith(codecs.BOM_UTF8):
        candidates.append("utf-8-sig")
    for pattern in (_HTML_META_CHARSET_RE, _HTML_META_CONTENT_RE):
        match = pattern.search(head)
        if match is None:
            continue
        encoding = _canonical_declared_encoding(match.group(1))
        if encoding is not None:
            candidates.append(encoding)
    candidates.extend(("utf-8-sig", "cp949", "cp1252"))
    return list(dict.fromkeys(candidates))


def validate_html_signature(head: bytes) -> None:
    candidate = head[:_HTML_SIGNATURE_BYTES].lstrip(codecs.BOM_UTF8 + b" \t\r\n")
    if candidate.startswith(b"<?xml"):
        declaration_end = candidate.find(b"?>")
        if declaration_end >= 0:
            candidate = candidate[declaration_end + 2 :].lstrip()
    while candidate.startswith(b"<!--"):
        comment_end = candidate.find(b"-->")
        if comment_end < 0:
            break
        candidate = candidate[comment_end + 3 :].lstrip()
    if _HTML_SIGNATURE_RE.match(candidate) is None:
        raise HtmlExtractionError("HTML signature mismatch")


def _is_hidden(attributes: list[tuple[str, str | None]]) -> bool:
    normalized = {name.casefold(): (value or "").casefold() for name, value in attributes}
    if "hidden" in normalized or normalized.get("aria-hidden") == "true":
        return True
    style = re.sub(r"\s+", "", normalized.get("style", ""))
    return "display:none" in style or "visibility:hidden" in style


class _BoundedVisibleHtmlParser(HTMLParser):
    def __init__(
        self,
        *,
        document_id: str,
        max_chars: int,
        deadline: float,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.document_id = document_id
        self.max_chars = max_chars
        self.deadline = deadline
        self.blocks: list[EvidenceBlock] = []
        self.extracted_chars = 0
        self.table_row_count = 0
        self.truncation_reason: str | None = None
        self._pending_chars = 0
        self._peak_pending_chars = 0
        self._observed_table_cells = 0
        self._suppressed_tags: list[str] = []
        self._captures: list[_Capture] = []
        self._tables: list[_Table] = []
        self._rows: list[_Row] = []
        self._cells: list[_Cell] = []
        self._headings: list[str] = []
        self._loose = _Cell()
        self._paragraph_number = 0
        self._list_item_number = 0
        self._heading_number = 0
        self._title_number = 0
        self._table_number = 0

    @property
    def section_path(self) -> str:
        return " > ".join(self._headings) or "Body"

    def _check_time(self) -> None:
        if time.monotonic() >= self.deadline:
            self.truncation_reason = "time_limit"
            raise _StopHtmlParsing

    def _append_text(
        self,
        buffer: _Capture | _Cell,
        value: str,
    ) -> None:
        normalized = _normalize_text(value)
        if not normalized:
            return
        remaining = max(self.max_chars - self.extracted_chars - self._pending_chars, 0)
        if remaining <= 0:
            self.truncation_reason = "character_limit"
            raise _StopHtmlParsing
        separator = " " if buffer.parts else ""
        candidate = f"{separator}{normalized}"
        appended = candidate[:remaining]
        buffer.parts.append(appended)
        buffer.pending_chars += len(appended)
        self._pending_chars += len(appended)
        self._peak_pending_chars = max(self._peak_pending_chars, self._pending_chars)
        if len(candidate) > remaining:
            self.truncation_reason = "character_limit"

    def _release_pending(self, count: int) -> None:
        self._pending_chars = max(0, self._pending_chars - count)

    def _emit(
        self,
        *,
        locator_kind: str,
        locator_label: str,
        section_path: str,
        block_kind: str,
        text: str,
        rows: list[list[str]] | None = None,
    ) -> None:
        self._check_time()
        if len(self.blocks) >= _MAX_HTML_BLOCKS:
            self.truncation_reason = "structure_limit"
            raise _StopHtmlParsing
        cleaned = _normalize_text(text)
        if not cleaned:
            return
        remaining = self.max_chars - self.extracted_chars
        if remaining <= 0:
            self.truncation_reason = "character_limit"
            raise _StopHtmlParsing
        clipped = cleaned[:remaining].strip()
        if not clipped:
            return
        if len(cleaned) > remaining:
            self.truncation_reason = "character_limit"
        block_number = len(self.blocks) + 1
        self.blocks.append(
            EvidenceBlock(
                document_id=self.document_id,
                block_id=f"{self.document_id}:html:{block_number}",
                locator_kind=locator_kind,
                locator_label=locator_label,
                section_path=section_path,
                block_kind=block_kind,
                text=clipped,
                rows=rows or [],
            )
        )
        self.extracted_chars += len(clipped)
        if self.truncation_reason is not None:
            raise _StopHtmlParsing

    def _flush_loose_text(self) -> None:
        if not self._loose.parts:
            return
        loose, self._loose = self._loose, _Cell()
        self._release_pending(loose.pending_chars)
        self._paragraph_number += 1
        self._emit(
            locator_kind="paragraph",
            locator_label=f"Paragraph {self._paragraph_number}",
            section_path=self.section_path,
            block_kind="text",
            text="".join(loose.parts),
        )

    def _start_capture(self, tag: str, kind: str, label: str) -> None:
        self._flush_loose_text()
        if len(self._captures) >= _MAX_HTML_NESTING:
            self.truncation_reason = "structure_limit"
            raise _StopHtmlParsing
        self._captures.append(
            _Capture(
                tag=tag,
                kind=kind,
                label=label,
                section_path=self.section_path,
            )
        )

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._check_time()
        tag = tag.casefold()
        if self._suppressed_tags:
            if tag not in _VOID_TAGS:
                if len(self._suppressed_tags) >= _MAX_HTML_NESTING:
                    self.truncation_reason = "structure_limit"
                    raise _StopHtmlParsing
                self._suppressed_tags.append(tag)
            return
        if tag in _ACTIVE_OR_NONVISIBLE_TAGS or _is_hidden(attrs):
            if tag not in _VOID_TAGS:
                self._suppressed_tags.append(tag)
            return
        if tag in _LOOSE_TEXT_BOUNDARIES or tag == "br":
            self._flush_loose_text()
        if tag == "table":
            if len(self._tables) >= _MAX_HTML_NESTING:
                self.truncation_reason = "structure_limit"
                raise _StopHtmlParsing
            self._flush_loose_text()
            self._table_number += 1
            self._tables.append(_Table(number=self._table_number))
        elif tag == "tr" and self._tables:
            if len(self._rows) >= _MAX_HTML_NESTING:
                self.truncation_reason = "structure_limit"
                raise _StopHtmlParsing
            self._rows.append(_Row(table=self._tables[-1]))
        elif tag in {"td", "th"} and self._rows:
            self._observed_table_cells += 1
            if (
                self._observed_table_cells > _MAX_HTML_TABLE_CELLS
                or len(self._cells) >= _MAX_HTML_NESTING
            ):
                self.truncation_reason = "structure_limit"
                raise _StopHtmlParsing
            self._cells.append(_Cell())
        elif tag == "title":
            self._title_number += 1
            self._start_capture(tag, "title", "Title")
        elif tag in _HEADING_TAGS and not self._cells:
            self._heading_number += 1
            self._start_capture(tag, "heading", f"Heading {self._heading_number}")
        elif (
            tag == "p"
            and not self._cells
            and not any(capture.kind == "list_item" for capture in self._captures)
        ):
            self._paragraph_number += 1
            self._start_capture(tag, "paragraph", f"Paragraph {self._paragraph_number}")
        elif tag == "li" and not self._cells:
            self._list_item_number += 1
            self._start_capture(tag, "list_item", f"List item {self._list_item_number}")

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in _VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        self._check_time()
        tag = tag.casefold()
        if self._suppressed_tags:
            if tag in self._suppressed_tags:
                while self._suppressed_tags:
                    suppressed = self._suppressed_tags.pop()
                    if suppressed == tag:
                        break
            return
        if tag in {"td", "th"} and self._cells and self._rows:
            cell = self._cells.pop()
            text = _normalize_text("".join(cell.parts))
            self._rows[-1].cells.append(text)
            self._rows[-1].pending_chars += cell.pending_chars
            return
        if tag == "tr" and self._rows:
            row = self._rows.pop()
            cells = [cell for cell in row.cells if cell]
            if cells:
                self._release_pending(row.pending_chars)
                row.table.row_number += 1
                self.table_row_count += 1
                self._emit(
                    locator_kind="table_row",
                    locator_label=f"Table {row.table.number}, row {row.table.row_number}",
                    section_path=self.section_path,
                    block_kind="table_row",
                    text="\t".join(cells),
                    rows=[cells],
                )
            return
        if tag == "table" and self._tables:
            self._tables.pop()
            return
        if self._captures and any(capture.tag == tag for capture in self._captures):
            while self._captures:
                capture = self._captures.pop()
                if capture.tag != tag:
                    continue
                text = _normalize_text("".join(capture.parts))
                section_path = capture.section_path
                if capture.kind == "heading" and text:
                    level = int(tag[1])
                    self._headings = self._headings[: level - 1]
                    self._headings.append(text)
                    section_path = self.section_path
                self._release_pending(capture.pending_chars)
                self._emit(
                    locator_kind=capture.kind,
                    locator_label=capture.label,
                    section_path=section_path,
                    block_kind="text",
                    text=text,
                )
                break
        if tag in _LOOSE_TEXT_BOUNDARIES:
            self._flush_loose_text()

    def handle_data(self, data: str) -> None:
        self._check_time()
        if self._suppressed_tags or not data.strip():
            return
        if self._cells:
            self._append_text(self._cells[-1], data)
        elif self._captures:
            self._append_text(self._captures[-1], data)
        else:
            self._append_text(self._loose, data)
        if self.truncation_reason is not None:
            raise _StopHtmlParsing

    def finish(self) -> None:
        if self._cells and self._rows:
            cell = self._cells[-1]
            text = _normalize_text("".join(cell.parts))
            if text:
                self._rows[-1].cells.append(text)
                self._rows[-1].pending_chars += cell.pending_chars
        if self._rows:
            row = self._rows[-1]
            cells = [cell for cell in row.cells if cell]
            if cells:
                self._release_pending(row.pending_chars)
                row.table.row_number += 1
                self.table_row_count += 1
                self._emit(
                    locator_kind="table_row",
                    locator_label=f"Table {row.table.number}, row {row.table.row_number}",
                    section_path=self.section_path,
                    block_kind="table_row",
                    text="\t".join(cells),
                    rows=[cells],
                )
        if self._captures:
            capture = self._captures[-1]
            self._release_pending(capture.pending_chars)
            self._emit(
                locator_kind=capture.kind,
                locator_label=capture.label,
                section_path=capture.section_path,
                block_kind="text",
                text="".join(capture.parts),
            )
        self._flush_loose_text()


def extract_html_stream(
    *,
    document_id: str,
    stream: BinaryIO,
    max_chars: int = _MAX_EXTRACTED_CHARS,
    max_seconds: float = _MAX_EXTRACT_SECONDS,
) -> HtmlExtractionResult:
    started_at = time.monotonic()
    deadline = started_at + max_seconds
    stream.seek(0, 2)
    input_bytes = stream.tell()
    stream.seek(0)
    head = stream.read(_HTML_SIGNATURE_BYTES)
    validate_html_signature(head)
    decoding_failed = False
    for encoding in _encoding_candidates(head):
        stream.seek(0)
        parser = _BoundedVisibleHtmlParser(
            document_id=document_id,
            max_chars=max_chars,
            deadline=deadline,
        )
        decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
        stopped = False
        try:
            while chunk := stream.read(_HTML_READ_CHUNK_BYTES):
                parser.feed(decoder.decode(chunk, final=False))
            parser.feed(decoder.decode(b"", final=True))
            parser.close()
        except UnicodeDecodeError:
            decoding_failed = True
            if time.monotonic() >= deadline:
                raise HtmlExtractionError("HTML parse time limit exceeded") from None
            continue
        except _StopHtmlParsing:
            stopped = True
        except Exception as error:
            raise HtmlExtractionError("HTML could not be parsed") from error
        try:
            parser.finish()
        except _StopHtmlParsing:
            stopped = True
        if stopped and parser.truncation_reason is None:
            parser.truncation_reason = "parser_limit"
        elapsed_ms = max(0, round((time.monotonic() - started_at) * 1000))
        return HtmlExtractionResult(
            evidence_blocks=parser.blocks,
            charset=encoding,
            input_bytes=input_bytes,
            extracted_chars=parser.extracted_chars,
            peak_pending_chars=parser._peak_pending_chars,
            table_row_count=parser.table_row_count,
            truncated=parser.truncation_reason is not None,
            truncation_reason=parser.truncation_reason,
            elapsed_ms=elapsed_ms,
        )
    if decoding_failed:
        raise HtmlExtractionError("Unsupported HTML encoding")
    raise HtmlExtractionError("HTML could not be decoded")


class HtmlExtractor:
    _CONTENT_TYPES = {"application/xhtml+xml", "text/html"}

    def supports(self, *, mime_type: str, filename: str) -> bool:
        normalized_mime = mime_type.split(";", 1)[0].strip().casefold()
        return filename.casefold().endswith((".htm", ".html")) or (
            normalized_mime in self._CONTENT_TYPES
        )

    def extract(
        self,
        *,
        document_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> DocumentExtractBundle:
        result = extract_html_stream(
            document_id=document_id,
            stream=BytesIO(content),
        )
        return DocumentExtractBundle(
            document_id=document_id,
            filename=filename,
            mime_type=mime_type,
            evidence_blocks=result.evidence_blocks,
            metadata=result.metadata,
        )


__all__ = [
    "HtmlExtractionError",
    "HtmlExtractionResult",
    "HtmlExtractor",
    "extract_html_stream",
    "validate_html_signature",
]
