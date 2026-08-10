from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.access import record_audit_log
from open_alm_api.domains.auth.platform_api_keys import (
    PlatformApiPrincipal,
    require_platform_api_scope,
)
from open_alm_api.domains.hr.integration_schemas import (
    HrIntegrationBasis,
    HrIntegrationEmployeesResponse,
    HrIntegrationGroupsResponse,
    HrIntegrationStatusResponse,
    HrIntegrationWorkforceCategoriesResponse,
)
from open_alm_api.domains.hr.integration_service import (
    HrIntegrationProjectionError,
    HrIntegrationSnapshotChanged,
    get_hr_integration_status,
    list_hr_integration_employees,
    list_hr_integration_groups,
    list_hr_integration_workforce_categories,
)
from open_alm_api.openapi_contract import ErrorResponse, PROTECTED_ERROR_RESPONSES


router = APIRouter(prefix="/integrations/hr", tags=["hr-integrations"])
require_hr_integration_read = require_platform_api_scope("hr:read")
HR_INTEGRATION_ERROR_RESPONSES = {
    **PROTECTED_ERROR_RESPONSES,
    409: {"model": ErrorResponse, "description": "HR snapshot changed."},
    503: {"model": ErrorResponse, "description": "HR snapshot unavailable."},
}


def _set_no_store_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Pragma"] = "no-cache"


def _audit_hr_integration_read(
    db: Session,
    *,
    principal: PlatformApiPrincipal,
    action: str,
    basis: HrIntegrationBasis,
    snapshot_id: str | None,
    page: int | None,
    page_size: int | None,
    result_count: int,
    outcome: Literal["succeeded", "failed"],
    error_code: str | None,
    requested_snapshot_id_provided: bool,
) -> None:
    record_audit_log(
        db,
        action=action,
        entity_kind="hr_integration",
        entity_id=(snapshot_id if snapshot_id is not None and len(snapshot_id) <= 36 else None),
        summary=(
            "Read HR integration projection"
            if outcome == "succeeded"
            else "HR integration projection read failed"
        ),
        payload={
            "api_key_id": principal.key_id,
            "basis": basis,
            "snapshot_id": snapshot_id,
            "page": page,
            "page_size": page_size,
            "result_count": result_count,
            "outcome": outcome,
            "error_code": error_code,
            "requested_snapshot_id_provided": requested_snapshot_id_provided,
        },
    )
    db.commit()


def _projection_error_code(error: HrIntegrationProjectionError) -> str:
    if isinstance(error, HrIntegrationSnapshotChanged):
        return "hr.integration_snapshot_changed"
    return "hr.integration_snapshot_unavailable"


def _raise_projection_error(error: HrIntegrationProjectionError) -> None:
    headers = {
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
    }
    if isinstance(error, HrIntegrationSnapshotChanged):
        raise localized_http_exception(
            status_code=409,
            code="hr.integration_snapshot_changed",
            headers=headers,
            basis=error.basis,
        ) from error
    raise localized_http_exception(
        status_code=503,
        code="hr.integration_snapshot_unavailable",
        headers=headers,
        basis=error.basis,
    ) from error


