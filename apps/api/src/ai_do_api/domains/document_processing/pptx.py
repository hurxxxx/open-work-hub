from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree
import zipfile

from .contracts import (
    DocumentExtractBundle,
    EvidenceBlock,
    UnsupportedDocumentType,
    _ExtractionBudget,
    _MAX_EXTRACT_SECONDS,
    _MAX_EXTRACTED_CHARS,
)


_DRAWING_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_TEXT_TAG = f"{_DRAWING_NS}t"
_PARA_TAG = f"{_DRAWING_NS}p"
_TABLE_TAG = f"{_DRAWING_NS}tbl"
_ROW_TAG = f"{_DRAWING_NS}tr"
_CELL_TAG = f"{_DRAWING_NS}tc"
_SLIDE_RE = re.compile(r"ppt/slides/slide(\d+)\.xml$")
_NOTES_RE = re.compile(r"ppt/notesSlides/notesSlide(\d+)\.xml$")
_MAX_ARCHIVE_ENTRIES = 1_000
_MAX_ARCHIVE_COMPRESSED_BYTES = 120 * 1024 * 1024
_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 240 * 1024 * 1024
_MAX_ARCHIVE_MEMBER_BYTES = 120 * 1024 * 1024
_MAX_ARCHIVE_EXPANSION_RATIO = 100


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _paragraph_text(paragraph: ElementTree.Element) -> str:
    return _clean_text(" ".join(node.text or "" for node in paragraph.iter(_TEXT_TAG)))


