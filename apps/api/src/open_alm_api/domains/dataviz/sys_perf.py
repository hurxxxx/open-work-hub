"""시스템 성능 — 레거시 sys_perf_routes.py 의 파싱/분석 로직 포팅(헬퍼).

Flask/sqlite3 의존만 제거하고(세션·sqlite3 → FastAPI·SQLAlchemy), 헤더 자동감지·파일명
정규식 파싱·시트 분석 로직은 원본 그대로 옮긴다. 업로드 원본 파일은 워크스페이스별 디스크
디렉터리에 보관(레거시 UPLOAD_DIR/CSV_DIR 대응)하고 경로를 file_master 에 저장한다.
"""

from __future__ import annotations

import io
import math
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from open_alm_api.core.settings import get_settings

# CoolProp (선택) — 사이클/선도 라우트에서만 사용. 없으면 폴백.
try:
    from CoolProp.CoolProp import PropsSI  # noqa: F401

    HAS_COOLPROP = True
except Exception:
    HAS_COOLPROP = False
    PropsSI = None  # type: ignore

# 사이클 포인트(클라이언트 표시키) → DB standard_name(_MI n_nm 포맷). 원본 CYCLE_MAP.
CYCLE_MAP = {
    "Comp In Pressure": "4_COMP IN",
    "Comp In Temperature": "13_COMP IN",
    "Comp Out Pressure": "5_COMP OUT",
    "Comp Out Temperature": "14_COMP OUT",
    "Condenser In Pressure": "7_COND IN",
    "Condenser In Temperature": "15_COND IN AVG",
    "Condenser Out Pressure": "8_COND OUT",
    "Condenser Out Temperature": "32_COND OUT",
    "TXV In Pressure": "9_TXV IN, ENG.TEI",
    "TXV In Temperature": "33_TXV IN",
    "TXV Out Pressure": "10_TXV OUT, ENG TEO",
    "TXV Out Temperature": "34_TXV OUT",
    "Evap In Pressure": "11_EVA IN",
    "Evap In Temperature": "35_EVA IN",
    "Evap Out Pressure": "12_EVA OUT",
    "Evap Out Temperature": "36_EVA OUT",
}

# 포인트별 "진짜 센서" 판정 키워드 (원본 CYCLE_STD_KW).
CYCLE_STD_KW = {
    "Comp In Pressure": ["PS", "Ps", "P_s", "Psuc"],
    "Comp In Temperature": ["TS", "Ts", "T_s", "Tsuc"],
    "Comp Out Pressure": ["PD", "Pd", "P_d", "PCO"],
    "Comp Out Temperature": ["TD", "Td", "T_d"],
    "Condenser In Pressure": ["PCI", "PCondIn"],
    "Condenser In Temperature": ["TCI", "TCondIn"],
    "Condenser Out Pressure": ["PCond", "PCOND", "PCondOut"],
    "Condenser Out Temperature": ["TCO", "TCOUT", "TCondOut"],
    "TXV In Pressure": ["PEI", "PTXV IN", "PTXVIN", "P_txvin"],
    "TXV In Temperature": ["E/TEI", "TEI", "TTXV IN", "TTXVIN", "T_txvin"],
    "TXV Out Pressure": ["PEO", "PTXV OUT", "PTXVOUT", "P_txvout"],
    "TXV Out Temperature": ["E/TEO", "TEO", "TTXV OUT", "TTXVOUT", "T_txvout"],
    "Evap In Pressure": ["EVA IN PRESS", "EVA IN P", "PEVAIN", "P_evain"],
    "Evap In Temperature": ["TEVA IN", "TEVAIN", "T_evain"],
    "Evap Out Pressure": ["EVA OUT P", "PEVAOUT", "P_evaout"],
    "Evap Out Temperature": ["TEVA OUT", "TEVAOUT", "T_evaout"],
}

POINT_LABEL_PT = {
    "Comp In": "Ps, Ts",
    "Comp Out": "Pd, Td",
    "Condenser In": "Pci, Tci",
    "Condenser Out": "Pco, Tco",
    "TXV In": "P_txvin, T_txvin",
    "TXV Out": "P_txvout, T_txvout",
    "Evap In": "PEvaIn, TEvaIn",
    "Evap Out": "PEvaOut, TEvaOut",
}

