from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO

from ai_do_api.core.settings import get_settings
from ai_do_api.core.storage import ensure_bucket, get_minio_client


RESULT_IMAGE_CONTENT_TYPE = "image/png"


@dataclass(frozen=True)
class ImageObjectRemovalFailure:
    storage_key: str
    exc: Exception


def put_reference_image_object(*, storage_key: str, data: bytes, content_type: str) -> None:
    settings = get_settings()
    ensure_bucket()
    get_minio_client().put_object(
        settings.minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def remove_image_objects(storage_keys: Iterable[str]) -> list[ImageObjectRemovalFailure]:
    keys = list(storage_keys)
    if not keys:
        return []
    settings = get_settings()
    client = get_minio_client()
    failures: list[ImageObjectRemovalFailure] = []
    for key in keys:
        try:
            client.remove_object(settings.minio_bucket, key)
        except Exception as exc:
            failures.append(ImageObjectRemovalFailure(storage_key=key, exc=exc))
    return failures


def presign_image_object(*, storage_key: str, expires: timedelta) -> str:
    settings = get_settings()
    return get_minio_client().presigned_get_object(
        settings.minio_bucket,
        storage_key,
        expires=expires,
    )


def read_image_object(storage_key: str) -> bytes:
    settings = get_settings()
    response = get_minio_client().get_object(
        settings.minio_bucket,
        storage_key,
    )
    try:
        return response.read()
    finally:
        try:
            response.close()
            response.release_conn()
        except Exception:
            pass
