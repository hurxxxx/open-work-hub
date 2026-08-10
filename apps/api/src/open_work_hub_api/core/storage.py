"""MinIO object-storage client singleton."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from minio import Minio

from open_work_hub_api.core.settings import get_settings


@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    settings = get_settings()
    parsed = urlparse(settings.minio_endpoint)
    secure = parsed.scheme == "https"
    host = parsed.netloc or parsed.path
    return Minio(
        host,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=secure,
    )


def ensure_bucket() -> None:
    settings = get_settings()
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