CYCLE_POINTS = [
    "Comp In", "Comp Out", "Condenser In", "Condenser Out",
    "TXV In", "TXV Out", "Evap In", "Evap Out",
]
KGFCM2_TO_PA = 98066.5


def _sysperf_root() -> str:
    return str(Path(get_settings().dataviz_sysperf_storage_dir).expanduser())


def workspace_dirs(workspace_id: str) -> tuple[str, str]:
    """(uploads_dir, csv_dir) — 워크스페이스별, 없으면 생성."""
    root = _sysperf_root()
    up = os.path.join(root, workspace_id, "uploads")
    csv = os.path.join(root, workspace_id, "csv")
    os.makedirs(up, exist_ok=True)
    os.makedirs(csv, exist_ok=True)
    return up, csv


def clean_nan(obj):
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_nan(v) for v in obj]
    return obj


# ── 헤더 행 자동감지 (원본 _detect_header_row 그대로) ──
_BASE_HEADER_KW = {
    "time", "ps", "ts", "pd", "td", "pc", "pci", "pco", "pcond", "pei", "peo",
    "tci", "tco", "tei", "teo", "e/tei", "e/teo", "ttxv", "ptxv",
    "comp", "cond", "txv", "eva", "evap", "amb", "ambient", "humidity",
    "room", "roomavg", "brea", "foot", "rpm", "kmh", "fbl", "crank",
    "mass flow", "volt", "cop", "ocr", "torque", "power", "cap",
}


def detect_header_row(df_raw: pd.DataFrame, extra_keywords: set[str] | None = None, max_scan: int = 60):
    """시트 상위 max_scan행 스캔 → 센서명 많이 든 행을 헤더로. 반환 (header_idx, info_idx) 0-based.
    실패 시 (1, 0) 폴백(레거시 2행 헤더 관례).
    """
    base_kw = set(_BASE_HEADER_KW)
    if extra_keywords:
        for k in extra_keywords:
            kk = (k or "").strip().lower()
            if kk and len(kk) >= 2:
                base_kw.add(kk)

    best_row, best_count = -1, 0
    scan = min(max_scan, len(df_raw))
    for i in range(scan):
        row = df_raw.iloc[i]
        count = 0
        for cell in row:
            s = str(cell).strip().lower()
            if not s or s == "nan":
                continue
            if s in base_kw:
                count += 2
                continue
            for kw in base_kw:
                if len(kw) >= 3 and (kw in s or s in kw):
                    count += 1
                    break
        if count > best_count:
            best_count = count
            best_row = i

    if best_count >= 5 and best_row >= 0:
        info_row = 0
        for j in range(best_row - 1, -1, -1):
            first = str(df_raw.iloc[j, 0]).strip()
            if first and first != "nan":
                info_row = j
                break
        return best_row, info_row
    return 1, 0


# ── 파일명 파싱 (원본 /upload 의 정규식 그대로) ──
def parse_filename(fname: str) -> tuple[dict, str]:
    """파일명 → (auto_match dict, car_code). comp/txv/condenser/냉매량/시험항목/일자 추출."""
    auto: dict[str, str] = {}
    code_m = re.match(r"^([A-Za-z0-9]+)", fname)
    car_code = code_m.group(1) if code_m else ""
    auto["car_code"] = car_code

    paren_m = re.search(r"\((.+?)\)", fname)
    paren_text = paren_m.group(1) if paren_m else ""

    comp_m = re.search(r"(DVE?\d+[A-Za-z]*|VS\d+|VSB\d+)", paren_text, re.I)
    auto["comp"] = comp_m.group(1) if comp_m else ""
    txv_m = re.search(r"TXV\s*([\d.]+\s*RT[^,]*)", paren_text, re.I)
    auto["txv"] = ("TXV " + txv_m.group(1).strip()) if txv_m else ""
    cond_m = re.search(r"(\d+종[#\d]*\s*COND[^,]*)", paren_text, re.I)
    auto["condenser"] = cond_m.group(1).strip() if cond_m else ""
    ref_m = re.search(r"냉매량?\s*(\d+)\s*g", paren_text)
    auto["refrigerant_charge"] = (ref_m.group(1) + "g") if ref_m else ""

    after_paren = fname[paren_m.end():] if paren_m else fname
    item_m = re.match(r"\s*(.+?)\s*\d{2}[\.\-]", after_paren)
    auto["test_item"] = item_m.group(1).strip() if item_m else ""
    date_m = re.search(r"(\d{2}[\.\-]\d{2}[\.\-]\d{2})", fname)
    auto["test_date"] = date_m.group(1) if date_m else ""
    return auto, car_code


