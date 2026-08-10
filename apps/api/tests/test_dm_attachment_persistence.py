from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException
import pytest

from open_work_hub_api.domains.dm import attachment_persistence
from open_work_hub_api.domains.dm.models import DmMessageAttachment


def test_persist_created_attachment_stores_object_and_commits() -> None:
    db = _FakeDb()
    storage = _FakeAttachmentStorage()
    row = _attachment()

    result = attachment_persistence.persist_created_attachment(
        db,
        row=row,
        object_write=_object_write(),
        object_storage=storage,
    )

    assert result is row
    assert db.added == [row]
    assert db.flushed is True
    assert storage.put_calls == [("dm/conversation-1/attachment-1/file.txt", 12, "text/plain")]
    assert db.committed is True
    assert db.refreshed == [row]


def test_persist_created_attachment_rolls_back_when_object_write_fails() -> None:
    db = _FakeDb()
    storage = _FakeAttachmentStorage(put_error=RuntimeError("upload"))

    with pytest.raises(HTTPException) as excinfo:
        attachment_persistence.persist_created_attachment(
            db,
            row=_attachment(),
            object_write=_object_write(),
            object_storage=storage,
        )

    assert excinfo.value.status_code == 502
    assert db.rollback_count == 1
    assert db.committed is False
    assert storage.remove_calls == []


def test_persist_created_attachment_removes_object_when_commit_fails() -> None:
    db = _FakeDb(commit_error=RuntimeError("commit"))
    storage = _FakeAttachmentStorage()

    with pytest.raises(HTTPException) as excinfo:
        attachment_persistence.persist_created_attachment(
            db,
            row=_attachment(),
            object_write=_object_write(),
            object_storage=storage,
        )

    assert excinfo.value.status_code == 500
    assert db.rollback_count == 1
    assert storage.remove_calls == ["dm/conversation-1/attachment-1/file.txt"]


def test_persist_created_attachment_hides_cleanup_failure_after_commit_error() -> None:
    db = _FakeDb(commit_error=RuntimeError("commit"))
    storage = _FakeAttachmentStorage(remove_error=RuntimeError("remove"))

    with pytest.raises(HTTPException) as excinfo:
        attachment_persistence.persist_created_attachment(
            db,
            row=_attachment(),
            object_write=_object_write(),
            object_storage=storage,
        )

    assert excinfo.value.status_code == 500
    assert db.rollback_count == 1
    assert storage.remove_calls == ["dm/conversation-1/attachment-1/file.txt"]


def _object_write() -> attachment_persistence.DmAttachmentObjectWrite:
    return attachment_persistence.DmAttachmentObjectWrite(
        storage_key="dm/conversation-1/attachment-1/file.txt",
        content=BytesIO(b"attachment"),
        size_bytes=12,
        content_type="text/plain",
    )


def _attachment() -> DmMessageAttachment:
    return DmMessageAttachment(
        id="attachment-1",
        conversation_id="conversation-1",
        message_id=None,
        uploader_id="user-1",
        filename="file.txt",
        content_type="text/plain",
        size_bytes=12,
        storage_key="dm/conversation-1/attachment-1/file.txt",
    )


class _FakeDb:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self.commit_error = commit_error
        self.added = []
        self.refreshed = []
        self.flushed = False
        self.committed = False
        self.rollback_count = 0

    def add(self, row) -> None:  # noqa: ANN001
        self.added.append(row)

    def flush(self) -> None:
        self.flushed = True

    def commit(self) -> None:
        if self.commit_error is not None:
            raise self.commit_error
        self.committed = True

    def rollback(self) -> None:
        self.rollback_count += 1

    def refresh(self, row) -> None:  # noqa: ANN001
        self.refreshed.append(row)


class _FakeAttachmentStorage:
    def __init__(
        self,
        *,
        put_error: Exception | None = None,
        remove_error: Exception | None = None,
    ) -> None:
        self.put_error = put_error
        self.remove_error = remove_error
        self.put_calls = []
        self.remove_calls = []

    def put(
        self,
        storage_key: str,
        *,
        content,  # noqa: ANN001
        size_bytes: int,
        content_type: str,
    ) -> None:
        if self.put_error is not None:
            raise self.put_error
        assert content.tell() == 0
        self.put_calls.append((storage_key, size_bytes, content_type))

    def remove(self, *, storage_key: str) -> None:
        self.remove_calls.append(storage_key)
        if self.remove_error is not None:
            raise self.remove_error
