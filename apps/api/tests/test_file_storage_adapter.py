from __future__ import annotations

from types import SimpleNamespace

from open_alm_api.domains.files import storage_adapter


def test_put_file_object_writes_to_configured_bucket(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeContent:
        pass

    class FakeClient:
        def put_object(self, bucket, key, content, *, length, content_type):
            captured["bucket"] = bucket
            captured["key"] = key
            captured["content"] = content
            captured["length"] = length
            captured["content_type"] = content_type

    content = FakeContent()
    monkeypatch.setattr(storage_adapter, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(storage_adapter, "get_minio_client", lambda: FakeClient())

    storage_adapter.put_file_object(
        storage_key="files/ws/file.txt",
        content=content,
        size_bytes=12,
        content_type="text/plain",
    )

    assert captured == {
        "bucket": "bucket-1",
        "key": "files/ws/file.txt",
        "content": content,
        "length": 12,
        "content_type": "text/plain",
    }


def test_open_file_object_reads_from_configured_bucket(monkeypatch) -> None:
    captured: dict[str, object] = {}
    storage_object = object()

    class FakeClient:
        def get_object(self, bucket, key):
            captured["bucket"] = bucket
            captured["key"] = key
            return storage_object

    monkeypatch.setattr(storage_adapter, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(storage_adapter, "get_minio_client", lambda: FakeClient())

    assert storage_adapter.open_file_object("files/ws/file.txt") is storage_object
    assert captured == {"bucket": "bucket-1", "key": "files/ws/file.txt"}


def test_remove_file_objects_returns_failures(monkeypatch) -> None:
    removed: list[str] = []

    class FakeClient:
        def remove_object(self, bucket, key):
            assert bucket == "bucket-1"
            if key == "bad-key":
                raise RuntimeError("cannot remove")
            removed.append(key)

    monkeypatch.setattr(storage_adapter, "get_settings", lambda: SimpleNamespace(minio_bucket="bucket-1"))
    monkeypatch.setattr(storage_adapter, "get_minio_client", lambda: FakeClient())

    failures = storage_adapter.remove_file_objects(["ok-key", "bad-key"])

    assert removed == ["ok-key"]
    assert [failure.storage_key for failure in failures] == ["bad-key"]
    assert isinstance(failures[0].exc, RuntimeError)
