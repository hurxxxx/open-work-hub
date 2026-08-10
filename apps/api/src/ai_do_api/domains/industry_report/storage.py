"""Object-storage helpers for uploaded Trend report files.

Mirrors ``domains/images/storage.py`` — bytes live in the shared MinIO bucket;
the DB row (``IndustryReportFile``) holds the storage key.
"""
from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO

from minio.error import S3Error

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import ensure_bucket, get_minio_client

DEFAULT_REPORT_CONTENT_TYPE = "application/pdf"
REPORT_STREAM_CHUNK_SIZE = 1024 * 1024
PDF_SIGNATURE = b"%PDF-"


def is_pdf_report(*, filename: str | None, content_type: str | None) -> bool:
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    return normalized_type == DEFAULT_REPORT_CONTENT_TYPE and (filename or "").lower().endswith(
        ".pdf"
    )


def has_pdf_signature(data: bytes) -> bool:
    return data.lstrip().startswith(PDF_SIGNATURE)


def is_pdf_upload(*, filename: str | None, content_type: str | None, data: bytes) -> bool:
    type_or_name_is_pdf = (
        (content_type or "").split(";", 1)[0].strip().lower() == DEFAULT_REPORT_CONTENT_TYPE
        or (filename or "").lower().endswith(".pdf")
    )
    return type_or_name_is_pdf and has_pdf_signature(data)


def build_report_storage_key(*, file_id: str, filename: str) -> str:
    return f"industry-reports/{file_id}/{filename}"


def put_report_object(*, storage_key: str, data: bytes, content_type: str | None) -> None:
    settings = get_settings()
    ensure_bucket()
    get_minio_client().put_object(
        settings.minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type or DEFAULT_REPORT_CONTENT_TYPE,
    )


def open_report_stream(
    storage_key: str, *, chunk_size: int = REPORT_STREAM_CHUNK_SIZE
) -> Iterable[bytes]:
    settings = get_settings()
    obj = get_minio_client().get_object(settings.minio_bucket, storage_key)
    try:
        yield from obj.stream(chunk_size)
    finally:
        obj.close()
        obj.release_conn()


def remove_report_object(*, storage_key: str) -> None:
    settings = get_settings()
    try:
        get_minio_client().remove_object(settings.minio_bucket, storage_key)
    except S3Error:
        # Best-effort: a missing object should not block deleting the DB row.
        pass
