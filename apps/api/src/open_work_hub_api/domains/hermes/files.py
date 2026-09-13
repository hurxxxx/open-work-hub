from __future__ import annotations

import hashlib
import mimetypes
from datetime import timedelta
from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.storage import ensure_bucket, get_minio_client
from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.hermes.models import (
    HermesFileObject,
    HermesProfileBinding,
    HermesRunProjection,
    HermesSessionBinding,
    HermesSessionFile,
)

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_SESSION_BYTES = 256 * 1024 * 1024
MAX_SESSION_FILES = 10_000


def normalize_path(value: str) -> str:
    parts = value.replace("\\", "/").split("/")
    if (
        not value
        or len(value) > 1024
        or any(
            not part or part in {".", "..", ".owh-runtime"} or any(ord(c) < 32 for c in part)
            for part in parts
        )
    ):
        raise ValueError("Invalid workspace file path")
    return PurePosixPath(*parts).as_posix()


def list_files(db: Session, *, session_id: str) -> list[HermesSessionFile]:
    return list(
        db.scalars(
            select(HermesSessionFile)
            .where(
                HermesSessionFile.session_id == session_id,
                HermesSessionFile.expires_at > utcnow_naive(),
            )
            .order_by(HermesSessionFile.relative_path)
        )
    )


def require_active_file_run(
    db: Session,
    *,
    run_id: str,
    user_id: str,
    session_id: str | None = None,
    for_update: bool = False,
) -> HermesRunProjection:
    from open_work_hub_api.domains.hermes.repository import ACTIVE_RUN_STATUSES

    query = (
        select(HermesRunProjection)
        .join(
            HermesSessionBinding, HermesSessionBinding.id == HermesRunProjection.session_binding_id
        )
        .join(
            HermesProfileBinding, HermesProfileBinding.id == HermesRunProjection.profile_binding_id
        )
        .where(
            HermesRunProjection.id == run_id,
            HermesRunProjection.user_id == user_id,
            HermesRunProjection.kind == "interactive",
            HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES - {"stopping"}),
            HermesSessionBinding.user_id == user_id,
            HermesSessionBinding.status != "deleted",
            HermesSessionBinding.profile_binding_id == HermesProfileBinding.id,
            HermesProfileBinding.user_id == user_id,
            HermesProfileBinding.status == "active",
        )
        .execution_options(populate_existing=True)
    )
    if session_id is not None:
        query = query.where(HermesSessionBinding.id == session_id)
    if for_update:
        query = query.with_for_update(of=HermesRunProjection)
    run = db.scalar(query)
    if run is None or not can_use_app(db, user_id=user_id, app_id=run.owner_app_id):
        raise ValueError("File execution is no longer available")
    return run


def _require_upload_access(db: Session, session: HermesSessionBinding) -> None:
    if db.scalar(
        select(HermesSessionBinding.id).where(
            HermesSessionBinding.id == session.id,
            HermesSessionBinding.user_id == session.user_id,
            HermesSessionBinding.status != "deleted",
        )
    ) is None or not can_use_app(db, user_id=session.user_id, app_id="chatbot"):
        raise ValueError("File upload is no longer authorized")


