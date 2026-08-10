from __future__ import annotations

from typing import Any

import pytest
from minio.error import S3Error

from open_alm_api.domains.media.object_storage import (
    DEFAULT_MEDIA_CONTENT_TYPE,
    MediaObjectNotFoundError,
    MediaObjectReadError,
    MediaObjectStorage,
    build_media_storage_key,
)


def test_build_media_storage_key_preserves_existing_layout() -> None:
    assert (
        build_media_storage_key(
            user_id="user-1",
            media_id="media-1",
            filename="fixture.png",
        )
        == "media/user-1/media-1/fixture.png"
    )


def test_put_bytes_writes_bytes_to_configured_bucket_and_key() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.call: dict[str, Any] | None = None

        def put_object(
            self,
            bucket_name: str,
            object_name: str,
            data: Any,
            *,
            length: int,
            content_type: str,
        ) -> None:
            self.call = {
                "bucket_name": bucket_name,
                "object_name": object_name,
                "data": data.read(),
                "length": length,
                "content_type": content_type,
            }

    client = FakeClient()
    storage = MediaObjectStorage(bucket_name="bucket", client=client)

    storage.put_bytes(
        storage_key="media/user-1/media-1/fixture.png",
        data=b"image-bytes",
        content_type="image/png",
    )

    assert client.call == {
        "bucket_name": "bucket",
        "object_name": "media/user-1/media-1/fixture.png",
        "data": b"image-bytes",
        "length": len(b"image-bytes"),
        "content_type": "image/png",
    }


def test_put_bytes_defaults_missing_content_type() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.content_type: str | None = None

        def put_object(
            self,
            bucket_name: str,
            object_name: str,
            data: Any,
            *,
            length: int,
            content_type: str,
        ) -> None:
            self.content_type = content_type

    client = FakeClient()
    storage = MediaObjectStorage(bucket_name="bucket", client=client)

    storage.put_bytes(
        storage_key="media/user-1/media-1/fixture.bin",
        data=b"bytes",
        content_type=None,
    )

    assert client.content_type == DEFAULT_MEDIA_CONTENT_TYPE


def test_open_stream_streams_and_closes_storage_object() -> None:
    class FakeStorageObject:
        def __init__(self) -> None:
            self.chunk_size: int | None = None
            self.closed = False
            self.released = False

        def stream(self, amt: int):
            self.chunk_size = amt
            yield b"png-"
            yield b"bytes"

        def close(self) -> None:
            self.closed = True

        def release_conn(self) -> None:
            self.released = True

    class FakeClient:
        def __init__(self, obj: FakeStorageObject) -> None:
            self.obj = obj
            self.request: tuple[str, str] | None = None

        def get_object(self, bucket_name: str, object_name: str) -> FakeStorageObject:
            self.request = (bucket_name, object_name)
            return self.obj

    obj = FakeStorageObject()
    client = FakeClient(obj)
    storage = MediaObjectStorage(bucket_name="bucket", client=client)

    chunks = list(
        storage.open_stream(
            storage_key="media/user-1/media-1/fixture.png",
            chunk_size=16,
        )
    )

    assert chunks == [b"png-", b"bytes"]
    assert client.request == ("bucket", "media/user-1/media-1/fixture.png")
    assert obj.chunk_size == 16
    assert obj.closed is True
    assert obj.released is True


def test_open_stream_maps_minio_missing_key_to_media_not_found() -> None:
    class FakeClient:
        def get_object(self, bucket_name: str, object_name: str):
            raise S3Error(
                None,
                "NoSuchKey",
                "The specified key does not exist.",
                None,
                "request-id",
                "host-id",
                bucket_name=bucket_name,
                object_name=object_name,
            )

    storage = MediaObjectStorage(bucket_name="bucket", client=FakeClient())

    with pytest.raises(MediaObjectNotFoundError) as exc_info:
        storage.open_stream(storage_key="missing-key")

    assert exc_info.value.storage_key == "missing-key"


def test_open_stream_wraps_generic_read_failure() -> None:
    class FakeClient:
        def get_object(self, bucket_name: str, object_name: str):
            raise RuntimeError("storage unavailable")

    storage = MediaObjectStorage(bucket_name="bucket", client=FakeClient())

    with pytest.raises(MediaObjectReadError) as exc_info:
        storage.open_stream(storage_key="media/user-1/media-1/fixture.png")

    assert exc_info.value.storage_key == "media/user-1/media-1/fixture.png"


def test_remove_many_reports_successes_and_failures() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.removed: list[tuple[str, str]] = []

        def remove_object(self, bucket_name: str, object_name: str) -> None:
            if object_name == "bad-key":
                raise RuntimeError("delete failed")
            self.removed.append((bucket_name, object_name))

    client = FakeClient()
    storage = MediaObjectStorage(bucket_name="bucket", client=client)

    result = storage.remove_many(["good-key", "bad-key", "other-good-key"])

    assert result.removed_storage_keys == ["good-key", "other-good-key"]
    assert [failure.storage_key for failure in result.failures] == ["bad-key"]
    assert client.removed == [("bucket", "good-key"), ("bucket", "other-good-key")]
