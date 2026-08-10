"""Attachment text extraction for the Q&A corpus, with table-aware OCR.

Order of operations for a file's bytes:

1. Office/PDF → fast text extraction via ``document_processing`` extractors.
   docx/xlsx/pptx tables are preserved as rows by that path, so office formats
   trust it whenever it produced text.
2. PDFs need a closer look. The fast PDF path (pdfplumber ``extract_text``) only
   returns the embedded text layer: it yields *nothing* for scanned/image-only
   pages and *flattens* tables into run-together text. So for PDFs we escalate to
   the configured RAG OCR client (Docling / inference gateway → markdown, with
   structured tables) when the document looks scanned, is sparse per page (image
   pages mixed into a mostly-text file), or contains tables. Image files always
   use OCR.
3. Choose the richer result — OCR markdown wins when it recovers more text, or
   when it captured a table the fast path lost.

OCR degrades gracefully: if no OCR provider is configured or the backend is
unreachable, extraction returns whatever fast-path text was found (possibly "").
"""
from __future__ import annotations

import logging
import mimetypes
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO

from ai_do_api.core.settings import get_settings
from ai_do_api.domains.document_processing.extractors import extract_document
from ai_do_api.domains.rag.providers.base import OcrClient

logger = logging.getLogger(__name__)

# Files the fast (non-OCR) extractors handle directly.
TEXT_EXTRACTABLE_EXTS = (".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".ppt")
# Image files that require OCR.
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")
# Anything we will attempt to read text from.
SUPPORTED_ATTACHMENT_EXTS = TEXT_EXTRACTABLE_EXTS + IMAGE_EXTS

# Below this many chars from the fast path, treat any document as empty/scanned
# and OCR it.
_OCR_FALLBACK_MIN_CHARS = 24
# A PDF whose fast-path text falls below this many chars *per page* is treated as
# scanned or image-heavy (e.g. a mostly-image notice with only a short header),
# so we escalate to OCR to recover the visual content.
_MIN_CHARS_PER_PAGE = 120
# Cap how many pages we inspect for the table signal, to bound cost on large PDFs.
_TABLE_SIGNAL_MAX_PAGES = 10
# Resource ceilings for the OCR escalation. OCR reuses the shared RAG OCR gateway
# (Docling concurrency 1) and the Q&A crawl runs on the shared default worker, so an
# unbounded escalation could occupy shared infrastructure far longer than the native
# extractor's own page/time budget. Past these limits we skip OCR and keep the
# (budget-bounded) native text instead of sending the whole file to the gateway.
_OCR_MAX_PAGES = 40
_OCR_MAX_BYTES = 16 * 1024 * 1024  # 16 MiB


@lru_cache(maxsize=1)
def _ocr_client() -> OcrClient | None:
    """Build (and cache) the configured RAG OCR client, or None if unavailable."""
    settings = get_settings()
    if not getattr(settings, "rag_ocr_provider", ""):
        return None
    try:
        from ai_do_api.domains.rag.runtime import build_provider_bundle

        return build_provider_bundle(settings).ocr
    except Exception as error:  # noqa: BLE001 - OCR is best-effort
        logger.warning("qna: OCR provider unavailable: %s", error)
        return None


def _resolve_mime(filename: str, mime_type: str | None) -> str:
    return mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _ocr_text(content: bytes, content_type: str) -> str:
    client = _ocr_client()
    if client is None:
        return ""
    try:
        return (client.extract_text(content=content, content_type=content_type) or "").strip()
    except Exception as error:  # noqa: BLE001 - OCR backend may be down
        logger.warning("qna: OCR extraction failed: %s", error)
        return ""


def _pdf_signals(content: bytes) -> tuple[int, bool]:
    """Return ``(page_count, has_tables)`` for a PDF.

    Best-effort and isolated from the fast extractor: returns ``(0, False)`` if the
    PDF cannot be inspected, so a parse failure never blocks extraction.
    """
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(content)) as pdf:
            page_count = len(pdf.pages)
            has_tables = False
            for page in pdf.pages[:_TABLE_SIGNAL_MAX_PAGES]:
                try:
                    if page.find_tables():
                        has_tables = True
                        break
                except Exception:  # noqa: BLE001 - table detection is best-effort
                    continue
            return page_count, has_tables
    except Exception as error:  # noqa: BLE001 - signal inspection is best-effort
        logger.debug("qna: pdf signal inspection failed: %s", error)
        return 0, False


