from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import BinaryIO, Protocol

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import get_minio_client


class FileStorageObject(Protocol):
    def stream(self, amt: int) -> Iterator[bytes]: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


@dataclass(frozen=True)
class FileStorageRemovalFailure:
    storage_key: str
    exc: Exception


def put_file_object(
    *,
    storage_key: str,
    content: BinaryIO,
    size_bytes: int,
    content_type: str,
) -> None:
    get_minio_client().put_object(
        get_settings().minio_bucket,
        storage_key,
        content,
        length=size_bytes,
        content_type=content_type,
    )


def open_file_object(storage_key: str) -> FileStorageObject:
    return get_minio_client().get_object(get_settings().minio_bucket, storage_key)


def remove_file_object(storage_key: str) -> None:
    get_minio_client().remove_object(get_settings().minio_bucket, storage_key)


def remove_file_objects(storage_keys: Iterable[str]) -> list[FileStorageRemovalFailure]:
    keys = list(storage_keys)
    if not keys:
        return []
    bucket = get_settings().minio_bucket
    client = get_minio_client()
    failures: list[FileStorageRemovalFailure] = []
    for key in keys:
        try:
            client.remove_object(bucket, key)
        except Exception as exc:
            failures.append(FileStorageRemovalFailure(storage_key=key, exc=exc))
    return failures