_SCORE_KW = [
    "time", "ts", "ps", "pd", "tci", "tco", "pci", "pco", "pcond", "pei", "peo",
    "tei", "teo", "e/tei", "e/teo", "amb", "ambient", "humidity", "rpm", "fbl",
    "comp in", "comp out", "cond in", "cond out", "txv in", "txv out", "eva in", "eva out",
    "roomavg", "brea", "foot", "cond sc", "txv in sc", "eva sh", "comp sh", "압축비",
]


def lttb_indices(data_arr, threshold: int) -> list[int]:
    """LTTB 다운샘플 인덱스 반환 (원본 _lttb_indices 그대로). Time 축 기준 적용용."""
    n = len(data_arr)
    if n <= threshold:
        return list(range(n))
    sampled = [0]
    every = (n - 2) / (threshold - 2)
    a = 0
    for i in range(1, threshold - 1):
        avg_start = int((i) * every) + 1
        avg_end = int((i + 1) * every) + 1
        if avg_end > n:
            avg_end = n
        avg_val = np.nanmean(data_arr[avg_start:avg_end])
        rng_start = int((i - 1) * every) + 1
        rng_end = int(i * every) + 1
        if rng_end > n:
            rng_end = n
        max_area = -1
        next_a = rng_start
        for j in range(rng_start, rng_end):
            area = abs(
                (j - a) * (avg_val - data_arr[a])
                - (data_arr[j] - data_arr[a]) * ((avg_start + avg_end) / 2 - a)
            )
            if area > max_area:
                max_area = area
                next_a = j
        sampled.append(next_a)
        a = next_a
    sampled.append(n - 1)
    return sampled


# 냉매별 선도 배경 캐시 — PropsSI 수천 회라 재계산 방지(배경은 냉매에만 의존, 정적).
_PH_DIAGRAM_CACHE: dict[str, dict] = {}


