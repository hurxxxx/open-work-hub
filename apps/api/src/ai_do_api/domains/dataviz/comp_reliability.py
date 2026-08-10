"""컴프 신뢰성(복합내구벤치 + 간이벤치) — 레거시 08_data_viz/routes.py 포팅.

엑셀/CSV 파싱·헤더 자동감지·CH↔Signal 매핑·LTTB 다운샘플링·전동 X축 슬라이싱 로직은
원본 Flask 구현을 그대로 옮긴 것이다. Flask 의존(session/request/jsonify)만 제거하고,
업로드→그래프 사이의 상태는 세션 대신 (workspace, type, machine, test_item)로 결정되는
pkl 파일 경로로 전달한다(원본도 경로가 그 셋으로 결정적이었다).
"""

from __future__ import annotations

import math
import os
import re
import tempfile

import numpy as np
import pandas as pd

# 업로드 병합 결과(pkl) 저장 루트 — 워크스페이스별 하위 디렉터리.
# 원본의 C:\cache\ido_portal\durability 를 OS 임시 디렉터리 기반으로 대체.
DUR_ROOT = os.path.join(tempfile.gettempdir(), "aido_dataviz_durability")

SKIP_COLS = {"Elapse Time(Abs)", "Elapse Time", "Test Step no"}


def clean_nan(obj):
    """NaN/Infinity → None 재귀 변환 (원본 _safe_json._clean)."""
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


def dur_pkl_path(workspace_id: str, dur_type: str, machine: str, test_item: str) -> str:
    """병합 데이터 pkl 경로 — (type, machine, test_item)로 결정적. 파일명 안전화."""
    safe = re.sub(r"[^\w가-힣]", "_", f"{dur_type}_{machine}_{test_item}")
    return os.path.join(DUR_ROOT, workspace_id, f"merged_{safe}.pkl")


# ═══ LTTB 다운샘플링 (원본 _lttb / _lttb_columns 그대로) ═══

def _lttb(x, y, threshold):
    """LTTB (Largest Triangle Three Buckets) 다운샘플링."""
    n = len(x)
    if threshold >= n or threshold <= 2:
        return x, y

    mask = ~(np.isnan(x) | np.isnan(y))
    x_clean = x[mask]
    y_clean = y[mask]
    n = len(x_clean)
    if threshold >= n:
        return x_clean, y_clean

    sampled_x = np.zeros(threshold)
    sampled_y = np.zeros(threshold)

    sampled_x[0] = x_clean[0]
    sampled_y[0] = y_clean[0]
    sampled_x[threshold - 1] = x_clean[n - 1]
    sampled_y[threshold - 1] = y_clean[n - 1]

    bucket_size = (n - 2) / (threshold - 2)
    a_idx = 0

    for i in range(1, threshold - 1):
        bucket_start = int(math.floor((i - 1) * bucket_size)) + 1
        bucket_end = int(math.floor(i * bucket_size)) + 1
        bucket_end = min(bucket_end, n)

        next_start = int(math.floor(i * bucket_size)) + 1
        next_end = int(math.floor((i + 1) * bucket_size)) + 1
        next_end = min(next_end, n)

        avg_x = np.mean(x_clean[next_start:next_end])
        avg_y = np.mean(y_clean[next_start:next_end])

        max_area = -1
        max_idx = bucket_start

        for j in range(bucket_start, bucket_end):
            area = abs(
                (x_clean[a_idx] - avg_x) * (y_clean[j] - y_clean[a_idx])
                - (x_clean[a_idx] - x_clean[j]) * (avg_y - y_clean[a_idx])
            )
            if area > max_area:
                max_area = area
                max_idx = j

        sampled_x[i] = x_clean[max_idx]
        sampled_y[i] = y_clean[max_idx]
        a_idx = max_idx

    return sampled_x, sampled_y


