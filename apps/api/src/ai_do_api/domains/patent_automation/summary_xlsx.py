"""Generate the two monthly summary workbooks from parsed cost lines.

* ``build_industrial_summary`` — 산업재산권 지출 비용 요약 (single sheet, B..K,
  variable-height 7 sections each with 소계, then 총합계).
* ``build_overseas_summary`` — 해외출원특허 지출 비용 요약 (per-case 13-row
  blocks, 해외/국내 소계 + 합계, then 총합계).

Layouts follow the reference Jan files; exact cell fidelity is verified by the
regression diff in testing. Amounts are read summary-ready off the cost lines
(공급가액 = supply_amount, 부가세 = vat, 합계 = line_total).
"""

from __future__ import annotations

import re
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Color, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ai_do_api.domains.patent_automation.invoice_pipeline import (
    SECTION_ANNUITY,
    SUMMARY_SECTION_ORDER,
)
from ai_do_api.domains.patent_automation.models import PatentCostLine


def parse_period(period: str) -> tuple[str, str] | None:
    """'2026-06' | '202606' | '2026.06' | '2026/6' → ('2026', '06'); 형식 불명은 None."""
    match = re.match(r"^\s*(\d{4})\D?(\d{1,2})\s*$", period or "")
    if not match or not (1 <= int(match.group(2)) <= 12):
        return None
    return match.group(1), f"{int(match.group(2)):02d}"


def period_sheet_name(period: str) -> str:
    """시트 탭 이름: 정본과 동일한 '2026년 06월'. 형식 불명이면 원본 문자열."""
    parsed = parse_period(period)
    return f"{parsed[0]}년 {parsed[1]}월" if parsed else (period or "요약")


