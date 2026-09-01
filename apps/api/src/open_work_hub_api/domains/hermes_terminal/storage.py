from __future__ import annotations

import hashlib
import mimetypes
import tarfile
from collections.abc import Iterable
from io import BytesIO
from pathlib import PurePosixPath

from minio.error import S3Error

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import ensure_bucket, get_minio_client
from open_work_hub_api.domains.hermes_terminal.security import normalize_relative_path


STREAM_CHUNK_SIZE = 1024 * 1024
MAX_ARTIFACT_FILE_BYTES = 64 * 1024 * 1024


def profile_storage_key(*, workspace_id: str, user_id: str) -> str:
    return f"workspaces/{workspace_id}/users/{user_id}/hermes-terminal/profile.tar.gz"


def artifact_storage_key(*, workspace_id: str, user_id: str, session_id: str, path: str) -> str:
    path_digest = hashlib.sha256(path.encode()).hexdigest()
    return (
        f"workspaces/{workspace_id}/users/{user_id}/hermes-terminal/"
        f"sessions/{session_id}/artifacts/{path_digest}"
    )


def put_object(*, key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    ensure_bucket()
    get_minio_client().put_object(
        settings.minio_bucket,
        key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def read_object(key: str) -> bytes:
    return b"".join(open_object(key))


def open_object(key: str) -> Iterable[bytes]:
    settings = get_settings()
    obj = get_minio_client().get_object(settings.minio_bucket, key)
    try:
        yield from obj.stream(STREAM_CHUNK_SIZE)
    finally:
        obj.close()
        obj.release_conn()


def remove_object(key: str) -> None:
    settings = get_settings()
    try:
        get_minio_client().remove_object(settings.minio_bucket, key)
    except S3Error:
        pass


def iter_workspace_artifacts(
    archive: bytes,
    *,
    max_total_bytes: int,
) -> Iterable[tuple[str, bytes, str, str]]:
    total = 0
    with tarfile.open(fileobj=BytesIO(archive), mode="r:*") as tar:
        for member in tar:
            if not member.isfile() or member.issym() or member.islnk():
                continue
            parts = PurePosixPath(member.name).parts
            if parts and parts[0] == "workspace":
                parts = parts[1:]
            if not parts:
                continue
            try:
                relative_path = normalize_relative_path("/".join(parts), allow_root=False)
            except ValueError:
                continue
            if member.size < 0 or member.size > MAX_ARTIFACT_FILE_BYTES:
                continue
            total += member.size
            if total > max_total_bytes:
                raise ValueError("Hermes terminal workspace archive exceeds the configured limit.")
            source = tar.extractfile(member)
            if source is None:
                continue
            data = source.read(MAX_ARTIFACT_FILE_BYTES + 1)
            if len(data) != member.size or len(data) > MAX_ARTIFACT_FILE_BYTES:
                continue
            media_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
            yield relative_path, data, media_type, hashlib.sha256(data).hexdigest()