def lttb_columns(df: pd.DataFrame, col_list, max_points=5000) -> dict:
    """여러 컬럼 LTTB → {col: {x:[...], y:[...]}}. 시간축 = index/3600(시간)."""
    n = len(df)
    time_hrs = np.arange(n, dtype=float) / 3600.0
    result: dict[str, dict] = {}
    for c in col_list:
        if c not in df.columns or c in SKIP_COLS or str(c) == "nan" or str(c).startswith("nan_"):
            continue
        col_data = df[c]
        if isinstance(col_data, pd.DataFrame):
            col_data = col_data.iloc[:, 0]
        y = pd.to_numeric(col_data, errors="coerce").to_numpy().astype(float)
        sx, sy = _lttb(time_hrs, y, max_points)
        result[c] = {
            "x": [round(float(v), 4) for v in sx],
            "y": [None if (math.isnan(v) or math.isinf(v)) else round(float(v), 4) for v in sy],
        }
    return result


# ═══ 헤더/채널 자동감지 (원본 그대로) ═══

def detect_channel_signal_map(raw, max_scan=35) -> dict:
    """엑셀 상단 'CH | Signal Name' 매핑 추출 (예: {'CH1':'PD', 'CH15':'RPM'})."""
    if raw is None or len(raw) == 0:
        return {}
    header_ri = None
    ch_col_idx = None
    sig_col_idx = None
    for ri in range(min(max_scan, len(raw))):
        row = raw.iloc[ri].tolist()
        ch_idx, sig_idx = None, None
        for ci, v in enumerate(row):
            sv = str(v).strip().lower()
            if sv == "ch":
                ch_idx = ci
            elif sv == "signal name" or sv.startswith("signal"):
                sig_idx = ci
        if ch_idx is not None and sig_idx is not None:
            header_ri = ri
            ch_col_idx = ch_idx
            sig_col_idx = sig_idx
            break
    if header_ri is None:
        return {}
    mapping: dict[str, str] = {}
    for ri in range(header_ri + 1, min(header_ri + 30, len(raw))):
        try:
            ch_val = str(raw.iloc[ri, ch_col_idx]).strip()
            sig_val = str(raw.iloc[ri, sig_col_idx]).strip()
            if re.match(r"^CH\d+$", ch_val, re.I) and sig_val and sig_val.lower() not in ("nan", ""):
                mapping[ch_val.upper()] = sig_val
        except Exception:
            continue
    return mapping


def detect_simple_header_rows(raw, max_scan=60):
    """간이벤치 헤더 행 자동 탐지. 반환 (fix_row1, fix_row2) 1-based, 실패 시 (0, 0)."""
    if raw is None or len(raw) == 0:
        return 0, 0
    req_kw = ["no", "date", "time", "ms"]
    ch_kw = ["ch1", "ch2", "ch3", "ch4", "ch5"]
    best_row, best_score = -1, 0
    for ri in range(min(max_scan, len(raw))):
        row_vals = [str(v).strip().lower() for v in raw.iloc[ri].tolist()]
        score = 0
        for kw in req_kw:
            if any(kw == v or v.startswith(kw) for v in row_vals):
                score += 2
        for kw in ch_kw:
            if any(kw == v for v in row_vals):
                score += 2
        if any("alarm" in v for v in row_vals):
            score += 1
        if score > best_score:
            best_score = score
            best_row = ri
    if best_row >= 0 and best_score >= 6:
        return best_row + 1, best_row + 2
    return 0, 0


# ═══ 멀티파일 병합 (원본 durability_upload 본문 그대로) ═══

def _detect_max_cols(path: str) -> int:
    max_cols = 2
    for enc in ("utf-8", "cp949"):
        try:
            with open(path, "r", encoding=enc) as tf:
                for line in tf:
                    nc = len(line.split(","))
                    if nc > max_cols:
                        max_cols = nc
                    if max_cols > 10:
                        break
            break
        except Exception:
            continue
    return max_cols


