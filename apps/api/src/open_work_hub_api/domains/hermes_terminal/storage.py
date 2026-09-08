from __future__ import annotations

import hashlib
import mimetypes
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

from minio.error import S3Error

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import ensure_bucket, get_minio_client
from open_work_hub_api.domains.hermes_terminal.security import normalize_relative_path

STREAM_CHUNK_SIZE = 1024 * 1024
MAX_ARTIFACT_FILE_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_FILES = 10_000


@dataclass(frozen=True)
class WorkspaceArtifactScan:
    items: list[tuple[str, bytes, str, str]]
    archived_bytes: int
    omitted_count: int


def profile_storage_key(
    *,
    user_id: str,
    session_id: str,
    attempt_id: str,
) -> str:
    return f"users/{user_id}/hermes-terminal/profiles/{session_id}/{attempt_id}.tar.gz"


def artifact_storage_key(
    *,
    user_id: str,
    session_id: str,
    attempt_id: str,
    path: str,
) -> str:
    path_digest = hashlib.sha256(path.encode()).hexdigest()
    return (
        f"users/{user_id}/hermes-terminal/"
        f"sessions/{session_id}/attempts/{attempt_id}/artifacts/{path_digest}"
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
    except S3Error as error:
        if error.code not in {"NoSuchKey", "NoSuchObject", "NoSuchBucket"}:
            raise


def collect_workspace_artifacts(
    archive: bytes,
    *,
    max_total_bytes: int,
) -> WorkspaceArtifactScan:
    total = 0
    omitted_count = 0
    items: list[tuple[str, bytes, str, str]] = []
    seen_paths: set[str] = set()
    with tarfile.open(fileobj=BytesIO(archive), mode="r:*") as tar:
        for member in tar:
            if member.isdir():
                continue
            if not member.isfile() or member.issym() or member.islnk():
                omitted_count += 1
                continue
            parts = PurePosixPath(member.name).parts
            if parts and parts[0] == "workspace":
                parts = parts[1:]
            if not parts:
                omitted_count += 1
                continue
            if parts[0] == ".owh-runtime":
                omitted_count += 1
                continue
            try:
                relative_path = normalize_relative_path("/".join(parts), allow_root=False)
            except ValueError:
                omitted_count += 1
                continue
            if relative_path in seen_paths:
                omitted_count += 1
                continue
            seen_paths.add(relative_path)
            if len(items) >= MAX_ARTIFACT_FILES:
                omitted_count += 1
                continue
            if member.size < 0 or member.size > MAX_ARTIFACT_FILE_BYTES:
                omitted_count += 1
                continue
            if total + member.size > max_total_bytes:
                omitted_count += 1
                continue
            source = tar.extractfile(member)
            if source is None:
                omitted_count += 1
                continue
            data = source.read(MAX_ARTIFACT_FILE_BYTES + 1)
            if len(data) != member.size or len(data) > MAX_ARTIFACT_FILE_BYTES:
                omitted_count += 1
                continue
            media_type = mimetypes.guess_type(relative_path)[0] or "application/octet-stream"
            total += len(data)
            items.append((relative_path, data, media_type, hashlib.sha256(data).hexdigest()))
    return WorkspaceArtifactScan(
        items=items,
        archived_bytes=total,
        omitted_count=omitted_count,
    )
