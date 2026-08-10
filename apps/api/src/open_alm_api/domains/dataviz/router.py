from __future__ import annotations

import json
import os
import tempfile
import urllib.parse
from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
    require_workspace_membership,
)
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.dataviz import service
from open_alm_api.domains.dataviz.app_catalog import DATA_VIZ_WORKSPACE_APP
from open_alm_api.domains.dataviz.compressor_perf import (
    CATEGORY_ELECTRIC,
    CATEGORY_VARIABLE,
    average_by_group,
    parse_perf_source,
    rows_to_dicts,
)
from open_alm_api.domains.dataviz import comp_reliability as rel
from open_alm_api.domains.dataviz.core_measurement import ModelGroup, load_groups


def _safe_json(obj: dict, status_code: int = 200) -> Response:
    """NaN/Infinity → null 로 정리한 뒤 JSON 응답 (레거시 _safe_json 대응)."""
    return Response(
        json.dumps(rel.clean_nan(obj), ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
    )


require_dataviz_app_enabled = require_workspace_app_enabled(
    DATA_VIZ_WORKSPACE_APP.app_id,
    error_code="dataviz.app_disabled",
)

router = APIRouter(
    prefix="/dataviz",
    tags=["dataviz"],
    dependencies=[Depends(require_dataviz_app_enabled)],
)
_MAX_UPLOAD_BYTES = 80 * 1024 * 1024
_VALID_CATEGORIES = {CATEGORY_VARIABLE, CATEGORY_ELECTRIC}
_require_ws_admin = require_workspace_membership("admin")


class SpecOut(BaseModel):
    raw: str
    nominal: float | None = None
    lsl: float | None = None
    usl: float | None = None


class ItemOut(BaseModel):
    item: str
    spec: SpecOut
    count: int


class GroupOut(BaseModel):
    id: str
    file: str
    sheet: str
    model: str
    items: list[ItemOut]


class PointOut(BaseModel):
    index: int
    value: float
    date: str | None = None


class SeriesOut(BaseModel):
    id: str
    model: str
    sheet: str
    item: str
    spec: SpecOut
    points: list[PointOut]


class PerfParseResponse(BaseModel):
    category: str
    file_count: int
    row_count: int
    rows: list[dict]
    averages: list[dict]


class ResetRequest(BaseModel):
    category: str | None = None


class UpdateRowRequest(BaseModel):
    values: dict


class SaveToleranceRequest(BaseModel):
    category: str
    refrigerant: str
    capacity: str
    car_model: str = ""
    ref_values: dict


class DeleteToleranceRequest(BaseModel):
    category: str
    refrigerant: str
    capacity: str = ""
    car_model: str


class SaveProfileRequest(BaseModel):
    category: str
    refrigerant: str
    capacity: str
    profile: str = "BASE"
    tol_data: dict
    cars: list[str] = []


class SetCarModelRequest(BaseModel):
    source_file: str
    car_model: str


class CarModelRequest(BaseModel):
    code: str
    description: str = ""


async def _read_upload(file: UploadFile) -> bytes:
    data = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > _MAX_UPLOAD_BYTES:
            raise localized_http_exception(status_code=413, code="dataviz.upload_too_large")
    return bytes(data)


async def _stream_upload_to_temp(file: UploadFile) -> str:
    """업로드를 디스크 temp 파일로 청크 스트리밍(전체를 메모리에 안 올림). 경로 반환.

    파일당 _MAX_UPLOAD_BYTES 초과 시 temp 를 지우고 413. 호출자가 반환 경로를 정리한다.
    """
    suffix = os.path.splitext(file.filename or "")[1]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    total = 0
    try:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_UPLOAD_BYTES:
                raise localized_http_exception(status_code=413, code="dataviz.upload_too_large")
            tmp.write(chunk)
    except BaseException:
        tmp.close()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise
    tmp.close()
    return tmp.name


def _validate_category(category: str) -> str:
    if category not in _VALID_CATEGORIES:
        raise localized_http_exception(status_code=400, code="dataviz.invalid_category")
    return category


@router.get("/core-measurement/groups", response_model=list[GroupOut])
def list_groups() -> list[GroupOut]:
    out: list[GroupOut] = []
    for group in load_groups():
        out.append(
            GroupOut(
                id=group.id,
                file=group.file,
                sheet=group.sheet,
                model=group.model,
                items=[
                    ItemOut(
                        item=item.item,
                        spec=SpecOut(
                            raw=item.spec.raw,
                            nominal=item.spec.nominal,
                            lsl=item.spec.lsl,
                            usl=item.spec.usl,
                        ),
                        count=len(item.points),
                    )
                    for item in group.items
                ],
            )
        )
    return out


@router.get("/core-measurement/series", response_model=SeriesOut)
def get_series(
    group_id: str = Query(..., description="ModelGroup id (file::sheet::model)"),
    item: str = Query(..., description="Inspection item name"),
) -> SeriesOut:
    for group in load_groups():
        if group.id != group_id:
            continue
        spec = _spec_out(group, item)
        if spec is None:
            break
        for measurement in group.items:
            if measurement.item != item:
                continue
            return SeriesOut(
                id=group.id,
                model=group.model,
                sheet=group.sheet,
                item=measurement.item,
                spec=spec,
                points=[
                    PointOut(index=point.index, value=point.value, date=point.date)
                    for point in measurement.points
                ],
            )
    raise localized_http_exception(status_code=404, code="dataviz.core_series_not_found")


def _spec_out(group: ModelGroup, item_name: str) -> SpecOut | None:
    for item in group.items:
        if item.item == item_name:
            spec = item.spec
            return SpecOut(raw=spec.raw, nominal=spec.nominal, lsl=spec.lsl, usl=spec.usl)
    return None


@router.post("/compressor-perf/parse", response_model=PerfParseResponse)
async def parse_compressor_perf(
    files: list[UploadFile] = File(...),
    category: str = Form(CATEGORY_VARIABLE),
) -> PerfParseResponse:
    _validate_category(category)
    all_rows = []
    parsed_files = 0
    for upload in files:
        data = await _read_upload(upload)
        try:
            rows = parse_perf_source(data, category, upload.filename or "")
        except Exception as exc:  # noqa: BLE001
            raise localized_http_exception(
                status_code=422,
                code="dataviz.parse_failed",
                filename=upload.filename or "",
                error=str(exc),
            ) from exc
        if rows:
            all_rows.extend(rows)
            parsed_files += 1
    return PerfParseResponse(
        category=category,
        file_count=parsed_files,
        row_count=len(all_rows),
        rows=rows_to_dicts(all_rows),
        averages=average_by_group(all_rows),
    )


@router.post("/compressor-perf/upload-master")
async def upload_master(
    file: UploadFile = File(...),
    category: str = Form(CATEGORY_VARIABLE),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    content = await _read_upload(file)
    return service.import_master_workbook(
        db,
        workspace_id=workspace.id,
        owner_id=current_user.id,
        category=category,
        filename=file.filename or "",
        content=content,
    )


@router.post("/compressor-perf/upload-sources")
async def upload_sources(
    files: list[UploadFile] = File(...),
    category: str = Form(...),
    refrigerant: str = Form(...),
    capacity: str = Form(...),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    uploads = [(file.filename or "", await _read_upload(file)) for file in files]
    return service.upload_source_workbooks(
        db,
        workspace_id=workspace.id,
        owner_id=current_user.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
        files=uploads,
    )


@router.get("/compressor-perf/data")
def get_perf_data(
    category: str,
    refrigerant: str,
    capacity: str,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    return service.list_perf_data(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
    )


@router.get("/compressor-perf/analysis")
def get_analysis(
    category: str,
    refrigerant: str,
    capacity: str,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    return service.analyze_perf_data(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
    )


@router.put("/compressor-perf/data/{row_id}")
def update_row(
    row_id: str,
    payload: UpdateRowRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    try:
        result = service.update_perf_row(
            db,
            workspace_id=workspace.id,
            row_id=row_id,
            values=payload.values,
        )
    except KeyError as exc:
        raise localized_http_exception(status_code=404, code="dataviz.row_not_found") from exc
    if "error" in result:
        raise localized_http_exception(status_code=400, code="dataviz.no_valid_fields")
    return result


@router.delete("/compressor-perf/data/{row_id}")
def delete_row(
    row_id: str,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    try:
        return service.delete_perf_row(db, workspace_id=workspace.id, row_id=row_id)
    except KeyError as exc:
        raise localized_http_exception(status_code=404, code="dataviz.row_not_found") from exc


@router.post("/compressor-perf/reset")
def reset_data(
    payload: ResetRequest,
    _: object = Depends(_require_ws_admin),
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    category = payload.category or None
    if category:
        _validate_category(category)
    return service.reset_perf_data(db, workspace_id=workspace.id, category=category)


@router.get("/compressor-perf/car-models")
def get_car_models(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    return service.list_car_models(db, workspace_id=workspace.id)


@router.post("/compressor-perf/car-models")
def add_car_model(
    payload: CarModelRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    if not payload.code.strip():
        raise localized_http_exception(status_code=400, code="dataviz.car_model_code_required")
    result = service.add_car_model(
        db,
        workspace_id=workspace.id,
        code=payload.code,
        description=payload.description,
    )
    if "error" in result:
        raise localized_http_exception(status_code=409, code="dataviz.car_model_duplicate")
    return result


@router.delete("/compressor-perf/car-models/{model_id}")
def delete_car_model(
    model_id: str,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    return service.delete_car_model(db, workspace_id=workspace.id, model_id=model_id)


@router.get("/compressor-perf/tolerance")
def get_tolerance(
    category: str,
    refrigerant: str,
    capacity: str,
    car_model: str = "",
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    return service.get_tolerance(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
        car_model=car_model,
    )


@router.get("/compressor-perf/tolerance/all")
def get_tolerance_all(
    category: str,
    refrigerant: str,
    capacity: str = "",
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    return service.get_tolerance_all(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
    )


@router.post("/compressor-perf/tolerance")
def save_tolerance(
    payload: SaveToleranceRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(payload.category)
    return service.save_tolerance(
        db,
        workspace_id=workspace.id,
        category=payload.category,
        refrigerant=payload.refrigerant,
        capacity=payload.capacity,
        car_model=payload.car_model,
        ref_values=payload.ref_values,
    )


@router.post("/compressor-perf/tolerance/upload")
async def upload_tolerance(
    file: UploadFile = File(...),
    category: str = Form(...),
    refrigerant: str = Form(...),
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    return service.upload_tolerance_file(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        filename=file.filename or "",
        content=await _read_upload(file),
    )


@router.post("/compressor-perf/tolerance/delete")
def delete_tolerance(
    payload: DeleteToleranceRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(payload.category)
    return service.delete_tolerance(
        db,
        workspace_id=workspace.id,
        category=payload.category,
        refrigerant=payload.refrigerant,
        capacity=payload.capacity,
        car_model=payload.car_model,
    )


@router.get("/compressor-perf/tol-profile")
def get_tolerance_profile(
    category: str,
    refrigerant: str,
    capacity: str,
    profile: str = "BASE",
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    return service.get_tolerance_profile(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
        profile_name=profile,
    )


@router.get("/compressor-perf/tol-profile/all")
def get_tolerance_profiles_all(
    category: str,
    refrigerant: str,
    capacity: str,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(category)
    return service.get_all_tolerance_profiles(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
    )


@router.post("/compressor-perf/tol-profile")
def save_tolerance_profile(
    payload: SaveProfileRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    _validate_category(payload.category)
    return service.save_tolerance_profile(
        db,
        workspace_id=workspace.id,
        category=payload.category,
        refrigerant=payload.refrigerant,
        capacity=payload.capacity,
        profile_name=payload.profile,
        tol_data=payload.tol_data,
        cars=payload.cars,
    )


@router.post("/compressor-perf/set-car-model")
def set_car_model(
    payload: SetCarModelRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> dict:
    if not payload.source_file:
        raise localized_http_exception(status_code=400, code="dataviz.source_file_required")
    return service.set_car_model_for_source(
        db,
        workspace_id=workspace.id,
        source_file=payload.source_file,
        car_model=payload.car_model,
    )


@router.get("/compressor-perf/download-data")
def download_data(
    category: str,
    refrigerant: str = "",
    capacity: str = "",
    all_refrigerant: bool = False,
    no_warning_color: bool = False,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    _validate_category(category)
    content = service.build_result_workbook(
        db,
        workspace_id=workspace.id,
        category=category,
        refrigerant=refrigerant,
        capacity=capacity,
        all_refrigerant=all_refrigerant,
        no_warning_color=no_warning_color,
    )
    today = date.today().strftime("%Y%m%d")
    filename = urllib.parse.quote(f"{today}_{category} 마스터 파일.xlsx")
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# ─────────────────────────────────────────────────────────────
#  컴프 신뢰성 (복합내구벤치 + 간이벤치) — 레거시 durability_* 포팅
#  세션 대신 (type, machine, test_item)로 결정되는 pkl 경로로 상태 전달.
# ─────────────────────────────────────────────────────────────


@router.post("/comp-reliability/durability-upload")
async def durability_upload(
    files: list[UploadFile] = File(...),
    type: str = Form(""),
    test_item: str = Form(""),
    machine: str = Form("1"),
    fix_row1: int = Form(0),
    fix_row2: int = Form(0),
    auto_detect: str = Form(""),
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    if not files:
        raise localized_http_exception(status_code=400, code="dataviz.no_files")
    # 각 업로드를 디스크 temp 로 스트리밍(피크 RAM = 1파일 분량) 후 경로만 병합에 넘긴다.
    # 42개 × 수십MB(수백MB) 시험도 전체를 동시에 메모리에 들지 않도록.
    temp_files: list[tuple[str, str]] = []
    try:
        for upload in files:
            temp_files.append((upload.filename or "", await _stream_upload_to_temp(upload)))
        merged, count, fix_row1, fix_row2, ch_map = rel.merge_durability_files(
            temp_files,
            dur_type=type,
            fix_row1=fix_row1,
            fix_row2=fix_row2,
            auto_detect=auto_detect.lower() in ("1", "true", "yes"),
        )
        if merged is None:
            raise localized_http_exception(status_code=400, code="dataviz.no_data")
        path = rel.dur_pkl_path(workspace.id, type, machine, test_item)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        merged.to_pickle(path)
        import math as _math

        col_list = [
            str(c) if not (isinstance(c, float) and _math.isnan(c)) else "unnamed"
            for c in merged.columns.tolist()
        ]
        return _safe_json(
            {
                "status": "ok",
                "file_count": count,
                "total_rows": len(merged),
                "columns": len(col_list),
                "column_names": col_list,
                "fix_row1": fix_row1,
                "fix_row2": fix_row2,
                "channel_signal_map": ch_map,
            }
        )
    finally:
        for _, tmp_path in temp_files:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _load_dur_df(workspace_id: str, dur_type: str, machine: str, test_item: str):
    path = rel.dur_pkl_path(workspace_id, dur_type, machine, test_item)
    if not os.path.exists(path):
        raise localized_http_exception(status_code=400, code="dataviz.no_data")
    return pd.read_pickle(path)


@router.get("/comp-reliability/durability-graph")
def durability_graph(
    type: str = "",
    machine: str = "1",
    test_item: str = "",
    cols: str = "__ALL__",
    max_points: int = 5000,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    df = _load_dur_df(workspace.id, type, machine, test_item)
    if cols == "__ALL__":
        col_list = [
            c
            for c in df.columns
            if c not in rel.SKIP_COLS and str(c) != "nan" and not str(c).startswith("nan_")
        ]
    else:
        col_list = [c.strip() for c in cols.split(",") if c.strip()]
    data = rel.lttb_columns(df, col_list, max_points)
    return _safe_json(
        {
            "status": "ok",
            "data": data,
            "columns": col_list,
            "total_rows": len(df),
            "sampled_points": max_points,
            "type": type,
            "machine": machine,
        }
    )


@router.get("/comp-reliability/durability-graph-elec")
def durability_graph_elec(
    type: str = "전동",
    machine: str = "1",
    test_item: str = "",
    cols: str = "",
    x_mode: str = "",
    x_param: str = "",
    max_points: int = 5000,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    df = _load_dur_df(workspace.id, type, machine, test_item)
    n = len(df)
    col_list = [c.strip() for c in cols.split(",") if c.strip() and c.strip() in df.columns]
    start_idx, end_idx = rel.slice_elec(df, x_mode, x_param)
    sliced = df.iloc[start_idx:end_idx].reset_index(drop=True)
    if isinstance(sliced.columns, pd.MultiIndex):
        sliced.columns = [str(col[0]).strip() for col in sliced.columns]
    result = rel.lttb_columns(sliced, col_list, max_points)
    # 전동: 압력 kgf/cm2G → kPaG (×98.0665)
    for pc in rel.ELEC_PRESSURE_COLS:
        if pc in result and "y" in result[pc]:
            result[pc]["y"] = [
                None if v is None else round(v * 98.0665, 2) for v in result[pc]["y"]
            ]
    return _safe_json(
        {
            "status": "ok",
            "data": result,
            "columns": col_list,
            "total_rows": len(sliced),
            "original_rows": n,
            "slice_start": start_idx,
            "slice_end": end_idx,
        }
    )