def save_file(
    db: Session,
    *,
    session: HermesSessionBinding,
    path: str,
    data: bytes,
    reject_active_run: bool = False,
    execution_run_id: str | None = None,
) -> HermesSessionFile:
    path = normalize_path(path)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Workspace file exceeds the size limit")
    file_id = str(uuid4())
    key = f"users/{session.user_id}/hermes/sessions/{session.id}/{file_id}"
    # Reserve before object upload: a lost connection or process still leaves
    # an authoritative cleanup record. No object key is forgotten on replace.
    reservation = HermesFileObject(object_key=key, expires_at=utcnow_naive() + timedelta(hours=1))
    db.add(reservation)
    db.commit()
    db.execute(
        select(HermesSessionBinding.id)
        .where(
            HermesSessionBinding.id == session.id,
        )
        .with_for_update()
    ).scalar_one()
    if execution_run_id is not None:
        require_active_file_run(
            db, run_id=execution_run_id, user_id=session.user_id, session_id=session.id
        )
    if reject_active_run:
        _require_upload_access(db, session)
        from open_work_hub_api.domains.hermes.repository import ACTIVE_RUN_STATUSES

        if db.scalar(
            select(HermesRunProjection.id)
            .where(
                HermesRunProjection.session_binding_id == session.id,
                HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES),
            )
            .limit(1)
        ):
            raise ValueError("Wait for the active run before uploading files")
    ancestors = [str(parent) for parent in PurePosixPath(path).parents if str(parent) != "."]
    if db.scalar(
        select(HermesSessionFile.id)
        .where(
            HermesSessionFile.session_id == session.id,
            or_(
                HermesSessionFile.relative_path.in_(ancestors),
                HermesSessionFile.relative_path.startswith(path + "/", autoescape=True),
            ),
        )
        .limit(1)
    ):
        raise ValueError("Workspace file path conflicts with a saved file or directory")
    existing = db.scalar(
        select(HermesSessionFile).where(
            HermesSessionFile.session_id == session.id,
            HermesSessionFile.relative_path == path,
        )
    )
    digest = hashlib.sha256(data).hexdigest()
    if existing is not None and existing.sha256 == digest and existing.expires_at > utcnow_naive():
        return existing
    count, size = db.execute(
        select(func.count(), func.coalesce(func.sum(HermesSessionFile.size_bytes), 0)).where(
            HermesSessionFile.session_id == session.id
        )
    ).one()
    if (existing is None and count >= MAX_SESSION_FILES) or size - (
        existing.size_bytes if existing else 0
    ) + len(data) > MAX_SESSION_BYTES:
        raise ValueError("Workspace file storage limit reached")
    media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    settings = get_settings()
    ensure_bucket()
    client = get_minio_client()
    client.put_object(settings.minio_bucket, key, BytesIO(data), len(data), content_type=media_type)
    # Object upload is outside the final catalog decision. A stopped/revoked
    # execution cannot publish late bytes. The committed reservation remains
    # available to normal cleanup if this check rejects the uploaded object.
    try:
        if execution_run_id is not None:
            require_active_file_run(
                db,
                run_id=execution_run_id,
                user_id=session.user_id,
                session_id=session.id,
                for_update=True,
            )
        if reject_active_run:
            _require_upload_access(db, session)
    except Exception:
        db.rollback()
        raise
    old_key = existing.object_key if existing is not None else None
    row = existing or HermesSessionFile(id=file_id, user_id=session.user_id, session_id=session.id)
    row.relative_path, row.size_bytes, row.sha256 = path, len(data), digest
    row.object_key, row.media_type, row.updated_at = key, media_type, utcnow_naive()
    row.expires_at = utcnow_naive() + timedelta(
        days=settings.hermes_terminal_artifact_retention_days
    )
    reservation.expires_at = row.expires_at
    if old_key:
        old_object = db.get(HermesFileObject, old_key)
        if old_object:
            old_object.expires_at = utcnow_naive()
    try:
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return row


def cleanup_files(db: Session, *, limit: int = 100) -> int:
    """Retry deletions under row locks; failed deletes retain their queue row."""
    rows = list(
        db.scalars(
            select(HermesFileObject)
            .where(
                HermesFileObject.expires_at <= utcnow_naive(),
            )
            .order_by(HermesFileObject.expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    client = get_minio_client()
    for row in rows:
        client.remove_object(get_settings().minio_bucket, row.object_key)
        db.execute(delete(HermesSessionFile).where(HermesSessionFile.object_key == row.object_key))
        db.delete(row)
    db.commit()
    return len(rows)


def read_file(row: HermesSessionFile) -> bytes:
    response = get_minio_client().get_object(get_settings().minio_bucket, row.object_key)
    try:
        data = response.read(MAX_FILE_BYTES + 1)
    finally:
        response.close()
        response.release_conn()
    if len(data) != row.size_bytes or hashlib.sha256(data).hexdigest() != row.sha256:
        raise ValueError("Workspace artifact integrity check failed")
    return data