def _dot_date(value) -> str:
    """출원일/등록일 표기를 정본과 동일한 점 구분(YYYY.MM.DD)으로 정규화. 빈 값은 '-'."""
    text = str(value or "").strip()
    if not text:
        return "-"
    match = re.match(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$", text)
    if match:
        return f"{match.group(1)}.{int(match.group(2)):02d}.{int(match.group(3)):02d}"
    return text


_MONEY_FMT = "#,##0_);[Red]\\(#,##0\\)"
_SUBTOTAL_FMT = "#,##0_ "
_TOTAL_FMT = "#,##0"

# 기준 파일(2026년 1월 …-260119.xlsx)과 동일한 서식: 굴림 글꼴, 헤더는 채움 없이
# 굵게, 소계 공급가액 칸만 노랑(indexed 13), 총합계 라벨 청록(15)·값 노랑, medium
# 외곽 + thin 격자.
_FONT = "굴림"
_TITLE_FONT = Font(name=_FONT, bold=True, size=18)
_DATE_FONT = Font(name=_FONT, size=11)
_SECTION_FONT = Font(name=_FONT, size=12)
_HEADER_FONT = Font(name=_FONT, bold=True, size=12)
_DATA_FONT = Font(name=_FONT, size=11)
_SUBTOTAL_FONT = Font(name=_FONT, bold=True, size=11)
_TOTAL_LABEL_FONT = Font(name=_FONT, bold=True, size=14)
_TOTAL_FONT = Font(name=_FONT, bold=True, size=11)

_YELLOW = PatternFill(fill_type="solid", fgColor=Color(indexed=13))
_CYAN = PatternFill(fill_type="solid", fgColor=Color(indexed=15))

_MED = Side(style="medium", color="FF000000")
_THIN = Side(style="thin", color="FF000000")
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
_RIGHT = Alignment(horizontal="right", vertical="center")

# 해외출원 요약(별도 파일)이 쓰는 기존 상수 — 유지.
_HEADER_FILL = PatternFill(fill_type="solid", fgColor="DDE7F6")
_SUBTOTAL_FILL = PatternFill(fill_type="solid", fgColor="F2F2F2")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

# ── 해외출원특허 요약 서식(기준 …-260116.xlsx): 돋움 글꼴, 케이스별 12행 블록 ──
_OV_FONT = "돋움"
_OV_TITLE_FONT = Font(name=_OV_FONT, bold=True, size=20)
_OV_DATE_FONT = Font(name=_OV_FONT, size=11)
_OV_SECTION_FONT = Font(name=_OV_FONT, bold=True, size=12)
_OV_HEAD_FONT = Font(name=_OV_FONT, bold=True, size=11)
_OV_N = Font(name=_OV_FONT, size=11)
_OV_B = Font(name=_OV_FONT, bold=True, size=11)
_WON_FMT = '"₩"#,##0;[Red]\\-"₩"#,##0'
_WON_FMT2 = '"₩"#,##0'
_USD_FMT = "0.00_);[Red]\\(0.00\\)"
_DBL = Side(style="double", color="FF000000")
_OV_LEFT, _OV_RIGHT = 2, 6  # B..F (G는 보조)


def _ov_country(no: str) -> str:
    s = (no or "").upper()
    if "/" in s or s.startswith("US"):
        return "미국"
    if s.startswith("DE") or re.match(r"^10\s?20", s) or re.match(r"^1020\d", s):
        return "독일"
    if s.startswith("CN") or s.startswith("ZL") or re.match(r"^20\d{10}", s):
        return "중국"
    return ""


def _overseas_desc(line) -> str:
    """해외 섹션 C열 2번째 줄: [국가{출원/등록}특허(번호)건의 {N년차 }{업무} 비용].
    등록유지(마크프로)만 등록특허+등록(공고)번호, 그 외는 출원특허+출원번호."""
    d = line.cost_details or {}
    work = d.get("업무") or "해외"
    is_reg = work == "등록유지"
    no = (
        (line.registration_no if is_reg else line.application_no)
        or line.application_no
        or line.registration_no
        or ""
    )
    no = re.sub(r"\.0$", "", str(no))  # float 임포트로 붙은 ".0" 제거(체크디지트 ".6" 등은 보존)
    if (
        "/" not in no
    ):  # 독일/중국 체크디지트 구분은 원본 표기상 쉼표(미국 19/394,605는 슬래시라 제외)
        no = no.replace(".", ",")
    kind = "등록특허" if is_reg else "출원특허"
    annu = f"{line.annuity_year}년차 " if (line.annuity_year and "유지" in work) else ""
    return f"[{_ov_country(no)}{kind}({no})건의 {annu}{work} 비용]"


_TABLE_LEFT, _TABLE_RIGHT = 2, 11  # B..K


def _gb(col: int, top: Side, bottom: Side) -> Border:
    """medium 외곽(B/K 열·지정한 top/bottom) + thin 내부 격자."""
    return Border(
        left=_MED if col == _TABLE_LEFT else _THIN,
        right=_MED if col == _TABLE_RIGHT else _THIN,
        top=top,
        bottom=bottom,
    )


_SECTION_TITLES = {
    "국내출원": "국내출원 비용",
    "심사청구": "심사청구 비용",
    "의견제출": "의견제출 비용",
    "재심사": "재심사 비용",
    "특허등록": "특허등록 비용",
    "연차료": "연차료 비용",
    "해외": "해외 비용",
}

_HEADERS = [
    "순번",
    "발명의 명칭",
    "출원일",
    "출원번호",
    "등록일",
    "등록번호",
    "발명자",
    "공급가액",
    "부가세",
    "합  계",
]


def internal_inventors_only(inventors: str | None) -> str:
    """비용요약 발명자 칸은 사내(내부) 발명자만 — 외부 발명자는 ``(괄호)``로
    표기되므로 괄호 구간을 제거하고 남은 내부 이름만 콤마로 정리한다.
    예: '이원석,김철민,최두열,(추성호)' → '이원석,김철민,최두열';
        '김성준,임혁주(강동수,김기범)' → '김성준,임혁주'."""
    if not inventors:
        return ""
    stripped = re.sub(r"\([^)]*\)", "", inventors)
    names = [n.strip() for n in stripped.split(",") if n.strip()]
    return ",".join(names)


# 발명의 명칭 끝에 붙은 영문 병기 "(ENGLISH …)"를 제거(비용요약은 국문 명칭만 표기).
# 한글이 포함된 괄호(예: "(제어방법)")는 보존한다.
_RE_EN_PAREN = re.compile(r"\s*\((?=[^)]*[A-Za-z])(?![^)]*[가-힣])[^)]*\)\s*$")


def korean_title(title: str | None) -> str:
    return _RE_EN_PAREN.sub("", (title or "").strip())


def _set(ws, row, col, value, *, fmt=None, font=None, fill=None, border=True, align=None):
    cell = ws.cell(row=row, column=col, value=value)
    if fmt:
        cell.number_format = fmt
    if font:
        cell.font = font
    if fill:
        cell.fill = fill
    if border:
        cell.border = _BORDER
    if align:
        cell.alignment = align
    return cell


def build_industrial_summary(
    cost_lines: list[PatentCostLine], *, title: str, date_label: str, period: str = ""
) -> bytes:
    by_section: dict[str, list[PatentCostLine]] = {}
    for line in cost_lines:
        if line.region == "해외":
            section = "해외"
        else:
            section = line.section
        by_section.setdefault(section, []).append(line)

    wb = Workbook()
    ws = wb.active
    ws.title = period_sheet_name(period)

    # 제목 + 작성일
    ws.merge_cells("B1:K1")
    _set(ws, 1, 2, title, font=_TITLE_FONT, border=False, align=_CENTER)
    ws.row_dimensions[1].height = 25.5
    _set(ws, 2, 11, date_label, font=_DATE_FONT, border=False, align=_RIGHT)
    ws.row_dimensions[2].height = 14.2

    row = 3
    subtotal_cells: list[int] = []
    section_index = 0
    for section in SUMMARY_SECTION_ORDER:
        lines = by_section.get(section)
        if not lines:
            continue
        section_index += 1
        is_annuity = section == SECTION_ANNUITY
        is_overseas = section == "해외"

        # 섹션 제목 (굴림 12, 굵기 없음, 테두리 없음)
        _set(
            ws,
            row,
            2,
            f"{section_index}. {_SECTION_TITLES.get(section, section)}",
            font=_SECTION_FONT,
            border=False,
        )
        ws.row_dimensions[row].height = 18.0
        row += 1

        # 표 헤더 (채움 없이 굵게, medium 상/하)
        headers = list(_HEADERS)
        if is_annuity:
            headers[6] = "년차"
        if is_overseas:
            headers[1] = "발명의 명칭 (업무 내용)"
        for col, text in enumerate(headers, start=2):
            c = _set(ws, row, col, text, font=_HEADER_FONT, align=_CENTER)
            c.border = _gb(col, _MED, _MED)
        ws.row_dimensions[row].height = 30.0
        row += 1

        data_start = row
        for seq, line in enumerate(lines, start=1):
            c_text = (
                (korean_title(line.title) + "\n" + _overseas_desc(line))
                if is_overseas
                else korean_title(line.title)
            )
            _set(ws, row, 2, seq, font=_DATA_FONT, align=_CENTER).border = _gb(2, _THIN, _THIN)
            _set(ws, row, 3, c_text, font=_DATA_FONT, align=_LEFT).border = _gb(3, _THIN, _THIN)
            _set(
                ws, row, 4, _dot_date(line.application_date), font=_DATA_FONT, align=_CENTER
            ).border = _gb(4, _THIN, _THIN)
            _set(
                ws, row, 5, line.application_no or "-", font=_DATA_FONT, align=_CENTER
            ).border = _gb(5, _THIN, _THIN)
            _set(
                ws, row, 6, _dot_date(line.registration_date), font=_DATA_FONT, align=_CENTER
            ).border = _gb(6, _THIN, _THIN)
            _set(
                ws, row, 7, line.registration_no or "-", font=_DATA_FONT, align=_CENTER
            ).border = _gb(7, _THIN, _THIN)
            # 발명자 칸은 좌측정렬(정본과 동일), 연차료 섹션의 '년차'는 가운데정렬.
            _set(
                ws,
                row,
                8,
                (line.annuity_year if is_annuity else internal_inventors_only(line.inventors))
                or "",
                font=_DATA_FONT,
                align=_CENTER if is_annuity else _LEFT,
            ).border = _gb(8, _THIN, _THIN)
            _set(
                ws, row, 9, line.supply_amount or 0, fmt=_MONEY_FMT, font=_DATA_FONT, align=_RIGHT
            ).border = _gb(9, _THIN, _THIN)
            _set(
                ws, row, 10, line.vat or 0, fmt=_MONEY_FMT, font=_DATA_FONT, align=_RIGHT
            ).border = _gb(10, _THIN, _THIN)
            _set(
                ws, row, 11, f"=SUM(I{row}:J{row})", fmt=_MONEY_FMT, font=_DATA_FONT, align=_RIGHT
            ).border = _gb(11, _THIN, _THIN)
            ws.row_dimensions[row].height = 30.0
            row += 1
        data_end = row - 1

        # 소계 (라벨 B:C 병합, E:H 병합, 공급가액 칸만 노랑, medium 상/하)
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=8)
        for col in range(2, 12):
            ws.cell(row=row, column=col).border = _gb(col, _MED, _MED)
        _set(ws, row, 2, "소  계", font=_SUBTOTAL_FONT, align=_CENTER).border = _gb(2, _MED, _MED)
        _set(
            ws,
            row,
            9,
            f"=SUM(I{data_start}:I{data_end})",
            fmt=_SUBTOTAL_FMT,
            font=_SUBTOTAL_FONT,
            fill=_YELLOW,
            align=_RIGHT,
        ).border = _gb(9, _MED, _MED)
        _set(
            ws,
            row,
            10,
            f"=SUM(J{data_start}:J{data_end})",
            fmt=_SUBTOTAL_FMT,
            font=_SUBTOTAL_FONT,
            align=_RIGHT,
        ).border = _gb(10, _MED, _MED)
        _set(
            ws,
            row,
            11,
            f"=SUM(K{data_start}:K{data_end})",
            fmt=_SUBTOTAL_FMT,
            font=_SUBTOTAL_FONT,
            align=_RIGHT,
        ).border = _gb(11, _MED, _MED)
        ws.row_dimensions[row].height = 30.0
        subtotal_cells.append(row)
        row += 2  # 빈 줄

    # 총 합계 비용 (2행 블록: 라벨 E:H 병합, I/J/K 헤더 + 값)
    if subtotal_cells:
        r1, r2 = row, row + 1
        ws.merge_cells(start_row=r1, start_column=2, end_row=r2, end_column=3)
        ws.merge_cells(start_row=r1, start_column=4, end_row=r2, end_column=4)
        ws.merge_cells(start_row=r1, start_column=5, end_row=r2, end_column=8)
        _set(ws, r1, 5, "총 합계 비용", font=_TOTAL_LABEL_FONT, border=False, align=_CENTER)
        _set(ws, r1, 9, "공급가액 총액", font=_TOTAL_FONT, fill=_CYAN, border=False, align=_CENTER)
        _set(ws, r1, 10, "VAT 총액", font=_TOTAL_FONT, border=False, align=_CENTER)
        _set(ws, r1, 11, "총 합계비용", font=_DATA_FONT, border=False, align=_CENTER)
        i_refs = ",".join(f"I{r}" for r in subtotal_cells)
        j_refs = ",".join(f"J{r}" for r in subtotal_cells)
        k_refs = ",".join(f"K{r}" for r in subtotal_cells)
        _set(
            ws,
            r2,
            9,
            f"=SUM({i_refs})",
            fmt=_TOTAL_FMT,
            font=_TOTAL_FONT,
            fill=_YELLOW,
            border=False,
            align=_CENTER,
        )
        _set(
            ws,
            r2,
            10,
            f"=SUM({j_refs})",
            fmt=_TOTAL_FMT,
            font=_TOTAL_FONT,
            fill=_YELLOW,
            border=False,
            align=_CENTER,
        )
        _set(
            ws,
            r2,
            11,
            f"=SUM({k_refs})",
            fmt=_TOTAL_FMT,
            font=_TOTAL_FONT,
            fill=_YELLOW,
            border=False,
            align=_CENTER,
        )
        # 테두리는 _set 이후에 일괄 적용(기본 _BORDER 덮어쓰기 방지)
        for rr in (r1, r2):
            for col in range(2, 12):
                ws.cell(row=rr, column=col).border = _gb(
                    col, _MED if rr == r1 else _THIN, _MED if rr == r2 else _THIN
                )
        ws.row_dimensions[r1].height = 24.9
        ws.row_dimensions[r2].height = 24.9

    # 정본(…-260618.xlsx)과 동일한 컬럼 너비: A=왼쪽여백(6px), B=순번(40px).
    _apply_widths(
        ws,
        {
            1: 0.66,
            2: 4.44,
            3: 44.78,
            4: 9.78,
            5: 16.66,
            6: 9.78,
            7: 16.44,
            8: 13.33,
            9: 14.0,
            10: 11.22,
            11: 11.78,
        },
    )
    return _to_bytes(wb)


