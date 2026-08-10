from __future__ import annotations

from collections.abc import Callable
from datetime import date
from io import BytesIO
from typing import Literal, NoReturn, TypeVar

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import record_audit_log
from open_alm_api.domains.auth.dependencies import (
    WorkspaceAccessContext,
    require_workspace_membership,
)
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled

from . import service
from .app_catalog import MANAGEMENT_TASKS_WORKSPACE_APP
from .schemas import (
    HealthCheckupDeterminationListResponse,
    HealthCheckupPriorExamStatus,
    HealthCheckupPriorExamUploadResponse,
    HealthCheckupSettingsHistoryResponse,
    HealthCheckupSettingsResponse,
    HealthCheckupSettingsUpdateRequest,
    HealthCheckupSourceStatusResponse,
)
from .xlsx import MAX_UPLOAD_BYTES, XLSX_MEDIA_TYPE, UnsafeXlsxError, read_upload_limited


require_management_tasks_enabled = require_workspace_app_enabled(
    MANAGEMENT_TASKS_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)
require_management_tasks_member = require_workspace_membership()
DEFAULT_TARGET_YEAR = date.today().year
_MAX_MULTIPART_BODY_BYTES = MAX_UPLOAD_BYTES + (2 * 1024 * 1024)
_BODY_LIMIT_BY_ENDPOINT: dict[Callable[..., object], int] = {}
ServiceResult = TypeVar("ServiceResult")


class _BodySizeLimitRoute(APIRoute):
    """Reject unverifiable or oversized multipart bodies before parser buffering."""

    def get_route_handler(self) -> Callable[[Request], object]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            limit = _BODY_LIMIT_BY_ENDPOINT.get(self.endpoint)
            if limit is not None:
                content_length = request.headers.get("content-length")
                if (
                    not content_length
                    or not content_length.isdigit()
                    or int(content_length) > limit
                ):
                    raise localized_http_exception(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        code="management_tasks.health_checkup.request_too_large",
                    )
            return await original(request)

        return handler


router = APIRouter(
    prefix="/management-tasks/health-checkup",
    tags=["management-tasks-health-checkup"],
    dependencies=[
        Depends(require_management_tasks_enabled),
        Depends(require_management_tasks_member),
    ],
    route_class=_BodySizeLimitRoute,
)


def _source_unavailable(error: service.SourceUnavailableError) -> NoReturn:
    raise localized_http_exception(
        status_code=status.HTTP_409_CONFLICT,
        code="management_tasks.health_checkup.source_unavailable",
        reason=error.reason,
    )


def _feature_not_available() -> NoReturn:
    raise localized_http_exception(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="management_tasks.health_checkup.not_available",
    )


def _run_service(operation: Callable[[], ServiceResult]) -> ServiceResult:
    try:
        return operation()
    except service.FeatureNotAvailableError:
        _feature_not_available()


def _decision_not_found() -> NoReturn:
    raise localized_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="management_tasks.health_checkup.decision_not_found",
    )


