from __future__ import annotations

import base64
from collections.abc import Iterable
from io import BytesIO

from minio.error import S3Error

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import ensure_bucket, get_minio_client

DIAGRAM_XML_CONTENT_TYPE = "application/vnd.jgraph.mxfile"
DIAGRAM_PNG_CONTENT_TYPE = "image/png"
DIAGRAM_SOURCE_MAX_BYTES = 10 * 1024 * 1024
DIAGRAM_PREVIEW_MAX_BYTES = 5 * 1024 * 1024
DIAGRAM_STREAM_CHUNK_SIZE = 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_DATA_URL_PREFIX = "data:image/png;base64,"


def diagram_source_storage_key(*, workspace_id: str, diagram_id: str) -> str:
    return f"workspaces/{workspace_id}/diagrams/{diagram_id}/source.drawio.xml"


def diagram_preview_storage_key(*, workspace_id: str, diagram_id: str) -> str:
    return f"workspaces/{workspace_id}/diagrams/{diagram_id}/preview.png"


def decode_preview_data_url(value: str) -> bytes | None:
    if not value:
        return None
    if not value.startswith(PNG_DATA_URL_PREFIX):
        return None
    try:
        data = base64.b64decode(value[len(PNG_DATA_URL_PREFIX) :], validate=True)
    except Exception:
        return None
    if not data.startswith(PNG_SIGNATURE):
        return None
    return data


def put_diagram_object(*, storage_key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    ensure_bucket()
    get_minio_client().put_object(
        settings.minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def open_diagram_stream(
    storage_key: str,
    *,
    chunk_size: int = DIAGRAM_STREAM_CHUNK_SIZE,
) -> Iterable[bytes]:
    settings = get_settings()
    obj = get_minio_client().get_object(settings.minio_bucket, storage_key)
    try:
        yield from obj.stream(chunk_size)
    finally:
        obj.close()
        obj.release_conn()


def read_diagram_object(storage_key: str) -> bytes:
    return b"".join(open_diagram_stream(storage_key))


def remove_diagram_object(*, storage_key: str) -> None:
    settings = get_settings()
    try:
        get_minio_client().remove_object(settings.minio_bucket, storage_key)
    except S3Error:
        pass