def _ovb(col: int, top: Side, bottom: Side) -> Border:
    return Border(
        left=_MED if col == _OV_LEFT else _THIN,
        right=_MED if col == _OV_RIGHT else _THIN,
        top=top,
        bottom=bottom,
    )


def _company_count(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        count = value
    elif isinstance(value, str) and value.strip().isdigit():
        count = int(value.strip())
    else:
        return None
    return count if 2 <= count <= 20 else None


def _positive_amount(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    amount = float(value)
    return amount if amount > 0 else None


def build_overseas_summary(
    cost_lines: list[PatentCostLine], *, title: str, date_label: str, period: str = ""
) -> bytes:
    """해외출원특허 지출 비용 요약 — 기준 …-260116.xlsx와 동일 양식(돋움, 케이스별
    12행 블록: 구분/청구내역/업무내용/비고 + 해외비용→원화→송금→소계 / 국내비용→
    대리인수수료→부가세→소계 / 합계). D:E 병합, ₩/USD 서식, medium 외곽·double 구분선."""
    overseas = [line for line in cost_lines if line.region == "해외"]
    wb = Workbook()
    ws = wb.active
    ws.title = period_sheet_name(period)

    ws.merge_cells("B1:F1")
    _set(
        ws,
        1,
        2,
        title,
        font=_OV_TITLE_FONT,
        border=False,
        align=Alignment(horizontal="center", vertical="center"),
    )
    ws.row_dimensions[1].height = 30.0
    _set(ws, 2, 6, date_label, font=_OV_DATE_FONT, border=False, align=_RIGHT)

    stride = 13
    supply_refs: list[str] = []
    vat_refs: list[str] = []

    def put(r, c, value, *, font=_OV_N, fmt=None, align=None, fill=None):
        cell = ws.cell(row=r, column=c, value=value)
        cell.font = font
        if fmt:
            cell.number_format = fmt
        # 정본과 동일하게 모든 셀 세로 가운데. 명시 align이 없던 셀(소계/원화비용/송금수수료
        # 등)이 아래쪽으로 붙던 문제를 세로 가운데로 통일한다.
        cell.alignment = align or Alignment(vertical="center")
        if fill:
            cell.fill = fill
        return cell

    for n, line in enumerate(overseas, start=1):
        t = 3 + stride * (n - 1)
        d = line.cost_details or {}
        foreign_krw = int(d.get("해외비용", line.foreign_cost_krw or 0) or 0)
        agent = int(d.get("대리인수수료", 0) or 0)
        remit = int(d.get("송금수수료", 0) or 0)
        vat = line.vat or 0
        work = d.get("업무") or "해외"
        no = line.application_no or line.registration_no or ""
        country = _ov_country(no)
        no_type = "등록" if (line.registration_no and not line.application_no) else "출원"
        ccy = line.foreign_currency or ""
        amt = float(line.foreign_amount or 0)
        fx = float(line.fx_rate or 0)
        usd_txt = f"{ccy} {amt:,.2f}".strip()
        # 환율 라인 끝에 원화 글리프(₩, 한글 폰트에서 '\'로 렌더)를 붙인다 — 기준 양식 동일.
        fx_txt = f"{usd_txt} (1 {ccy} = {fx:,.2f} \\)" if ccy and fx else usd_txt
        # 명시적인 분담 근거가 있을 때만 총액/업체 수를 표시한다. 근거가 없는 단독·과거
        # 데이터는 저장된 외화금액을 그대로 사용해 임의의 3사 분담으로 확대하지 않는다.
        company_count = _company_count(d.get("균등분담업체수"))
        total_foreign = _positive_amount(d.get("외화총액"))
        fx_reference_date = d.get("환율기준일") or d.get("송금일")
        claim_txt = (
            f"{work} 비용\n({total_foreign:.2f} {ccy} / {company_count}업체)"
            if (ccy and amt and company_count and total_foreign)
            else f"{work} 비용\n({usd_txt})"
        )

        # 케이스 제목
        put(
            t,
            2,
            f'{n}. "{korean_title(line.title)}" ({country}{no_type}번호: {no})',
            font=_OV_SECTION_FONT,
        )
        ws.row_dimensions[t].height = 24.95

        # 헤더(2행 병합) + 설명
        ws.merge_cells(start_row=t + 1, start_column=2, end_row=t + 2, end_column=2)
        ws.merge_cells(start_row=t + 1, start_column=3, end_row=t + 2, end_column=3)
        ws.merge_cells(start_row=t + 1, start_column=6, end_row=t + 2, end_column=6)
        ws.merge_cells(start_row=t + 1, start_column=4, end_row=t + 1, end_column=5)
        ws.merge_cells(start_row=t + 2, start_column=4, end_row=t + 2, end_column=5)
        put(t + 1, 2, "구  분", font=_OV_HEAD_FONT, align=_CENTER)
        put(t + 1, 3, "청구내역", font=_OV_HEAD_FONT, align=_CENTER)
        put(t + 1, 4, "업무 내용", font=_OV_HEAD_FONT, align=_CENTER)
        put(t + 1, 6, "비     고", font=_OV_HEAD_FONT, align=_CENTER)
        put(
            t + 2,
            4,
            f"{country}{no_type}특허({no})건의 {work} 비용",
            font=_OV_HEAD_FONT,
            align=_CENTER,
        )
        ws.row_dimensions[t + 1].height = 24.9
        ws.row_dimensions[t + 2].height = 35.1

        # 데이터 D:E 병합
        for rr in range(t + 3, t + 12):
            ws.merge_cells(start_row=rr, start_column=4, end_row=rr, end_column=5)
        ws.merge_cells(start_row=t + 3, start_column=2, end_row=t + 7, end_column=2)  # 해외비용
        ws.merge_cells(start_row=t + 8, start_column=2, end_row=t + 10, end_column=2)  # 국내비용
        ws.merge_cells(start_row=t + 11, start_column=2, end_row=t + 11, end_column=3)  # 합계 라벨

        put(t + 3, 2, "해외비용", align=_CENTER)
        put(t + 3, 3, claim_txt, align=_LEFT)
        put(t + 3, 4, usd_txt, fmt=_USD_FMT, align=_CENTER)
        put(t + 4, 3, "소계")
        put(t + 4, 4, fx_txt, align=_CENTER)
        put(t + 5, 3, "원화비용")
        put(t + 5, 4, foreign_krw, fmt=_WON_FMT, align=_CENTER)
        # 청구서에서 확인 가능한 것은 환율 고시·기준일이며 실제 송금 완료일은 아니다.
        if fx_reference_date:
            put(t + 5, 6, f"환율 기준일: {fx_reference_date}", align=_LEFT)
        put(t + 6, 3, "송금수수료")
        put(t + 6, 4, remit, fmt=_WON_FMT, align=_CENTER)
        put(t + 7, 3, "소  계", align=_CENTER)
        put(t + 7, 4, f"=D{t + 5}+D{t + 6}", fmt=_WON_FMT, font=_OV_B, align=_CENTER)
        put(t + 8, 2, "국내비용", align=_CENTER)
        put(t + 8, 3, "대리인수수료", align=_LEFT)
        put(t + 8, 4, agent, fmt=_WON_FMT2, font=_OV_B, align=_CENTER)
        put(t + 9, 3, "부가세(VAT)")
        put(t + 9, 4, vat, fmt=_WON_FMT2, align=_CENTER)
        put(t + 10, 3, "소  계", align=_CENTER)
        put(t + 10, 4, f"=D{t + 8}+D{t + 9}", fmt=_WON_FMT2, align=_CENTER)
        put(t + 11, 2, "합  계", font=_OV_B, align=_CENTER)
        put(t + 11, 4, f"=D{t + 7}+D{t + 10}", fmt=_WON_FMT2, font=_OV_B, align=_CENTER)

        # 테두리(_set 미사용이라 직접) — medium 외곽 + double 해외/국내 구분
        for rr in range(t + 1, t + 12):
            top = _MED if rr == t + 1 else _DBL if rr == t + 8 else _MED if rr == t + 11 else _THIN
            bot = _DBL if rr == t + 7 else _MED if rr in (t + 2, t + 11) else _THIN
            for c in range(2, 7):
                ws.cell(row=rr, column=c).border = _ovb(c, top, bot)
        for rr in range(t + 4, t + 12):
            ws.row_dimensions[rr].height = 24.9
        ws.row_dimensions[t + 3].height = 31.5

        supply_refs += [f"D{t + 7}", f"D{t + 8}"]
        vat_refs.append(f"D{t + 9}")

    # 총 합 계 비 용 (2행)
    if overseas:
        bt = 3 + stride * len(overseas) + 1
        ws.merge_cells(start_row=bt, start_column=2, end_row=bt, end_column=3)
        ws.merge_cells(start_row=bt, start_column=4, end_row=bt, end_column=5)
        ws.merge_cells(start_row=bt + 1, start_column=2, end_row=bt + 1, end_column=3)
        ws.merge_cells(start_row=bt + 1, start_column=4, end_row=bt + 1, end_column=5)
        put(bt, 2, "총 합 계 비 용", font=_OV_B, align=_CENTER)
        put(bt, 4, "공급가액 총액", font=_OV_B, align=_CENTER, fill=_CYAN)
        put(bt, 6, "VAT 총액", font=_OV_N, align=_CENTER)
        put(bt + 1, 2, f"=D{bt + 1}+F{bt + 1}", fmt=_WON_FMT, font=_OV_B, align=_CENTER)
        put(
            bt + 1,
            4,
            f"=SUM({','.join(supply_refs)})",
            fmt=_WON_FMT,
            font=_OV_B,
            align=_CENTER,
            fill=_YELLOW,
        )
        put(bt + 1, 6, f"=SUM({','.join(vat_refs)})", fmt=_WON_FMT2, font=_OV_N, align=_CENTER)
        for rr in (bt, bt + 1):
            for c in range(2, 7):
                ws.cell(row=rr, column=c).border = _ovb(
                    c, _MED if rr == bt else _THIN, _MED if rr == bt + 1 else _THIN
                )

    # 정본(…-260618.xlsx)과 동일한 너비: A=왼쪽여백(5px), B=구분(98px), 나머지 동일.
    _apply_widths(ws, {1: 0.55, 2: 10.78, 3: 32.78, 4: 25.78, 6: 33.0, 7: 13.78})
    return _to_bytes(wb)


_CA_SECTION_COL = {  # 섹션 → (건수 열, 금액 열)
    "국내출원": (3, 4),
    "심사청구": (5, 6),
    "의견제출": (7, 8),
    "재심사": (9, 10),
    "특허등록": (11, 12),
    "연차료": (13, 14),
    "해외": (15, 16),
}
_CA_LABELS = [
    (3, "출원비용"),
    (5, "심사청구비용"),
    (7, "의견제출비용"),
    (9, "재심사청구비용"),
    (11, "등록비용"),
    (13, "등록유지비용"),
]
_CA_FONT9 = Font(name=_OV_FONT, size=9)
_CA_FONT9B = Font(name=_OV_FONT, bold=True, size=9)
_CA_FONT11B = Font(name=_OV_FONT, bold=True, size=11)


def build_count_amount_summary(
    cost_lines, *, period: str, date_label: str, team: str = "기술지원팀"
) -> bytes:
    """6번 '국내외 특허비용(건수,금액정리)' — 월별 (건수, 공급가액) 롤업.
    국내 6분류(출원/심사청구/의견제출/재심사/등록/등록유지)+해외, Q=공급가액 총액.
    인자 period='YYYY-MM'의 해당 월 행만 채우고 나머지 월은 0, 합계행은 SUM."""
    # period는 '2026-06' 외에 '202606'/'2026.06' 등으로 들어올 수 있으므로 견고하게 파싱한다
    # (형식 불명으로 split이 실패해 다운로드가 500으로 죽던 문제 방지).
    parsed = parse_period(period)
    year, month = parsed if parsed else ((period or "").strip() or "-", "0")
    by_section: dict[str, list[int]] = {}
    for ln in cost_lines:
        sec = "해외" if ln.region == "해외" else ln.section
        by_section.setdefault(sec, [0, 0])
        by_section[sec][0] += 1
        by_section[sec][1] += ln.supply_amount or 0

    wb = Workbook()
    ws = wb.active
    ws.title = f"{year}년 특허비용실적"
    thin = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

    def put(r, c, v, *, font=_CA_FONT9, fmt=None, border=True, align=_CENTER):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font = font
        if fmt:
            cell.number_format = fmt
        if border:
            cell.border = thin
        cell.alignment = align
        return cell

    put(
        2,
        2,
        team,
        font=Font(name=_OV_FONT, size=10),
        border=False,
        align=Alignment(horizontal="left"),
    )
    put(2, 17, date_label, font=_CA_FONT9, border=False, align=_RIGHT)
    for rng in (
        "B3:B6",
        "C3:Q3",
        "C4:N4",
        "O4:P5",
        "Q4:Q6",
        "C5:D5",
        "E5:F5",
        "G5:H5",
        "I5:J5",
        "K5:L5",
        "M5:N5",
    ):
        ws.merge_cells(rng)
    put(3, 3, f"{year}년", font=_CA_FONT11B)
    put(4, 3, "국내비용", font=_CA_FONT9B)
    put(4, 15, "해외비용", font=_CA_FONT9B)
    put(4, 17, "월별비용", font=_CA_FONT9B)
    for col, label in _CA_LABELS:
        put(5, col, label, font=_CA_FONT9B)
    for col in (3, 5, 7, 9, 11, 13):
        put(6, col, "건수", font=_CA_FONT9B)
        put(6, col + 1, "금액", font=_CA_FONT9B)
    put(6, 15, "건수", font=_CA_FONT9B)
    put(6, 16, "금액", font=_CA_FONT9B)
    # 12개월 행
    for mi in range(1, 13):
        r = 6 + mi
        put(r, 2, f"{mi}월", font=_CA_FONT11B)
        for sec, (cc, ac) in _CA_SECTION_COL.items():
            if mi == int(month) and sec in by_section:
                cnt, amt = by_section[sec]
                put(r, cc, cnt, fmt="#,##0")
                put(r, ac, amt, fmt=_MONEY_FMT)
            else:
                put(r, cc, None)
                put(r, ac, None)
        put(r, 17, f"=SUM(D{r},F{r},H{r},J{r},L{r},N{r},P{r})", fmt=_MONEY_FMT)
    # 합계 행
    put(19, 2, "합계", font=_CA_FONT11B)
    for c in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
        col = get_column_letter(c)
        put(19, c, f"=SUM({col}7:{col}18)", fmt=("#,##0" if c % 2 == 1 else _MONEY_FMT))
    _apply_widths(
        ws,
        {
            2: 4.7,
            3: 5.7,
            4: 12.9,
            5: 5.7,
            6: 12.9,
            7: 5.7,
            8: 12.9,
            9: 5.7,
            10: 12.9,
            11: 5.7,
            12: 12.9,
            13: 5.7,
            14: 12.9,
            15: 12.2,
            16: 13.0,
            17: 15.2,
        },
    )
    return _to_bytes(wb)


def _apply_widths(ws, widths: dict[int, int]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def _to_bytes(wb: Workbook) -> bytes:
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
