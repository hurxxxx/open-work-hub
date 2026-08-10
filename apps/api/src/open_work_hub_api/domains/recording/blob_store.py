from __future__ import annotations

import os
import shutil
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterator

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import get_minio_client


def recording_spool_root() -> Path:
    path = Path(get_settings().recording_spool_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


class RecordingSpoolStore:
    def __init__(self, *, root: Path) -> None:
        self._root = root

    def allocate(self, staging_id: str) -> Path:
        path = self._root / staging_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_chunk(self, *, spool_path: str, seq: int, data: bytes) -> None:
        _fsync_path(_chunk_path(spool_path, seq), data)

    def assemble_chunks(self, *, spool_path: str, sequences: list[int]) -> Path:
        assembled_path = _assembled_path(spool_path)
        with assembled_path.open("wb") as output:
            for seq in sequences:
                with _chunk_path(spool_path, seq).open("rb") as handle:
                    shutil.copyfileobj(handle, output)
            output.flush()
            os.fsync(output.fileno())
        return assembled_path

    def cleanup(self, spool_path: str | None) -> None:
        if not spool_path:
            return
        try:
            shutil.rmtree(spool_path, ignore_errors=True)
        except Exception:
            pass


def default_spool_store() -> RecordingSpoolStore:
    return RecordingSpoolStore(root=recording_spool_root())


def spool_dir_for_recording(staging_id: str) -> Path:
    return default_spool_store().allocate(staging_id)


def build_recording_storage_key(
    *,
    workspace_id: str,
    user_id: str,
    recording_id: str,
    started_at: datetime,
    file_extension: str,
) -> str:
    timestamp = f"{started_at:%Y%m%dT%H%M%SZ}"
    return (
        f"recordings/{workspace_id}/{user_id}/{started_at:%Y/%m/%d}/"
        f"{timestamp}-{recording_id}{file_extension}"
    )


def write_chunk(*, spool_path: str, seq: int, data: bytes) -> None:
    default_spool_store().write_chunk(spool_path=spool_path, seq=seq, data=data)


def assemble_chunks(*, spool_path: str, sequences: list[int]) -> Path:
    return default_spool_store().assemble_chunks(spool_path=spool_path, sequences=sequences)


def cleanup_spool_dir(spool_path: str | None) -> None:
    default_spool_store().cleanup(spool_path)


class RecordingArtifactStore:
    def __init__(self, *, bucket_name: str, client: Any) -> None:
        self._bucket_name = bucket_name
        self._client = client

    def put_bytes(self, *, storage_key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            self._bucket_name,
            storage_key,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def put_file(self, *, storage_key: str, path: Path, content_type: str) -> None:
        self._client.fput_object(
            self._bucket_name,
            storage_key,
            str(path),
            content_type=content_type,
        )

    def open_stream(self, *, storage_key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        obj = self._client.get_object(self._bucket_name, storage_key)
        try:
            yield from obj.stream(chunk_size)
        finally:
            obj.close()
            obj.release_conn()


def default_artifact_store() -> RecordingArtifactStore:
    settings = get_settings()
    return RecordingArtifactStore(
        bucket_name=settings.minio_bucket,
        client=get_minio_client(),
    )


def put_recording_bytes(*, storage_key: str, data: bytes, content_type: str) -> None:
    default_artifact_store().put_bytes(
        storage_key=storage_key,
        data=data,
        content_type=content_type,
    )


def put_recording_file(*, storage_key: str, path: Path, content_type: str) -> None:
    default_artifact_store().put_file(
        storage_key=storage_key,
        path=path,
        content_type=content_type,
    )


def open_recording_stream(*, storage_key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    return default_artifact_store().open_stream(
        storage_key=storage_key,
        chunk_size=chunk_size,
    )


def _chunk_path(spool_path: str, seq: int) -> Path:
    return Path(spool_path) / f"{seq:08d}.chunk"


def _assembled_path(spool_path: str) -> Path:
    return Path(spool_path) / "assembled.bin"


def _fsync_path(path: Path, data: bytes) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
