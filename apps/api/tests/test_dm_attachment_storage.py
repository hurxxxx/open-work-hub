from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from types import SimpleNamespace

import pytest

from ai_do_api.domains.dm import attachment_storage


def test_dm_attachment_storage_put_rewinds_content_and_maps_client_arguments() -> None:
    client = _FakeStorageClient()
    storage = attachment_storage.DmAttachmentStorage(bucket_name="dm-test", client=client)
    content = BytesIO(b"payload")
    content.read(3)

    storage.put(
        storage_key="dm/conversation-1/attachment-1/file.txt",
        content=content,
        size_bytes=7,
        content_type="text/plain",
    )

    assert client.put_calls == [
        (
            "dm-test",
            "dm/conversation-1/attachment-1/file.txt",
            content,
            7,
            "text/plain",
            0,
        ),
    ]


def test_dm_attachment_storage_remove_maps_client_arguments() -> None:
    client = _FakeStorageClient()
    storage = attachment_storage.DmAttachmentStorage(bucket_name="dm-test", client=client)

    storage.remove(storage_key="dm/conversation-1/attachment-1/file.txt")

    assert client.remove_calls == [("dm-test", "dm/conversation-1/attachment-1/file.txt")]


def test_dm_attachment_storage_open_stream_gets_object_and_closes_storage_object() -> None:
    storage_object = _FakeStorageObject()
    client = _FakeStorageClient(storage_object=storage_object)
    storage = attachment_storage.DmAttachmentStorage(bucket_name="dm-test", client=client)

    body = storage.open_stream(
        storage_key="dm/conversation-1/attachment-1/file.txt",
        chunk_size=128,
    )

    assert list(body) == [b"chunk-a", b"chunk-b"]
    assert client.get_calls == [("dm-test", "dm/conversation-1/attachment-1/file.txt")]
    assert storage_object.chunk_size == 128
    assert storage_object.events == ["stream:128", "close", "release"]
    assert storage_object.closed is True
    assert storage_object.released is True


def test_dm_attachment_storage_open_stream_cleans_up_when_iteration_raises() -> None:
    storage_object = _FakeStorageObject(error=RuntimeError("stream failed"))
    client = _FakeStorageClient(storage_object=storage_object)
    storage = attachment_storage.DmAttachmentStorage(bucket_name="dm-test", client=client)

    body = storage.open_stream(
        storage_key="dm/conversation-1/attachment-1/file.txt",
        chunk_size=64,
    )

    with pytest.raises(RuntimeError, match="stream failed"):
        list(body)

    assert client.get_calls == [("dm-test", "dm/conversation-1/attachment-1/file.txt")]
    assert storage_object.chunk_size == 64
    assert storage_object.events == ["stream:64", "close", "release"]
    assert storage_object.closed is True
    assert storage_object.released is True


def test_dm_attachment_storage_factory_uses_settings_and_minio_client(monkeypatch) -> None:
    client = _FakeStorageClient()
    monkeypatch.setattr(
        attachment_storage,
        "get_settings",
        lambda: SimpleNamespace(minio_bucket="dm-test"),
    )
    monkeypatch.setattr(attachment_storage, "get_minio_client", lambda: client)

    storage = attachment_storage.dm_attachment_storage()

    assert storage.bucket_name == "dm-test"
    assert storage.client is client
    storage.remove(storage_key="dm/conversation-1/attachment-1/file.txt")
    assert client.remove_calls == [("dm-test", "dm/conversation-1/attachment-1/file.txt")]


class _FakeStorageClient:
    def __init__(self, *, storage_object: "_FakeStorageObject | None" = None) -> None:
        self.storage_object = storage_object
        self.put_calls = []
        self.remove_calls = []
        self.get_calls = []

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        *,
        length: int,
        content_type: str,
    ) -> None:
        self.put_calls.append((bucket_name, object_name, data, length, content_type, data.tell()))

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.remove_calls.append((bucket_name, object_name))

    def get_object(self, bucket_name: str, object_name: str) -> "_FakeStorageObject":
        self.get_calls.append((bucket_name, object_name))
        assert self.storage_object is not None
        return self.storage_object


class _FakeStorageObject:
    def __init__(
        self,
        *,
        chunks: tuple[bytes, ...] = (b"chunk-a", b"chunk-b"),
        error: Exception | None = None,
    ) -> None:
        self.chunks = chunks
        self.error = error
        self.chunk_size: int | None = None
        self.closed = False
        self.released = False
        self.events: list[str] = []

    def stream(self, chunk_size: int) -> Iterator[bytes]:
        self.chunk_size = chunk_size
        self.events.append(f"stream:{chunk_size}")
        yield from self.chunks
        if self.error is not None:
            raise self.error

    def close(self) -> None:
        self.closed = True
        self.events.append("close")

    def release_conn(self) -> None:
        self.released = True
        self.events.append("release")
