"""Unit tests for the Q&A notice change-detection checksum.

Covers the fix that folds attachment byte-content hashes into the checksum, so a
same-filename attachment replacement is detected even when the extracted text is
identical (e.g. a swapped image whose OCR yields the same/empty text).
"""
from __future__ import annotations

from ai_do_api.domains.qna import service


_BASE = dict(
    title="복지제도 기준",
    category="주요공지사항(관리팀)",
    body_text="본문 텍스트는 그대로",
    attachment_names=["복리후생 기준.pdf"],
)


def test_checksum_is_stable_for_identical_inputs() -> None:
    a = service._notice_content_checksum(**_BASE, attachment_content_hashes=["sha-A"])
    b = service._notice_content_checksum(**_BASE, attachment_content_hashes=["sha-A"])
    assert a == b


def test_checksum_changes_when_attachment_bytes_change() -> None:
    # Same title/body/filename, but the file bytes changed → different hash → detected.
    before = service._notice_content_checksum(**_BASE, attachment_content_hashes=["sha-A"])
    after = service._notice_content_checksum(**_BASE, attachment_content_hashes=["sha-B"])
    assert before != after


def test_checksum_changes_when_attachment_added() -> None:
    one = service._notice_content_checksum(**_BASE, attachment_content_hashes=["sha-A"])
    two = service._notice_content_checksum(
        title="복지제도 기준",
        category="주요공지사항(관리팀)",
        body_text="본문 텍스트는 그대로",
        attachment_names=["복리후생 기준.pdf", "복리후생 기준.pptx"],
        attachment_content_hashes=["sha-A", "sha-pptx"],
    )
    assert one != two


def test_checksum_hash_order_independent() -> None:
    # Attachment order from the crawler must not flip the checksum.
    a = service._notice_content_checksum(
        title="t", category="c", body_text="b",
        attachment_names=["a.pdf", "b.pdf"], attachment_content_hashes=["h1", "h2"],
    )
    b = service._notice_content_checksum(
        title="t", category="c", body_text="b",
        attachment_names=["b.pdf", "a.pdf"], attachment_content_hashes=["h2", "h1"],
    )
    assert a == b


def test_checksum_without_hashes_is_stable() -> None:
    # Backward-compatible callers (no hashes) still get a stable checksum.
    a = service._notice_content_checksum(**_BASE, attachment_content_hashes=None)
    b = service._notice_content_checksum(**_BASE, attachment_content_hashes=[])
    assert a == b
