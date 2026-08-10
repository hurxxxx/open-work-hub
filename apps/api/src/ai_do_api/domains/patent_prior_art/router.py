from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException
from starlette.types import Message, Receive, Scope, Send

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.ai.gateway import AiGatewayPolicyViolation
from ai_do_api.domains.patent_prior_art import service
from ai_do_api.domains.patent_prior_art.app_catalog import PATENT_PRIOR_ART_WORKSPACE_APP
from ai_do_api.domains.patent_prior_art.schemas import (
    PatentPriorArtConfigResponse,
    PatentPriorArtDeleteResponse,
    PatentPriorArtFileParseResponse,
    PatentPriorArtJobCreateRequest,
    PatentPriorArtJobListResponse,
    PatentPriorArtJobOut,
    PatentPriorArtQueryPreviewRequest,
    PatentPriorArtQueryPreviewResponse,
    PatentPriorArtReportFormat,
    PatentPriorArtResultResponse,
)


require_patent_prior_art_app_enabled = require_workspace_app_enabled(
    PATENT_PRIOR_ART_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

_MAX_JSON_BODY_BYTES = 2 * 1024 * 1024
_MAX_MULTIPART_BODY_BYTES = (30 * 1024 * 1024) + (2 * 1024 * 1024)
_MAX_UPLOAD_BYTES = 30 * 1024 * 1024
_UPLOAD_CHUNK_BYTES = 1024 * 1024
_BODY_LIMIT_BY_ENDPOINT: dict[Callable[..., object], int] = {}


class _BodyLimitExceeded(MultiPartException):
    """Abort body parsing while preserving multipart temporary-file cleanup."""

    def __init__(self) -> None:
        super().__init__("request body exceeds the configured limit")


def _content_length_is_invalid_or_exceeds(value: str, limit: int) -> bool:
    if not value.isascii() or not value.isdigit():
        return True
    normalized = value.lstrip("0") or "0"
    limit_text = str(limit)
    return len(normalized) > len(limit_text) or (
        len(normalized) == len(limit_text) and normalized > limit_text
    )


class _BodySizeLimitRoute(APIRoute):
    """Reject unsafe body sizes before FastAPI parses JSON or multipart data."""

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.methods and scope["method"] not in self.methods:
            await super().handle(scope, receive, send)
            return

        limit = _BODY_LIMIT_BY_ENDPOINT.get(self.endpoint)
        if limit is None:
            await super().handle(scope, receive, send)
            return

        content_length = Headers(scope=scope).get("content-length")
        if content_length is not None and _content_length_is_invalid_or_exceeds(
            content_length, limit
        ):
            raise localized_http_exception(
                status_code=413,
                code="patent_prior_art.request_too_large",
            )

        received_bytes = 0
        body_limit_exceeded = False

        async def receive_with_limit() -> Message:
            nonlocal body_limit_exceeded, received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > limit:
                    body_limit_exceeded = True
                    raise _BodyLimitExceeded()
            return message

        async def send_unless_limited(message: Message) -> None:
            if not body_limit_exceeded:
                await send(message)

        try:
            await super().handle(scope, receive_with_limit, send_unless_limited)
        except (_BodyLimitExceeded, StarletteHTTPException):
            if not body_limit_exceeded:
                raise

        if body_limit_exceeded:
            raise localized_http_exception(
                status_code=413,
                code="patent_prior_art.request_too_large",
            )


router = APIRouter(
    prefix="/patent-prior-art",
    tags=["patent-prior-art"],
    dependencies=[Depends(require_patent_prior_art_app_enabled)],
    route_class=_BodySizeLimitRoute,
)


async def _read_upload(file: UploadFile) -> bytes:
    content = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > _MAX_UPLOAD_BYTES:
            raise localized_http_exception(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                code="patent_prior_art.request_too_large",
            )
    return bytes(content)


@router.get("/config", response_model=PatentPriorArtConfigResponse)
def get_config() -> PatentPriorArtConfigResponse:
    return service.config()


@router.post("/files/parse", response_model=PatentPriorArtFileParseResponse)
async def parse_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtFileParseResponse:
    try:
        content = await _read_upload(file)
        return await run_in_threadpool(
            service.parse_file,
            db,
            workspace=workspace,
            user=current_user,
            filename=file.filename or "",
            mime_type=file.content_type or "",
            content=content,
        )
    finally:
        await file.close()


@router.post("/query-preview", response_model=PatentPriorArtQueryPreviewResponse)
def preview_query(
    request: PatentPriorArtQueryPreviewRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtQueryPreviewResponse:
    try:
        return service.preview_query(
            db,
            workspace=workspace,
            user=current_user,
            request=request,
        )
    except AiGatewayPolicyViolation as error:
        raise localized_http_exception(
            status_code=(
                status.HTTP_403_FORBIDDEN
                if error.reason_code == "external_transfer_blocked"
                else status.HTTP_400_BAD_REQUEST
            ),
            code=(
                "ai.external_transfer_blocked"
                if error.reason_code == "external_transfer_blocked"
                else "ai.gateway_policy_violation"
            ),
            reason=error.reason_code,
        ) from error


@router.post(
    "/jobs",
    response_model=PatentPriorArtJobOut,
    status_code=status.HTTP_201_CREATED,
)
def create_job(
    request: PatentPriorArtJobCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtJobOut:
    return service.create_job(
        db,
        workspace=workspace,
        user=current_user,
        request=request,
    )


@router.get("/jobs", response_model=PatentPriorArtJobListResponse)
def list_jobs(
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtJobListResponse:
    return service.list_jobs(
        db,
        workspace=workspace,
        user=current_user,
        limit=limit,
    )


@router.get("/jobs/{job_id}", response_model=PatentPriorArtJobOut)
def get_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtJobOut:
    return service.get_job(db, workspace=workspace, user=current_user, job_id=job_id)


@router.post("/jobs/{job_id}/cancel", response_model=PatentPriorArtJobOut)
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtJobOut:
    return service.cancel_job(db, workspace=workspace, user=current_user, job_id=job_id)


@router.get("/jobs/{job_id}/result", response_model=PatentPriorArtResultResponse)
def get_result(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtResultResponse:
    return service.get_result(db, workspace=workspace, user=current_user, job_id=job_id)


@router.get(
    "/jobs/{job_id}/artifacts/{artifact_id}",
    response_class=Response,
    responses={
        200: {
            "description": "Patent prior-art result artifact.",
            "content": {
                "application/json": {},
                "text/markdown": {},
            },
        }
    },
)
def get_artifact(
    job_id: str,
    artifact_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    return service.get_artifact(
        db,
        workspace=workspace,
        user=current_user,
        job_id=job_id,
        artifact_id=artifact_id,
    )


@router.get(
    "/jobs/{job_id}/reports/{report_format}",
    response_class=Response,
    responses={
        200: {
            "description": "Rendered patent prior-art research report.",
            "content": {
                "text/html": {},
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
            },
        }
    },
)
def get_report(
    job_id: str,
    report_format: PatentPriorArtReportFormat,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    return service.get_report(
        db,
        workspace=workspace,
        user=current_user,
        job_id=job_id,
        report_format=report_format,
    )


@router.delete("/jobs/{job_id}", response_model=PatentPriorArtDeleteResponse)
def delete_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> PatentPriorArtDeleteResponse:
    return service.delete_job(db, workspace=workspace, user=current_user, job_id=job_id)


_BODY_LIMIT_BY_ENDPOINT.update(
    {
        parse_file: _MAX_MULTIPART_BODY_BYTES,
        preview_query: _MAX_JSON_BODY_BYTES,
        create_job: _MAX_JSON_BODY_BYTES,
    }
)