@router.get(
    "/employees",
    response_model=HrIntegrationEmployeesResponse,
    responses=HR_INTEGRATION_ERROR_RESPONSES,
)
def list_employees(
    http_response: Response,
    basis: HrIntegrationBasis = Query(),
    snapshot_id: str | None = Query(default=None, min_length=1, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    principal: PlatformApiPrincipal = Depends(require_hr_integration_read),
    db: Session = Depends(get_db_session),
) -> HrIntegrationEmployeesResponse:
    _set_no_store_headers(http_response)
    try:
        response = list_hr_integration_employees(
            db,
            basis=basis,
            snapshot_id=snapshot_id,
            page=page,
            page_size=page_size,
        )
    except HrIntegrationProjectionError as error:
        _audit_hr_integration_read(
            db,
            principal=principal,
            action="hr.integration.employees.read",
            basis=basis,
            snapshot_id=None,
            page=page,
            page_size=page_size,
            result_count=0,
            outcome="failed",
            error_code=_projection_error_code(error),
            requested_snapshot_id_provided=snapshot_id is not None,
        )
        _raise_projection_error(error)
    _audit_hr_integration_read(
        db,
        principal=principal,
        action="hr.integration.employees.read",
        basis=basis,
        snapshot_id=response.snapshot_id,
        page=page,
        page_size=page_size,
        result_count=len(response.items),
        outcome="succeeded",
        error_code=None,
        requested_snapshot_id_provided=snapshot_id is not None,
    )
    return response


@router.get(
    "/groups",
    response_model=HrIntegrationGroupsResponse,
    responses=HR_INTEGRATION_ERROR_RESPONSES,
)
def list_groups(
    http_response: Response,
    basis: HrIntegrationBasis = Query(),
    snapshot_id: str | None = Query(default=None, min_length=1, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    principal: PlatformApiPrincipal = Depends(require_hr_integration_read),
    db: Session = Depends(get_db_session),
) -> HrIntegrationGroupsResponse:
    _set_no_store_headers(http_response)
    try:
        response = list_hr_integration_groups(
            db,
            basis=basis,
            snapshot_id=snapshot_id,
            page=page,
            page_size=page_size,
        )
    except HrIntegrationProjectionError as error:
        _audit_hr_integration_read(
            db,
            principal=principal,
            action="hr.integration.groups.read",
            basis=basis,
            snapshot_id=None,
            page=page,
            page_size=page_size,
            result_count=0,
            outcome="failed",
            error_code=_projection_error_code(error),
            requested_snapshot_id_provided=snapshot_id is not None,
        )
        _raise_projection_error(error)
    _audit_hr_integration_read(
        db,
        principal=principal,
        action="hr.integration.groups.read",
        basis=basis,
        snapshot_id=response.snapshot_id,
        page=page,
        page_size=page_size,
        result_count=len(response.items),
        outcome="succeeded",
        error_code=None,
        requested_snapshot_id_provided=snapshot_id is not None,
    )
    return response


@router.get(
    "/status",
    response_model=HrIntegrationStatusResponse,
    responses=PROTECTED_ERROR_RESPONSES,
)
def get_status(
    http_response: Response,
    basis: HrIntegrationBasis = Query(),
    principal: PlatformApiPrincipal = Depends(require_hr_integration_read),
    db: Session = Depends(get_db_session),
) -> HrIntegrationStatusResponse:
    _set_no_store_headers(http_response)
    response = get_hr_integration_status(db, basis=basis)
    _audit_hr_integration_read(
        db,
        principal=principal,
        action="hr.integration.status.read",
        basis=basis,
        snapshot_id=response.snapshot_id,
        page=None,
        page_size=None,
        result_count=response.employee_count + response.group_count,
        outcome="succeeded",
        error_code=None,
        requested_snapshot_id_provided=False,
    )
    return response


@router.get(
    "/workforce-categories",
    response_model=HrIntegrationWorkforceCategoriesResponse,
    responses=PROTECTED_ERROR_RESPONSES,
)
def list_workforce_categories(
    http_response: Response,
    include_inactive: bool = Query(default=False),
    principal: PlatformApiPrincipal = Depends(require_hr_integration_read),
    db: Session = Depends(get_db_session),
) -> HrIntegrationWorkforceCategoriesResponse:
    _set_no_store_headers(http_response)
    response = list_hr_integration_workforce_categories(
        db,
        include_inactive=include_inactive,
    )
    _audit_hr_integration_read(
        db,
        principal=principal,
        action="hr.integration.workforce_categories.read",
        basis="integrated",
        snapshot_id=None,
        page=None,
        page_size=None,
        result_count=len(response.items),
        outcome="succeeded",
        error_code=None,
        requested_snapshot_id_provided=False,
    )
    return response