def _xlsx_response(content: bytes, *, filename: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(content),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _upload_prior_exam_and_audit(
    db: Session,
    *,
    target_year: int,
    filename: str | None,
    content: bytes,
    actor_user_id: str,
    workspace_id: str,
    workspace_key: str,
) -> HealthCheckupPriorExamUploadResponse:
    result = service.upload_prior_exam(
        db,
        target_year=target_year,
        filename=filename,
        content=content,
        actor_user_id=actor_user_id,
    )
    record_audit_log(
        db,
        actor_user_id=actor_user_id,
        action="health_checkup.prior_exam.upload",
        entity_kind="health_checkup_prior_upload",
        entity_id=result.upload_id,
        summary="Uploaded prior-year health checkup evidence",
        payload={
            "workspace_id": workspace_id,
            "workspace_key": workspace_key,
            "target_year": result.target_year,
            "exam_year": result.exam_year,
            "total_row_count": result.total_rows,
            "matched_employee_count": result.matched_count,
            "unresolved_row_count": result.ambiguous_count,
        },
    )
    db.commit()
    return result


@router.get("/source/status", response_model=HealthCheckupSourceStatusResponse)
def get_source_status(
    db: Session = Depends(get_db_session),
) -> HealthCheckupSourceStatusResponse:
    return _run_service(lambda: service.get_source_status(db))


@router.get("/prior-exams/status", response_model=HealthCheckupPriorExamStatus)
def get_prior_exam_status(
    year: int = Query(default=DEFAULT_TARGET_YEAR, ge=2000, le=2100),
    db: Session = Depends(get_db_session),
) -> HealthCheckupPriorExamStatus:
    return _run_service(lambda: service.get_prior_exam_status(db, target_year=year))


@router.post(
    "/prior-exams",
    response_model=HealthCheckupPriorExamUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_prior_exam(
    year: int = Query(default=DEFAULT_TARGET_YEAR, ge=2000, le=2100),
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    context: WorkspaceAccessContext = Depends(require_management_tasks_member),
) -> HealthCheckupPriorExamUploadResponse:
    try:
        content = await read_upload_limited(file)
        return await run_in_threadpool(
            _upload_prior_exam_and_audit,
            db,
            target_year=year,
            filename=file.filename,
            content=content,
            actor_user_id=context.auth.user.id,
            workspace_id=context.workspace.id,
            workspace_key=context.workspace.key,
        )
    except UnsafeXlsxError as error:
        raise localized_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="management_tasks.health_checkup.invalid_workbook",
            reason=error.code,
        ) from error
    except service.SourceUnavailableError as error:
        _source_unavailable(error)
    except service.FeatureNotAvailableError:
        _feature_not_available()


@router.post(
    "/determinations/refresh",
    response_model=HealthCheckupDeterminationListResponse,
)
def refresh_determinations(
    year: int = Query(default=DEFAULT_TARGET_YEAR, ge=2000, le=2100),
    db: Session = Depends(get_db_session),
    context: WorkspaceAccessContext = Depends(require_management_tasks_member),
) -> HealthCheckupDeterminationListResponse:
    try:
        result = service.refresh_determinations(
            db,
            target_year=year,
            actor_user_id=context.auth.user.id,
        )
        record_audit_log(
            db,
            actor_user_id=context.auth.user.id,
            action="health_checkup.determination.refresh",
            entity_kind="health_checkup_decision_run",
            entity_id=result.run_id,
            summary="Refreshed health checkup determination",
            payload={
                "workspace_id": context.workspace.id,
                "workspace_key": context.workspace.key,
                "target_year": result.target_year,
                "publishable": result.publishable,
                "publish_blockers": result.publish_blockers,
                "employee_count": result.total,
                "target_count": result.target_count,
                "source_run_id": result.source.run_id,
                "source_erp_run_id": result.source.erp_run_id,
            },
        )
        db.commit()
        return result
    except service.SourceUnavailableError as error:
        _source_unavailable(error)
    except service.FeatureNotAvailableError:
        _feature_not_available()


@router.get(
    "/determinations",
    response_model=HealthCheckupDeterminationListResponse,
)
def list_determinations(
    year: int = Query(default=DEFAULT_TARGET_YEAR, ge=2000, le=2100),
    db: Session = Depends(get_db_session),
    context: WorkspaceAccessContext = Depends(require_management_tasks_member),
) -> HealthCheckupDeterminationListResponse:
    try:
        result = service.list_determinations(db, target_year=year)
        record_audit_log(
            db,
            actor_user_id=context.auth.user.id,
            action="health_checkup.determination.read",
            entity_kind="health_checkup_decision_run",
            entity_id=result.run_id,
            summary="Viewed health checkup determination",
            payload={
                "workspace_id": context.workspace.id,
                "workspace_key": context.workspace.key,
                "target_year": result.target_year,
                "employee_count": result.total,
                "target_count": result.target_count,
            },
        )
        db.commit()
        return result
    except (service.DecisionRunNotFoundError, service.DecisionRunStaleError):
        _decision_not_found()
    except service.SourceUnavailableError as error:
        _source_unavailable(error)
    except service.FeatureNotAvailableError:
        _feature_not_available()


@router.get("/settings", response_model=HealthCheckupSettingsResponse)
def get_settings(
    db: Session = Depends(get_db_session),
) -> HealthCheckupSettingsResponse:
    return _run_service(lambda: service.get_settings(db))


@router.put("/settings", response_model=HealthCheckupSettingsResponse)
def update_settings(
    payload: HealthCheckupSettingsUpdateRequest,
    db: Session = Depends(get_db_session),
    context: WorkspaceAccessContext = Depends(require_management_tasks_member),
) -> HealthCheckupSettingsResponse:
    try:
        before = service.get_settings(db)
        result = service.update_settings(
            db,
            payload=payload,
            actor_user_id=context.auth.user.id,
        )
        record_audit_log(
            db,
            actor_user_id=context.auth.user.id,
            action="health_checkup.settings.update",
            entity_kind="health_checkup_settings",
            entity_id="company",
            summary="Updated health checkup settings",
            payload={
                "workspace_id": context.workspace.id,
                "workspace_key": context.workspace.key,
                "requested_fields": sorted(payload.model_fields_set),
                "changed_fields": sorted(
                    field_name
                    for field_name in payload.model_fields_set
                    if getattr(before, field_name) != getattr(result, field_name)
                ),
            },
        )
        db.commit()
        return result
    except ValueError as error:
        raise localized_http_exception(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="management_tasks.health_checkup.invalid_settings",
        ) from error
    except service.FeatureNotAvailableError:
        _feature_not_available()


@router.get(
    "/settings/history",
    response_model=HealthCheckupSettingsHistoryResponse,
)
def list_settings_history(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db_session),
) -> HealthCheckupSettingsHistoryResponse:
    return _run_service(lambda: service.list_settings_history(db, limit=limit))


