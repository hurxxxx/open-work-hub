"""Orphan media cleanup task."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from ai_do_worker.celery_app import celery_app
from ai_do_worker.settings import get_settings


def _get_db_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    settings = get_settings()
    if not settings.postgres_dsn:
        return None
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    return Session(engine)


def _get_minio_client():
    from minio import Minio

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


@celery_app.task(name="media.cleanup_orphans")
def cleanup_orphan_media() -> dict[str, int]:
    """Delete unlinked media files older than 24 hours."""
    from sqlalchemy import text

    session = _get_db_session()
    if session is None:
        return {"deleted": 0, "failed": 0, "error": "postgres_dsn not configured"}

    settings = get_settings()

    try:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
        rows = session.execute(
            text(
                "SELECT id, storage_key FROM media_files "
                "WHERE resource_type IS NULL AND created_at < :cutoff "
                "LIMIT 500"
            ),
            {"cutoff": cutoff},
        ).fetchall()

        client = _get_minio_client()
        deleted = 0
        failed = 0

        for row in rows:
            try:
                client.remove_object(settings.minio_bucket, row.storage_key)
            except Exception:
                failed += 1
                continue  # Keep DB row so we can retry next run
            session.execute(
                text("DELETE FROM media_files WHERE id = :id"),
                {"id": row.id},
            )
            deleted += 1

        session.commit()
        return {"deleted": deleted, "failed": failed}
    finally:
        session.close()
