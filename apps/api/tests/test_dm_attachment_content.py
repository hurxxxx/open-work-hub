from __future__ import annotations

from fastapi import HTTPException
import pytest

from ai_do_api.domains.dm import attachment_content
from ai_do_api.domains.dm.models import DmMessageAttachment


def _attachment(*, content_type: str = "image/png") -> DmMessageAttachment:
    return DmMessageAttachment(
        id="attachment-1",
        conversation_id="conversation-1",
        message_id=None,
        uploader_id="user-1",
        filename="quarterly report.txt",
        content_type=content_type,
        size_bytes=12,
        storage_key="dm/conversation-1/attachment-1/quarterly report.txt",
    )


def test_dm_attachment_content_headers_encode_filename_and_security_headers() -> None:
    headers = attachment_content.dm_attachment_content_headers(
        filename="quarterly/report #1?.txt",
        disposition="attachment",
    )

    assert headers == {
        "Cache-Control": "private, max-age=300",
        "Content-Disposition": "attachment; filename*=UTF-8''quarterly%2Freport%20%231%3F.txt",
        "X-Content-Type-Options": "nosniff",
    }


def test_open_dm_attachment_content_returns_stream_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    attachment = _attachment()
    fake_object = _FakeMinioObject()

    class FakeDb:
        def get(self, model, attachment_id: str) -> DmMessageAttachment:
            assert model is DmMessageAttachment
            assert attachment_id == attachment.id
            return attachment

    monkeypatch.setattr(
        attachment_content.attachment_links,
        "validate_dm_attachment_content_signature",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        attachment_content.attachment_storage,
        "dm_attachment_storage",
        lambda: _FakeAttachmentStorage(
            expected_storage_key=attachment.storage_key,
            storage_object=fake_object,
        ),
    )

    content = attachment_content.open_dm_attachment_content(
        FakeDb(),
        attachment_id=attachment.id,
        expires=123,
        signature="sig",
        disposition="inline",
    )

    assert content.media_type == "image/png"
    assert content.headers["Content-Disposition"].startswith("inline;")
    assert list(content.body) == [b"chunk-a", b"chunk-b"]
    assert fake_object.chunk_size == attachment_content.DM_ATTACHMENT_PROXY_CHUNK_SIZE
    assert fake_object.closed is True
    assert fake_object.released is True


def test_open_dm_attachment_content_rejects_missing_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signature_checked = False

    class FakeDb:
        def get(self, model, attachment_id: str) -> None:
            assert model is DmMessageAttachment
            assert attachment_id == "missing-attachment"
            return None

    def validate_signature(*args, **kwargs) -> bool:
        nonlocal signature_checked
        signature_checked = True
        return True

    monkeypatch.setattr(
        attachment_content.attachment_links,
        "validate_dm_attachment_content_signature",
        validate_signature,
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_content.open_dm_attachment_content(
            FakeDb(),
            attachment_id="missing-attachment",
            expires=123,
            signature="sig",
            disposition="attachment",
        )

    assert excinfo.value.status_code == 404
    assert signature_checked is False


def test_open_dm_attachment_content_maps_storage_open_failure_to_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachment = _attachment()

    class FakeDb:
        def get(self, model, attachment_id: str) -> DmMessageAttachment:
            assert model is DmMessageAttachment
            assert attachment_id == attachment.id
            return attachment

    class FailingAttachmentStorage:
        def open_stream(self, *, storage_key: str, chunk_size: int):
            assert storage_key == attachment.storage_key
            assert chunk_size == attachment_content.DM_ATTACHMENT_PROXY_CHUNK_SIZE
            raise RuntimeError("storage unavailable")

    monkeypatch.setattr(
        attachment_content.attachment_links,
        "validate_dm_attachment_content_signature",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        attachment_content.attachment_storage,
        "dm_attachment_storage",
        lambda: FailingAttachmentStorage(),
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_content.open_dm_attachment_content(
            FakeDb(),
            attachment_id=attachment.id,
            expires=123,
            signature="sig",
            disposition="inline",
        )

    assert excinfo.value.status_code == 502


def test_inline_dm_attachment_content_rejects_non_previewable_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signature_checked = False

    def validate_signature(*args, **kwargs) -> bool:
        nonlocal signature_checked
        signature_checked = True
        return True

    monkeypatch.setattr(
        attachment_content.attachment_links,
        "validate_dm_attachment_content_signature",
        validate_signature,
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_content.validate_dm_attachment_content_request(
            _attachment(content_type="text/plain"),
            expires=123,
            signature="sig",
            disposition="inline",
        )

    assert excinfo.value.status_code == 415
    assert signature_checked is False


def test_dm_attachment_content_rejects_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        attachment_content.attachment_links,
        "validate_dm_attachment_content_signature",
        lambda *args, **kwargs: False,
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_content.validate_dm_attachment_content_request(
            _attachment(),
            expires=123,
            signature="sig",
            disposition="inline",
        )

    assert excinfo.value.status_code == 403


class _FakeMinioObject:
    chunk_size: int | None = None
    closed = False
    released = False

    def stream(self, chunk_size: int):
        self.chunk_size = chunk_size
        yield b"chunk-a"
        yield b"chunk-b"

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeAttachmentStorage:
    def __init__(
        self,
        *,
        expected_storage_key: str,
        storage_object: _FakeMinioObject,
    ) -> None:
        self.expected_storage_key = expected_storage_key
        self.storage_object = storage_object

    def open_stream(self, *, storage_key: str, chunk_size: int):
        assert storage_key == self.expected_storage_key
        return attachment_content.attachment_storage.stream_attachment_storage_object(
            self.storage_object,
            chunk_size=chunk_size,
        )