def _export(
    db: Session,
    *,
    year: int,
    export_kind: Literal["employees", "targets", "roster"],
    filename: str,
    actor_user_id: str,
    workspace_id: str,
    workspace_key: str,
) -> StreamingResponse:
    try:
        exported = service.export_determinations(
            db,
            target_year=year,
            export_kind=export_kind,
        )
    except service.DecisionRunNotFoundError:
        _decision_not_found()
    except service.SourceUnavailableError as error:
        _source_unavailable(error)
    except service.DecisionNotPublishableError as error:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="management_tasks.health_checkup.not_publishable",
            blockers=",".join(error.blockers),
        ) from error
    except service.FeatureNotAvailableError:
        _feature_not_available()
    record_audit_log(
        db,
        actor_user_id=actor_user_id,
        action=f"health_checkup.export.{export_kind}",
        entity_kind="health_checkup_decision_run",
        entity_id=exported.run_id,
        summary=f"Exported health checkup {export_kind}",
        payload={
            "workspace_id": workspace_id,
            "workspace_key": workspace_key,
            "target_year": year,
            "export_kind": export_kind,
            "exported_row_count": exported.exported_count,
        },
    )
    db.commit()
    return _xlsx_response(exported.content, filename=filename)


@router.get(
    "/export/employees.xlsx",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "description": "Generated health checkup employee workbook",
        }
    },
)
def export_employees(
    year: int = Query(default=DEFAULT_TARGET_YEAR, ge=2000, le=2100),
    db: Session = Depends(get_db_session),
    context: WorkspaceAccessContext = Depends(require_management_tasks_member),
) -> StreamingResponse:
    return _export(
        db,
        year=year,
        export_kind="employees",
        filename=f"health-checkup-employees-{year}.xlsx",
        actor_user_id=context.auth.user.id,
        workspace_id=context.workspace.id,
        workspace_key=context.workspace.key,
    )


@router.get(
    "/export/targets.xlsx",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "description": "Generated health checkup target workbook",
        }
    },
)
def export_targets(
    year: int = Query(default=DEFAULT_TARGET_YEAR, ge=2000, le=2100),
    db: Session = Depends(get_db_session),
    context: WorkspaceAccessContext = Depends(require_management_tasks_member),
) -> StreamingResponse:
    return _export(
        db,
        year=year,
        export_kind="targets",
        filename=f"health-checkup-targets-{year}.xlsx",
        actor_user_id=context.auth.user.id,
        workspace_id=context.workspace.id,
        workspace_key=context.workspace.key,
    )


@router.get(
    "/export/roster.xlsx",
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "content": {XLSX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "description": "Generated health checkup roster workbook",
        }
    },
)
def export_roster(
    year: int = Query(default=DEFAULT_TARGET_YEAR, ge=2000, le=2100),
    db: Session = Depends(get_db_session),
    context: WorkspaceAccessContext = Depends(require_management_tasks_member),
) -> StreamingResponse:
    return _export(
        db,
        year=year,
        export_kind="roster",
        filename=f"health-checkup-roster-{year}.xlsx",
        actor_user_id=context.auth.user.id,
        workspace_id=context.workspace.id,
        workspace_key=context.workspace.key,
    )


_BODY_LIMIT_BY_ENDPOINT[upload_prior_exam] = _MAX_MULTIPART_BODY_BYTES
