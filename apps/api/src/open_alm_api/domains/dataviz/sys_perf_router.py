"""시스템 성능 — FastAPI 라우터 (레거시 sys_perf_routes.py 포팅).

레거시 sqlite3 + Flask session 을 SQLAlchemy(Postgres, 워크스페이스 스코프) + Depends 인증으로
적응한다. 파싱/분석 로직은 sys_perf.py 에, 모델은 sys_perf_models.py 에 있다.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
from datetime import datetime
from typing import NoReturn

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.core.i18n import (
    LocalizedApiMessage,
    localized_http_exception,
    select_locale,
    translate_message,
)
from open_alm_api.domains.auth.dependencies import (
    require_current_workspace,
    require_workspace_membership,
)
from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_alm_api.domains.dataviz.app_catalog import DATA_VIZ_WORKSPACE_APP
from open_alm_api.domains.dataviz import sys_perf as sp
from open_alm_api.domains.dataviz.sys_perf_models import (
    CAR_SEED,
    STANDARD_COLUMNS_SEED,
    SysPerfCarModel,
    SysPerfColumnMapping,
    SysPerfFileMaster,
    SysPerfItemKeyword,
    SysPerfPartsCatalog,
    SysPerfPartsSpec,
    SysPerfRefrigerantMaster,
    SysPerfRefrigerantProp,
    SysPerfRefrigerantStatePoint,
    SysPerfSheetHeader,
    SysPerfStandardColumn,
    SysPerfTestInfo,
    SysPerfTestMaster,
)

_require_ws_admin = require_workspace_membership("admin")

require_dataviz_app_enabled = require_workspace_app_enabled(
    DATA_VIZ_WORKSPACE_APP.app_id,
    error_code="dataviz.app_disabled",
)

router = APIRouter(
    prefix="/dataviz/sys-perf",
    tags=["dataviz-sysperf"],
    dependencies=[Depends(require_dataviz_app_enabled)],
)
_MAX_UPLOAD_BYTES = 80 * 1024 * 1024
_SYSPERF_WORKBOOK_EXTENSIONS = {".xls", ".xlsx"}
logger = logging.getLogger(__name__)


class SysPerfStrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SysPerfStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class SysPerfCountResponse(SysPerfStatusResponse):
    count: int


class SysPerfIdResponse(SysPerfStatusResponse):
    id: int


def _safe_json(obj: dict, status_code: int = 200) -> Response:
    return Response(
        json.dumps(sp.clean_nan(obj), ensure_ascii=False),
        status_code=status_code,
        media_type="application/json",
    )


def _localized_message(request: Request, code: str, **params: object) -> str:
    locale = select_locale(
        explicit_locale=request.headers.get("x-open-alm-locale"),
        accept_language=request.headers.get("accept-language"),
    )
    return translate_message(LocalizedApiMessage(code=code, params=params), locale)


def _raise_processing_failed(action: str, exc: Exception) -> NoReturn:
    logger.exception("dataviz.sys_perf.%s_failed", action)
    raise localized_http_exception(status_code=500, code="dataviz.processing_failed") from exc


def ensure_seed(db: Session, workspace_id: str) -> None:
    """워크스페이스에 표준 항목(standard_columns)이 없으면 30개 시드를 1회 삽입."""
    count = db.scalar(
        select(func.count())
        .select_from(SysPerfStandardColumn)
        .where(SysPerfStandardColumn.workspace_id == workspace_id)
    )
    if count and count > 0:
        return
    for name, kw, unit, cat, order in STANDARD_COLUMNS_SEED:
        db.add(
            SysPerfStandardColumn(
                workspace_id=workspace_id,
                standard_name=name,
                keywords=kw,
                unit=unit,
                category=cat,
                display_order=order,
            )
        )
    db.commit()


def _extra_keywords(db: Session, workspace_id: str) -> set[str]:
    """헤더 자동감지에 합류시킬 사용자 등록 키워드(item_keywords)."""
    rows = db.scalars(
        select(SysPerfItemKeyword.keywords).where(SysPerfItemKeyword.workspace_id == workspace_id)
    ).all()
    out: set[str] = set()
    for kws in rows:
        for k in (kws or "").split(","):
            out.add(k)
    return out


async def _stream_to(path: str, file: UploadFile) -> None:
    total = 0
    with open(path, "wb") as fh:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_UPLOAD_BYTES:
                fh.close()
                try:
                    os.unlink(path)
                except OSError:
                    pass
                raise localized_http_exception(status_code=413, code="dataviz.upload_too_large")
            fh.write(chunk)


@router.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    if not files:
        raise localized_http_exception(status_code=400, code="dataviz.no_files")
    ensure_seed(db, workspace.id)
    ensure_car_seed(db, workspace.id)
    uploads_dir, _ = sp.workspace_dirs(workspace.id)
    extra_kw = _extra_keywords(db, workspace.id)

    results: list[dict] = []
    for f in files:
        fname = f.filename or "upload.xlsx"
        suffix = (os.path.splitext(fname)[1] or ".xlsx").lower()
        if suffix not in _SYSPERF_WORKBOOK_EXTENSIONS:
            results.append(
                {
                    "filename": fname,
                    "error": _localized_message(request, "dataviz.excel_file_required"),
                }
            )
            continue
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=uploads_dir)
        tmp.close()
        await _stream_to(tmp.name, f)
        try:
            sheet_info, all_sheets, sheet_headers = sp.analyze_workbook(tmp.name, extra_kw)
            auto_match, car_code = sp.parse_filename(fname)

            # 차종 DB 매칭 (model_code) + 부품사양(car_code)
            car_models = db.scalars(
                select(SysPerfCarModel)
                .where(SysPerfCarModel.workspace_id == workspace.id)
                .order_by(func.length(SysPerfCarModel.model_code).desc())
            ).all()
            for cm in car_models:
                mc = (cm.model_code or "").strip()
                if mc and mc.upper() == car_code.upper():
                    auto_match["car_model"] = cm.car_name or ""
                    auto_match["segment"] = cm.segment_name or ""
                    break
            parts_specs = db.scalars(
                select(SysPerfPartsSpec).where(
                    SysPerfPartsSpec.workspace_id == workspace.id,
                    SysPerfPartsSpec.car_code == car_code,
                )
            ).all()
            auto_match["parts_specs"] = [
                {
                    "id": p.id,
                    "name": p.name,
                    "car_code": p.car_code,
                    "comp": p.comp,
                    "condenser": p.condenser,
                    "txv": p.txv,
                    "hvac": p.hvac,
                    "pipe": p.pipe,
                    "refrigerant_charge": p.refrigerant_charge,
                    "note": p.note,
                }
                for p in parts_specs
            ]

            fm = SysPerfFileMaster(
                workspace_id=workspace.id,
                filename=fname,
                file_path=tmp.name,
                sheet_count=len(sheet_info),
            )
            db.add(fm)
            db.flush()  # fm.id 확보
            for sh in sheet_headers:
                db.add(
                    SysPerfSheetHeader(
                        workspace_id=workspace.id,
                        file_id=fm.id,
                        sheet_name=sh["sheet_name"],
                        header_row=sh["header_row"],
                        info_row=sh["info_row"],
                    )
                )
            db.commit()

            results.append(
                {
                    "file_id": fm.id,
                    "filename": fname,
                    "sheets": sheet_info,
                    "all_sheets": all_sheets,
                    "auto_match": auto_match,
                }
            )
        except Exception:  # noqa: BLE001 — 한 파일 실패가 전체를 막지 않게
            db.rollback()
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            logger.exception("dataviz.sys_perf.upload_file_failed")
            results.append(
                {
                    "filename": fname,
                    "error": _localized_message(request, "dataviz.file_parse_failed"),
                }
            )

    return _safe_json({"status": "ok", "files": results})


class TestInfoItem(SysPerfStrictRequest):
    file_id: int = Field(gt=0)
    sheet_name: str = Field(min_length=1)
    car_model: str = ""
    spec: str = ""
    test_item: str = ""
    test_date: str = ""
    lot_no: str = ""
    refrigerant: str = ""
    note: str = ""


class SaveTestInfoRequest(SysPerfStrictRequest):
    items: list[TestInfoItem]


@router.post("/test-info", response_model=SysPerfStatusResponse)
def save_test_info(
    payload: SaveTestInfoRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> SysPerfStatusResponse:
    for item in payload.items:
        # 레거시 INSERT OR REPLACE 대응 — (file_id, sheet_name) 기존 행 제거 후 삽입.
        db.execute(
            delete(SysPerfTestInfo).where(
                SysPerfTestInfo.workspace_id == workspace.id,
                SysPerfTestInfo.file_id == item.file_id,
                SysPerfTestInfo.sheet_name == item.sheet_name,
            )
        )
        db.add(
            SysPerfTestInfo(
                workspace_id=workspace.id,
                file_id=item.file_id,
                sheet_name=item.sheet_name,
                car_model=item.car_model,
                spec=item.spec,
                test_item=item.test_item,
                test_date=item.test_date,
                lot_no=item.lot_no,
                refrigerant=item.refrigerant,
                note=item.note,
            )
        )
    db.commit()
    return SysPerfStatusResponse(status="ok")


# ═══ 항목 매칭 ═══


class AutoMatchRequest(SysPerfStrictRequest):
    file_id: int = Field(gt=0)
    headers: list[str]


class MatchedStandardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    standard_name: str
    unit: str
    category: str
    display_order: int


class AutoMatchColumnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    col_index: int
    original_name: str
    matched: MatchedStandardResponse | None


class AutoMatchResponse(SysPerfStatusResponse):
    matches: list[AutoMatchColumnResponse]


def _match_one(hdr: str, standards) -> MatchedStandardResponse | None:
    """헤더 1개를 표준 항목에 매칭. 정확도 순위:
    0=완전일치, 1=접두일치(3자+), 2=키워드가 헤더에 포함(3자+).

    레거시는 `kw in hdr or hdr in kw` 양방향 부분일치라 'PS'가 'elapsed'에 포함되어
    Time 으로 오매칭되는 등 짧은 헤더에서 오류가 많았다. 여기선 'hdr in kw' 방향(헤더가
    키워드 부분문자열)을 제거하고, 부분/접두 매칭은 3자 이상 키워드에만 허용해 'ps','pc',
    'sc' 같은 2자 토큰의 오매칭을 막는다. 완전일치는 길이 무관(흡입온도 'ps' 등 보존).
    동순위는 display_order 가 앞선(먼저 순회되는) 항목이 우선.
    """
    h = hdr.lower().strip()
    h_compact = h.replace(" ", "")
    best = None
    best_rank = 99
    for std in standards:
        kws = [k.strip().lower() for k in (std.keywords or "").split(",") if k.strip()]
        for kw in kws:
            kw_compact = kw.replace(" ", "")
            rank = None
            if h == kw or h_compact == kw_compact:
                rank = 0
            elif len(kw) >= 3 and (h.startswith(kw) or kw.startswith(h)):
                rank = 1
            elif len(kw) >= 3 and kw in h:
                rank = 2
            if rank is not None and rank < best_rank:
                best_rank = rank
                best = std
                if rank == 0:
                    break
        if best_rank == 0:
            break
    if best is None:
        return None
    return MatchedStandardResponse(
        id=best.id,
        standard_name=best.standard_name,
        unit=best.unit,
        category=best.category,
        display_order=best.display_order,
    )


@router.post("/auto-match", response_model=AutoMatchResponse)
def auto_match_columns(
    payload: AutoMatchRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> AutoMatchResponse:
    """헤더를 표준 항목(standard_columns.keywords)에 자동 매칭 (완전일치 우선)."""
    ensure_seed(db, workspace.id)
    standards = db.scalars(
        select(SysPerfStandardColumn)
        .where(SysPerfStandardColumn.workspace_id == workspace.id)
        .order_by(SysPerfStandardColumn.display_order)
    ).all()
    matches = [
        AutoMatchColumnResponse(
            col_index=idx,
            original_name=hdr,
            matched=_match_one(hdr, standards),
        )
        for idx, hdr in enumerate(payload.headers)
    ]
    return AutoMatchResponse(status="ok", matches=matches)


class MappingItem(SysPerfStrictRequest):
    original_name: str = Field(min_length=1)
    standard_name: str = Field(min_length=1)
    col_index: int = Field(ge=0)


class ConfirmMatchRequest(SysPerfStrictRequest):
    file_id: int = Field(gt=0)
    sheet_name: str = Field(min_length=1)
    mappings: list[MappingItem]


@router.post("/confirm-match", response_model=SysPerfStatusResponse)
def confirm_match(
    payload: ConfirmMatchRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> SysPerfStatusResponse:
    """매칭 확정 저장 + BASE 키워드 자동 학습(original_name → standard_columns.keywords)."""
    db.execute(
        delete(SysPerfColumnMapping).where(
            SysPerfColumnMapping.workspace_id == workspace.id,
            SysPerfColumnMapping.file_id == payload.file_id,
            SysPerfColumnMapping.sheet_name == payload.sheet_name,
        )
    )
    for m in payload.mappings:
        db.add(
            SysPerfColumnMapping(
                workspace_id=workspace.id,
                file_id=payload.file_id,
                sheet_name=payload.sheet_name,
                original_name=m.original_name,
                standard_name=m.standard_name,
                col_index=m.col_index,
                confirmed=1,
            )
        )
        if m.standard_name and m.original_name:
            std = db.scalar(
                select(SysPerfStandardColumn).where(
                    SysPerfStandardColumn.workspace_id == workspace.id,
                    SysPerfStandardColumn.standard_name == m.standard_name,
                )
            )
            if std:
                existing = {k.strip().lower() for k in (std.keywords or "").split(",") if k.strip()}
                if m.original_name.lower().strip() not in existing:
                    std.keywords = (std.keywords or "") + "," + m.original_name
    db.commit()
    return SysPerfStatusResponse(status="ok")


# ═══ 데이터 조회 ═══


def _get_header_row(
    db: Session, workspace_id: str, file_id: int, sheet_name: str, default: int = 1
) -> int:
    r = db.scalar(
        select(SysPerfSheetHeader.header_row).where(
            SysPerfSheetHeader.workspace_id == workspace_id,
            SysPerfSheetHeader.file_id == file_id,
            SysPerfSheetHeader.sheet_name == sheet_name,
        )
    )
    return int(r) if r is not None else default


def _file_master(db: Session, workspace_id: str, file_id: int) -> SysPerfFileMaster | None:
    return db.scalar(
        select(SysPerfFileMaster).where(
            SysPerfFileMaster.workspace_id == workspace_id,
            SysPerfFileMaster.id == file_id,
        )
    )


@router.get("/sheet-data")
def get_sheet_data(
    file_id: int,
    sheet: str = "",
    max_rows: int = 5000,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    fm = _file_master(db, workspace.id, file_id)
    if not fm or not fm.file_path or not os.path.exists(fm.file_path):
        raise localized_http_exception(status_code=404, code="dataviz.file_not_found")
    try:
        df = pd.read_excel(
            fm.file_path,
            sheet_name=sheet,
            header=_get_header_row(db, workspace.id, file_id, sheet, 1),
        )
        if len(df) > max_rows:
            df = df.iloc[:max_rows]
        columns = [str(c) for c in df.columns.tolist() if str(c) != "nan"]
        data = {}
        for c in df.columns.tolist():
            if str(c) == "nan":
                continue
            vals = pd.to_numeric(df[c], errors="coerce").tolist()
            data[str(c)] = [None if (isinstance(v, float) and math.isnan(v)) else v for v in vals]
        return _safe_json({"status": "ok", "columns": columns, "data": data, "total_rows": len(df)})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        _raise_processing_failed("sheet_data", e)


@router.get("/graph-data")
def get_graph_data(
    file_id: int,
    sheet: str = "",
    max_pts: int = 3000,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    """매칭된 표준항목 기준 데이터 반환. original_name 매칭(col_index fallback), Time축 LTTB."""
    fm = _file_master(db, workspace.id, file_id)
    if not fm or not fm.file_path or not os.path.exists(fm.file_path):
        raise localized_http_exception(status_code=404, code="dataviz.file_not_found")
    mappings = db.scalars(
        select(SysPerfColumnMapping).where(
            SysPerfColumnMapping.workspace_id == workspace.id,
            SysPerfColumnMapping.file_id == file_id,
            SysPerfColumnMapping.sheet_name == sheet,
        )
    ).all()
    if not mappings:
        raise localized_http_exception(status_code=400, code="dataviz.no_mappings")
    try:
        df = pd.read_excel(
            fm.file_path,
            sheet_name=sheet,
            header=_get_header_row(db, workspace.id, file_id, sheet, 1),
        )
        cols = [str(c).strip() for c in df.columns.tolist()]
        std_units = {
            s.standard_name: (s.unit or "")
            for s in db.scalars(
                select(SysPerfStandardColumn).where(
                    SysPerfStandardColumn.workspace_id == workspace.id
                )
            ).all()
        }

        result: dict[str, list] = {}
        units: dict[str, str] = {}
        time_col = None
        for m in mappings:
            orig = (m.original_name or "").strip()
            matched_col = None
            for c in cols:
                if c == orig or c.lower() == orig.lower():
                    matched_col = c
                    break
            if matched_col is None and m.col_index is not None and m.col_index < len(cols):
                matched_col = cols[m.col_index]
            if matched_col is not None:
                vals = pd.to_numeric(df[matched_col], errors="coerce").tolist()
                result[m.standard_name] = [
                    None if (isinstance(v, float) and math.isnan(v)) else v for v in vals
                ]
                if m.standard_name in std_units:
                    units[m.standard_name] = std_units[m.standard_name]
                sn = m.standard_name
                sn_l = sn.lower()
                if (
                    sn == "Time"
                    or sn.endswith("_Time")
                    or sn.endswith("_TIME")
                    or "_time (min)" in sn_l
                    or sn_l.endswith("_time")
                    or sn_l == "time"
                    or sn.startswith("92_")
                ):
                    time_col = sn

        if not time_col:
            best_col, best_valid, best_series = None, 0, None
            for c in cols:
                cl = str(c).lower().strip()
                if (
                    cl == "time"
                    or cl.startswith("time")
                    or "시간" in cl
                    or "elapse" in cl
                    or cl.startswith("t(")
                    or cl.startswith("t ")
                ):
                    try:
                        numeric = pd.to_numeric(df[c], errors="coerce")
                        valid = int(numeric.notna().sum())
                        if valid > best_valid:
                            best_valid, best_col, best_series = valid, c, numeric
                    except Exception:
                        continue
            if best_col is not None and best_valid > 0:
                vals = best_series.tolist()
                result["Time"] = [
                    None if (isinstance(v, float) and math.isnan(v)) else v for v in vals
                ]
                time_col = "Time"

        if time_col and time_col != "Time" and time_col in result:
            result["Time"] = list(result[time_col])

        if time_col and len(result.get(time_col, [])) > max_pts:
            time_arr = np.array(result[time_col], dtype=float)
            indices = sp.lttb_indices(time_arr, max_pts)
            for key in result:
                arr = result[key]
                result[key] = [arr[i] for i in indices]

        return _safe_json({"status": "ok", "data": result, "units": units, "total_rows": len(df)})
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        _raise_processing_failed("graph_data", e)


# ═══ 사이클 (P-H / T-S 선도용 8포인트 P·T·h·s) ═══


@router.get("/cycle-data")
def get_cycle_data(
    file_id: int,
    sheet: str = "",
    time: float | None = None,
    refrigerant: str = "R-134a",
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    fm = _file_master(db, workspace.id, file_id)
    if not fm or not fm.file_path or not os.path.exists(fm.file_path):
        raise localized_http_exception(status_code=404, code="dataviz.file_not_found")
    mappings = db.scalars(
        select(SysPerfColumnMapping).where(
            SysPerfColumnMapping.workspace_id == workspace.id,
            SysPerfColumnMapping.file_id == file_id,
            SysPerfColumnMapping.sheet_name == sheet,
        )
    ).all()
    try:
        df = pd.read_excel(
            fm.file_path,
            sheet_name=sheet,
            header=_get_header_row(db, workspace.id, file_id, sheet, 1),
        )
        cols = df.columns.tolist()
        mapping_dict = {m.standard_name: m.col_index for m in mappings}
        mapping_originals = {m.standard_name: (m.original_name or "") for m in mappings}

        # Time 컬럼 (매핑 → 자동탐지)
        time_idx = None
        for sname, idx in mapping_dict.items():
            sl = sname.lower()
            if (
                sname == "Time"
                or sname.endswith("_Time")
                or sname.endswith("_TIME")
                or "_time" in sl
                or sl == "time"
                or "_time (min)" in sl
                or sname.startswith("92_")
            ):
                time_idx = idx
                break
        if time_idx is None:
            best_idx, best_valid = None, 0
            for ci, c in enumerate(cols):
                cl = str(c).lower().strip()
                if (
                    cl == "time"
                    or cl.startswith("time")
                    or cl == "elapsed"
                    or "elapse" in cl
                    or "시간" in cl
                    or cl.startswith("t(")
                    or cl.startswith("t ")
                ):
                    try:
                        valid = int(pd.to_numeric(df[c], errors="coerce").notna().sum())
                        if valid > best_valid:
                            best_valid, best_idx = valid, ci
                    except Exception:
                        continue
            time_idx = best_idx
        if time_idx is None:
            raise localized_http_exception(status_code=400, code="dataviz.time_column_not_found")

        time_series = pd.to_numeric(df[cols[time_idx]], errors="coerce")
        if time_series.notna().sum() == 0:
            raise localized_http_exception(
                status_code=400,
                code="dataviz.time_column_no_numeric_values",
            )
        target_time = time if time is not None else float(time_series.dropna().iloc[0])
        row_idx = (time_series - target_time).abs().idxmin()

        # 사이클 값 — original_name 완전일치(소문자) 매칭
        cols_lower = [str(c).strip().lower() for c in cols]
        cycle_data: dict[str, float | None] = {}
        cycle_mappings_out: dict[str, str] = {}
        for client_key, db_key in sp.CYCLE_MAP.items():
            val_out = None
            orig_name = mapping_originals.get(db_key, "") if db_key in mapping_dict else ""
            if orig_name:
                target = orig_name.strip().lower()
                for i, cl in enumerate(cols_lower):
                    if cl == target:
                        try:
                            val = df.iloc[row_idx][cols[i]]
                            if pd.notna(val):
                                val_out = float(val)
                        except Exception:
                            pass
                        break
            cycle_data[client_key] = val_out
            cycle_mappings_out[client_key] = orig_name

        actual_time = (
            float(time_series.iloc[row_idx]) if pd.notna(time_series.iloc[row_idx]) else target_time
        )

        ref = refrigerant.replace("-", "")
        enthalpy: dict[str, float | None] = {}
        entropy: dict[str, float | None] = {}
        if sp.HAS_COOLPROP:
            for pt in sp.CYCLE_POINTS:
                P_kgf = cycle_data.get(pt + " Pressure")
                T_c = cycle_data.get(pt + " Temperature")
                h_val = s_val = None
                if P_kgf is not None and T_c is not None:
                    P_Pa = P_kgf * sp.KGFCM2_TO_PA
                    T_K = T_c + 273.15
                    try:
                        h_val = sp.PropsSI("H", "T", T_K, "P", P_Pa, ref) / 1000.0
                        s_val = sp.PropsSI("S", "T", T_K, "P", P_Pa, ref) / 1000.0
                        if math.isnan(h_val) or math.isinf(h_val):
                            h_val = None
                        if math.isnan(s_val) or math.isinf(s_val):
                            s_val = None
                    except Exception:
                        try:
                            T_sat_K = sp.PropsSI("T", "P", P_Pa, "Q", 0, ref)
                            q_use = 0 if T_K < T_sat_K else 1
                            h_val = sp.PropsSI("H", "P", P_Pa, "Q", q_use, ref) / 1000.0
                            s_val = sp.PropsSI("S", "P", P_Pa, "Q", q_use, ref) / 1000.0
                        except Exception:
                            h_val = s_val = None
                enthalpy[pt + " Enthalpy"] = h_val
                entropy[pt + " Entropy"] = s_val

        def _is_real_sensor(client_key: str) -> bool:
            orig = mapping_originals.get(sp.CYCLE_MAP.get(client_key, ""), "")
            if not orig:
                return False
            tgt = orig.strip().lower()
            return any(tgt == kw.strip().lower() for kw in sp.CYCLE_STD_KW.get(client_key, []))

        isenthalpic_notes: list[str] = []
        warnings_notes: dict[str, list[str]] = {}

        txv_p_real = _is_real_sensor("TXV In Pressure")
        txv_t_real = _is_real_sensor("TXV In Temperature")
        apply_isenthalpic = not (txv_p_real and txv_t_real)
        if apply_isenthalpic and enthalpy.get("TXV In Enthalpy") is not None:
            enthalpy["TXV Out Enthalpy"] = enthalpy["TXV In Enthalpy"]
            isenthalpic_notes.append("TXV Out: 독립 센서 없음 → 등엔탈피 (TXV In h 적용)")
            enthalpy["Evap In Enthalpy"] = enthalpy["TXV In Enthalpy"]
            isenthalpic_notes.append("HVAC In: TXV Out h 계승")
            if sp.HAS_COOLPROP:
                h_J = enthalpy["TXV In Enthalpy"] * 1000.0
                for pt2 in ("TXV Out", "Evap In"):
                    P_kgf2 = cycle_data.get(pt2 + " Pressure")
                    if P_kgf2 is not None:
                        try:
                            s_new = (
                                sp.PropsSI("S", "P", P_kgf2 * sp.KGFCM2_TO_PA, "H", h_J, ref)
                                / 1000.0
                            )
                            if not (math.isnan(s_new) or math.isinf(s_new)):
                                entropy[pt2 + " Entropy"] = s_new
                        except Exception:
                            pass

        warn_tmpl = "※ 본 수치는 {pt} 데이터를 기반으로 환산한 값이 아니므로, 실제 결과와 완전히 일치하지 않을 수 있습니다."
        for client_pt_name, label in sp.POINT_LABEL_PT.items():
            p_real = _is_real_sensor(client_pt_name + " Pressure")
            t_real = _is_real_sensor(client_pt_name + " Temperature")
            if not (p_real and t_real):
                p_orig = mapping_originals.get(
                    sp.CYCLE_MAP.get(client_pt_name + " Pressure", ""), ""
                )
                t_orig = mapping_originals.get(
                    sp.CYCLE_MAP.get(client_pt_name + " Temperature", ""), ""
                )
                if p_orig or t_orig:
                    warnings_notes.setdefault(client_pt_name, []).append(warn_tmpl.format(pt=label))

        sh_sc: dict[str, float] = {}
        if sp.HAS_COOLPROP:
            for pt, kind in [("Comp In", "SH"), ("TXV In", "SC")]:
                P_kgf = cycle_data.get(pt + " Pressure")
                T_c = cycle_data.get(pt + " Temperature")
                if P_kgf is None or T_c is None:
                    continue
                try:
                    T_sat_C = sp.PropsSI("T", "P", P_kgf * sp.KGFCM2_TO_PA, "Q", 0, ref) - 273.15
                    if kind == "SH":
                        sh_sc["Comp In SH"] = round(T_c - T_sat_C, 1)
                    else:
                        sh_sc["TXV In SC"] = round(T_sat_C - T_c, 1)
                except Exception:
                    pass

        return _safe_json(
            {
                "status": "ok",
                "time": actual_time,
                "row_index": int(row_idx),
                "cycle": cycle_data,
                "enthalpy": enthalpy,
                "entropy": entropy,
                "sh_sc": sh_sc,
                "mappings": cycle_mappings_out,
                "isenthalpic_notes": isenthalpic_notes,
                "warnings": warnings_notes,
            }
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        _raise_processing_failed("cycle_data", e)


# ═══ P-H 선도 배경 ═══


@router.get("/ph-diagram-data")
def get_ph_diagram_data(
    refrigerant: str = "R-134a",
    refrigerant_id: int | None = None,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    out: dict = {
        "has_coolprop": sp.HAS_COOLPROP,
        "has_cp_plots": False,
        "refrigerant": refrigerant,
        "saturation": {"h": [], "p": []},
        "isotherms": [],
        "isentropes": [],
        "isoquality": [],
        "isochor": [],
        "critical": {"T": None, "P": None, "h": None},
    }
    if sp.HAS_COOLPROP:
        try:
            out.update(sp.compute_ph_diagram(refrigerant))
            return _safe_json({"status": "ok", **out})
        except Exception as e:  # noqa: BLE001
            out["coolprop_error"] = str(e)

    # 폴백: DB refrigerant_props 의 포화 물성으로 종모양 곡선만 (isoline 없음)
    if refrigerant_id:
        rows = db.scalars(
            select(SysPerfRefrigerantProp)
            .where(
                SysPerfRefrigerantProp.workspace_id == workspace.id,
                SysPerfRefrigerantProp.refrigerant_id == refrigerant_id,
            )
            .order_by(SysPerfRefrigerantProp.temperature)
        ).all()
        rows = [
            r
            for r in rows
            if r.liq_enthalpy is not None
            and r.vap_enthalpy is not None
            and r.sat_pressure_kpa is not None
        ]
        if rows:
            hf = [r.liq_enthalpy for r in rows]
            Pf = [r.sat_pressure_kpa for r in rows]
            hg = [r.vap_enthalpy for r in rows]
            out["saturation"]["h"] = hf + list(reversed(hg))
            out["saturation"]["p"] = Pf + list(reversed(Pf))
            out["critical"] = {"T": None, "P": max(Pf) if Pf else 0, "h": None}
    return _safe_json({"status": "ok", **out})


# ═══ T-S 선도 배경 ═══


@router.get("/ts-diagram-data")
def get_ts_diagram_data(
    refrigerant: str = "R-134a",
    refrigerant_id: int | None = None,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    out: dict = {
        "has_coolprop": sp.HAS_COOLPROP,
        "refrigerant": refrigerant,
        "saturation": {"s": [], "t": []},
        "isobars": [],
        "isenthalps": [],
        "critical": {"T": None, "s": None, "P": None},
    }
    if sp.HAS_COOLPROP:
        try:
            out.update(sp.compute_ts_diagram(refrigerant))
            return _safe_json({"status": "ok", **out})
        except Exception as e:  # noqa: BLE001
            out["coolprop_error"] = str(e)

    # 폴백: DB refrigerant_props 의 포화 엔트로피/온도로 종모양 곡선만
    if refrigerant_id:
        rows = db.scalars(
            select(SysPerfRefrigerantProp)
            .where(
                SysPerfRefrigerantProp.workspace_id == workspace.id,
                SysPerfRefrigerantProp.refrigerant_id == refrigerant_id,
            )
            .order_by(SysPerfRefrigerantProp.temperature)
        ).all()
        rows = [
            r
            for r in rows
            if r.liq_entropy is not None and r.vap_entropy is not None and r.temperature is not None
        ]
        if rows:
            sf = [r.liq_entropy for r in rows]
            Tf = [r.temperature for r in rows]
            sg = [r.vap_entropy for r in rows]
            out["saturation"]["s"] = sf + list(reversed(sg))
            out["saturation"]["t"] = Tf + list(reversed(Tf))
            out["critical"] = {"T": max(Tf) if Tf else None, "s": None, "P": None}
    return _safe_json({"status": "ok", **out})


# ═══════════════════════════════════════════
#  BASE 관리 — 표준항목 / 냉매 / 물성 / 차종 / 키워드 / 부품
# ═══════════════════════════════════════════


# ── 표준 항목명 사전 ──
class StandardColumnItem(SysPerfStrictRequest):
    id: int | None = None
    standard_name: str = Field(min_length=1)
    keywords: str
    unit: str
    category: str
    display_order: int

    @field_validator("standard_name")
    @classmethod
    def _standard_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("standard_name is required")
        return value


class StandardColumnResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    standard_name: str
    keywords: str
    unit: str
    category: str
    display_order: int


class StandardColumnsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[StandardColumnResponse]


def _standard_column_response(row: SysPerfStandardColumn) -> StandardColumnResponse:
    return StandardColumnResponse(
        id=row.id,
        standard_name=row.standard_name,
        keywords=row.keywords,
        unit=row.unit,
        category=row.category,
        display_order=row.display_order,
    )


@router.get("/base/columns", response_model=StandardColumnsResponse)
def get_standard_columns(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> StandardColumnsResponse:
    ensure_seed(db, workspace.id)
    rows = db.scalars(
        select(SysPerfStandardColumn)
        .where(SysPerfStandardColumn.workspace_id == workspace.id)
        .order_by(SysPerfStandardColumn.display_order)
    ).all()
    return StandardColumnsResponse(data=[_standard_column_response(row) for row in rows])


@router.post("/base/columns", response_model=SysPerfStatusResponse)
def save_standard_column(
    item: StandardColumnItem,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    values = {
        "standard_name": item.standard_name.strip(),
        "keywords": item.keywords.strip(),
        "unit": item.unit.strip(),
        "category": item.category.strip(),
        "display_order": item.display_order,
    }
    if item.id:
        row = db.scalar(
            select(SysPerfStandardColumn).where(
                SysPerfStandardColumn.workspace_id == workspace.id,
                SysPerfStandardColumn.id == item.id,
            )
        )
        if row:
            row.standard_name = values["standard_name"]
            row.keywords = values["keywords"]
            row.unit = values["unit"]
            row.category = values["category"]
            row.display_order = values["display_order"]
    else:
        db.add(
            SysPerfStandardColumn(
                workspace_id=workspace.id,
                **values,
            )
        )
    db.commit()
    return SysPerfStatusResponse(status="ok")


@router.delete("/base/columns/{col_id}", response_model=SysPerfStatusResponse)
def delete_standard_column(
    col_id: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    db.execute(
        delete(SysPerfStandardColumn).where(
            SysPerfStandardColumn.workspace_id == workspace.id,
            SysPerfStandardColumn.id == col_id,
        )
    )
    db.commit()
    return SysPerfStatusResponse(status="ok")


# ── 냉매 ──
class RefrigerantItem(SysPerfStrictRequest):
    name: str = Field(min_length=1)
    formula: str

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name is required")
        return value


class RefrigerantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    formula: str


class RefrigerantsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[RefrigerantResponse]


def _refrigerant_response(row: SysPerfRefrigerantMaster) -> RefrigerantResponse:
    return RefrigerantResponse(id=row.id, name=row.name, formula=row.formula)


@router.get("/base/refrigerants", response_model=RefrigerantsResponse)
def get_refrigerants(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> RefrigerantsResponse:
    rows = db.scalars(
        select(SysPerfRefrigerantMaster)
        .where(SysPerfRefrigerantMaster.workspace_id == workspace.id)
        .order_by(SysPerfRefrigerantMaster.name)
    ).all()
    return RefrigerantsResponse(data=[_refrigerant_response(row) for row in rows])


@router.post("/base/refrigerants", response_model=SysPerfStatusResponse)
def save_refrigerant(
    item: RefrigerantItem,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    name = item.name.strip()
    formula = item.formula.strip()
    # INSERT OR IGNORE — 같은 이름 있으면 무시
    exists = db.scalar(
        select(SysPerfRefrigerantMaster).where(
            SysPerfRefrigerantMaster.workspace_id == workspace.id,
            SysPerfRefrigerantMaster.name == name,
        )
    )
    if not exists:
        db.add(SysPerfRefrigerantMaster(workspace_id=workspace.id, name=name, formula=formula))
        db.commit()
    return SysPerfStatusResponse(status="ok")


# ── 냉매 물성치 ──
class RefrigerantPropRow(SysPerfStrictRequest):
    temperature: float | None = None
    sat_pressure_kgcm2: float | None = None
    sat_pressure_kpa: float | None = None
    sat_pressure_bar: float | None = None
    liq_enthalpy: float | None = None
    vap_enthalpy: float | None = None
    liq_entropy: float | None = None
    vap_entropy: float | None = None
    liq_specific_vol: float | None = None
    vap_specific_vol: float | None = None


class RefrigerantPropsRequest(SysPerfStrictRequest):
    refrigerant_id: int = Field(gt=0)
    rows: list[RefrigerantPropRow]


class RefrigerantPropResponse(RefrigerantPropRow):
    id: int
    refrigerant_id: int


class RefrigerantPropsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[RefrigerantPropResponse]


class RefrigerantPropsImportResponse(SysPerfCountResponse):
    sheet: str
    col_map: dict[str, str]


def _refrigerant_prop_response(row: SysPerfRefrigerantProp) -> RefrigerantPropResponse:
    return RefrigerantPropResponse(
        id=row.id,
        refrigerant_id=row.refrigerant_id,
        temperature=row.temperature,
        sat_pressure_kgcm2=row.sat_pressure_kgcm2,
        sat_pressure_kpa=row.sat_pressure_kpa,
        sat_pressure_bar=row.sat_pressure_bar,
        liq_enthalpy=row.liq_enthalpy,
        vap_enthalpy=row.vap_enthalpy,
        liq_entropy=row.liq_entropy,
        vap_entropy=row.vap_entropy,
        liq_specific_vol=row.liq_specific_vol,
        vap_specific_vol=row.vap_specific_vol,
    )


@router.get("/base/refrigerant-props", response_model=RefrigerantPropsResponse)
def get_refrigerant_props(
    refrigerant_id: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> RefrigerantPropsResponse:
    rows = db.scalars(
        select(SysPerfRefrigerantProp)
        .where(
            SysPerfRefrigerantProp.workspace_id == workspace.id,
            SysPerfRefrigerantProp.refrigerant_id == refrigerant_id,
        )
        .order_by(SysPerfRefrigerantProp.temperature)
    ).all()
    return RefrigerantPropsResponse(data=[_refrigerant_prop_response(row) for row in rows])


@router.post("/base/refrigerant-props", response_model=SysPerfCountResponse)
def save_refrigerant_props(
    payload: RefrigerantPropsRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfCountResponse:
    db.execute(
        delete(SysPerfRefrigerantProp).where(
            SysPerfRefrigerantProp.workspace_id == workspace.id,
            SysPerfRefrigerantProp.refrigerant_id == payload.refrigerant_id,
        )
    )
    for r in payload.rows:
        db.add(
            SysPerfRefrigerantProp(
                workspace_id=workspace.id,
                refrigerant_id=payload.refrigerant_id,
                **r.model_dump(),
            )
        )
    db.commit()
    return SysPerfCountResponse(status="ok", count=len(payload.rows))


# ── 차종 ──
def ensure_car_seed(db: Session, workspace_id: str) -> None:
    """워크스페이스에 차종이 없으면 CAR_SEED(196종) 1회 삽입. (원본 _init_db 차종 시드)
    튜플 (era, brand, year, name, code, sc, sn) → 모델 컬럼 (brand, era, ...) 재배열."""
    count = db.scalar(
        select(func.count())
        .select_from(SysPerfCarModel)
        .where(SysPerfCarModel.workspace_id == workspace_id)
    )
    if count and count > 0:
        return
    for era, brand, yr, name, code, sc, sn in CAR_SEED:
        db.add(
            SysPerfCarModel(
                workspace_id=workspace_id,
                brand=brand,
                era=era,
                year=yr,
                car_name=name,
                model_code=code,
                segment_code=sc,
                segment_name=sn,
            )
        )
    db.commit()


_CAR_MODEL_FIELDS = (
    "brand",
    "era",
    "year",
    "car_name",
    "model_code",
    "segment_code",
    "segment_name",
    "refrigerant",
    "note",
)


class CarModelItem(SysPerfStrictRequest):
    id: int | None = None
    brand: str
    era: str
    year: str
    car_name: str = Field(min_length=1)
    model_code: str
    segment_code: str
    segment_name: str
    refrigerant: str
    note: str

    @field_validator("car_name")
    @classmethod
    def _car_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("car_name is required")
        return value


class CarModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    brand: str
    era: str
    year: str
    car_name: str
    model_code: str
    segment_code: str
    segment_name: str
    refrigerant: str
    note: str


class CarModelListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[CarModelResponse]


def _car_model_response(row: SysPerfCarModel) -> CarModelResponse:
    return CarModelResponse(
        id=row.id,
        brand=row.brand,
        era=row.era,
        year=row.year,
        car_name=row.car_name,
        model_code=row.model_code,
        segment_code=row.segment_code,
        segment_name=row.segment_name,
        refrigerant=row.refrigerant,
        note=row.note,
    )


@router.get("/base/car-models", response_model=CarModelListResponse)
def get_car_models(
    brand: str = "",
    era: str = "",
    segment: str = "",
    q: str = "",
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> CarModelListResponse:
    ensure_car_seed(db, workspace.id)
    rows = db.scalars(
        select(SysPerfCarModel)
        .where(SysPerfCarModel.workspace_id == workspace.id)
        .order_by(SysPerfCarModel.year.desc(), SysPerfCarModel.brand, SysPerfCarModel.car_name)
    ).all()
    data = [_car_model_response(row) for row in rows]
    ql = q.strip().lower()
    if brand:
        data = [row for row in data if row.brand == brand]
    if era:
        data = [row for row in data if row.era == era]
    if segment:
        data = [row for row in data if row.segment_name == segment]
    if ql:
        data = [row for row in data if ql in row.car_name.lower() or ql in row.model_code.lower()]
    return CarModelListResponse(data=data)


@router.post("/base/car-models", response_model=SysPerfStatusResponse)
def save_car_model(
    item: CarModelItem,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    values = {field: getattr(item, field).strip() for field in _CAR_MODEL_FIELDS}
    if item.id:
        row = db.scalar(
            select(SysPerfCarModel).where(
                SysPerfCarModel.workspace_id == workspace.id, SysPerfCarModel.id == item.id
            )
        )
        if row:
            for field, value in values.items():
                setattr(row, field, value)
    else:
        db.add(SysPerfCarModel(workspace_id=workspace.id, **values))
    db.commit()
    return SysPerfStatusResponse(status="ok")


@router.delete("/base/car-models/{model_id}", response_model=SysPerfStatusResponse)
def delete_car_model(
    model_id: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    db.execute(
        delete(SysPerfCarModel).where(
            SysPerfCarModel.workspace_id == workspace.id, SysPerfCarModel.id == model_id
        )
    )
    db.commit()
    return SysPerfStatusResponse(status="ok")


# ── 항목 키워드 오버라이드 (_MI n) ──
class ItemKeywordEntry(SysPerfStrictRequest):
    n: int = Field(gt=0)
    keywords: str = ""


class ItemKeywordsRequest(SysPerfStrictRequest):
    items: list[ItemKeywordEntry]


class ItemKeywordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_n: int
    keywords: str


class ItemKeywordsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[ItemKeywordResponse]


def _item_keyword_response(row: SysPerfItemKeyword) -> ItemKeywordResponse:
    return ItemKeywordResponse(item_n=row.item_n, keywords=row.keywords)


@router.get("/base/item-keywords", response_model=ItemKeywordsResponse)
def get_item_keywords(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> ItemKeywordsResponse:
    rows = db.scalars(
        select(SysPerfItemKeyword).where(SysPerfItemKeyword.workspace_id == workspace.id)
    ).all()
    return ItemKeywordsResponse(data=[_item_keyword_response(row) for row in rows])


@router.post("/base/item-keywords", response_model=SysPerfCountResponse)
def save_item_keywords(
    payload: ItemKeywordsRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfCountResponse:
    for it in payload.items:
        existing = db.scalar(
            select(SysPerfItemKeyword).where(
                SysPerfItemKeyword.workspace_id == workspace.id,
                SysPerfItemKeyword.item_n == it.n,
            )
        )
        if existing:
            existing.keywords = it.keywords
        else:
            db.add(SysPerfItemKeyword(workspace_id=workspace.id, item_n=it.n, keywords=it.keywords))
    db.commit()
    return SysPerfCountResponse(status="ok", count=len(payload.items))


# ── 부품사양 (조합 템플릿) ──
_PARTS_SPEC_FIELDS = (
    "name",
    "car_code",
    "comp",
    "comp_prod",
    "condenser",
    "cond_prod",
    "txv",
    "txv_prod",
    "hvac",
    "hvac_prod",
    "pipe",
    "pipe_prod",
    "refrigerant_charge",
    "note",
)


class PartsSpecItem(SysPerfStrictRequest):
    id: int | None = None
    name: str = Field(min_length=1)
    car_code: str = ""
    comp: str = ""
    comp_prod: int = 1
    condenser: str = ""
    cond_prod: int = 1
    txv: str = ""
    txv_prod: int = 1
    hvac: str = ""
    hvac_prod: int = 1
    pipe: str = ""
    pipe_prod: int = 1
    refrigerant_charge: str = ""
    note: str = ""

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name is required")
        return value


class PartsSpecResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    car_code: str
    comp: str
    comp_prod: int
    condenser: str
    cond_prod: int
    txv: str
    txv_prod: int
    hvac: str
    hvac_prod: int
    pipe: str
    pipe_prod: int
    refrigerant_charge: str
    note: str


class PartsSpecsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[PartsSpecResponse]


def _parts_spec_response(row: SysPerfPartsSpec) -> PartsSpecResponse:
    return PartsSpecResponse(
        id=row.id,
        **{field: getattr(row, field) for field in _PARTS_SPEC_FIELDS},
    )


@router.get("/base/parts-spec", response_model=PartsSpecsResponse)
def get_parts_specs(
    car_code: str = "",
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> PartsSpecsResponse:
    stmt = select(SysPerfPartsSpec).where(SysPerfPartsSpec.workspace_id == workspace.id)
    if car_code:
        stmt = stmt.where(SysPerfPartsSpec.car_code == car_code).order_by(SysPerfPartsSpec.name)
    else:
        stmt = stmt.order_by(SysPerfPartsSpec.car_code, SysPerfPartsSpec.name)
    rows = db.scalars(stmt).all()
    return PartsSpecsResponse(data=[_parts_spec_response(row) for row in rows])


@router.post("/base/parts-spec", response_model=SysPerfStatusResponse)
def save_parts_spec(
    item: PartsSpecItem,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    if item.id:
        row = db.scalar(
            select(SysPerfPartsSpec).where(
                SysPerfPartsSpec.workspace_id == workspace.id, SysPerfPartsSpec.id == item.id
            )
        )
        if row:
            for f in _PARTS_SPEC_FIELDS:
                setattr(row, f, getattr(item, f))
    else:
        db.add(
            SysPerfPartsSpec(
                workspace_id=workspace.id, **{f: getattr(item, f) for f in _PARTS_SPEC_FIELDS}
            )
        )
    db.commit()
    return SysPerfStatusResponse(status="ok")


@router.delete("/base/parts-spec/{spec_id}", response_model=SysPerfStatusResponse)
def delete_parts_spec(
    spec_id: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    db.execute(
        delete(SysPerfPartsSpec).where(
            SysPerfPartsSpec.workspace_id == workspace.id, SysPerfPartsSpec.id == spec_id
        )
    )
    db.commit()
    return SysPerfStatusResponse(status="ok")


# ── 부품 카탈로그 (카테고리별 이름 마스터) ──
class PartsCatalogItem(SysPerfStrictRequest):
    id: int | None = None
    category: str = Field(min_length=1)
    drive_type: str = ""
    sub_type: str = ""
    name: str = Field(min_length=1)
    sort_order: int = 0
    note: str = ""

    @field_validator("category", "name")
    @classmethod
    def _required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value is required")
        return value


class PartsCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    category: str
    drive_type: str
    sub_type: str
    name: str
    sort_order: int
    note: str
    created_at: datetime


class PartsCatalogResponseList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[PartsCatalogResponse]


def _parts_catalog_response(row: SysPerfPartsCatalog) -> PartsCatalogResponse:
    return PartsCatalogResponse(
        id=row.id,
        category=row.category,
        drive_type=row.drive_type,
        sub_type=row.sub_type,
        name=row.name,
        sort_order=row.sort_order,
        note=row.note,
        created_at=row.created_at,
    )


@router.get("/base/parts-catalog", response_model=PartsCatalogResponseList)
def get_parts_catalog(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> PartsCatalogResponseList:
    rows = db.scalars(
        select(SysPerfPartsCatalog)
        .where(SysPerfPartsCatalog.workspace_id == workspace.id)
        .order_by(
            SysPerfPartsCatalog.category,
            SysPerfPartsCatalog.drive_type,
            SysPerfPartsCatalog.sub_type,
            SysPerfPartsCatalog.sort_order,
            SysPerfPartsCatalog.id,
        )
    ).all()
    return PartsCatalogResponseList(data=[_parts_catalog_response(row) for row in rows])


@router.post("/base/parts-catalog", response_model=SysPerfIdResponse)
def save_parts_catalog(
    item: PartsCatalogItem,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfIdResponse:
    category = (item.category or "").strip()
    name = (item.name or "").strip()
    if not category or not name:
        raise localized_http_exception(status_code=400, code="dataviz.parts_catalog_required")
    if item.id:
        row = db.scalar(
            select(SysPerfPartsCatalog).where(
                SysPerfPartsCatalog.workspace_id == workspace.id, SysPerfPartsCatalog.id == item.id
            )
        )
        if row:
            row.category = category
            row.drive_type = (item.drive_type or "").strip()
            row.sub_type = (item.sub_type or "").strip()
            row.name = name
            row.sort_order = item.sort_order or 0
            row.note = (item.note or "").strip()
        db.commit()
        return SysPerfIdResponse(status="ok", id=item.id)
    new = SysPerfPartsCatalog(
        workspace_id=workspace.id,
        category=category,
        drive_type=(item.drive_type or "").strip(),
        sub_type=(item.sub_type or "").strip(),
        name=name,
        sort_order=item.sort_order or 0,
        note=(item.note or "").strip(),
    )
    db.add(new)
    db.commit()
    return SysPerfIdResponse(status="ok", id=new.id)


@router.delete("/base/parts-catalog/{cid}", response_model=SysPerfStatusResponse)
def delete_parts_catalog(
    cid: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfStatusResponse:
    db.execute(
        delete(SysPerfPartsCatalog).where(
            SysPerfPartsCatalog.workspace_id == workspace.id, SysPerfPartsCatalog.id == cid
        )
    )
    db.commit()
    return SysPerfStatusResponse(status="ok")


# ═══ 냉매 물성치 / 상태점 CSV 임포트 ═══


@router.post(
    "/base/refrigerant-props/import",
    response_model=RefrigerantPropsImportResponse,
)
async def import_refrigerant_props(
    file: UploadFile = File(...),
    refrigerant_id: int = Form(...),
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> RefrigerantPropsImportResponse:
    ref = db.scalar(
        select(SysPerfRefrigerantMaster).where(
            SysPerfRefrigerantMaster.workspace_id == workspace.id,
            SysPerfRefrigerantMaster.id == refrigerant_id,
        )
    )
    ref_name = ref.name if ref else ""
    try:
        content = await file.read()
        df, matched_sheet = sp.read_upload_df(content, file.filename or "", ref_name)
        rows, col_map = sp.parse_refrigerant_props_df(df)
        db.execute(
            delete(SysPerfRefrigerantProp).where(
                SysPerfRefrigerantProp.workspace_id == workspace.id,
                SysPerfRefrigerantProp.refrigerant_id == refrigerant_id,
            )
        )
        for r in rows:
            db.add(
                SysPerfRefrigerantProp(
                    workspace_id=workspace.id, refrigerant_id=refrigerant_id, **r
                )
            )
        db.commit()
        return RefrigerantPropsImportResponse(
            status="ok",
            count=len(rows),
            sheet=matched_sheet,
            col_map=col_map,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        db.rollback()
        _raise_processing_failed("refrigerant_props_import", e)


class StatePointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    refrigerant_id: int
    pressure_kpa: float | None
    pressure_kgcm2: float | None
    sat_temperature: float | None
    temperature: float | None
    enthalpy: float | None
    entropy: float | None
    specific_vol: float | None


class StatePointsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[StatePointResponse]


def _state_point_response(row: SysPerfRefrigerantStatePoint) -> StatePointResponse:
    return StatePointResponse(
        id=row.id,
        refrigerant_id=row.refrigerant_id,
        pressure_kpa=row.pressure_kpa,
        pressure_kgcm2=row.pressure_kgcm2,
        sat_temperature=row.sat_temperature,
        temperature=row.temperature,
        enthalpy=row.enthalpy,
        entropy=row.entropy,
        specific_vol=row.specific_vol,
    )


@router.get("/base/state-points", response_model=StatePointsResponse)
def get_state_points(
    refrigerant_id: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> StatePointsResponse:
    rows = db.scalars(
        select(SysPerfRefrigerantStatePoint)
        .where(
            SysPerfRefrigerantStatePoint.workspace_id == workspace.id,
            SysPerfRefrigerantStatePoint.refrigerant_id == refrigerant_id,
        )
        .order_by(
            SysPerfRefrigerantStatePoint.pressure_kpa, SysPerfRefrigerantStatePoint.temperature
        )
    ).all()
    return StatePointsResponse(data=[_state_point_response(row) for row in rows])


@router.post("/base/state-points/import", response_model=SysPerfCountResponse)
async def import_state_points(
    file: UploadFile = File(...),
    refrigerant_id: int = Form(...),
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
    _: object = Depends(_require_ws_admin),
) -> SysPerfCountResponse:
    ref = db.scalar(
        select(SysPerfRefrigerantMaster).where(
            SysPerfRefrigerantMaster.workspace_id == workspace.id,
            SysPerfRefrigerantMaster.id == refrigerant_id,
        )
    )
    ref_name = ref.name if ref else ""
    try:
        content = await file.read()
        df, _matched = sp.read_upload_df(content, file.filename or "", ref_name)
        rows = sp.parse_state_points_df(df)
        db.execute(
            delete(SysPerfRefrigerantStatePoint).where(
                SysPerfRefrigerantStatePoint.workspace_id == workspace.id,
                SysPerfRefrigerantStatePoint.refrigerant_id == refrigerant_id,
            )
        )
        for r in rows:
            db.add(
                SysPerfRefrigerantStatePoint(
                    workspace_id=workspace.id, refrigerant_id=refrigerant_id, **r
                )
            )
        db.commit()
        return SysPerfCountResponse(status="ok", count=len(rows))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        db.rollback()
        _raise_processing_failed("state_points_import", e)


# ═══ DB화 — 시험 마스터 + CSV 링크 ═══

_DB_SAVE_META = [
    "car_code",
    "car_type",
    "engine",
    "stage",
    "car_number",
    "test_item",
    "test_date",
    "refrigerant_charge",
    "comp",
    "indoor_condenser",
    "condenser",
    "cooling_fan",
    "radiator",
    "ihx",
    "txv",
    "battery_chiller",
    "eva",
    "hvac",
    "heater_core",
    "ptc",
]


class DbSaveRequest(SysPerfStrictRequest):
    file_id: int = Field(gt=0)
    sheet_name: str = Field(min_length=1)
    car_code: str
    car_type: str
    engine: str
    stage: str
    car_number: str
    test_item: str
    test_date: str
    refrigerant_charge: str
    comp: str
    indoor_condenser: str
    condenser: str
    cooling_fan: str
    radiator: str
    ihx: str
    txv: str
    battery_chiller: str
    eva: str
    hvac: str
    heater_core: str
    ptc: str


class DbSaveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    test_id: int
    csv: str
    row_count: int
    col_count: int


class DbTestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    file_id: int | None
    filename: str
    sheet_name: str
    saved_at: str
    csv_path: str
    row_count: int
    col_count: int
    car_code: str
    car_type: str
    engine: str
    stage: str
    car_number: str
    test_item: str
    test_date: str
    refrigerant_charge: str
    comp: str
    indoor_condenser: str
    condenser: str
    cooling_fan: str
    radiator: str
    ihx: str
    txv: str
    battery_chiller: str
    eva: str
    hvac: str
    heater_core: str
    ptc: str


class DbListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[DbTestResponse]


def _db_test_response(row: SysPerfTestMaster) -> DbTestResponse:
    values = {
        "id": row.id,
        "file_id": row.file_id,
        "filename": row.filename,
        "sheet_name": row.sheet_name,
        "saved_at": row.saved_at,
        "csv_path": row.csv_path,
        "row_count": row.row_count,
        "col_count": row.col_count,
    }
    values.update({field: getattr(row, field) for field in _DB_SAVE_META})
    return DbTestResponse(**values)


@router.post("/db-save", response_model=DbSaveResponse)
def db_save(
    payload: DbSaveRequest,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> DbSaveResponse:
    if not payload.file_id:
        raise localized_http_exception(status_code=400, code="dataviz.file_id_required")
    raw = payload.model_dump()
    meta = {k: str(raw.get(k) or "").strip() for k in _DB_SAVE_META}
    fm = _file_master(db, workspace.id, payload.file_id)
    if not fm or not fm.file_path or not os.path.exists(fm.file_path):
        raise localized_http_exception(status_code=404, code="dataviz.file_not_found")
    try:
        hdr_row = _get_header_row(db, workspace.id, payload.file_id, payload.sheet_name, 1)
        if fm.file_path.lower().endswith(".csv"):
            df = pd.read_csv(fm.file_path, header=hdr_row)
        else:
            df = pd.read_excel(fm.file_path, sheet_name=payload.sheet_name, header=hdr_row)

        _, csv_dir = sp.workspace_dirs(workspace.id)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r'[<>:"/\\|?*]', "_", os.path.splitext(fm.filename)[0])[:60]
        csv_filename = f"{ts}_{safe}.csv"
        df.to_csv(os.path.join(csv_dir, csv_filename), index=False, encoding="utf-8-sig")

        tm = SysPerfTestMaster(
            workspace_id=workspace.id,
            file_id=int(payload.file_id),
            filename=fm.filename,
            sheet_name=payload.sheet_name,
            csv_path=csv_filename,
            row_count=int(len(df)),
            col_count=int(len(df.columns)),
            **meta,
        )
        db.add(tm)
        db.commit()
        return DbSaveResponse(
            status="ok",
            test_id=tm.id,
            csv=csv_filename,
            row_count=len(df),
            col_count=len(df.columns),
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        db.rollback()
        _raise_processing_failed("db_save", e)


@router.get("/db-list", response_model=DbListResponse)
def db_list(
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> DbListResponse:
    rows = db.scalars(
        select(SysPerfTestMaster)
        .where(SysPerfTestMaster.workspace_id == workspace.id)
        .order_by(SysPerfTestMaster.id.desc())
    ).all()
    return DbListResponse(data=[_db_test_response(row) for row in rows])


@router.get("/db-csv/{test_id}")
def db_csv(
    test_id: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
):
    r = db.scalar(
        select(SysPerfTestMaster).where(
            SysPerfTestMaster.workspace_id == workspace.id, SysPerfTestMaster.id == test_id
        )
    )
    if not r:
        raise localized_http_exception(status_code=404, code="dataviz.saved_test_not_found")
    _, csv_dir = sp.workspace_dirs(workspace.id)
    path = os.path.join(csv_dir, r.csv_path or "")
    if not r.csv_path or not os.path.exists(path):
        raise localized_http_exception(status_code=404, code="dataviz.csv_file_missing")
    return FileResponse(path, media_type="text/csv", filename=f"test{test_id}_{r.csv_path}")


@router.delete("/db-delete/{test_id}", response_model=SysPerfStatusResponse)
def db_delete(
    test_id: int,
    db: Session = Depends(get_db_session),
    workspace: Workspace = Depends(require_current_workspace),
) -> SysPerfStatusResponse:
    r = db.scalar(
        select(SysPerfTestMaster).where(
            SysPerfTestMaster.workspace_id == workspace.id, SysPerfTestMaster.id == test_id
        )
    )
    if r:
        _, csv_dir = sp.workspace_dirs(workspace.id)
        csv_full = os.path.join(csv_dir, r.csv_path or "")
        if r.csv_path and os.path.exists(csv_full):
            try:
                os.remove(csv_full)
            except OSError:
                pass
        db.delete(r)
        db.commit()
    return SysPerfStatusResponse(status="ok")
