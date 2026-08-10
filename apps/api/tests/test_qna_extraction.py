"""Unit tests for the Q&A attachment extraction escalation logic.

These cover the decision that routes table-heavy / scanned / image-only PDFs to
the RAG OCR client (Docling / inference gateway) instead of accepting the flat
pdfplumber text layer. The OCR backend itself is stubbed, so the tests run
without Docling installed or a reachable inference gateway.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from open_alm_api.domains.qna import extraction


# --- pure helpers ---------------------------------------------------------


def test_looks_tabular_detects_pipe_tables() -> None:
    assert extraction._looks_tabular("| 항목 | 값 |\n| --- | --- |")
    assert not extraction._looks_tabular("일반 본문 텍스트, 표 아님")
    assert not extraction._looks_tabular("a | b")  # single pipe is not a table


def test_prefer_ocr_when_longer_or_recovers_table() -> None:
    # Longer OCR output wins.
    assert extraction._prefer_ocr(ocr_text="x" * 100, fast_text="x" * 10)
    # Equal-ish length but OCR captured a table the fast text lost.
    assert extraction._prefer_ocr(
        ocr_text="| a | b |\n| 1 | 2 |", fast_text="a b 1 2 padding padding"
    )
    # Neither longer nor table-recovering → keep the fast text.
    assert not extraction._prefer_ocr(ocr_text="short", fast_text="longer fast text")


# --- OCR escalation decision ---------------------------------------------


def test_should_run_ocr_image_always(monkeypatch: pytest.MonkeyPatch) -> None:
    assert extraction._should_run_ocr(ext=".png", fast_text="", content=b"")


def test_should_run_ocr_pdf_near_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (3, False))
    assert extraction._should_run_ocr(ext=".pdf", fast_text="tiny", content=b"%PDF")


def test_should_run_ocr_pdf_sparse_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    # 10 pages but only ~200 chars → well under the per-page floor → scanned/mixed.
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (10, False))
    assert extraction._should_run_ocr(ext=".pdf", fast_text="a" * 200, content=b"%PDF")


def test_should_run_ocr_pdf_with_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    # Dense enough text, but a table is present → Docling keeps table structure.
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (1, True))
    assert extraction._should_run_ocr(ext=".pdf", fast_text="a" * 5000, content=b"%PDF")


def test_should_not_run_ocr_for_dense_clean_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (2, False))
    assert not extraction._should_run_ocr(ext=".pdf", fast_text="a" * 5000, content=b"%PDF")


def test_should_not_run_ocr_for_office_with_text() -> None:
    # docx/xlsx already preserve tables in the fast path.
    assert not extraction._should_run_ocr(ext=".docx", fast_text="a" * 100, content=b"")


def test_should_run_ocr_for_empty_office() -> None:
    assert extraction._should_run_ocr(ext=".docx", fast_text="", content=b"")


# --- resource ceilings: never occupy the shared OCR gateway unboundedly ----


def test_should_not_run_ocr_for_oversized_attachment() -> None:
    # Larger than the OCR byte cap must never reach the shared OCR gateway, even an
    # image that would otherwise always OCR.
    oversized = b"\x89PNG" + b"\x00" * (extraction._OCR_MAX_BYTES + 1)
    assert not extraction._should_run_ocr(ext=".png", fast_text="", content=oversized)


def test_should_not_run_ocr_for_too_many_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    # A scanned/near-empty PDF with more pages than the cap keeps its native text
    # instead of occupying the shared OCR gateway.
    monkeypatch.setattr(
        extraction, "_pdf_signals", lambda content: (extraction._OCR_MAX_PAGES + 1, False)
    )
    assert not extraction._should_run_ocr(ext=".pdf", fast_text="", content=b"%PDF")


# --- end-to-end flow (OCR client stubbed) ---------------------------------


class _OcrSpy:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls = 0

    def __call__(self, content: bytes, content_type: str) -> str:
        self.calls += 1
        return self.text


def _stub_fast_text(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setattr(
        extraction,
        "extract_document",
        lambda **_: SimpleNamespace(normalized_text=text),
    )


def test_flow_dense_clean_pdf_skips_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_fast_text(monkeypatch, "본문 " * 400)
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (2, False))
    spy = _OcrSpy(text="ignored")
    monkeypatch.setattr(extraction, "_ocr_text", spy)

    result = extraction.extract_attachment_text(filename="clean.pdf", content=b"%PDF")

    assert spy.calls == 0
    assert result.startswith("본문")


def test_flow_table_pdf_prefers_ocr_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_fast_text(monkeypatch, "제목 표1 항목 값 " * 20)  # flattened, no pipes
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (1, True))
    spy = _OcrSpy(text="| 항목 | 값 |\n| 불량 | 3 |")
    monkeypatch.setattr(extraction, "_ocr_text", spy)

    result = extraction.extract_attachment_text(filename="table.pdf", content=b"%PDF")

    assert spy.calls == 1
    assert "| 항목 | 값 |" in result


def test_flow_image_uses_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _OcrSpy(text="스캔한 공지 내용")
    monkeypatch.setattr(extraction, "_ocr_text", spy)

    result = extraction.extract_attachment_text(filename="notice.png", content=b"\x89PNG")

    assert spy.calls == 1
    assert result == "스캔한 공지 내용"


def test_flow_degrades_when_ocr_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    # A table PDF escalates, but OCR returns nothing (no provider / backend down):
    # we keep the fast-path text rather than losing everything.
    _stub_fast_text(monkeypatch, "본문 텍스트만 있는 경우 " * 10)
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (1, True))
    spy = _OcrSpy(text="")
    monkeypatch.setattr(extraction, "_ocr_text", spy)

    result = extraction.extract_attachment_text(filename="table.pdf", content=b"%PDF")

    assert spy.calls == 1
    assert result.startswith("본문 텍스트만")


def test_flow_oversized_pdf_never_calls_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    # End-to-end: an over-page-cap PDF that would normally escalate must not trigger
    # any OCR provider I/O; the native text is kept.
    _stub_fast_text(monkeypatch, "짧은 표지")  # sparse → would normally escalate
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (200, True))
    spy = _OcrSpy(text="이 OCR은 실행되면 안 됨")
    monkeypatch.setattr(extraction, "_ocr_text", spy)

    result = extraction.extract_attachment_text(filename="huge.pdf", content=b"%PDF")

    assert spy.calls == 0
    assert result == "짧은 표지"


# --- extraction method tag + native-vs-OCR sibling dedup -------------------


def test_extract_attachment_tags_native(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_fast_text(monkeypatch, "본문 " * 100)  # dense → no OCR escalation
    monkeypatch.setattr(extraction, "_pdf_signals", lambda content: (1, False))
    monkeypatch.setattr(extraction, "_ocr_text", _OcrSpy(text="ignored"))
    r = extraction.extract_attachment(filename="doc.pdf", content=b"%PDF")
    assert r.method == "native"
    assert r.text.startswith("본문")


def test_extract_attachment_tags_ocr_for_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction, "_ocr_text", _OcrSpy(text="스캔 내용"))
    r = extraction.extract_attachment(filename="scan.png", content=b"\x89PNG")
    assert r.method == "ocr"
    assert r.text == "스캔 내용"


def test_extract_attachment_tags_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction, "_ocr_text", _OcrSpy(text=""))
    r = extraction.extract_attachment(filename="scan.png", content=b"\x89PNG")
    assert r.method == "none"
    assert r.text == ""


def test_combine_drops_ocr_when_native_sibling_present() -> None:
    items = [
        extraction.AttachmentExtraction("복리후생 기준.png", "OCR 저품질 글자", "ocr"),
        extraction.AttachmentExtraction("복리후생 기준.pptx", "네이티브 정확한 표 내용", "native"),
    ]
    combined = extraction.combine_attachment_texts(items)
    assert "네이티브 정확한 표 내용" in combined
    assert "OCR 저품질 글자" not in combined
    assert "복리후생 기준.png" not in combined


def test_combine_keeps_ocr_without_native_sibling() -> None:
    items = [extraction.AttachmentExtraction("공지스캔.png", "OCR 내용", "ocr")]
    assert "OCR 내용" in extraction.combine_attachment_texts(items)


def test_combine_keeps_ocr_for_different_base_name() -> None:
    items = [
        extraction.AttachmentExtraction("가족수당.png", "이미지 전용 내용", "ocr"),
        extraction.AttachmentExtraction("복리후생 기준.pptx", "네이티브 내용", "native"),
    ]
    combined = extraction.combine_attachment_texts(items)
    assert "이미지 전용 내용" in combined  # different document → must be kept
    assert "네이티브 내용" in combined


def test_combine_skips_empty_and_preserves_order() -> None:
    items = [
        extraction.AttachmentExtraction("a.pdf", "첫번째", "native"),
        extraction.AttachmentExtraction("b.png", "", "none"),
        extraction.AttachmentExtraction("c.pdf", "세번째", "native"),
    ]
    combined = extraction.combine_attachment_texts(items)
    assert combined.index("첫번째") < combined.index("세번째")
    assert "b.png" not in combined
