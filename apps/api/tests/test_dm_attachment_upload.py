from __future__ import annotations

import asyncio

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.dm import attachment_upload


def test_read_dm_attachment_upload_returns_content_size_and_sniff_prefix() -> None:
    upload = asyncio.run(
        attachment_upload.read_dm_attachment_upload(
            _FakeAsyncUploadReader([b"abc", b"def"]),
            content_length="6",
        )
    )

    try:
        assert upload.content.read() == b"abcdef"
        assert upload.size_bytes == 6
        assert upload.sniff_bytes == b"abcdef"
    finally:
        upload.content.close()


def test_read_dm_attachment_upload_allows_empty_stream_for_record_validation() -> None:
    upload = asyncio.run(
        attachment_upload.read_dm_attachment_upload(
            _FakeAsyncUploadReader([]),
            content_length="0",
        )
    )

    try:
        assert upload.content.read() == b""
        assert upload.size_bytes == 0
        assert upload.sniff_bytes == b""
    finally:
        upload.content.close()


def test_read_dm_attachment_upload_limits_sniff_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(attachment_upload.attachment_policy, "DM_ATTACHMENT_SNIFF_BYTES", 5)

    upload = asyncio.run(
        attachment_upload.read_dm_attachment_upload(
            _FakeAsyncUploadReader([b"abc", b"def"]),
            content_length="6",
        )
    )

    try:
        assert upload.content.read() == b"abcdef"
        assert upload.sniff_bytes == b"abcde"
    finally:
        upload.content.close()


def test_read_dm_attachment_upload_rejects_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(attachment_upload.attachment_policy, "DM_MAX_ATTACHMENT_SIZE", 3)
    reader = _FakeAsyncUploadReader([b"abc"])

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            attachment_upload.read_dm_attachment_upload(
                reader,
                content_length=str(
                    3 + attachment_upload.DM_ATTACHMENT_MULTIPART_OVERHEAD_BYTES + 1
                ),
            )
        )

    assert excinfo.value.status_code == 413
    assert reader.read_sizes == []


def test_read_dm_attachment_upload_closes_buffer_when_stream_exceeds_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(attachment_upload.attachment_policy, "DM_MAX_ATTACHMENT_SIZE", 3)
    fake_buffer = _FakeUploadBuffer()
    monkeypatch.setattr(
        attachment_upload,
        "SpooledTemporaryFile",
        lambda *, max_size: fake_buffer,
    )

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            attachment_upload.read_dm_attachment_upload(
                _FakeAsyncUploadReader([b"abcd"]),
                content_length=None,
            )
        )

    assert excinfo.value.status_code == 413
    assert fake_buffer.closed is True


class _FakeAsyncUploadReader:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _FakeUploadBuffer:
    closed = False

    def write(self, chunk: bytes) -> None:
        pass

    def seek(self, position: int) -> None:
        pass

    def close(self) -> None:
        self.closed = True