def compute_ph_diagram(refrigerant: str) -> dict:
    """P-H 선도 배경(포화곡선·등온/등엔트로피/등건도/등비체적선·임계점)을 PropsSI 로 계산.
    냉매명에만 의존 → 캐시. 반환 dict 는 status/flag 없이 물리값만. (원본 get_ph_diagram_data 그대로)
    """
    if refrigerant in _PH_DIAGRAM_CACHE:
        return _PH_DIAGRAM_CACHE[refrigerant]
    result: dict = {
        "saturation": {"h": [], "p": []},
        "isotherms": [],
        "isentropes": [],
        "isoquality": [],
        "isochor": [],
        "critical": {"T": None, "P": None, "h": None},
    }
    ref = refrigerant.replace("-", "")
    T_crit = PropsSI("Tcrit", ref)
    P_crit = PropsSI("Pcrit", ref)
    result["critical"] = {"T": T_crit - 273.15, "P": P_crit / 1000, "h": None}

    # 1. 포화 곡선 (Q=0 + Q=1 역순)
    T_min = max(200.0, PropsSI("Ttriple", ref) + 0.5)
    T_max = T_crit - 0.05
    Ts = np.linspace(T_min, T_max, 120)
    hf, Pf, hg, Pg = [], [], [], []
    for T in Ts:
        try:
            P = PropsSI("P", "T", T, "Q", 0, ref) / 1000.0
            h_f = PropsSI("H", "T", T, "Q", 0, ref) / 1000.0
            h_g = PropsSI("H", "T", T, "Q", 1, ref) / 1000.0
            if not (math.isnan(P) or math.isnan(h_f) or math.isnan(h_g)):
                hf.append(h_f)
                Pf.append(P)
                hg.append(h_g)
                Pg.append(P)
        except Exception:
            continue
    result["saturation"]["h"] = hf + list(reversed(hg))
    result["saturation"]["p"] = Pf + list(reversed(Pg))
    if hf and hg:
        result["critical"]["h"] = (hf[-1] + hg[-1]) / 2

    # 2. 등온선 (-40~140℃, 10℃)
    for T_c in range(-40, 141, 10):
        T = T_c + 273.15
        iso_h, iso_p = [], []
        try:
            if T < T_crit:
                P_sat = PropsSI("P", "T", T, "Q", 0, ref)
                for P in np.logspace(np.log10(min(P_crit * 1.5, 5e7)), np.log10(P_sat * 1.001), 25):
                    try:
                        h = PropsSI("H", "T", T, "P", P, ref) / 1000.0
                        if not math.isnan(h):
                            iso_h.append(h)
                            iso_p.append(P / 1000.0)
                    except Exception:
                        continue
                try:
                    h_f = PropsSI("H", "T", T, "Q", 0, ref) / 1000.0
                    h_g = PropsSI("H", "T", T, "Q", 1, ref) / 1000.0
                    iso_h.append(h_f)
                    iso_p.append(P_sat / 1000.0)
                    iso_h.append(h_g)
                    iso_p.append(P_sat / 1000.0)
                except Exception:
                    pass
                for P in np.logspace(np.log10(P_sat * 0.999), np.log10(5e4), 25):
                    try:
                        h = PropsSI("H", "T", T, "P", P, ref) / 1000.0
                        if not math.isnan(h):
                            iso_h.append(h)
                            iso_p.append(P / 1000.0)
                    except Exception:
                        continue
            else:
                for P in np.logspace(np.log10(5e4), np.log10(5e7), 50):
                    try:
                        h = PropsSI("H", "T", T, "P", P, ref) / 1000.0
                        if not math.isnan(h):
                            iso_h.append(h)
                            iso_p.append(P / 1000.0)
                    except Exception:
                        continue
            if iso_h:
                result["isotherms"].append({"T": T_c, "h": iso_h, "p": iso_p})
        except Exception:
            continue

    # 3. 등엔트로피선 (0.90~2.20, 0.05)
    for s_val in np.arange(0.90, 2.20, 0.05):
        s = float(s_val * 1000)
        iso_h, iso_p = [], []
        for P in np.logspace(np.log10(5e4), np.log10(min(P_crit * 1.5, 5e7)), 60):
            try:
                h = PropsSI("H", "S", s, "P", P, ref) / 1000.0
                if not math.isnan(h):
                    iso_h.append(h)
                    iso_p.append(P / 1000.0)
            except Exception:
                continue
        if len(iso_h) >= 3:
            result["isentropes"].append({"s": round(float(s_val), 2), "h": iso_h, "p": iso_p})

    # 4. 등건도선 (Q=0.1~0.9)
    for Q in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        iso_h, iso_p = [], []
        for T in np.linspace(T_min, T_crit - 0.5, 80):
            try:
                h = PropsSI("H", "T", T, "Q", Q, ref) / 1000.0
                P = PropsSI("P", "T", T, "Q", Q, ref) / 1000.0
                if not (math.isnan(h) or math.isnan(P)):
                    iso_h.append(h)
                    iso_p.append(P)
            except Exception:
                continue
        if iso_h:
            result["isoquality"].append({"Q": Q, "h": iso_h, "p": iso_p})

    # 5. 등비체적선 (밀도별, 과열 영역)
    for rho in [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500]:
        iso_h, iso_p = [], []
        for T in np.linspace(T_min, T_crit + 200, 60):
            try:
                P = PropsSI("P", "T", T, "D", rho, ref) / 1000.0
                h = PropsSI("H", "T", T, "D", rho, ref) / 1000.0
                if 50 <= P <= 50000 and 50 <= h <= 500:
                    iso_h.append(h)
                    iso_p.append(P)
            except Exception:
                continue
        if len(iso_h) >= 3:
            result["isochor"].append({"rho": rho, "h": iso_h, "p": iso_p})

    _PH_DIAGRAM_CACHE[refrigerant] = result
    return result


