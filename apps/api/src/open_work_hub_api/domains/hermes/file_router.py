from __future__ import annotations

import asyncio
from urllib.parse import quote, unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.hermes.files import MAX_FILE_BYTES, list_files, read_file, save_file
from open_work_hub_api.domains.hermes.models import (
    HermesRunProjection,
    HermesSessionBinding,
    HermesSessionFile,
)
from open_work_hub_api.domains.hermes.repository import (
    ACTIVE_RUN_STATUSES,
    get_owned_session,
    utcnow_naive,
)
from open_work_hub_api.domains.hermes.schemas import HermesFileListResponse, HermesFileResponse

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
    session = _owned_session(db, session_id, user)
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
    except (ValueError, TimeoutError) as error:
        raise HTTPException(status_code=422, detail={"code": "hermes.file_invalid"}) from error
    return HermesFileResponse.model_validate(row)


@router.get("/files/{file_id}/content")
def download_file(
    file_id: str, db: Session = Depends(get_db_session), user: User = Depends(require_current_user)
):
    row = db.get(HermesSessionFile, file_id)
    if row is None or row.user_id != user.id or row.expires_at <= utcnow_naive():
        raise HTTPException(status_code=404, detail={"code": "hermes.file_not_found"})
    _owned_session(db, row.session_id, user)
    return Response(
        read_file(row),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.relative_path.rsplit('/', 1)[-1], safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
