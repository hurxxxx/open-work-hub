"""FMEA 엑셀 파싱 — 병합 셀 + forward-fill 처리, 헤더 자동 감지, 항목 추출.

원본(`C:\\server\\routes\\fmea.py`)의 ``_parse_fmea_excel`` / ``_detect_fmea_columns`` /
``_extract_fmea_items`` 를 임시파일 대신 ``bytes`` 입력으로 받도록 포팅한 것이다.
"""

from __future__ import annotations

import io
import re

# 헤더 컬럼 자동 감지 패턴. 먼저 정의된 것이 우선(정확한 매칭 → 넓은 매칭 순서 중요).
_COLUMN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("rpn", r"R\.?\s*P\.?\s*N|위험.*우선.*순위|RPN"),
    ("severity", r"심\s*각\s*도|심각도|severity|S\.?$"),
    ("occurrence", r"발\s*생\s*도|발생도|occurrence|O\.?$"),
    ("detection", r"검\s*출\s*도|검출도|detection\s*rating|D\.?$"),
    ("item", r"항목.*기능|기능\s*요구|항목/기능"),
    ("failure_mode", r"고장\s*모드|고장\s*형태|잠재적\s*고장\s*형태|failure.*mode"),
    ("failure_effect", r"고장.*영향|잠재적\s*영향|고장의.*영향|effect"),
    ("classification", r"분\s*류|class"),
    ("failure_cause", r"고장.*원인|잠재.*원인|원인|cause"),
    ("prevention", r"예\s*방|현.*설계.*관리|prevention|예방.*대책|현\s*관리"),
    ("detection_method", r"검\s*출|검증|검출.*방법|detection.*method"),
    ("recommended_action", r"권고.*조치|개선.*대책|조치.*내용|recommend|권고"),
    ("action_result", r"조치.*결과|완료.*예정|조치결과"),
    ("action_date", r"완료.*예정일|목표.*일|예정일"),
)

_NUMERIC_KEYS = ("severity", "occurrence", "detection", "rpn")


class FmeaParseError(Exception):
    """FMEA 엑셀을 파싱할 수 없을 때 발생."""


def _parse_xlsx(content: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(content), data_only=True)
    try:
        ws = wb.active
        # 병합 셀 맵: 병합 영역의 모든 셀을 좌상단 값으로 채운다.
        merge_map: dict[tuple[int, int], object] = {}
        for mg in list(ws.merged_cells.ranges):
            val = ws.cell(mg.min_row, mg.min_col).value
            for r in range(mg.min_row, mg.max_row + 1):
                for c in range(mg.min_col, mg.max_col + 1):
                    merge_map[(r, c)] = val

        rows_data: list[list[str]] = []
        prev: dict[int, object] = {}
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
            cells: list[str] = []
            for cell in row:
                val = merge_map.get((cell.row, cell.column), cell.value)
                col = cell.column
                if val is not None and str(val).strip():
                    prev[col] = val
                elif col in prev and cell.row > 1:
                    val = prev[col]
                cells.append(str(val).strip() if val is not None else "")
            rows_data.append(cells)
        return rows_data
    finally:
        wb.close()


def _parse_xls(content: bytes) -> list[list[str]]:
    import xlrd

    # xlrd 2.x 는 formatting_info(병합 셀 정보)를 지원하지 않으므로 병합 맵은 생략하고
    # forward-fill 로만 보정한다(.xlsx 권장).
    try:
        wb = xlrd.open_workbook(file_contents=content, formatting_info=True)
        ws = wb.sheet_by_index(0)
        merge_ranges = list(ws.merged_cells)
    except NotImplementedError:
        wb = xlrd.open_workbook(file_contents=content)
        ws = wb.sheet_by_index(0)
        merge_ranges = []

    merge_map: dict[tuple[int, int], object] = {}
    for rlo, rhi, clo, chi in merge_ranges:
        val = ws.cell_value(rlo, clo)
        for r in range(rlo, rhi):
            for c in range(clo, chi):
                merge_map[(r, c)] = val

    rows_data: list[list[str]] = []
    prev: dict[int, object] = {}
    for r in range(ws.nrows):
        cells: list[str] = []
        for c in range(ws.ncols):
            val = merge_map.get((r, c), ws.cell_value(r, c))
            if val is not None and str(val).strip():
                prev[c] = val
            elif c in prev and r > 0:
                val = prev[c]
            cells.append(str(val).strip() if val is not None else "")
        rows_data.append(cells)
    return rows_data


def parse_fmea_excel(content: bytes, filename: str) -> list[list[str]]:
    """FMEA 엑셀(bytes)을 2차원 문자열 리스트로 파싱한다."""
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        return _parse_xlsx(content)
    if name.endswith(".xls"):
        return _parse_xls(content)
    raise FmeaParseError("지원하지 않는 파일 형식입니다. (.xls, .xlsx만 가능)")


def detect_fmea_columns(rows_data: list[list[str]]) -> dict[str, int]:
    """FMEA 헤더 행을 자동 감지하여 {컬럼키: 컬럼인덱스} 매핑을 만든다."""
    col_map: dict[str, int] = {}

    # 고유 값이 4개 이상인 상위 행을 헤더 후보로 본다.
    header_rows = [
        ri
        for ri, row in enumerate(rows_data[:15])
        if len({c.strip() for c in row if c.strip()}) >= 4
    ]

    for ri in header_rows:
        for ci, cell in enumerate(rows_data[ri]):
            cell_clean = re.sub(r"\s+", " ", cell.strip()).lower()
            if not cell_clean or len(cell_clean) > 50:
                continue
            for key, pat in _COLUMN_PATTERNS:
                if key not in col_map and re.search(pat, cell_clean, re.IGNORECASE):
                    col_map[key] = ci
                    break

    return col_map


def extract_fmea_items(
    rows_data: list[list[str]], col_map: dict[str, int]
) -> list[dict[str, str]]:
    """헤더 이후 데이터 행을 추출하고 숫자 정리 + RPN 자동 계산을 수행한다."""
    # 마지막 헤더 행 다음을 데이터 시작 행으로 본다.
    start_row = 0
    for i, row in enumerate(rows_data[:15]):
        has_pattern = any(
            re.search(
                r"고장|failure|심각도|발생도|검출도|R\.?P\.?N|예방|검출", c, re.IGNORECASE
            )
            for c in row
            if c
        )
        if has_pattern:
            start_row = i + 1
    if start_row == 0:
        start_row = 4

    items: list[dict[str, str]] = []
    for row in rows_data[start_row:]:
        if not any(c.strip() for c in row):
            continue
        item: dict[str, str] = {}
        for key, ci in col_map.items():
            if ci < len(row):
                item[key] = row[ci].strip()

        # 숫자 값 정리 (4.0 → 4, 빈값 → '')
        for nk in _NUMERIC_KEYS:
            val = item.get(nk, "").strip()
            if val:
                try:
                    item[nk] = str(int(float(val)))
                except (ValueError, TypeError):
                    item[nk] = ""

        # RPN 이 없거나 0 이면 S*O*D 로 자동 계산
        rpn_val = int(item.get("rpn", "0") or "0")
        if rpn_val == 0:
            try:
                s = int(item.get("severity", "0") or "0")
                o = int(item.get("occurrence", "0") or "0")
                d = int(item.get("detection", "0") or "0")
                if s and o and d:
                    item["rpn"] = str(s * o * d)
            except (ValueError, TypeError):
                pass

        if item.get("failure_mode") or item.get("item"):
            items.append(item)

    return items