def merge_durability_files(
    files: list[tuple[str, str]],
    *,
    dur_type: str,
    fix_row1: int,
    fix_row2: int,
    auto_detect: bool,
):
    """업로드 파일들을 병합. files = [(filename, 디스크에 저장된 temp 경로), ...].

    호출자(라우터)가 각 업로드를 디스크에 스트리밍한 뒤 경로를 넘긴다 — 전체 바이트를
    메모리에 동시에 들고 있지 않도록(대용량 42파일/수백MB 대응). temp 정리도 호출자 책임.
    반환 (merged_df, count, fix_row1, fix_row2, detected_ch_map).
    """
    merged: pd.DataFrame | None = None
    count = 0
    detected_ch_map: dict[str, str] = {}

    for filename, path in sorted(files, key=lambda x: x[0]):
        try:
            ext = filename.lower()
            df = None
            is_simple = fix_row1 > 0 and fix_row2 > 0

            if is_simple:
                raw = None
                if ext.endswith(".xlsx") or ext.endswith(".xls"):
                    try:
                        raw = pd.read_excel(path, header=None)
                    except Exception:
                        raw = None
                else:
                    max_cols = _detect_max_cols(path)
                    col_names = list(range(max_cols))
                    for enc in ("utf-8", "cp949"):
                        try:
                            raw = pd.read_csv(
                                path, sep=",", header=None, names=col_names,
                                encoding=enc, on_bad_lines="skip",
                            )
                            break
                        except Exception:
                            raw = None
                if (fix_row1 == 0 and fix_row2 == 0) or auto_detect:
                    det1, det2 = detect_simple_header_rows(raw)
                    if det1 > 0 and det2 > 0:
                        fix_row1, fix_row2 = det1, det2
                        is_simple = True
                if raw is not None and len(raw) >= fix_row2:
                    cols = raw.iloc[fix_row2 - 1].astype(str).tolist()
                    ch_sig_map = detect_channel_signal_map(raw)
                    if ch_sig_map and not detected_ch_map:
                        detected_ch_map = ch_sig_map.copy()
                    seen: dict[str, int] = {}
                    for i, c in enumerate(cols):
                        c_up = c.strip().upper()
                        if c_up in ch_sig_map:
                            c = ch_sig_map[c_up]
                            cols[i] = c
                        if c in seen:
                            seen[c] += 1
                            cols[i] = f"{c}_{seen[c]}"
                        else:
                            seen[c] = 1
                    df = raw.iloc[fix_row2:].reset_index(drop=True)
                    df.columns = cols
            else:
                dur_hdr = None
                raw = None
                if ext.endswith(".xlsx") or ext.endswith(".xls"):
                    try:
                        raw = pd.read_excel(path, header=None)
                    except Exception:
                        raw = None
                else:
                    max_cols = _detect_max_cols(path)
                    col_names = list(range(max_cols))
                    for enc in ("cp949", "utf-8-sig", "euc-kr", "utf-8"):
                        try:
                            raw = pd.read_csv(
                                path, sep=",", header=None, names=col_names,
                                encoding=enc, on_bad_lines="skip",
                            )
                            if raw is not None and len(raw.columns) > 5:
                                break
                            raw = None
                        except Exception:
                            raw = None
                if raw is not None:
                    for ri in range(min(50, len(raw))):
                        row_str = " ".join(str(v) for v in raw.iloc[ri].tolist())
                        if "Elapse Time" in row_str or "Elapse" in row_str:
                            dur_hdr = ri
                            break
                    if dur_hdr is None:
                        dur_hdr = 1
                if raw is not None and len(raw) > dur_hdr:
                    cols = raw.iloc[dur_hdr].astype(str).tolist()
                    seen = {}
                    for i, c in enumerate(cols):
                        if c in seen:
                            seen[c] += 1
                            cols[i] = f"{c}_{seen[c]}"
                        else:
                            seen[c] = 1
                    df = raw.iloc[dur_hdr + 1:].reset_index(drop=True)
                    df.columns = cols

            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [
                        str(col[0]).strip()
                        if str(col[0]).strip() and str(col[0]) != "nan"
                        else str(col[1]).strip()
                        for col in df.columns
                    ]
                if merged is None:
                    merged = df
                else:
                    if len(df.columns) == len(merged.columns):
                        df.columns = merged.columns
                    merged = pd.concat([merged, df], ignore_index=True)
                count += 1
        except Exception:
            # 한 파일 파싱 실패가 전체 배치를 죽이지 않도록 건너뛴다(레거시 동작).
            continue

    return merged, count, fix_row1, fix_row2, detected_ch_map


