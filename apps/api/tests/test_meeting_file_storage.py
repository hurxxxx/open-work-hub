from __future__ import annotations

from types import SimpleNamespace

from open_alm_api.domains.meeting import file_storage


def test_attachment_storage_key_preserves_existing_layout() -> None:
    assert file_storage.attachment_storage_key(
        meeting_id="meeting-1",
        attachment_id="attachment-1",
        filename="notes.txt",
    ) == "meeting/meeting-1/attachment-1/notes.txt"


def test_put_attachment_object_writes_to_configured_bucket(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def put_object(self, bucket, key, body, *, length, content_type):
            captured["bucket"] = bucket
            captured["key"] = key
            captured["body"] = body.read()
            captured["length"] = length
            captured["content_type"] = content_type

    monkeypatch.setattr(file_storage, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(file_storage, "get_minio_client", lambda: FakeClient())

    file_storage.put_attachment_object(
        storage_key="meeting/meeting-1/attachment-1/notes.txt",
        data=b"hello",
        content_type=None,
    )

    assert captured == {
        "bucket": "bucket-1",
        "key": "meeting/meeting-1/attachment-1/notes.txt",
        "body": b"hello",
        "length": 5,
        "content_type": "application/octet-stream",
    }


def test_remove_and_open_attachment_object_delegate_to_minio(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeObject:
        def __init__(self) -> None:
            self.closed = False
            self.released = False

        def stream(self, chunk_size: int):
            captured["chunk_size"] = chunk_size
            yield b"hello"

        def close(self) -> None:
            self.closed = True
            captured["closed"] = True

        def release_conn(self) -> None:
            self.released = True
            captured["released"] = True

    fake_object = FakeObject()

    class FakeClient:
        def remove_object(self, bucket, key):
            captured["removed"] = (bucket, key)

        def get_object(self, bucket, key):
            captured["opened"] = (bucket, key)
            return fake_object

    monkeypatch.setattr(file_storage, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(file_storage, "get_minio_client", lambda: FakeClient())

    file_storage.remove_attachment_object("meeting/meeting-1/attachment-1/notes.txt")
    chunks = list(
        file_storage.open_attachment_object(
            storage_key="meeting/meeting-1/attachment-1/notes.txt",
            chunk_size=8,
        )
    )

    assert captured["removed"] == ("bucket-1", "meeting/meeting-1/attachment-1/notes.txt")
    assert captured["opened"] == ("bucket-1", "meeting/meeting-1/attachment-1/notes.txt")
    assert captured["chunk_size"] == 8
    assert chunks == [b"hello"]
    assert captured["closed"] is True
    assert captured["released"] is True