_TS_DIAGRAM_CACHE: dict[str, dict] = {}


def compute_ts_diagram(refrigerant: str) -> dict:
    """T-S 선도 배경(포화곡선 s/T·등압선·등엔탈피선·임계점). 원본 get_ts_diagram_data 그대로. 냉매별 캐시."""
    if refrigerant in _TS_DIAGRAM_CACHE:
        return _TS_DIAGRAM_CACHE[refrigerant]
    result: dict = {
        "saturation": {"s": [], "t": []},
        "isobars": [],
        "isenthalps": [],
        "critical": {"T": None, "s": None, "P": None},
    }
    ref = refrigerant.replace("-", "")
    T_crit = PropsSI("Tcrit", ref)
    P_crit = PropsSI("Pcrit", ref)

    # 1. 포화곡선 (Q=0 + Q=1 역순)
    T_min = max(200.0, PropsSI("Ttriple", ref) + 0.5)
    T_max = T_crit - 0.05
    sf, Tf, sg, Tg = [], [], [], []
    for T in np.linspace(T_min, T_max, 120):
        try:
            s_f = PropsSI("S", "T", T, "Q", 0, ref) / 1000.0
            s_g = PropsSI("S", "T", T, "Q", 1, ref) / 1000.0
            if not (math.isnan(s_f) or math.isnan(s_g)):
                sf.append(s_f)
                Tf.append(T - 273.15)
                sg.append(s_g)
                Tg.append(T - 273.15)
        except Exception:
            continue
    result["saturation"]["s"] = sf + list(reversed(sg))
    result["saturation"]["t"] = Tf + list(reversed(Tg))
    if sf and sg:
        result["critical"] = {"T": T_crit - 273.15, "s": (sf[-1] + sg[-1]) / 2, "P": P_crit / 1000}

    # 2. 등압선 (logspace 14개) — 과냉→포화 수평→과열, 초임계는 전 온도 범위
    for P in np.logspace(np.log10(5e4), np.log10(min(P_crit * 1.5, 5e7)), 14):
        iso_s, iso_t = [], []
        try:
            if P < P_crit:
                T_sat = PropsSI("T", "P", P, "Q", 0, ref)
                for T in np.linspace(T_min, T_sat - 0.5, 20):
                    try:
                        s = PropsSI("S", "T", T, "P", P, ref) / 1000.0
                        if not math.isnan(s):
                            iso_s.append(s)
                            iso_t.append(T - 273.15)
                    except Exception:
                        continue
                try:
                    s_f = PropsSI("S", "T", T_sat, "Q", 0, ref) / 1000.0
                    s_g = PropsSI("S", "T", T_sat, "Q", 1, ref) / 1000.0
                    iso_s.append(s_f)
                    iso_t.append(T_sat - 273.15)
                    iso_s.append(s_g)
                    iso_t.append(T_sat - 273.15)
                except Exception:
                    pass
                for T in np.linspace(T_sat + 0.5, T_crit + 200, 20):
                    try:
                        s = PropsSI("S", "T", T, "P", P, ref) / 1000.0
                        if not math.isnan(s):
                            iso_s.append(s)
                            iso_t.append(T - 273.15)
                    except Exception:
                        continue
            else:
                for T in np.linspace(T_min, T_crit + 200, 40):
                    try:
                        s = PropsSI("S", "T", T, "P", P, ref) / 1000.0
                        if not math.isnan(s):
                            iso_s.append(s)
                            iso_t.append(T - 273.15)
                    except Exception:
                        continue
            if len(iso_s) >= 3:
                result["isobars"].append({
                    "P_kpa": round(P / 1000, 1),
                    "P_kgf": round(P / 98066.5, 2),
                    "s": iso_s,
                    "t": iso_t,
                })
        except Exception:
            continue

    # 3. 등엔탈피선 (120~460 kJ/kg, 30 간격)
    for h_val in np.arange(120, 461, 30):
        h_J = float(h_val) * 1000
        iso_s, iso_t = [], []
        for P in np.logspace(np.log10(5e4), np.log10(min(P_crit * 1.3, 5e7)), 30):
            try:
                T_K = PropsSI("T", "H", h_J, "P", P, ref)
                s = PropsSI("S", "H", h_J, "P", P, ref) / 1000.0
                if not (math.isnan(T_K) or math.isnan(s)):
                    iso_s.append(s)
                    iso_t.append(T_K - 273.15)
            except Exception:
                continue
        if len(iso_s) >= 3:
            result["isenthalps"].append({"h": float(h_val), "s": iso_s, "t": iso_t})

    _TS_DIAGRAM_CACHE[refrigerant] = result
    return result


