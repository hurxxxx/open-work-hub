from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_work_hub_api.domains.spec_compare import service
from open_work_hub_api.domains.spec_compare.app_catalog import SPEC_COMPARE_WORKSPACE_APP
from open_work_hub_api.domains.spec_compare.schemas import (
    SpecCompareJobListResponse,
    SpecCompareJobOut,
    SpecCompareResultResponse,
)


require_spec_compare_app_enabled = require_workspace_app_enabled(
    SPEC_COMPARE_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/spec-compare",
    tags=["spec-compare"],
    dependencies=[Depends(require_spec_compare_app_enabled)],
)
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PDF_MEDIA_TYPE = "application/pdf"
_BINARY_RESPONSE_SCHEMA = {"type": "string", "format": "binary"}


async def _read_upload(file: UploadFile) -> bytes:
    data = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > _MAX_UPLOAD_BYTES:
            raise localized_http_exception(
                status_code=413,
                code="spec_compare.upload_too_large",
            )
    return bytes(data)


@router.post("/jobs", response_model=SpecCompareJobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    base_file: UploadFile = File(...),
    target_file: UploadFile = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpecCompareJobOut:
    base_content = await _read_upload(base_file)
    target_content = await _read_upload(target_file)
    return service.create_job(
        db,
        workspace=workspace,
        user=current_user,
        title=title,
        base_filename=base_file.filename or "",
        base_mime_type=base_file.content_type or "application/octet-stream",
        base_content=base_content,
        target_filename=target_file.filename or "",
        target_mime_type=target_file.content_type or "application/octet-stream",
        target_content=target_content,
    )


@router.get("/jobs", response_model=SpecCompareJobListResponse)
def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpecCompareJobListResponse:
    return service.list_jobs(db, workspace=workspace, user=current_user, limit=limit)


@router.get("/jobs/{job_id}", response_model=SpecCompareJobOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpecCompareJobOut:
    return service.get_job(db, workspace=workspace, user=current_user, job_id=job_id)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_200_OK)
def delete_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict[str, object]:
    service.delete_job(db, workspace=workspace, user=current_user, job_id=job_id)
    return {"id": job_id, "deleted": True}


@router.get("/jobs/{job_id}/result", response_model=SpecCompareResultResponse)
def get_result(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> SpecCompareResultResponse:
    return service.get_result(db, workspace=workspace, user=current_user, job_id=job_id)


def _report_response(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
    fmt: str,
) -> Response:
    content, media_type, filename = service.get_report_document(
        db, workspace=workspace, user=user, job_id=job_id, fmt=fmt
    )
    # ASCII fallback must be a safe, header-legal token (no quotes, backslashes,
    # or control chars); non-ASCII/Korean names travel via the RFC 5987 filename*.
    ascii_name = re.sub(
        r"[^A-Za-z0-9._-]+", "_", filename.encode("ascii", "ignore").decode("ascii")
    ).strip("_")
    if not ascii_name:
        ascii_name = f"spec-compare-report.{fmt}"
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": disposition},
    )


@router.get(
    "/jobs/{job_id}/report.docx",
    response_class=Response,
    responses={
        200: {
            "description": "Successful Response",
            "content": {_DOCX_MEDIA_TYPE: {"schema": _BINARY_RESPONSE_SCHEMA}},
        }
    },
)
def download_report_docx(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    return _report_response(db, workspace=workspace, user=current_user, job_id=job_id, fmt="docx")


@router.get(
    "/jobs/{job_id}/report.pdf",
    response_class=Response,
    responses={
        200: {
            "description": "Successful Response",
            "content": {_PDF_MEDIA_TYPE: {"schema": _BINARY_RESPONSE_SCHEMA}},
        }
    },
)
def download_report_pdf(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    return _report_response(db, workspace=workspace, user=current_user, job_id=job_id, fmt="pdf")
