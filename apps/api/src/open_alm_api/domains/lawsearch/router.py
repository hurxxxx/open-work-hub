from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.dependencies import (
    require_any_system_role,
    require_current_user,
)
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.lawsearch import schemas as S
from open_alm_api.domains.lawsearch import service
from open_alm_api.domains.lawsearch.app_catalog import LAW_SEARCH_WORKSPACE_APP


require_law_search_app_enabled = require_workspace_app_enabled(
    LAW_SEARCH_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/lawsearch",
    tags=["lawsearch"],
    dependencies=[Depends(require_law_search_app_enabled)],
)

require_admin = require_any_system_role("platform_admin")


# ─── Master/card endpoints ─────────────────────────────────────────


@router.get("/parts", response_model=S.PartsResponse)
def parts(_user=Depends(require_current_user), db: Session = Depends(get_db_session)):
    return service.list_parts(db)


@router.get("/regions", response_model=S.RegionsResponse)
def regions(_user=Depends(require_current_user), db: Session = Depends(get_db_session)):
    return service.list_regions(db)


@router.get("/types", response_model=S.TypesResponse)
def types(_user=Depends(require_current_user), db: Session = Depends(get_db_session)):
    return service.list_types(db)


# ─── By-X / search ─────────────────────────────────────────────────


@router.get("/by-part/{part_id}", response_model=S.ByPartResponse)
def items_by_part(
    part_id: str,
    _user=Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    out = service.by_part(db, part_id)
    if not out:
        raise localized_http_exception(status_code=404, code="lawsearch.part_not_found")
    return out


@router.get("/by-region/{region_id}", response_model=S.ByRegionResponse)
def items_by_region(
    region_id: str,
    _user=Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    out = service.by_region(db, region_id)
    if not out:
        raise localized_http_exception(status_code=404, code="lawsearch.region_not_found")
    return out


@router.get("/by-type/{type_id}", response_model=S.ByTypeResponse)
def items_by_type(
    type_id: str,
    _user=Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    out = service.by_type(db, type_id)
    if not out:
        raise localized_http_exception(status_code=404, code="lawsearch.type_not_found")
    return out


@router.get("/search", response_model=S.SearchResponse)
def items_search(
    q: str = Query(default=""),
    _user=Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    return service.search(db, q)


# ─── Single item / CRUD ───────────────────────────────────────────


@router.get("/item/{item_id}", response_model=S.LawItemRaw)
def item_get(
    item_id: str,
    _user=Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    raw = service.get_item_raw(db, item_id)
    if not raw:
        raise localized_http_exception(status_code=404, code="lawsearch.item_not_found")
    return raw


@router.post(
    "/item",
    response_model=S.LawItemRaw,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def item_create(
    payload: S.LawItemWriteIn,
    db: Session = Depends(get_db_session),
):
    errors = service.validate_payload(db, payload)
    if errors:
        raise localized_http_exception(
            status_code=400,
            code="lawsearch.validation_failed",
            details=errors,
        )
    raw = service.create_item(db, payload)
    db.commit()
    return raw


@router.put(
    "/item/{item_id}",
    response_model=S.LawItemRaw,
    dependencies=[Depends(require_admin)],
)
def item_update(
    item_id: str,
    payload: S.LawItemWriteIn,
    db: Session = Depends(get_db_session),
):
    errors = service.validate_payload(db, payload)
    if errors:
        raise localized_http_exception(
            status_code=400,
            code="lawsearch.validation_failed",
            details=errors,
        )
    raw = service.update_item(db, item_id, payload)
    if not raw:
        raise localized_http_exception(status_code=404, code="lawsearch.item_not_found")
    db.commit()
    return raw


@router.delete(
    "/item/{item_id}",
    dependencies=[Depends(require_admin)],
)
def item_delete(
    item_id: str,
    db: Session = Depends(get_db_session),
):
    if not service.delete_item(db, item_id):
        raise localized_http_exception(status_code=404, code="lawsearch.item_not_found")
    db.commit()
    return {"status": "ok", "deleted": item_id}


# ─── Competitors ──────────────────────────────────────────────────


@router.get("/competitors", response_model=S.CompetitorsResponse)
def competitors(
    _user=Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    return service.list_competitors(db)


@router.get("/competitors/{company_id}", response_model=S.CompetitorSpecsResponse)
def competitor_specs(
    company_id: str,
    _user=Depends(require_current_user),
    db: Session = Depends(get_db_session),
):
    out = service.competitor_specs(db, company_id)
    if not out:
        raise localized_http_exception(status_code=404, code="lawsearch.competitor_not_found")
    return out
