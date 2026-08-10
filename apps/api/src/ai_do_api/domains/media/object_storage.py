"""Object storage Adapter for media blobs."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Protocol

from minio.error import S3Error

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import get_minio_client

DEFAULT_MEDIA_CONTENT_TYPE = "application/octet-stream"
MEDIA_OBJECT_STREAM_CHUNK_SIZE = 1024 * 1024


class MediaStorageObject(Protocol):
    def stream(self, amt: int) -> Iterator[bytes]: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class MediaObjectStorageClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: Any,
        *,
        length: int,
        content_type: str,
    ) -> None: ...

    def get_object(self, bucket_name: str, object_name: str) -> MediaStorageObject: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...


class MediaObjectStorageError(Exception):
    """Base error for media object storage failures."""


@dataclass(frozen=True)
class MediaObjectNotFoundError(MediaObjectStorageError):
    storage_key: str


@dataclass(frozen=True)
class MediaObjectReadError(MediaObjectStorageError):
    storage_key: str


@dataclass(frozen=True)
class MediaObjectRemovalFailure:
    storage_key: str
    exc: Exception


@dataclass(frozen=True)
class MediaObjectRemovalResult:
    removed_storage_keys: list[str]
    failures: list[MediaObjectRemovalFailure]


@dataclass(frozen=True)
class MediaObjectStorage:
    bucket_name: str
    client: MediaObjectStorageClient

    def put_bytes(
        self,
        *,
        storage_key: str,
        data: bytes,
        content_type: str | None,
    ) -> None:
        self.client.put_object(
            self.bucket_name,
            storage_key,
            BytesIO(data),
            length=len(data),
            content_type=content_type or DEFAULT_MEDIA_CONTENT_TYPE,
        )

    def open_stream(
        self,
        *,
        storage_key: str,
        chunk_size: int = MEDIA_OBJECT_STREAM_CHUNK_SIZE,
    ) -> Iterable[bytes]:
        try:
            obj = self.client.get_object(self.bucket_name, storage_key)
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                raise MediaObjectNotFoundError(storage_key) from exc
            raise MediaObjectReadError(storage_key) from exc
        except Exception as exc:
            raise MediaObjectReadError(storage_key) from exc
        return stream_media_storage_object(obj, chunk_size=chunk_size)

    def remove(self, *, storage_key: str) -> None:
        self.client.remove_object(self.bucket_name, storage_key)

    def remove_many(self, storage_keys: Iterable[str]) -> MediaObjectRemovalResult:
        removed_storage_keys: list[str] = []
        failures: list[MediaObjectRemovalFailure] = []
        for storage_key in storage_keys:
            try:
                self.remove(storage_key=storage_key)
            except Exception as exc:
                failures.append(MediaObjectRemovalFailure(storage_key=storage_key, exc=exc))
            else:
                removed_storage_keys.append(storage_key)
        return MediaObjectRemovalResult(
            removed_storage_keys=removed_storage_keys,
            failures=failures,
        )


def media_object_storage() -> MediaObjectStorage:
    return MediaObjectStorage(
        bucket_name=get_settings().minio_bucket,
        client=get_minio_client(),
    )


def build_media_storage_key(*, user_id: str, media_id: str, filename: str) -> str:
    return f"media/{user_id}/{media_id}/{filename}"


def stream_media_storage_object(
    obj: MediaStorageObject,
    *,
    chunk_size: int,
) -> Iterable[bytes]:
    try:
        yield from obj.stream(chunk_size)
    finally:
        obj.close()
        obj.release_conn()
