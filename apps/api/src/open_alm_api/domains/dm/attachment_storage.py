from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from open_alm_api.core.settings import get_settings
from open_alm_api.core.storage import get_minio_client


class DmAttachmentStorageObject(Protocol):
    def stream(self, chunk_size: int) -> Iterable[bytes]: ...
    def close(self) -> None: ...
    def release_conn(self) -> None: ...


class DmAttachmentStorageClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        *,
        length: int,
        content_type: str,
    ) -> None: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...

    def get_object(self, bucket_name: str, object_name: str) -> DmAttachmentStorageObject: ...


@dataclass(frozen=True)
class _DmAttachmentObjectStreamOpener:
    obj: DmAttachmentStorageObject

    def open(self, *, chunk_size: int) -> Iterable[bytes]:
        try:
            yield from self.obj.stream(chunk_size)
        finally:
            try:
                self.obj.close()
            finally:
                self.obj.release_conn()


@dataclass(frozen=True)
class _DmAttachmentStorageAdapter:
    bucket_name: str
    client: DmAttachmentStorageClient

    def put(
        self,
        *,
        storage_key: str,
        content: BinaryIO,
        size_bytes: int,
        content_type: str,
    ) -> None:
        content.seek(0)
        self.client.put_object(
            self.bucket_name,
            storage_key,
            content,
            length=size_bytes,
            content_type=content_type,
        )

    def remove(self, *, storage_key: str) -> None:
        self.client.remove_object(self.bucket_name, storage_key)

    def open_stream(self, *, storage_key: str, chunk_size: int) -> Iterable[bytes]:
        obj = self.client.get_object(self.bucket_name, storage_key)
        return stream_attachment_storage_object(obj, chunk_size=chunk_size)


@dataclass(frozen=True)
class DmAttachmentStorage:
    bucket_name: str
    client: DmAttachmentStorageClient

    def _storage_adapter(self) -> _DmAttachmentStorageAdapter:
        return _DmAttachmentStorageAdapter(
            bucket_name=self.bucket_name,
            client=self.client,
        )

    def put(
        self,
        *,
        storage_key: str,
        content: BinaryIO,
        size_bytes: int,
        content_type: str,
    ) -> None:
        self._storage_adapter().put(
            storage_key=storage_key,
            content=content,
            size_bytes=size_bytes,
            content_type=content_type,
        )

    def remove(self, *, storage_key: str) -> None:
        self._storage_adapter().remove(storage_key=storage_key)

    def open_stream(self, *, storage_key: str, chunk_size: int) -> Iterable[bytes]:
        return self._storage_adapter().open_stream(storage_key=storage_key, chunk_size=chunk_size)


def dm_attachment_storage() -> DmAttachmentStorage:
    settings = get_settings()
    return DmAttachmentStorage(
        bucket_name=settings.minio_bucket,
        client=get_minio_client(),
    )


def stream_attachment_storage_object(
    obj: DmAttachmentStorageObject,
    *,
    chunk_size: int,
) -> Iterable[bytes]:
    yield from _DmAttachmentObjectStreamOpener(obj).open(chunk_size=chunk_size)