# ── 냉매 물성/상태점 CSV·Excel 임포트 파싱 (원본 _read_upload_df 등 그대로) ──
def _is_unit_row(row) -> bool:
    unit_keywords = ["℃", "c", "kpa", "bar", "kj", "kg", "m3", "m³", "%", "kgf", "rpm", "kw", "nm"]
    count = 0
    for v in row:
        s = str(v).lower().strip()
        if any(u in s for u in unit_keywords) or s == "" or s == "nan":
            count += 1
    return count >= len(row) * 0.5


def _combine_header(df_raw) -> list[str]:
    names = [str(v) if str(v) != "nan" else "" for v in df_raw.iloc[0]]
    units = [str(v) if str(v) != "nan" else "" for v in df_raw.iloc[1]]
    combined = [(n + "(" + u + ")") if (u and u != n) else n for n, u in zip(names, units)]
    seen: dict[str, int] = {}
    for i, c in enumerate(combined):
        if c in seen:
            seen[c] += 1
            combined[i] = c + "_" + str(seen[c])
        else:
            seen[c] = 0
    return combined


def read_upload_df(content: bytes, filename: str, ref_name: str = ""):
    """업로드 파일(bytes) → DataFrame. xlsx 냉매명 시트 자동매칭 + 2행 헤더(이름+단위) 인식."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".xlsx", ".xls"):
        xls = pd.ExcelFile(io.BytesIO(content))
        sheet = None
        for sn in xls.sheet_names:
            if ref_name and ref_name.lower() in sn.lower():
                sheet = sn
                break
        if sheet is None:
            sheet = xls.sheet_names[0]
        df_raw = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=3)
        if len(df_raw) >= 2 and _is_unit_row(df_raw.iloc[1]):
            combined = _combine_header(df_raw)
            df = pd.read_excel(xls, sheet_name=sheet, header=None, skiprows=2)
            df.columns = combined[: len(df.columns)]
        else:
            df = pd.read_excel(xls, sheet_name=sheet)
        return df, sheet
    # CSV
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            text = content.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        text = content.decode("utf-8", errors="replace")
    sep = "\t" if "\t" in text.split("\n")[0] else ","
    df_check = pd.read_csv(io.StringIO(text), sep=sep, header=None, nrows=3)
    if len(df_check) >= 2 and _is_unit_row(df_check.iloc[1]):
        combined = _combine_header(df_check)
        df = pd.read_csv(io.StringIO(text), sep=sep, header=None, skiprows=2)
        df.columns = combined[: len(df.columns)]
    else:
        df = pd.read_csv(io.StringIO(text), sep=sep)
    return df, ""


def parse_refrigerant_props_df(df) -> tuple[list[dict], dict]:
    """냉매 물성치 df → (rows, col_map). 키워드 매핑·밀도→비체적·압력 3단위 보간 (원본 그대로)."""
    col_map: dict[str, object] = {}
    for c in df.columns:
        cl = str(c).lower().strip()
        if col_map.get("temperature") is None and ("temp" in cl or "온도" in cl or cl in ("t", "tc")):
            col_map["temperature"] = c
        elif "kgf" in cl or ("kg/" in cl and "cm" in cl) or "kgcm" in cl:
            col_map["sat_pressure_kgcm2"] = c
        elif "kpa" in cl:
            col_map["sat_pressure_kpa"] = c
        elif "bar" in cl:
            col_map["sat_pressure_bar"] = c
        elif ("액" in cl or "liq" in cl) and ("밀도" in cl or "density" in cl):
            col_map["_liq_density"] = c
        elif ("증기" in cl or "vap" in cl) and ("밀도" in cl or "density" in cl):
            col_map["_vap_density"] = c
        elif ("액" in cl or "liq" in cl or cl == "hf") and ("엔탈" in cl or "enth" in cl or cl == "hf"):
            col_map["liq_enthalpy"] = c
        elif ("증기" in cl or "vap" in cl or cl == "hg") and ("엔탈" in cl or "enth" in cl or cl == "hg"):
            col_map["vap_enthalpy"] = c
        elif ("액" in cl or "liq" in cl or cl == "sf") and ("엔트" in cl or "entrop" in cl or cl == "sf"):
            col_map["liq_entropy"] = c
        elif ("증기" in cl or "vap" in cl or cl == "sg") and ("엔트" in cl or "entrop" in cl or cl == "sg"):
            col_map["vap_entropy"] = c
        elif ("액" in cl or "liq" in cl or cl == "vf") and ("비체적" in cl or "vol" in cl or cl == "vf"):
            col_map["liq_specific_vol"] = c
        elif ("증기" in cl or "vap" in cl or cl == "vg") and ("비체적" in cl or "vol" in cl or cl == "vg"):
            col_map["vap_specific_vol"] = c

    rows = []
    for _, row in df.iterrows():
        r: dict = {}
        for prop, src_col in col_map.items():
            if prop.startswith("_"):
                continue
            val = row[src_col]
            r[prop] = float(val) if pd.notna(val) else None
        if "_liq_density" in col_map:
            rho = row[col_map["_liq_density"]]
            if pd.notna(rho) and float(rho) != 0:
                r["liq_specific_vol"] = 1.0 / float(rho)
        if "_vap_density" in col_map:
            rho = row[col_map["_vap_density"]]
            if pd.notna(rho) and float(rho) != 0:
                r["vap_specific_vol"] = 1.0 / float(rho)
        if r.get("sat_pressure_kpa") is not None:
            p = r["sat_pressure_kpa"]
            r.setdefault("sat_pressure_kgcm2", None)
            if r.get("sat_pressure_kgcm2") is None:
                r["sat_pressure_kgcm2"] = p / 98.0665
            if r.get("sat_pressure_bar") is None:
                r["sat_pressure_bar"] = p / 100.0
        elif r.get("sat_pressure_kgcm2") is not None:
            p = r["sat_pressure_kgcm2"]
            if r.get("sat_pressure_kpa") is None:
                r["sat_pressure_kpa"] = p * 98.0665
            if r.get("sat_pressure_bar") is None:
                r["sat_pressure_bar"] = p * 0.980665
        elif r.get("sat_pressure_bar") is not None:
            p = r["sat_pressure_bar"]
            if r.get("sat_pressure_kgcm2") is None:
                r["sat_pressure_kgcm2"] = p * 1.01972
            if r.get("sat_pressure_kpa") is None:
                r["sat_pressure_kpa"] = p * 100.0
        rows.append(r)
    return rows, {k: str(v) for k, v in col_map.items()}


def parse_state_points_df(df) -> list[dict]:
    """상태점 df → rows. 키워드 매핑 + fallback 컬럼순서 + 압력 단위 보간 (원본 그대로)."""
    col_map: dict[str, object] = {}
    for c in df.columns:
        cl = str(c).lower().strip()
        if ("압력" in cl or "press" in cl or "p(" in cl) and ("kpa" in cl):
            col_map["pressure_kpa"] = c
        elif ("압력" in cl or "press" in cl or "p(" in cl) and ("kg" in cl or "kgf" in cl):
            col_map["pressure_kgcm2"] = c
        elif "포화" in cl or ("sat" in cl and ("온도" in cl or "temp" in cl)):
            col_map["sat_temperature"] = c
        elif "온도" in cl or "temp" in cl or cl in ("t", "t(c)"):
            col_map["temperature"] = c
        elif "엔탈" in cl or "enthalp" in cl or cl in ("h", "h(kj/kg)"):
            col_map["enthalpy"] = c
        elif "엔트" in cl or "entrop" in cl or cl in ("s", "s(kj/kgk)"):
            col_map["entropy"] = c
        elif "비체적" in cl or "vol" in cl or cl in ("v", "v(m3/kg)"):
            col_map["specific_vol"] = c
    cols = list(df.columns)
    for i, p in enumerate(["pressure_kpa", "sat_temperature", "temperature", "enthalpy", "entropy"]):
        if p not in col_map and i < len(cols):
            col_map[p] = cols[i]

    rows = []
    for _, row in df.iterrows():
        r: dict = {}
        for prop, src_col in col_map.items():
            val = row[src_col]
            r[prop] = float(val) if pd.notna(val) else None
        if r.get("pressure_kgcm2") is not None and r.get("pressure_kpa") is None:
            r["pressure_kpa"] = r["pressure_kgcm2"] * 98.0665
        elif r.get("pressure_kpa") is not None and r.get("pressure_kgcm2") is None:
            r["pressure_kgcm2"] = r["pressure_kpa"] / 98.0665
        rows.append(r)
    return rows


def _sheet_score(headers: list[str]) -> int:
    s = 0
    for h in headers:
        hl = str(h).strip().lower()
        if not hl or hl == "nan":
            continue
        for kw in _SCORE_KW:
            if kw in hl:
                s += 1
                break
    return s


def analyze_workbook(path: str, extra_keywords: set[str] | None = None):
    """엑셀 파일 분석 → (sheet_info[list], all_sheets[list], sheet_headers[list]).

    레거시 /upload 의 시트 선별·헤더감지·헤더별 numeric 카운트 로직 그대로.
    """
    xls = pd.ExcelFile(path)
    sheets = list(xls.sheet_names)
    hash_sheets = [s for s in sheets if s.startswith("#")]
    candidate_sheets = hash_sheets if hash_sheets else sheets[:5]

    sheet_info: list[dict] = []
    sheet_headers: list[dict] = []
    for sn in candidate_sheets:
        try:
            df_sample_raw = pd.read_excel(path, sheet_name=sn, header=None, nrows=5000)
        except Exception:
            continue
        df_head = df_sample_raw.head(60)
        hdr_row, info_row = detect_header_row(df_head, extra_keywords)

        if (
            not sn.startswith("#")
            and hdr_row == 1
            and (
                len(df_head) < 3
                or all(str(v).strip().lower() in ("", "nan") for v in df_head.iloc[1].tolist())
            )
        ):
            continue

        info_text = str(df_head.iloc[info_row, 0]) if len(df_head) > info_row else ""
        headers: list[str] = []
        if len(df_head) > hdr_row:
            headers = [
                str(v).strip()
                for v in df_head.iloc[hdr_row].tolist()
                if str(v).strip() and str(v).strip().lower() != "nan"
            ]

        header_stats: dict[str, int] = {}
        try:
            if len(df_sample_raw) > hdr_row + 1:
                cols_full = df_sample_raw.iloc[hdr_row].astype(str).tolist()
                df_data = df_sample_raw.iloc[hdr_row + 1:].reset_index(drop=True)
                df_data.columns = cols_full
                for c in df_data.columns:
                    cs = str(c).strip()
                    if not cs or cs.lower() == "nan":
                        continue
                    try:
                        col_data = df_data[c]
                        if isinstance(col_data, pd.DataFrame):
                            col_data = col_data.iloc[:, 0]
                        cnt = int(pd.to_numeric(col_data, errors="coerce").notna().sum())
                    except Exception:
                        cnt = 0
                    header_stats[cs] = cnt
        except Exception:
            pass

        sheet_info.append({
            "sheet_name": sn,
            "info_text": info_text,
            "headers": headers,
            "header_count": len(headers),
            "header_row": hdr_row,
            "info_row": info_row,
            "header_numeric_counts": header_stats,
        })
        sheet_headers.append({"sheet_name": sn, "header_row": hdr_row, "info_row": info_row})

    if len(sheet_info) > 1:
        sheet_info.sort(key=lambda si: _sheet_score(si.get("headers", [])), reverse=True)

    return sheet_info, sheets, sheet_headers