def _element_text(element: ElementTree.Element) -> str:
    return _clean_text(" ".join(node.text or "" for node in element.iter(_TEXT_TAG)))


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _natural_office_xml_paths(names: Iterable[str], pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    matches: list[tuple[int, str]] = []
    for name in names:
        match = pattern.match(name)
        if match:
            matches.append((int(match.group(1)), name))
    return sorted(matches)


def archive_exceeds_limits(infos: Iterable[zipfile.ZipInfo]) -> bool:
    """Return true when a PPTX zip directory exceeds conservative safety caps."""

    count = 0
    compressed = 0
    uncompressed = 0
    for info in infos:
        if info.is_dir():
            continue
        count += 1
        compressed += max(0, info.compress_size)
        uncompressed += max(0, info.file_size)
        if (
            count > _MAX_ARCHIVE_ENTRIES
            or info.file_size > _MAX_ARCHIVE_MEMBER_BYTES
            or compressed > _MAX_ARCHIVE_COMPRESSED_BYTES
            or uncompressed > _MAX_ARCHIVE_UNCOMPRESSED_BYTES
        ):
            return True
    if compressed and uncompressed / compressed > _MAX_ARCHIVE_EXPANSION_RATIO:
        return True
    return False


def _drain(
    budget: _ExtractionBudget,
    blocks: list[EvidenceBlock],
    candidates: list[EvidenceBlock],
) -> bool:
    """Append candidates under the budget; return False once it is exhausted."""

    for block in candidates:
        if not budget.append(blocks, block):
            return False
    return True


class PptxOpenXmlExtractor:
    _CONTENT_TYPES = {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/powerpoint",
        "application/vnd.ms-powerpoint",
    }

    def supports(self, *, mime_type: str, filename: str) -> bool:
        suffix = Path(filename).suffix.lower()
        return suffix == ".pptx" or mime_type.lower() in self._CONTENT_TYPES

    def extract(
        self,
        *,
        document_id: str,
        filename: str,
        mime_type: str,
        content: bytes,
    ) -> DocumentExtractBundle:
        blocks: list[EvidenceBlock] = []
        budget = _ExtractionBudget(
            max_chars=_MAX_EXTRACTED_CHARS,
            max_seconds=_MAX_EXTRACT_SECONDS,
        )
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                if archive_exceeds_limits(archive.infolist()):
                    raise UnsupportedDocumentType("PPTX archive exceeds safety limits")
                names = archive.namelist()
                slide_paths = _natural_office_xml_paths(names, _SLIDE_RE)
                if not slide_paths:
                    raise UnsupportedDocumentType("PPTX contains no slides")
                exhausted = False
                for slide_number, path in slide_paths:
                    if not budget.should_continue():
                        exhausted = True
                        break
                    if not _drain(
                        budget,
                        blocks,
                        self._extract_slide(
                            document_id=document_id,
                            slide_number=slide_number,
                            xml=archive.read(path),
                            start_index=len(blocks) + 1,
                        ),
                    ):
                        exhausted = True
                        break
                if not exhausted:
                    for notes_number, path in _natural_office_xml_paths(names, _NOTES_RE):
                        if not budget.should_continue():
                            break
                        if not _drain(
                            budget,
                            blocks,
                            self._extract_notes(
                                document_id=document_id,
                                notes_number=notes_number,
                                xml=archive.read(path),
                                start_index=len(blocks) + 1,
                            ),
                        ):
                            break
        except zipfile.BadZipFile as exc:
            raise UnsupportedDocumentType("PPTX file is not a valid zip package") from exc
        except ElementTree.ParseError as exc:
            raise UnsupportedDocumentType("PPTX XML could not be parsed") from exc

        return DocumentExtractBundle(
            document_id=document_id,
            filename=filename,
            mime_type=mime_type,
            evidence_blocks=blocks,
        )

    def _extract_slide(
        self,
        *,
        document_id: str,
        slide_number: int,
        xml: bytes,
        start_index: int,
    ) -> list[EvidenceBlock]:
        root = ElementTree.fromstring(xml)
        heading = self._slide_heading(root, fallback=f"Slide {slide_number}")
        blocks: list[EvidenceBlock] = []

        table_paragraph_ids = {
            id(paragraph)
            for table in root.iter(_TABLE_TAG)
            for paragraph in table.iter(_PARA_TAG)
        }
        for paragraph in root.iter(_PARA_TAG):
            if id(paragraph) in table_paragraph_ids:
                continue
            text = _paragraph_text(paragraph)
            if not text:
                continue
            blocks.append(
                EvidenceBlock(
                    document_id=document_id,
                    block_id=f"{document_id}:s{slide_number}:b{start_index + len(blocks)}",
                    locator_kind="slide",
                    locator_label=f"Slide {slide_number}",
                    section_path=heading,
                    block_kind="text",
                    text=text,
                )
            )

        for table_index, table in enumerate(root.iter(_TABLE_TAG), start=1):
            rows: list[list[str]] = []
            for row in table.iter(_ROW_TAG):
                cells = [_element_text(cell) for cell in row.iter(_CELL_TAG)]
                cleaned = [cell for cell in cells if cell]
                if cleaned:
                    rows.append(cleaned)
            if not rows:
                continue
            table_text = "\n".join(" | ".join(row) for row in rows)
            blocks.append(
                EvidenceBlock(
                    document_id=document_id,
                    block_id=f"{document_id}:s{slide_number}:t{table_index}",
                    locator_kind="slide",
                    locator_label=f"Slide {slide_number}",
                    section_path=heading,
                    block_kind="table",
                    text=table_text,
                    rows=rows,
                )
            )
        return blocks

    def _extract_notes(
        self,
        *,
        document_id: str,
        notes_number: int,
        xml: bytes,
        start_index: int,
    ) -> list[EvidenceBlock]:
        root = ElementTree.fromstring(xml)
        texts = _dedupe_keep_order(_paragraph_text(paragraph) for paragraph in root.iter(_PARA_TAG))
        blocks: list[EvidenceBlock] = []
        for text in texts:
            blocks.append(
                EvidenceBlock(
                    document_id=document_id,
                    block_id=f"{document_id}:n{notes_number}:b{start_index + len(blocks)}",
                    locator_kind="slide_notes",
                    locator_label=f"Slide {notes_number} notes",
                    section_path=f"Slide {notes_number} notes",
                    block_kind="text",
                    text=text,
                )
            )
        return blocks

    def _slide_heading(self, root: ElementTree.Element, *, fallback: str) -> str:
        for paragraph in root.iter(_PARA_TAG):
            text = _paragraph_text(paragraph)
            if text:
                return text[:120]
        return fallback
