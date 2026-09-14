from __future__ import annotations

import asyncio
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.app_access import allowed_app_ids, can_use_app
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.hermes.files import (
    MAX_FILE_BYTES,
    list_files,
    normalize_path,
    read_file,
    save_file,
)
from open_work_hub_api.domains.hermes.models import (
    HermesRunProjection,
    HermesSessionBinding,
    HermesSessionFile,
    HermesFileRevision,
)
from open_work_hub_api.domains.hermes.repository import (
    ACTIVE_RUN_STATUSES,
    get_owned_session,
    utcnow_naive,
)
from open_work_hub_api.domains.hermes.schemas import (
    HermesFileListResponse,
    HermesFileResponse,
    HermesFileRevisionResponse,
    HermesFileRevisionListResponse,
)

router = APIRouter()


def _owned_session(db: Session, session_id: str, user: User):
    session = get_owned_session(db, session_id=session_id, user_id=user.id)
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.session_not_found"})
    return session


@router.get("/sessions/{session_id}/files", response_model=HermesFileListResponse)
def session_files(
    session_id: str,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    session = _owned_session(db, session_id, user)
    return HermesFileListResponse(
        data=[
            HermesFileResponse.model_validate(row) for row in list_files(db, session_id=session.id)
        ]
    )


@router.get("/sessions/{session_id}/file-revisions", response_model=HermesFileRevisionListResponse)
def session_file_revisions(
    session_id: str,
    file_id: str | None = Query(default=None, max_length=36),
    run_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    session = _owned_session(db, session_id, user)
    predicates = [
        HermesFileRevision.session_id == session.id,
        HermesFileRevision.user_id == user.id,
        HermesFileRevision.expires_at > utcnow_naive(),
        or_(
            HermesFileRevision.run_id.is_(None),
            HermesFileRevision.run_id.in_(
                select(HermesRunProjection.id).where(
                    HermesRunProjection.user_id == user.id,
                    HermesRunProjection.owner_app_id.in_(allowed_app_ids(db, user_id=user.id)),
                )
            ),
        ),
    ]
    if file_id is not None:
        predicates.append(HermesFileRevision.file_id == file_id)
    if run_id is not None:
        predicates.append(HermesFileRevision.run_id == run_id)
    rows = list(
        db.scalars(
            select(HermesFileRevision)
            .where(*predicates)
            .order_by(
                HermesFileRevision.created_at.desc(),
                HermesFileRevision.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
    )
    return HermesFileRevisionListResponse(
        data=[HermesFileRevisionResponse.model_validate(row) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )


def _owned_revision(db: Session, revision_id: str, user: User) -> HermesFileRevision:
    row = db.get(HermesFileRevision, revision_id)
    if row is None or row.user_id != user.id or row.expires_at <= utcnow_naive():
        raise HTTPException(status_code=404, detail={"code": "hermes.file_not_found"})
    _owned_session(db, row.session_id, user)
    if row.run_id:
        run = db.get(HermesRunProjection, row.run_id)
        if (
            run is None
            or run.user_id != user.id
            or not can_use_app(db, user_id=user.id, app_id=run.owner_app_id)
        ):
            raise HTTPException(status_code=404, detail={"code": "hermes.file_not_found"})
    return row


@router.get("/file-revisions/{revision_id}", response_model=HermesFileRevisionResponse)
def file_revision(
    revision_id: str,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    return HermesFileRevisionResponse.model_validate(_owned_revision(db, revision_id, user))


@router.get("/file-revisions/{revision_id}/content")
def download_file_revision(
    revision_id: str,
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    return _file_content_response(_owned_revision(db, revision_id, user))


@router.get("/file-revisions/{revision_id}/preview-asset")
def preview_file_asset(
    revision_id: str,
    path: str = Query(min_length=1, max_length=1024),
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    anchor = _owned_revision(db, revision_id, user)
    try:
        relative_path = normalize_path(path)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "hermes.file_not_found"}) from None
    # Historical HTML never picks up a newer dependency, a different
    # conversation's file, or a fallback revision hidden by access controls.
    candidate = db.scalar(
        select(HermesFileRevision)
        .where(
            HermesFileRevision.session_id == anchor.session_id,
            HermesFileRevision.relative_path == relative_path,
            HermesFileRevision.created_at <= anchor.created_at,
        )
        .order_by(HermesFileRevision.created_at.desc(), HermesFileRevision.id.desc())
        .limit(1)
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail={"code": "hermes.file_not_found"})
    candidate = _owned_revision(db, candidate.id, user)
    if candidate.size_bytes > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail={"code": "hermes.file_too_large"})
    body = read_file(candidate)
    # Recheck both the anchor and dependency after potentially slow object I/O.
    db.expire_all()
    _owned_revision(db, revision_id, user)
    _owned_revision(db, candidate.id, user)
    require_app_access("chatbot")(db=db, user=user)
    return Response(
        body,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "attachment",
        },
    )


def _file_content_response(row: HermesSessionFile | HermesFileRevision):
    return Response(
        read_file(row),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.relative_path.rsplit('/', 1)[-1], safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


def _persist_upload(
    db: Session, *, session_id: str, user: User, file_name: str, data: bytearray
) -> HermesFileResponse:
    # Recheck authority after body reception and keep DB/object work together.
    require_app_access("chatbot")(db=db, user=user)
    session = _owned_session(db, session_id, user)
    db.execute(
        select(HermesSessionBinding.id)
        .where(HermesSessionBinding.id == session.id)
        .with_for_update()
    ).scalar_one()
    if db.scalar(
        select(HermesRunProjection.id)
        .where(
            HermesRunProjection.session_binding_id == session.id,
            HermesRunProjection.status.in_(ACTIVE_RUN_STATUSES),
        )
        .limit(1)
    ):
        raise HTTPException(status_code=409, detail={"code": "hermes.files_active_run"})
    row = save_file(
        db,
        session=session,
        path=unquote(file_name, errors="strict"),
        data=bytes(data),
        reject_active_run=True,
    )
    return HermesFileResponse.model_validate(row)


@router.post(
    "/sessions/{session_id}/files",
    response_model=HermesFileResponse,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
async def upload_file(
    session_id: str,
    request: Request,
    file_name: str = Header(alias="X-File-Name", min_length=1, max_length=4096),
    db: Session = Depends(get_db_session),
    user: User = Depends(require_current_user),
):
    await run_in_threadpool(_owned_session, db, session_id, user)
    try:
        if request.headers.get("content-type", "").split(";", 1)[0] != "application/octet-stream":
            raise ValueError("Binary upload required")
        declared_size = request.headers.get("content-length")
        if declared_size is not None and not 0 <= int(declared_size) <= MAX_FILE_BYTES:
            raise ValueError("File exceeds size limit")
        data = bytearray()
        async with asyncio.timeout(60):
            async for chunk in request.stream():
                if len(data) + len(chunk) > MAX_FILE_BYTES:
                    raise ValueError("File exceeds size limit")
                data.extend(chunk)
        return await run_in_threadpool(
            _persist_upload,
            db,
            session_id=session_id,
            user=user,
            file_name=file_name,
            data=data,
        )
    except (ValueError, TimeoutError) as error:
        raise HTTPException(status_code=422, detail={"code": "hermes.file_invalid"}) from error


@router.get("/files/{file_id}/content")
def download_file(
    file_id: str, db: Session = Depends(get_db_session), user: User = Depends(require_current_user)
):
    row = db.get(HermesSessionFile, file_id)
    if row is None or row.user_id != user.id or row.expires_at <= utcnow_naive():
        raise HTTPException(status_code=404, detail={"code": "hermes.file_not_found"})
    _owned_session(db, row.session_id, user)
    return _file_content_response(row)
