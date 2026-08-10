from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from ai_do_api.domains.dm import attachment_records
from ai_do_api.domains.dm.models import DmMessageAttachment


def test_create_attachment_persists_row_and_stores_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb()
    storage = _FakeAttachmentStorage()
    _patch_attachment_dependencies(monkeypatch, storage)

    row = attachment_records.create_attachment(
        db,
        current_user=_user("user-1"),
        conversation_id="conversation-1",
        filename=r"C:\tmp\pic?.png",
        content_type="application/octet-stream",
        content=BytesIO(b"image-bytes"),
        size_bytes=11,
        sniff_bytes=b"\x89PNG\r\n\x1a\nrest",
    )

    assert row is db.added[0]
    assert row.id == "attachment-1"
    assert row.conversation_id == "conversation-1"
    assert row.uploader_id == "user-1"
    assert row.filename == "pic_.png"
    assert row.content_type == "image/png"
    assert row.storage_key == "dm/conversation-1/attachment-1/pic_.png"
    assert storage.put_calls == [
        (row.storage_key, 11, "image/png"),
    ]
    assert db.flushed is True
    assert db.committed is True
    assert db.refreshed == [row]


def test_create_attachment_rejects_empty_size_after_conversation_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb()
    storage = _FakeAttachmentStorage()
    checked = _patch_attachment_dependencies(monkeypatch, storage)

    with pytest.raises(HTTPException) as excinfo:
        attachment_records.create_attachment(
            db,
            current_user=_user("user-1"),
            conversation_id="conversation-1",
            filename="file.txt",
            content_type="text/plain",
            content=BytesIO(b""),
            size_bytes=0,
        )

    assert excinfo.value.status_code == 422
    assert checked == [("user-1", "conversation-1")]
    assert db.added == []
    assert storage.put_calls == []


