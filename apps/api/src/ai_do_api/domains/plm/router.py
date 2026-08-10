from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.access import resolve_workspace_role, workspace_role_allows
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.plm.app_catalog import PLM_WORKSPACE_APP
from ai_do_api.domains.plm.query_policy import PlmQueryPolicyError, build_plm_query_preview
from ai_do_api.domains.plm.raw_oracle import (
    PLM_MAX_LIMIT,
    PlmRawOracleError,
    PlmRawRowsResult,
    get_plm_raw_client,
)
from ai_do_api.domains.source_access import SourceAclPolicy


class SearchPlmRequest(BaseModel):
    query: str = Field(..., min_length=1)
    preview_only: bool = True


class PlmRow(BaseModel):
    item_code: str
    status: str
    owner: str


class SearchPlmResponse(BaseModel):
    scenario_id: str = "plm-query"
    sql_preview: str
    result_summary: str
    result_table: list[PlmRow]
    warnings: list[str]


class PlmRawColumnResponse(BaseModel):
    name: str
    type: str = ""


class PlmRawTableResponse(BaseModel):
    owner: str
    name: str
    object_type: str


class PlmRawTableListResponse(BaseModel):
    items: list[PlmRawTableResponse]


class PlmRawTableRowsRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=128)
    limit: int = Field(default=100, ge=1, le=PLM_MAX_LIMIT)
    offset: int = Field(default=0, ge=0)


class PlmRawSqlRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20_000)
    limit: int = Field(default=100, ge=1, le=PLM_MAX_LIMIT)
    offset: int = Field(default=0, ge=0)


class PlmRawRowsResponse(BaseModel):
    columns: list[PlmRawColumnResponse]
    rows: list[list[str | None]]
    has_more: bool
    limit: int
    offset: int
    sql_preview: str


require_plm_app_enabled = require_workspace_app_enabled(
    PLM_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    tags=["plm"],
    dependencies=[Depends(require_plm_app_enabled)],
)


def _raise_plm_raw_error(exc: PlmRawOracleError) -> None:
    raise localized_http_exception(
        status_code=exc.status_code,
        code=exc.code,
        **exc.params,
    ) from exc


def _ensure_plm_raw_admin(
    db: Session,
    *,
    current_user: User,
    current_workspace: Workspace,
) -> None:
    role = resolve_workspace_role(db, current_user, current_workspace.id)
    if workspace_role_allows(role, "admin"):
        return
    raise localized_http_exception(
        status_code=403,
        code="plm.raw_admin_required",
    )


def _serialize_raw_rows(result: PlmRawRowsResult) -> PlmRawRowsResponse:
    return PlmRawRowsResponse(
        columns=[
            PlmRawColumnResponse(name=column.name, type=column.type) for column in result.columns
        ],
        rows=[list(row) for row in result.rows],
        has_more=result.has_more,
        limit=result.limit,
        offset=result.offset,
        sql_preview=result.sql_preview,
    )


@router.post("/search/plm", response_model=SearchPlmResponse)
def search_plm(
    payload: SearchPlmRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> SearchPlmResponse:
    policy = SourceAclPolicy.for_workspace(db, workspace=current_workspace, user=current_user)
    try:
        preview = build_plm_query_preview(policy)
    except PlmQueryPolicyError as exc:
        raise localized_http_exception(
            status_code=exc.status_code,
            code=exc.code,
            **exc.params,
        ) from exc

    warnings = ["preview_only route", *preview.warnings]
    if not payload.preview_only:
        warnings.append("execution disabled; returning preview only")
    return SearchPlmResponse(
        sql_preview=preview.sql,
        result_summary=f"Scaffold preview for '{payload.query}'. Replace with template match + validator.",
        result_table=[
            PlmRow(item_code="ECO-991", status="Delayed", owner="Kim"),
            PlmRow(item_code="BOM-214", status="Open", owner="Lee"),
        ],
        warnings=warnings,
    )


@router.get("/plm/raw/tables", response_model=PlmRawTableListResponse)
def list_plm_raw_tables(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PlmRawTableListResponse:
    _ensure_plm_raw_admin(db, current_user=current_user, current_workspace=current_workspace)
    try:
        tables = get_plm_raw_client().list_tables()
    except PlmRawOracleError as exc:
        _raise_plm_raw_error(exc)
    return PlmRawTableListResponse(
        items=[
            PlmRawTableResponse(
                owner=table.owner,
                name=table.name,
                object_type=table.object_type,
            )
            for table in tables
        ],
    )


@router.post("/plm/raw/table/rows", response_model=PlmRawRowsResponse)
def read_plm_raw_table_rows(
    payload: PlmRawTableRowsRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PlmRawRowsResponse:
    _ensure_plm_raw_admin(db, current_user=current_user, current_workspace=current_workspace)
    try:
        result = get_plm_raw_client().fetch_table_rows(
            owner=payload.owner,
            name=payload.name,
            limit=payload.limit,
            offset=payload.offset,
        )
    except PlmRawOracleError as exc:
        _raise_plm_raw_error(exc)
    return _serialize_raw_rows(result)


@router.post("/plm/raw/query", response_model=PlmRawRowsResponse)
def run_plm_raw_query(
    payload: PlmRawSqlRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> PlmRawRowsResponse:
    _ensure_plm_raw_admin(db, current_user=current_user, current_workspace=current_workspace)
    try:
        result = get_plm_raw_client().execute_user_query(
            sql=payload.sql,
            limit=payload.limit,
            offset=payload.offset,
        )
    except PlmRawOracleError as exc:
        _raise_plm_raw_error(exc)
    return _serialize_raw_rows(result)
