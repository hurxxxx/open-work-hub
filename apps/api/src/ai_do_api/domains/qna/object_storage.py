from __future__ import annotations

import re
from io import BytesIO

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import ensure_bucket, get_minio_client

DEFAULT_CONTENT_TYPE = "application/octet-stream"

_UNSAFE_KEY_CHARS = re.compile(r'[\\\r\n]+')


def _safe_segment(value: str) -> str:
    return _UNSAFE_KEY_CHARS.sub("_", value).strip().lstrip("/")


def build_upload_storage_key(*, workspace_id: str, document_id: str, filename: str) -> str:
    return f"qna/{workspace_id}/upload/{document_id}/{_safe_segment(filename)}"


def build_company_upload_storage_key(*, document_id: str, filename: str) -> str:
    return f"company/qna/upload/{document_id}/{_safe_segment(filename)}"


def build_notice_attachment_storage_key(
    *, workspace_id: str, notice_external_id: str, filename: str
) -> str:
    return f"qna/{workspace_id}/notice/{notice_external_id}/{_safe_segment(filename)}"


def build_company_notice_attachment_storage_key(
    *, notice_external_id: str, filename: str
) -> str:
    return f"company/qna/notice/{notice_external_id}/{_safe_segment(filename)}"


def put_qna_object(*, storage_key: str, content: bytes, content_type: str | None) -> None:
    ensure_bucket()
    client = get_minio_client()
    client.put_object(
        get_settings().minio_bucket,
        storage_key,
        BytesIO(content),
        length=len(content),
        content_type=content_type or DEFAULT_CONTENT_TYPE,
    )


def read_qna_object(storage_key: str) -> bytes:
    client = get_minio_client()
    response = client.get_object(get_settings().minio_bucket, storage_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