def _should_run_ocr(*, ext: str, fast_text: str, content: bytes) -> bool:
    """Decide whether to escalate to OCR after the fast path.

    Images always OCR. PDFs escalate when scanned/near-empty, sparse per page, or
    table-bearing (the fast pdfplumber path flattens tables, Docling keeps their
    structure). Other office formats already preserve tables, so they only OCR
    when the fast path produced essentially nothing.

    Oversized or many-page inputs are never escalated regardless of the content
    signal: OCR runs on the shared RAG gateway consumed by the shared default
    worker, so an over-limit file would occupy shared infrastructure far beyond the
    native extractor's page/time budget. Such files keep their native text.
    """
    if len(content) > _OCR_MAX_BYTES:
        logger.warning(
            "qna: skipping OCR for oversized attachment (%d bytes > %d cap)",
            len(content),
            _OCR_MAX_BYTES,
        )
        return False
    if ext in IMAGE_EXTS:
        return True
    if ext == ".pdf":
        page_count, has_tables = _pdf_signals(content)
        warranted = (
            len(fast_text) < _OCR_FALLBACK_MIN_CHARS
            or (bool(page_count) and len(fast_text) < _MIN_CHARS_PER_PAGE * page_count)
            or has_tables
        )
        if not warranted:
            return False
        if page_count > _OCR_MAX_PAGES:
            logger.warning(
                "qna: skipping OCR for %d-page PDF (> %d-page cap)",
                page_count,
                _OCR_MAX_PAGES,
            )
            return False
        return True
    if ext in TEXT_EXTRACTABLE_EXTS:
        return len(fast_text) < _OCR_FALLBACK_MIN_CHARS
    return False


def _looks_tabular(text: str) -> bool:
    """Heuristic: markdown/pipe tables have lines with several ``|`` separators."""
    return any(line.count("|") >= 2 for line in text.splitlines())


def _prefer_ocr(*, ocr_text: str, fast_text: str) -> bool:
    """Prefer OCR output when it recovered more text or captured a lost table."""
    if len(ocr_text) > len(fast_text):
        return True
    return _looks_tabular(ocr_text) and not _looks_tabular(fast_text)


@dataclass(frozen=True)
class AttachmentExtraction:
    """One attachment's extracted text plus how it was obtained."""

    filename: str
    text: str
    method: str  # "native" | "ocr" | "none"


def extract_attachment(
    *, filename: str, content: bytes, mime_type: str | None = None
) -> AttachmentExtraction:
    """Extract an attachment's text, recording whether it came from the native
    fast path or the OCR fallback.

    The method tag lets the corpus prefer a native-format copy over an OCR copy
    of the same document (see ``combine_attachment_texts``).
    """
    ext = os.path.splitext(filename)[1].lower()
    resolved_mime = _resolve_mime(filename, mime_type)
    fast_text = ""

    if ext in TEXT_EXTRACTABLE_EXTS:
        try:
            fast_text = extract_document(
                document_id=filename,
                filename=filename,
                mime_type=resolved_mime,
                content=content,
            ).normalized_text.strip()
        except Exception as error:  # noqa: BLE001 - best effort, OCR may still recover
            logger.warning("qna: text extract failed for %s: %s", filename, error)

    if _should_run_ocr(ext=ext, fast_text=fast_text, content=content):
        ocr_text = _ocr_text(content, resolved_mime)
        if ocr_text and _prefer_ocr(ocr_text=ocr_text, fast_text=fast_text):
            return AttachmentExtraction(filename=filename, text=ocr_text, method="ocr")

    return AttachmentExtraction(
        filename=filename,
        text=fast_text,
        method="native" if fast_text else "none",
    )


def extract_attachment_text(*, filename: str, content: bytes, mime_type: str | None = None) -> str:
    """Return extracted text for an attachment/upload, using OCR when needed."""
    return extract_attachment(filename=filename, content=content, mime_type=mime_type).text


def _attachment_base_key(filename: str) -> str:
    """Normalized base filename (no extension) used to group format-variants."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return re.sub(r"\s+", " ", stem).strip().casefold()


def combine_attachment_texts(items: Sequence[AttachmentExtraction]) -> str:
    """Join attachment texts for one notice, skipping an OCR-derived artifact when
    a native-text sibling with the same base filename exists.

    Prevents a low-quality OCR copy (e.g. ``복리후생 기준.png``) from competing in
    the Q&A corpus with the clean native copy (``복리후생 기준.pptx``) of the same
    document. Attachments without a native-format sibling are always kept, so an
    image-only notice loses nothing.
    """
    native_bases = {
        _attachment_base_key(item.filename)
        for item in items
        if item.method == "native" and item.text.strip()
    }
    parts: list[str] = []
    for item in items:
        if not item.text.strip():
            continue
        if item.method == "ocr" and _attachment_base_key(item.filename) in native_bases:
            logger.info(
                "qna: skipping OCR text for %s (native-format sibling present)",
                item.filename,
            )
            continue
        parts.append(f"[첨부: {item.filename}]\n{item.text}")
    return "\n\n".join(parts)