# ═══ 전동 X축 슬라이싱 (원본 durability_graph_elec 그대로) ═══

ELEC_PRESSURE_COLS = {"토출 압력", "흡입 압력", "Crank Case 압력"}


def slice_elec(df: pd.DataFrame, x_mode: str, x_param: str) -> tuple[int, int]:
    """전동 시험항목별 X축 슬라이스 구간 (start_idx, end_idx) 계산."""
    n = len(df)
    start_idx, end_idx = 0, n
    if x_mode == "last_min":
        start_idx = max(0, n - int(float(x_param)) * 60)
    elif x_mode == "last_hr":
        start_idx = max(0, n - int(float(x_param)) * 3600)
    elif x_mode == "range_hr":
        parts = x_param.split(",")
        start_idx = int(float(parts[0]) * 3600)
        end_idx = min(n, int(float(parts[1]) * 3600))
    elif x_mode == "rpm_drop":
        parts = x_param.split(",")
        before, after = int(parts[0]), int(parts[1])
        rpm_col = "Comp.Speed" if "Comp.Speed" in df.columns else None
        if rpm_col:
            rpm = pd.to_numeric(df[rpm_col], errors="coerce")
            above = rpm > 5
            for i in range(1, n):
                if above.iloc[i - 1] and not above.iloc[i]:
                    start_idx = max(0, i - before)
                    end_idx = min(n, i + after)
                    break
    elif x_mode == "rpm_reach":
        parts = x_param.split(",")
        threshold = float(parts[0])
        before_sec = int(parts[1])
        after_sec = int(parts[2])
        rpm_col = "Comp.Speed" if "Comp.Speed" in df.columns else None
        if rpm_col:
            rpm = pd.to_numeric(df[rpm_col], errors="coerce")
            for i in range(n):
                if rpm.iloc[i] >= threshold:
                    start_idx = max(0, i - before_sec)
                    end_idx = min(n, i + after_sec)
                    break
    elif x_mode == "range_sec":
        parts = x_param.split(",")
        start_idx = int(float(parts[0]))
        end_idx = min(n, int(float(parts[1])))
    elif x_mode == "pd_rise":
        parts = x_param.split(",")
        threshold, before_sec, after_sec = float(parts[0]), int(parts[1]), int(parts[2])
        pd_col = "토출 압력" if "토출 압력" in df.columns else None
        if pd_col:
            pv = pd.to_numeric(df[pd_col], errors="coerce")
            for i in range(1, n):
                if pv.iloc[i - 1] < threshold and pv.iloc[i] >= threshold:
                    start_idx = max(0, i - before_sec)
                    end_idx = min(n, i + after_sec)
                    break
    elif x_mode == "pd_fall":
        parts = x_param.split(",")
        threshold, before_sec, after_sec = float(parts[0]), int(parts[1]), int(parts[2])
        pd_col = "토출 압력" if "토출 압력" in df.columns else None
        if pd_col:
            pv = pd.to_numeric(df[pd_col], errors="coerce")
            was_above = False
            for i in range(n):
                if pv.iloc[i] > threshold * 1.5:
                    was_above = True
                if was_above and pv.iloc[i] <= threshold:
                    start_idx = max(0, i - before_sec)
                    end_idx = min(n, i + after_sec)
                    break
    return start_idx, end_idx