def test_create_attachment_rejects_oversize_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb()
    storage = _FakeAttachmentStorage()
    checked = _patch_attachment_dependencies(monkeypatch, storage)
    monkeypatch.setattr(
        attachment_records.attachment_policy,
        "is_dm_attachment_size_allowed",
        lambda size_bytes: False,
    )
    monkeypatch.setattr(
        attachment_records.attachment_policy,
        "dm_attachment_size_limit_mb",
        lambda: 50,
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_records.create_attachment(
            db,
            current_user=_user("user-1"),
            conversation_id="conversation-1",
            filename="file.txt",
            content_type="text/plain",
            content=BytesIO(b"content"),
            size_bytes=51,
        )

    assert excinfo.value.status_code == 413
    assert checked == [("user-1", "conversation-1")]
    assert db.added == []
    assert storage.put_calls == []


def test_create_attachment_rolls_back_when_object_upload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb()
    _patch_attachment_dependencies(
        monkeypatch,
        _FakeAttachmentStorage(put_error=RuntimeError("upload")),
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_records.create_attachment(
            db,
            current_user=_user("user-1"),
            conversation_id="conversation-1",
            filename="file.txt",
            content_type="text/plain",
            content=BytesIO(b"content"),
            size_bytes=7,
        )

    assert excinfo.value.status_code == 502
    assert db.rollback_count == 1
    assert db.committed is False


def test_create_attachment_removes_object_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(commit_error=RuntimeError("commit"))
    storage = _FakeAttachmentStorage()
    _patch_attachment_dependencies(monkeypatch, storage)

    with pytest.raises(HTTPException) as excinfo:
        attachment_records.create_attachment(
            db,
            current_user=_user("user-1"),
            conversation_id="conversation-1",
            filename="file.txt",
            content_type="text/plain",
            content=BytesIO(b"content"),
            size_bytes=7,
        )

    assert excinfo.value.status_code == 500
    assert db.rollback_count == 1
    assert storage.remove_calls == ["dm/conversation-1/attachment-1/file.txt"]


def test_require_attachment_access_loads_attachment_and_checks_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachment = _attachment()
    db = _FakeDb(attachment=attachment)
    checked: list[tuple[str, str]] = []

    def require_user_conversation(db, *, current_user, conversation_id):  # noqa: ANN001
        checked.append((current_user.id, conversation_id))
        return SimpleNamespace(id=conversation_id)

    monkeypatch.setattr(
        attachment_records.conversation_queries,
        "require_user_conversation",
        require_user_conversation,
    )

    assert (
        attachment_records.require_attachment_access(
            db,
            current_user=_user("user-1"),
            attachment_id="attachment-1",
        )
        is attachment
    )
    assert checked == [("user-1", "conversation-1")]


def test_require_attachment_access_rejects_missing_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb()
    checked: list[tuple[str, str]] = []

    def require_user_conversation(db, *, current_user, conversation_id):  # noqa: ANN001
        checked.append((current_user.id, conversation_id))
        return SimpleNamespace(id=conversation_id)

    monkeypatch.setattr(
        attachment_records.conversation_queries,
        "require_user_conversation",
        require_user_conversation,
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_records.require_attachment_access(
            db,
            current_user=_user("user-1"),
            attachment_id="attachment-1",
        )

    assert excinfo.value.status_code == 404
    assert checked == []


def test_require_attachment_access_propagates_conversation_denial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(attachment=_attachment())
    checked: list[tuple[str, str]] = []

    def require_user_conversation(db, *, current_user, conversation_id):  # noqa: ANN001
        checked.append((current_user.id, conversation_id))
        raise HTTPException(status_code=403, detail="forbidden")

    monkeypatch.setattr(
        attachment_records.conversation_queries,
        "require_user_conversation",
        require_user_conversation,
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_records.require_attachment_access(
            db,
            current_user=_user("user-1"),
            attachment_id="attachment-1",
        )

    assert excinfo.value.status_code == 403
    assert checked == [("user-1", "conversation-1")]


def test_attachment_preview_url_rejects_non_previewable_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeDb(attachment=_attachment(content_type="text/plain"))
    monkeypatch.setattr(
        attachment_records.conversation_queries,
        "require_user_conversation",
        lambda db, *, current_user, conversation_id: SimpleNamespace(id=conversation_id),
    )

    with pytest.raises(HTTPException) as excinfo:
        attachment_records.attachment_preview_url(
            db,
            current_user=_user("user-1"),
            attachment_id="attachment-1",
        )

    assert excinfo.value.status_code == 415


def _patch_attachment_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    storage: "_FakeAttachmentStorage",
) -> list[tuple[str, str]]:
    checked: list[tuple[str, str]] = []

    def require_user_conversation(db, *, current_user, conversation_id):  # noqa: ANN001
        checked.append((current_user.id, conversation_id))
        return SimpleNamespace(id=conversation_id)

    monkeypatch.setattr(
        attachment_records.conversation_queries,
        "require_user_conversation",
        require_user_conversation,
    )
    monkeypatch.setattr(attachment_records, "new_id", lambda: "attachment-1")
    monkeypatch.setattr(
        attachment_records.attachment_persistence.attachment_storage,
        "dm_attachment_storage",
        lambda: storage,
    )
    return checked


def _attachment(*, content_type: str = "image/png") -> DmMessageAttachment:
    return DmMessageAttachment(
        id="attachment-1",
        conversation_id="conversation-1",
        message_id=None,
        uploader_id="user-1",
        filename="file.png",
        content_type=content_type,
        size_bytes=12,
        storage_key="dm/conversation-1/attachment-1/file.png",
    )


def _user(user_id: str) -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


class _FakeDb:
    def __init__(self, *, attachment=None, commit_error: Exception | None = None) -> None:
        self.attachment = attachment
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

    def refresh(self, row) -> None:  # noqa: ANN001
        self.refreshed.append(row)

    def rollback(self) -> None:
        self.rollback_count += 1

    def get(self, model, key: str):  # noqa: ANN001
        assert model is DmMessageAttachment
        assert key == "attachment-1"
        return self.attachment


class _FakeAttachmentStorage:
    def __init__(self, *, put_error: Exception | None = None) -> None:
        self.put_error = put_error
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
