# -*- coding: utf-8 -*-
"""Open ALM 사내 진행보고 "하우스 스타일" 데이터 드리븐 렌더러 (python-pptx).

SPEC_house_style.md(§4~§6) 이식. 연파랑 헤더 전체격자표 + 파란 강조 + ■섹션 +
하단 마일스톤 화살표를 데이터(JSON)만으로 동일 양식 .pptx 로 찍어낸다.

슬라이드 1장의 ``data`` 모델(= families pipeline 의 slide["data"]):

    {
      "no": 1, "title": "스마트 팩토리 진행 사항", "tag": "AI 비전 도입",
      "meta": {"date": "2026. 6. 16", "confidential": true, "total": 5},
      "blocks": [
        {"type": "lead", "label": "목적", "text": "..."},
        {"type": "table", "section": "개선방법", "colW": [...], "align": [...],
         "header": [...], "rows": [[cell, ...], ...], "rowH": [...], "fs": 10.5, "hfs": 12, "headerH": 0.6},
        {"type": "timeline", "section": "진행 현황",
         "nodes": [{"label": "...", "date": "...", "state": "done|prog|todo"}, ...]},
        {"type": "conclusion", "text": "..."}
      ]
    }

셀(Cell) 4형태(§5):
  1) "문자열"
  2) {"lines": ["AI 비전","자체 개발"], "al": "c"}
  3) {"runs": [{"t": "...", "b": true, "c": "blue", "u": false}, ...]}  # 각 run=한 줄
  4) {"t": "완료", "b": true, "c": "blue", "al": "c"}

확장 지점(후속): 폰트 임베드 / 로고 PNG(add_picture) / 차트 블록.
"""
from __future__ import annotations

import functools
import math
import re

from lxml import etree
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import (
    XL_CHART_TYPE,
    XL_LABEL_POSITION,
    XL_LEGEND_POSITION,
    XL_TICK_MARK,
)
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Cm, Emu, Pt

# ============================================================
# §4.1 캔버스 & 좌표계
# ============================================================
# A4(가로) 용지 — Open ALM a4/세미나 양식과 동일 치수(27.517 × 19.05cm).
SLIDE_W_CM = 27.517
SLIDE_H_CM = 19.05
SLIDE_W = Cm(SLIDE_W_CM)
SLIDE_H = Cm(SLIDE_H_CM)

# 본문 논리 캔버스 — 세미나(A4) 본문 틀(apply_body_chrome)의 콘텐츠 안전구역에 맞춤.
# 가로선 y=1.85 바로 아래(공백 최소) ~ 하단 영문 저작권 y=18.50 위, 좌우 0.8cm 여백.
BODY_X_CM = 0.8
BODY_Y_CM = 2.1
BODY_W_CM = 25.9
BODY_H_CM = 16.1


def bx(cm: float) -> Emu:
    """논리 x(cm) → 절대 EMU."""
    return Cm(BODY_X_CM + cm)


def by(cm: float) -> Emu:
    """논리 y(cm) → 절대 EMU."""
    return Cm(BODY_Y_CM + cm)


def L(cm: float) -> Emu:
    """폭/높이(cm) → EMU."""
    return Cm(cm)


# ============================================================
# §4.2 색 토큰
# ============================================================
COLORS = {
    "ink": RGBColor(0x1A, 0x1A, 0x1A),
    "blue": RGBColor(0x1F, 0x4E, 0x9C),
    "link": RGBColor(0x25, 0x40, 0xC0),
    "hdr": RGBColor(0xDC, 0xE6, 0xF1),
    "grid": RGBColor(0x80, 0x80, 0x80),
    "red": RGBColor(0xE2, 0x23, 0x1A),
    "g400": RGBColor(0x9C, 0xA3, 0xAF),
    "white": RGBColor(0xFF, 0xFF, 0xFF),
    "dwNavy": RGBColor(0x1B, 0x3A, 0x8B),
    "dwOrange": RGBColor(0xF2, 0x6A, 0x21),
}


def _color(token_or_hex) -> RGBColor:
    """'blue'/'ink' 토큰 또는 'RRGGBB' HEX → RGBColor. 기본 ink."""
    if token_or_hex is None:
        return COLORS["ink"]
    if isinstance(token_or_hex, RGBColor):
        return token_or_hex
    key = str(token_or_hex).strip()
    if key in COLORS:
        return COLORS[key]
    try:
        return RGBColor.from_string(key.lstrip("#"))
    except Exception:
        return COLORS["ink"]


# ============================================================
# §4.3 타이포그래피
# ============================================================
# SPEC §4.3 은 Pretendard 를 지정하나, 기존 PPT 시스템 전체가 사내 표준 폰트 'Pretendard'
# 으로 통일돼 있고 사내 뷰어/라이선스에 설치돼 있어 그쪽으로 맞춘다. latin/ea/cs 모두 동일
# 이름으로 통일해 한글이 기본폰트로 깨지지 않게 한다. 다른 폰트로 바꾸려면 이 상수만 교체.
FONT = "Pretendard"

_ALIGN = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}


def _kill_shadow(shape) -> None:
    """자동 도형 그림자 제거."""
    try:
        spPr = shape._element.spPr
        existing = spPr.find(qn("a:effectLst"))
        if existing is None:
            spPr.append(spPr.makeelement(qn("a:effectLst"), {}))
    except Exception:
        pass


def set_run(run, text, size, *, bold=False, color="ink", underline=False, font=FONT) -> None:
    """런에 텍스트+폰트 적용. §6.1: 한글이 FONT 로 렌더되도록 a:ea·a:cs 강제 지정."""
    run.text = "" if text is None else str(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.underline = underline
    run.font.color.rgb = _color(color)
    run.font.name = font  # latin
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", font)


# 인라인 강조: **단어** → 그 단어만 굵게(검정 유지). 사내 요청 — 강조는 색·전체 볼드 대신 단어 볼드.
_EMPH_RE = re.compile(r"\*\*(.+?)\*\*")


def _strip_emph(s: str) -> str:
    """폭/줄수 추정용 — ** 마커는 렌더 시 사라지므로 측정에서 제거한다."""
    return _EMPH_RE.sub(r"\1", str(s or ""))


def _emit_emph_runs(p, text, fs, *, bold=False, color="ink", underline=False, font=FONT) -> None:
    """문단 p 에 text 를 런으로 추가하되 **...** 구간만 굵게 그린다(나머지는 base 스타일)."""
    s = "" if text is None else str(text)
    pos = 0
    emitted = False
    for m in _EMPH_RE.finditer(s):
        if m.start() > pos:
            set_run(p.add_run(), s[pos:m.start()], fs, bold=bold, color=color, underline=underline, font=font)
            emitted = True
        set_run(p.add_run(), m.group(1), fs, bold=True, color=color, underline=underline, font=font)
        emitted = True
        pos = m.end()
    if pos < len(s) or not emitted:
        set_run(p.add_run(), s[pos:], fs, bold=bold, color=color, underline=underline, font=font)


# ============================================================
# §6.2 표 테두리 (python-pptx 미지원 → tcPr XML)
# ============================================================
def _set_cell_border(cell, color="808080", w_emu=9525, sides=("L", "R", "T", "B")) -> None:
    """셀 4면 괘선. 0.75pt ≈ 9525 EMU. 전체 격자 = 모든 셀 4면 호출."""
    tcPr = cell._tc.get_or_add_tcPr()
    for side in sides:
        tag = qn(f"a:ln{side}")
        for old in tcPr.findall(tag):
            tcPr.remove(old)
        ln = etree.SubElement(tcPr, tag)
        ln.set("w", str(int(w_emu)))
        ln.set("cap", "flat")
        fill = etree.SubElement(ln, qn("a:solidFill"))
        clr = etree.SubElement(fill, qn("a:srgbClr"))
        clr.set("val", str(color))


# ============================================================
# §6.3 도형 헬퍼
# ============================================================
def _add_textbox(slide, left, top, width, height, *, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    return tb, tf


def _add_rect(slide, left, top, width, height, *, fill=None, line_color=None, line_pt=0.0):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _color(fill)
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _color(line_color)
        shape.line.width = Pt(line_pt)
    _kill_shadow(shape)
    return shape


def _add_shape(slide, mso, left, top, width, height, *, fill=None, line_color=None, line_pt=0.0):
    shape = slide.shapes.add_shape(mso, left, top, width, height)
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = _color(fill)
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _color(line_color)
        shape.line.width = Pt(line_pt)
    _kill_shadow(shape)
    return shape


# ============================================================
# §4.4 프레임 (슬라이드 공통)
# ============================================================
def _draw_frame(slide, data: dict, logo_path=None) -> None:
    """본문 공통 틀 — 세미나(A4) 본문 틀(builders_a4.apply_body_chrome)을 그대로 재사용.

    ▣ 제목(좌상) + 우상단 날짜 + 가로선 사이 OPEN ALM 로고 + 사선 DCC 워터마크 +
    하단 영문 저작권 + Confidential 배지. (하우스 고유의 'N. 제목 [태그]'·'N/total' 푸터는 제거)
    """
    from open_alm_api.domains.ppt_generator.design.builders_a4 import apply_body_chrome

    # 제목은 ▣ 헤더에 그대로 표시한다. 태그는 붙이지 않는다(제목+태그가 길면 말줄임 '…'
    # 발생). title_fixed_pt 를 주지 않아 길면 폰트만 자동 축소(말줄임 없이 전체 표시).
    # 사선 DCC 워터마크·하단 저작권 footer 는 본문마다 그리지 않고(watermark=False, footer=False)
    # 슬라이드 마스터에 1회만 올린다(_build_pptx_bytes). → 모든 본문이 배경으로 상속해 선택·이동/
    # 편집 불가한 진짜 워터마크가 된다.
    title = str(data.get("title") or "")
    apply_body_chrome(slide, title, logo_path=logo_path, watermark=False, footer=False)


# ============================================================
# §4.5 ■ 섹션 헤딩
# ============================================================
_SECTION_H = 0.66  # cm (실제 렌더에 맞춰 약간 축소 — 블록 간 공백 감소)
_SECTION_GAP = 0.3  # cm — ■ 섹션 제목과 바로 아래 내용(표/글) 사이 간격(사내 요청: 너무 붙지 않게)
# 섹션명 앞 불릿 기호(■ 등) 제거용 — 렌더러가 ■ 를 자동으로 붙이므로 LLM 이 넣어 온 ■ 와 중복 방지.
_BULLET_PREFIX_RE = re.compile(r"^[\s■□▣▪◼◾●○◆◇·•∎]+")


def _strip_bullet(s) -> str:
    return _BULLET_PREFIX_RE.sub("", str(s or "")).strip()


def _section(
    slide, y_cm: float, heading: str, x_cm: float = 0.0, w_cm: float = BODY_W_CM,
    ole: dict | None = None,
) -> float:
    tb, tf = _add_textbox(slide, bx(x_cm), by(y_cm), L(w_cm), L(_SECTION_H), anchor=MSO_ANCHOR.MIDDLE)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    label = f"■ {_strip_bullet(heading)}"
    set_run(p.add_run(), label, 15.5, bold=True, color="ink")
    # 섹션 똑딱이(OLE): 제목 글자 뒤 0.5cm 옆에 0.6×0.6cm 작은 아이콘. finalize 가 이 자리를 OLE 로
    # 교체. 폭은 렌더와 같은 정확한 계수(_text_width_wrap_cm, COM 보정)로 재야 아이콘이 글자 바로 옆에
    # 붙는다(옛 _text_width_cm 은 ~1.1cm 과대추정해 아이콘이 멀리 떨어졌음).
    if isinstance(ole, dict):
        _draw_section_ole_icon(slide, ole, y_cm, x_cm + _heading_width_cm(label, 15.5) + 0.45)
    return y_cm + _SECTION_H


def _draw_section_ole_icon(slide, ole: dict, y_cm: float, x_cm: float) -> None:
    """섹션 제목 옆 '똑딱이' 아이콘(0.6×0.6cm)을 그린다. src(data-URI) 의 PNG 를 그대로 쓴다."""
    import base64
    from io import BytesIO

    src = str((ole or {}).get("src") or "")
    if not src.startswith("data:") or "," not in src:
        return
    try:
        img = base64.b64decode(src.split(",", 1)[1])
    except Exception:  # noqa: BLE001
        return
    side = 0.6
    x = min(x_cm, BODY_W_CM - side - 0.05)
    # 제목 행(_SECTION_H) 안에서 세로 가운데 정렬.
    y = y_cm + max(0.0, (_SECTION_H - side) / 2)
    try:
        pic = slide.shapes.add_picture(BytesIO(img), bx(x), by(y), L(side), L(side))
        # finalize 의 OLE 주입이 이 그림을 찾을 때, PNG 바이트 재인코딩에도 견고하도록 shape 이름으로
        # 표식한다(1순위 매칭 키). idx 는 임베드와 1:1.
        idx = (ole or {}).get("idx")
        if isinstance(idx, int):
            pic.name = f"ole-icon-{idx}"
    except Exception:  # noqa: BLE001
        return


# ============================================================
# lead 블록 — ■ 목적 : <텍스트> 한 줄
# ============================================================
_LEAD_H = 0.85


def _lead(slide, y_cm: float, block: dict, x_cm: float = 0.0, w_cm: float = BODY_W_CM) -> float:
    label = _strip_bullet(block.get("label")) or "목적"
    text = str(block.get("text") or "")
    tb, tf = _add_textbox(slide, bx(x_cm), by(y_cm), L(w_cm), L(_LEAD_H), anchor=MSO_ANCHOR.MIDDLE)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    set_run(p.add_run(), f"■ {label} : ", 15.5, bold=True, color="ink")
    _emit_emph_runs(p, text, 12.5, color="ink")
    return y_cm + _LEAD_H


# ============================================================
# conclusion 블록 — 파란 굵은 1~2줄
# ============================================================
_CONCLUSION_H = 1.0


def _conclusion(slide, y_cm: float, block: dict, x_cm: float = 0.0, w_cm: float = BODY_W_CM) -> float:
    text = str(block.get("text") or "")
    tb, tf = _add_textbox(slide, bx(x_cm), by(y_cm), L(w_cm), L(_CONCLUSION_H), anchor=MSO_ANCHOR.MIDDLE)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    set_run(p.add_run(), text, 14, bold=True, color="blue")
    return y_cm + _CONCLUSION_H


# ============================================================
# §4.6 표 — 연파랑 헤더 + 전체 격자
# ============================================================
_BR_RE = re.compile(r"<br\s*/?>|\n", re.IGNORECASE)

# 본문 표 셀 글자 크기(pt) — 사내 요청으로 12pt 고정. LLM 이 보낸 fs 는 무시한다.
BODY_FS = 12.0

# 글자 폭 추정 계수(em). Pretendard 한글 실측 ≈ 1.0em 이라 1.1 로 약간만 여유(실제보다 살짝
# 넓게 → 줄바꿈/행높이 추정이 안전). 예전 1.25 는 과대추정이라 옆으로 들어갈 표를 세로로 쌓았다.
_KO_EM = 1.1
_ASCII_EM = 0.6


def _cell_segments(value) -> list[str]:
    """셀 값(4형태)을 명시적 줄(<br>/\\n, lines/runs) 단위 문자열 리스트로 펼친다."""
    if isinstance(value, str):
        return _BR_RE.split(value) or [""]
    if isinstance(value, dict):
        # lines/runs 가 (LLM 실수로) 리스트가 아니라 문자열로 올 수 있다 → 단일 항목 리스트로 보정.
        # (문자열을 그대로 순회하면 글자 단위로 쪼개져 셀이 세로로 찍힌다.)
        lines = value.get("lines")
        if isinstance(lines, str):
            lines = [lines]
        if isinstance(lines, list):
            out: list[str] = []
            for ln in lines:
                out += _BR_RE.split(str(ln))
            return out or [""]
        runs = value.get("runs")
        if isinstance(runs, str):
            runs = [runs]
        if isinstance(runs, list):
            out = []
            for r in runs:
                t = r.get("t", "") if isinstance(r, dict) else str(r)
                out += _BR_RE.split(str(t))
            return out or [""]
        return _BR_RE.split(str(value.get("t", ""))) or [""]
    return [str(value)]


def _regroup_flat_table_rows(block: dict) -> None:
    """LLM 이 표 rows 를 '행들의 리스트'가 아니라 **셀을 평탄하게 나열**해 보낸 경우 교정(in-place).

    예: header 5칸인데 rows=[{"t":"수치"}, "20.7백만", "25.5%", "$108", "국면"] → 5행 5×1 로
    오해돼 값이 1열에 세로로 쌓인다. header 칸수로 재그룹해 1행 5열로 되돌린다.

    안전장치: 모든 원소가 **scalar 셀**(문자열 또는 lines/runs 없는 dict)이고 개수가 칸수의 배수일
    때만 동작. 정상 표(행이 리스트)나 {lines/runs} 셀(→ _as_cells 가 다중 셀로 푸는 케이스)엔 무영향.
    """
    rows = block.get("rows")
    header = block.get("header")
    if not isinstance(rows, list) or not rows:
        return
    ncols = len(header) if isinstance(header, list) and header else 0
    if ncols < 2 or len(rows) % ncols != 0:
        return

    def _scalar_cell(x) -> bool:
        if isinstance(x, str):
            return True
        if isinstance(x, dict):
            return not (isinstance(x.get("lines"), list) or isinstance(x.get("runs"), list))
        return False

    if all(_scalar_cell(x) for x in rows):
        block["rows"] = [rows[i : i + ncols] for i in range(0, len(rows), ncols)]


def _as_cells(r) -> list:
    """표의 한 행(row)을 셀 리스트로 정규화.

    정상은 ["셀", "셀", …] 이지만 LLM 이 행을 셀 형식 dict({"lines":[...]}/{"runs":[...]})로
    감싸 보내는 실수가 잦다 → 그 경우 안의 값을 셀들로 풀어낸다(크래시·빈칸 방지).
    """
    if isinstance(r, list):
        return r
    if isinstance(r, tuple):
        return list(r)
    if isinstance(r, dict):
        if isinstance(r.get("lines"), list):
            return list(r["lines"])
        if isinstance(r.get("runs"), list):
            return [x.get("t", "") if isinstance(x, dict) else x for x in r["runs"]]
        return list(r.values())
    return [r]


# 줄바꿈·열폭·side-by-side 판정 공용 글자폭 — Pretendard **COM 실측**: 한글 1.03em, ASCII 0.51~0.59.
# 예전 1.3(과대 26%)은 1줄에 들어갈 셀을 2~3줄로 세어 행을 억지로 키웠다('행 세로 크기 늘어남').
# 실측 1.03 그대로 쓴다(1.08도 근소 boundary 에서 1줄→2줄 과대판정). PowerPoint 실제 배치가 이 추정보다
# 관대(더 많이 1줄에 넣음)해 under-count 위험은 낮고, _LINE_CM(줄당 0.601>실제0.5)+_TABLE_SAFETY_CM 이 완충.
_WRAP_KO_EM = 1.03
_WRAP_ASCII_EM = 0.6
# 공백·문장부호는 글자보다 훨씬 좁다(Pretendard 실측: 공백 0.30 / 쉼표·콜론 0.31 / 괄호 0.34em).
# 예전엔 이들을 ascii 글자폭(0.6)으로 세어, 공백·쉼표 많은 문장이 2배 가까이 부풀어 줄바꿈 오판 →
# 행 팽창 + 표 과대추정 → 페이지 공백. 실측폭(0.33)으로 센다.
_WRAP_NARROW = set(" ,.:;·|/\\-–—()[]{}'\"~!?%")
_WRAP_NARROW_EM = 0.33


def _char_wrap_w(ch: str) -> float:
    """글자 1개의 폭(em) — 줄바꿈/자연폭 공용. 공백·문장부호는 좁게, 한글 1.03, ascii 0.6."""
    if ch == " " or ch in _WRAP_NARROW:
        return _WRAP_NARROW_EM
    if ord(ch) < 0x2500 and ch.isascii():
        return _WRAP_ASCII_EM
    return _WRAP_KO_EM


@functools.lru_cache(maxsize=8192)
def _wrap_lines(text: str, col_w_cm: float, fs: float) -> int:
    """주어진 열 폭·글자크기에서 한 문장이 자동 줄바꿈으로 차지하는 줄 수(보수적 추정).

    순수 함수(입력 → 줄 수)라 lru_cache 로 메모이즈한다. 리패킹·트림 루프가 동일 (text, 폭, fs)
    조합으로 셀당 문자 스캔을 수천 번 반복하던 것을 캐시 히트로 제거한다(핫패스 CPU 절감).

    PowerPoint 행 높이는 '최소값'이라 셀 내용이 길면 행이 자동으로 늘어난다. 이를 반영하지
    않으면 표 아래 블록이 늘어난 표와 겹친다. PowerPoint 는 공백(어절) 단위로 줄바꿈하고 라틴
    토큰을 중간에서 안 자르므로, 연속 채움이 아니라 **어절 greedy 줄바꿈**으로 세야 실제와 맞는다
    (연속 채움 추정은 줄 수를 과소계산 → 행이 커져 겹침). 과대추정(여백)이 겹침보다 안전하다.
    """
    s = _strip_emph(text)
    if not s:
        return 1
    # 셀 좌우 margin(0.14*2=0.28) → 사용 가능 폭.
    usable = max(0.5, col_w_cm - 0.28)
    em_cm = fs * 0.03528  # 1em
    cap_em = max(1.0, usable / em_cm)  # 한 줄에 들어가는 em 수

    def _w(tok: str) -> float:
        return sum(_char_wrap_w(ch) for ch in tok)

    space_w = _WRAP_NARROW_EM
    lines = 1
    cur = 0.0
    for tok in s.split(" "):
        if not tok:
            cur += space_w
            continue
        w = _w(tok)
        add = w + (space_w if cur > 0 else 0.0)
        if cur + add <= cap_em:
            cur += add
        elif w <= cap_em:
            lines += 1  # 새 줄에 토큰 하나
            cur = w
        else:
            # 토큰이 한 줄보다 김 → 연속 문자 줄바꿈으로 여러 줄 차지
            extra = math.ceil(w / cap_em)
            lines += extra
            cur = w - (extra - 1) * cap_em
    return max(1, lines)


def _cell_line_count(value, col_w_cm: float | None = None, fs: float | None = None) -> int:
    """셀 표시 줄 수. col_w_cm·fs 가 주어지면 자동 줄바꿈까지 반영, 아니면 명시적 줄만 센다."""
    segs = _cell_segments(value)
    if col_w_cm is None or fs is None:
        return max(1, len(segs))
    return max(1, sum(_wrap_lines(s, col_w_cm, fs) for s in segs))


def _content_col_widths(block: dict, cols: int, fs: float = BODY_FS) -> list[float]:
    """각 열의 '한 줄' 자연 폭(cm) — 헤더+셀 내용 중 가장 긴 줄 기준.

    렌더 줄바꿈(_wrap_lines, 한글 1.3em)과 **같은 계수**로 잡는다. 이래야 _norm_colw 가 이 폭을
    배분했을 때 실제로 1줄에 들어간다(1.1em 으로 좁게 잡으면 그 폭에서 줄바꿈돼 행이 커졌다).
    """
    header = list(block.get("header") or [])
    rows = list(block.get("rows") or [])
    cw = [0.0] * cols
    for c in range(cols):
        if c < len(header):
            cw[c] = max(cw[c], _text_width_wrap_cm(str(header[c]), fs))
    for r in rows:
        rr = _as_cells(r)
        for c in range(min(cols, len(rr))):
            segs = _cell_segments(rr[c])  # {lines:[...]} 등은 줄별 → 최대 줄 폭
            mw = max((_text_width_wrap_cm(s, fs) for s in segs), default=0.0)
            cw[c] = max(cw[c], mw)
    return cw


def _norm_colw(block: dict, cols: int, w_cm: float = BODY_W_CM) -> list[float]:
    """열 폭을 **내용 기반**으로 자동 배분(긴 내용 열에 더 넓게) — 최대한 한 줄로 출력되도록.

    각 열의 한 줄 자연 폭에 비례해 영역 폭(w_cm)을 나누되, 짧은 열(구분/기업 등)이 찌부되지
    않도록 최소 폭을 보장한다. 내용이 없으면 균등 분배. (LLM 의 colW 는 참고하지 않는다 —
    내용에 맞춘 자동 폭이 한 줄 출력에 유리.)
    """
    floor = min(1.6, w_cm / cols)  # 최소 열 폭(단, 균등폭은 넘지 않게)
    nat = _content_col_widths(block, cols)
    nat = [max(floor, n + 0.35) for n in nat]  # 셀 좌우 여백 가산(margin 0.28+여유) + 최소 폭
    total = sum(nat)
    if total <= 0:
        return [w_cm / cols] * cols
    if total <= w_cm:
        extra = w_cm - total
        return [n + extra * (n / total) for n in nat]  # 남는 폭은 긴 열에 더 많이
    return [n * w_cm / total for n in nat]


def _render_cell(cell, value, col_align: str, fs: float, plain: bool = False) -> None:
    """셀 값(4형태) → 문단/런. 세로 가운데, 작은 여백.

    plain=True 면 본문 셀의 굵게·색·밑줄을 무시하고 평범한 검정 글씨로 그린다(사내 요청).
    헤더는 plain=False 로 두어 굵게·가운데를 유지한다.
    """
    tf = cell.text_frame
    tf.word_wrap = True
    # 세로 가운데: 표 셀은 tcPr@anchor 를 따르므로 셀 객체에 직접 지정한다(text_frame 쪽은 무시됨).
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = Cm(0.14)
    cell.margin_right = Cm(0.14)
    cell.margin_top = Cm(0.1)
    cell.margin_bottom = Cm(0.1)

    # value 를 (문단 정의 리스트)로 정규화. 각 항목 = {"al", "runs":[{t,b,c,u}]}
    # LLM 이 셀 줄바꿈을 <br>(또는 \n)으로 넣는 경우가 많아, 런 텍스트를 줄 단위로 쪼개
    # 여러 문단으로 펼친다(그대로 두면 '<br>' 가 글자로 찍힘).
    paras: list[dict] = []

    def _emit(run_dict: dict, al: str) -> None:
        segs = _BR_RE.split(str(run_dict.get("t", "")))
        for seg in segs:
            paras.append({"al": al, "runs": [{**run_dict, "t": seg}]})

    if isinstance(value, str):
        _emit({"t": value}, col_align)
    elif isinstance(value, dict) and "lines" in value:
        al = value.get("al", col_align)
        lines = value.get("lines")
        if isinstance(lines, str):  # LLM 이 리스트 대신 문자열을 준 경우(세로로 쪼개짐) 보정
            lines = [lines]
        for line in lines or []:
            _emit({"t": str(line)}, al)
    elif isinstance(value, dict) and "runs" in value:
        runs = value.get("runs")
        if isinstance(runs, str):
            runs = [runs]
        for r in runs or []:
            if isinstance(r, dict):
                _emit(r, r.get("al", col_align))
            else:
                _emit({"t": str(r)}, col_align)
    elif isinstance(value, dict):  # 단일 스타일 {t,b,c,al}
        _emit(value, value.get("al", col_align))
    else:
        _emit({"t": str(value)}, col_align)

    if not paras:
        paras = [{"al": col_align, "runs": [{"t": ""}]}]

    for i, pd in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        # 사내 요청: 우측 정렬('r')은 쓰지 않는다 → 좌측으로. (헤더의 'c' 가운데는 유지)
        al = pd.get("al", col_align)
        if al == "r":
            al = "l"
        p.alignment = _ALIGN.get(al, PP_ALIGN.LEFT)
        # 셀 세로 공백 제거(사내 요청): 줄 간격 단일·문단 앞뒤 여백 0 → 여러 줄/문단이라도 딱 붙는다.
        p.line_spacing = 1.0
        p.space_before = Pt(0)
        p.space_after = Pt(0)
        for rd in pd["runs"]:
            # **단어** 인라인 볼드 지원. plain(본문)이면 base 는 검정·보통이되 ** 구간만 굵게.
            _emit_emph_runs(
                p,
                rd.get("t", ""),
                fs,
                bold=False if plain else bool(rd.get("b", False)),
                color="ink" if plain else rd.get("c", "ink"),
                underline=False if plain else bool(rd.get("u", False)),
            )


# 셀 상하 여백 합(_render_cell 의 margin_top+margin_bottom). 행 높이 = 줄높이 + 이 여백.
_CELL_VPAD = 0.24
# 12pt 셀 한 줄의 실제 높이 근사(Pretendard). 실측(COM) 기준 상향 — set≥실제여야 PPT 가 행을
# 안 키우고 아래 블록과 안 겹친다(과대추정=약간의 여백, 겹침보다 안전).
_LINE_CM = BODY_FS * 0.03528 * 1.42
# 본문행 1줄 최소 높이(cm). **이 값을 행 높이로 직접 지정**하므로 추정=실제가 되어 겹치지 않는다.
# (예전엔 최소만 주고 PPT auto-fit 에 맡겨, 추정 place_total 보다 실제가 커지면 아래 블록과 겹쳤다.)
_ROW_MIN = max(0.6, _LINE_CM + _CELL_VPAD)
# PowerPoint 표의 고정 렌더 오버헤드(헤더/행 누적)를 흡수하는 안전 여백(cm) — 다음 블록 위치·높이
# 추정에 더해 표와 겹치지 않게 한다. 추정과 렌더 반환에 동일하게 적용(compaction↔layout 일치).
_TABLE_SAFETY_CM = 0.4


def _body_row_heights(rows: list, cols: int, col_w: list, fs: float, w_cm: float = BODY_W_CM) -> list[float]:
    """각 본문행의 렌더 높이(cm) 리스트 — 자동 줄바꿈 줄 수 × 줄높이 + 셀 여백.

    이 값을 그대로 행 높이로 지정하므로(=추정이 곧 실제 높이), 다음 블록이 표와 겹치지 않는다.
    줄 수는 보수적으로(과대) 추정해, 실제 PowerPoint 가 행을 더 키우는 일이 없게 한다.
    """
    out: list[float] = []
    for r in rows:
        max_lines = 1
        for c in range(cols):
            cw = col_w[c] if c < len(col_w) else w_cm / cols
            cells = _as_cells(r)
            max_lines = max(max_lines, _cell_line_count(cells[c] if c < len(cells) else "", cw, fs))
        out.append(max(_ROW_MIN, max_lines * _LINE_CM + _CELL_VPAD))
    return out


def _estimate_body_rows(rows: list, cols: int, col_w: list, fs: float, w_cm: float = BODY_W_CM) -> float:
    """본문행 총 높이(cm) — 행별 렌더 높이의 합(배치/리패킹·실제 렌더 공통 기준)."""
    return sum(_body_row_heights(rows, cols, col_w, fs, w_cm))


# 짧은 값(수치·퍼센트·연도·상태 등) 한 칸 최대 글자수 — 이하면 그 열을 가운데 정렬한다.
_SHORT_CELL_CHARS = 6


def _auto_center_cols(block: dict, cols: int, align: list) -> list:
    """짧은 값(≤_SHORT_CELL_CHARS자)으로만 채워진 본문 열은 가운데 정렬로 맞춘다(사내 요청).

    수치/퍼센트처럼 글자수 적은 열은 가운데가 깔끔하다. 한 칸이라도 긴 내용이 있으면 그대로 둔다.
    """
    rows = list(block.get("rows") or [])
    out = list(align) + ["l"] * max(0, cols - len(align))
    for c in range(cols):
        longest = 0
        any_val = False
        for r in rows:
            cells = _as_cells(r)
            if c >= len(cells):
                continue
            for s in _cell_segments(cells[c]):
                s = str(s).strip()
                if s:
                    any_val = True
                    longest = max(longest, len(s))
        if any_val and longest <= _SHORT_CELL_CHARS:
            out[c] = "c"
    return out[:cols]


def _table(slide, y_cm: float, block: dict, body_h_cm: float, x_cm: float = 0.0, w_cm: float = BODY_W_CM, fill_h: float | None = None) -> float:
    _regroup_flat_table_rows(block)  # 평탄 나열된 rows 를 header 칸수로 재그룹(방어적)
    header = list(block.get("header") or [])
    has_header = bool(header)  # 헤더 없는 표(단일 열 목록 등) 지원
    hoff = 1 if has_header else 0
    rows = list(block.get("rows") or [])
    cols = len(header) if header else (len(_as_cells(rows[0])) if rows else 1)
    col_w = _norm_colw(block, cols, w_cm)
    align = list(block.get("align") or ["l"] * cols)
    align = _auto_center_cols(block, cols, align)  # 짧은 값(수치·%) 열은 가운데 정렬
    fs = BODY_FS  # 본문 글자 12pt 고정(사내 요청). LLM 의 fs 는 무시.
    hfs = float(block.get("hfs", 12))
    header_h = float(block.get("headerH", 0.6))
    row_h = block.get("rowH")

    n_body = len(rows)
    head = header_h if has_header else 0.0
    if row_h is None:
        # 행별 자연 높이를 그대로 지정 → 추정=실제(PPT 가 더 키우지 않음) → 아래 블록과 겹치지 않음.
        set_row_h = _body_row_heights(rows, cols, col_w, fs, w_cm)
    else:
        set_row_h = [float(h) for h in row_h]
        if len(set_row_h) < n_body:
            set_row_h += [set_row_h[-1] if set_row_h else 0.9] * (n_body - len(set_row_h))
    place_total = head + sum(set_row_h)

    # 표는 행을 늘려 옆 블록 높이에 맞추지 않는다(사내 요청). 예전엔 fill_h 까지 행을 균등 가산해
    # 키를 맞췄으나, 내용이 적은 표는 행마다 큰 공백이 생겨('쓸데없는 공백 줄') 보기 싫었다.
    # → 표는 항상 내용에 딱 맞는 자연 높이로 컴팩트하게 그린다. (차트·timeline 은 fill_h 로 늘림.)
    # 옆 블록이 더 높으면 표는 위로 정렬되고 아래 공간은 비워둔다(리패킹·내용 보강이 채움).

    n_rows = n_body + hoff

    gfx = slide.shapes.add_table(n_rows, cols, bx(x_cm), by(y_cm), L(sum(col_w)), L(place_total))
    tbl = gfx.table
    tbl.first_row = tbl.last_row = tbl.horz_banding = tbl.vert_banding = False
    # 기본 표 스타일(밴딩/음영) 제거 — styleId 박혀 자동 적용되므로 지움.
    try:
        tblPr = tbl._tbl.tblPr
        for el in tblPr.findall(qn("a:tableStyleId")):
            tblPr.remove(el)
    except Exception:
        pass

    for i in range(cols):
        tbl.columns[i].width = L(col_w[i] if i < len(col_w) else w_cm / cols)
    if has_header:
        tbl.rows[0].height = L(header_h)
    for r in range(n_body):
        tbl.rows[r + hoff].height = L(set_row_h[r])

    # 헤더행: hdr 채움 + ink 굵게 + 가운데 (헤더가 있을 때만)
    if has_header:
        for c in range(cols):
            cell = tbl.cell(0, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = COLORS["hdr"]
            label = header[c] if c < len(header) else ""
            _render_cell(cell, {"t": label, "b": True, "al": "c"}, "c", hfs)
            _set_cell_border(cell)

    # 본문행
    for r in range(n_body):
        row = rows[r]
        for c in range(cols):
            cell = tbl.cell(r + hoff, c)
            cells = _as_cells(row)
            value = cells[c] if c < len(cells) else ""
            col_align = align[c] if c < len(align) else "l"
            _render_cell(cell, value, col_align, fs, plain=True)  # 본문 셀: 평범한 검정(굵게·색·밑줄 무시)
            _set_cell_border(cell)

    # PowerPoint 가 표를 우리 설정 높이보다 일정하게 조금 더 크게 렌더(헤더/행 오버헤드 누적)하므로,
    # **다음 블록 위치**에 안전 여백을 더해 표와 겹치지 않게 한다. 셀 높이 자체는 건드리지 않는다.
    return y_cm + place_total + _TABLE_SAFETY_CM


# ============================================================
# text 블록 — 표/차트가 필요 없을 때의 본문 단락/불릿
# ============================================================
_TEXT_FS = 12.0
_TEXT_LINE_CM = (_TEXT_FS * 0.03528) * 1.5


def _text_lines(block: dict) -> list[tuple[str, bool]]:
    """text 블록을 (문자열, 불릿여부) 리스트로 정규화. bullets[] 또는 text(여러 줄) 지원."""
    out: list[tuple[str, bool]] = []
    bullets = block.get("bullets")
    if isinstance(bullets, list) and bullets:
        for b in bullets:
            out.append((str(b), True))
        return out
    txt = str(block.get("text") or "")
    for seg in _BR_RE.split(txt):
        if seg.strip():
            out.append((seg, False))
    return out or [("", False)]


def _text(slide, y_cm: float, block: dict, body_h_cm: float, x_cm: float = 0.0, w_cm: float = BODY_W_CM) -> float:
    lines = _text_lines(block)
    # 폭 기준 자동 줄바꿈까지 반영해 높이 산정(겹침 방지).
    total_lines = 0
    for s, _ in lines:
        total_lines += _wrap_lines(s, w_cm, _TEXT_FS)
    h = max(_TEXT_LINE_CM, total_lines * _TEXT_LINE_CM + 0.10)
    tb, tf = _add_textbox(slide, bx(x_cm), by(y_cm), L(w_cm), L(h), anchor=MSO_ANCHOR.TOP)
    for i, (s, bullet) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        if bullet:
            set_run(p.add_run(), "• ", _TEXT_FS, color="ink")
        _emit_emph_runs(p, s, _TEXT_FS, color="ink")
    return y_cm + h


# ============================================================
# chart 블록 — PowerPoint 네이티브 편집 차트(엑셀 데이터 내장)
# ============================================================
_CHART_H = 5.2  # 차트 블록 기본 높이(cm) — 너무 크지 않게
_CHART_H_PIE = 4.8  # 원형/도넛은 더 작게(좌우 여백을 덜 잡아먹도록)
_CHART_TYPES = {
    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
    "bar": XL_CHART_TYPE.BAR_CLUSTERED,
    "line": XL_CHART_TYPE.LINE_MARKERS,
    "pie": XL_CHART_TYPE.PIE,
    "doughnut": XL_CHART_TYPE.DOUGHNUT,
}
# 계열/조각 색 팔레트(Open ALM 톤).
_CHART_PALETTE = ["blue", "dwOrange", "dwNavy", "g400", "link", "red"]


def _num(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _style_chart_axes(chart) -> None:
    """막대/꺾은선 차트 축·격자선을 옅게 다듬는다(기본 PowerPoint 스타일이 너무 진함)."""
    light = RGBColor(0xE5, 0xE7, 0xEB)  # 격자선 연회색
    axln = RGBColor(0xD1, 0xD5, 0xDB)  # 축선 연회색
    ink = RGBColor(0x37, 0x41, 0x51)
    muted = RGBColor(0x6B, 0x72, 0x80)
    try:
        va = chart.value_axis
        va.has_major_gridlines = True
        va.has_minor_gridlines = False
        gl = va.major_gridlines.format.line
        gl.color.rgb = light
        gl.width = Pt(0.5)
        va.format.line.color.rgb = light  # 값축 세로선도 옅게
        va.format.line.width = Pt(0.5)
        va.tick_labels.font.size = Pt(9)
        va.tick_labels.font.color.rgb = muted
        va.tick_labels.font.name = FONT
        va.major_tick_mark = XL_TICK_MARK.NONE
        va.minor_tick_mark = XL_TICK_MARK.NONE
    except Exception:
        pass
    try:
        ca = chart.category_axis
        ca.has_major_gridlines = False
        ca.has_minor_gridlines = False
        ca.format.line.color.rgb = axln
        ca.format.line.width = Pt(0.75)
        ca.tick_labels.font.size = Pt(10)
        ca.tick_labels.font.color.rgb = ink
        ca.tick_labels.font.name = FONT
        ca.major_tick_mark = XL_TICK_MARK.NONE
        ca.minor_tick_mark = XL_TICK_MARK.NONE
    except Exception:
        pass


def _chart(slide, y_cm: float, block: dict, body_h_cm: float, x_cm: float = 0.0, w_cm: float = BODY_W_CM, fill_h: float | None = None) -> float:
    ctype = _CHART_TYPES.get(str(block.get("chart", "column")).lower(), XL_CHART_TYPE.COLUMN_CLUSTERED)
    is_pie = ctype in (XL_CHART_TYPE.PIE, XL_CHART_TYPE.DOUGHNUT)
    cats = [str(c) for c in (block.get("categories") or [])]
    series = [s for s in (block.get("series") or []) if isinstance(s, dict)]
    if not series:
        return y_cm  # 데이터 없으면 그리지 않음

    # 빈 라벨 카테고리(맨 끝 빈 칸 등) 제거 — 같은 인덱스의 계열 값도 함께 제거.
    keep = [i for i, c in enumerate(cats) if str(c).strip()]
    if keep and len(keep) != len(cats):
        cats = [cats[i] for i in keep]
        trimmed = []
        for s in series:
            vals = list(s.get("values") or [])
            trimmed.append({**s, "values": [vals[i] for i in keep if i < len(vals)]})
        series = trimmed
    # 값이 없는(계열 값 개수보다 많은) 뒤쪽 카테고리 제거 — '부채비율'처럼 빈 막대 칸 방지.
    max_vals = max((len(s.get("values") or []) for s in series), default=0)
    if 0 < max_vals < len(cats):
        cats = cats[:max_vals]
    if not cats:
        cats = ["1"]

    cd = CategoryChartData()
    cd.categories = cats
    if is_pie:
        s0 = series[0]
        cd.add_series(str(s0.get("name") or ""), [_num(v) for v in (s0.get("values") or [])])
    else:
        for s in series:
            cd.add_series(str(s.get("name") or ""), [_num(v) for v in (s.get("values") or [])])

    h = float(block.get("h") or (_CHART_H_PIE if is_pie else _CHART_H))
    h = max(3.0, min(h, 8.0))
    # 2단(row) 세로 높이 맞춤: 옆 블록이 더 크면 차트 높이를 키워 키를 맞춘다(최대 8cm).
    if fill_h and fill_h > h:
        h = min(fill_h, 8.0)
    # 원형/도넛은 좌우 여백을 덜 잡아먹도록 폭을 줄이고 좌측 정렬(범례를 오른쪽에 둔다).
    # 단, 이미 2단 컬럼(w_cm 가 본문폭보다 작음) 안이면 그대로 컬럼 폭을 쓴다.
    w = (w_cm * 0.62) if (is_pie and w_cm >= BODY_W_CM - 0.01) else w_cm
    gframe = slide.shapes.add_chart(ctype, bx(x_cm), by(y_cm), L(w), L(h), cd)
    chart = gframe.chart
    chart.has_title = False
    try:
        chart.font.name = FONT
        chart.font.size = Pt(10)
    except Exception:
        pass

    # 범례: 다계열 또는 원형일 때만. 원형은 오른쪽(파이 옆 여백 활용), 막대/선은 아래.
    chart.has_legend = is_pie or len(series) > 1
    if chart.has_legend:
        chart.legend.position = (
            XL_LEGEND_POSITION.RIGHT if is_pie else XL_LEGEND_POSITION.BOTTOM
        )
        chart.legend.include_in_layout = False

    plot = chart.plots[0]
    if is_pie:
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.number_format = "0"
        dl.number_format_is_linked = False
        try:
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
        except Exception:
            pass
        # 조각별 색
        pts = plot.series[0].points
        for i, pt in enumerate(pts):
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = _color(_CHART_PALETTE[i % len(_CHART_PALETTE)])
    else:
        # 계열별 색
        for i, s in enumerate(chart.series):
            s.format.fill.solid()
            s.format.fill.fore_color.rgb = _color(_CHART_PALETTE[i % len(_CHART_PALETTE)])
            s.format.line.fill.background()  # 막대 테두리 제거(깔끔하게)
        # 막대 간격을 좁혀 더 시원하게(기본 150 → 80). line 차트엔 무해.
        try:
            plot.gap_width = 80
        except Exception:
            pass
        # 값 라벨(막대 끝/꺾은선 점 위)로 가독성 보완.
        try:
            plot.has_data_labels = True
            dl = plot.data_labels
            dl.number_format = "0"
            dl.number_format_is_linked = False
            dl.font.size = Pt(9)
            dl.font.color.rgb = RGBColor(0x37, 0x41, 0x51)
            dl.font.name = FONT
            if ctype == XL_CHART_TYPE.LINE_MARKERS:
                dl.position = XL_LABEL_POSITION.ABOVE
            else:
                dl.position = XL_LABEL_POSITION.OUTSIDE_END
        except Exception:
            pass
        _style_chart_axes(chart)

    # 사내 요청: 차트(원형+범례 등)를 1행1열 표처럼 테두리 박스로 감싼다(표와 동일한 회색 0.75pt).
    _add_shape(
        slide, MSO_SHAPE.RECTANGLE, bx(x_cm), by(y_cm), L(w), L(h),
        fill=None, line_color="808080", line_pt=0.75,
    )

    return y_cm + h


# ============================================================
# §4.7 마일스톤 화살표 (하단 진행 현황)
# ============================================================
_TIMELINE_H = 2.8  # 타임라인 블록 고정 높이(라벨 위 + 가는 화살표 선 + 날짜 아래)


def _add_arrow_line(slide, x1_cm: float, y_cm: float, x2_cm: float, *, color="dwNavy", pt=1.5) -> None:
    """가는 가로 직선 + 우측 끝 화살촉(연결선). 마일스톤 타임라인의 축선."""
    cxn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, bx(x1_cm), by(y_cm), bx(x2_cm), by(y_cm))
    cxn.line.color.rgb = _color(color)
    cxn.line.width = Pt(pt)
    ln = cxn.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))


def _timeline(slide, y_cm: float, block: dict, body_h_cm: float, x_cm: float = 0.0, w_cm: float = BODY_W_CM, fill_h: float | None = None) -> float:
    nodes = list(block.get("nodes") or [])
    if not nodes:
        return y_cm

    # 노드 개수·라벨 길이에 맞춰 박스 폭을 줄인다(적으면 좁게, 왼쪽 정렬). 전폭을 다 먹어 노드가
    # 멀찍이 퍼져 휑해 보이는 걸 막는다. **단독 배치(fill_h is None)일 때만** 줄이고, row·compare
    # 셀처럼 폭이 배정된 경우(fill_h 숫자)는 그 칸을 가득 채운다.
    if fill_h is None:
        nn = len(nodes)
        if nn > 1:
            needs = [
                max(
                    _text_width_cm(str(nd.get("label") or ""), 10),
                    _text_width_cm(f"({nd.get('date') or ''})", 9.5),
                    1.4,
                )
                for nd in nodes
            ]
            step_want = max(2.6, min(max(needs) + 0.9, 5.5))  # 인접 라벨 안 겹치게 여백
            natural_w = step_want * (nn - 1) + 2.2  # span(=w-2.2) 역산 + 좌우 패딩
            w_cm = min(w_cm, max(natural_w, 6.0))
        else:
            w_cm = min(w_cm, 8.0)

    # 고정 높이 블록(라벨 위 + 가는 화살표 선 + 날짜 아래). 2단 키 맞춤(fill_h)이면 박스를 키운다.
    area_h = max(_TIMELINE_H, fill_h) if fill_h else _TIMELINE_H
    # 사내 요청: 타임라인도 차트처럼 1행1열 표같은 테두리 박스로 감싼다.
    _add_shape(
        slide, MSO_SHAPE.RECTANGLE, bx(x_cm), by(y_cm), L(w_cm), L(area_h),
        fill=None, line_color="808080", line_pt=0.75,
    )
    line_y = y_cm + area_h * 0.5  # 축선(가로) 세로 중앙

    # 가는 네이비 가로 직선 + 우측 끝 화살촉(굵은 블록 화살표 대신).
    _add_arrow_line(slide, x_cm + 0.6, line_y, x_cm + w_cm - 0.5, color="dwNavy", pt=1.5)

    n = len(nodes)
    span = w_cm - 2.2  # 우측 화살촉 자리 남김
    step = span / max(1, n - 1) if n > 1 else 0.0
    node_d = 0.34  # 작은 점 지름 cm
    cx0 = x_cm + 1.0
    # 노드가 많으면 라벨 폭·글자를 간격에 맞춰 줄여 겹침 방지.
    lbl_w = min(4.0, step * 0.96) if n > 1 else 4.0
    label_fs = 10 if n <= 6 else (9 if n <= 8 else 8)
    date_fs = 9.5 if n <= 6 else (8.5 if n <= 8 else 7.5)

    for i, node in enumerate(nodes):
        cx = cx0 + step * i
        state = str(node.get("state") or "todo")

        # 작은 점: 예정(todo)=흰 원+네이비 테두리, 그 외=네이비 채움.
        if state == "todo":
            _add_shape(
                slide, MSO_SHAPE.OVAL,
                bx(cx - node_d / 2), by(line_y - node_d / 2), L(node_d), L(node_d),
                fill="white", line_color="dwNavy", line_pt=1.25,
            )
        else:
            _add_shape(
                slide, MSO_SHAPE.OVAL,
                bx(cx - node_d / 2), by(line_y - node_d / 2), L(node_d), L(node_d),
                fill="dwNavy", line_color="dwNavy", line_pt=1.0,
            )

        # 라벨 (점 위)
        ltb, ltf = _add_textbox(
            slide, bx(cx - lbl_w / 2), by(line_y - 1.25), L(lbl_w), L(1.05), anchor=MSO_ANCHOR.BOTTOM,
        )
        ltf.word_wrap = True
        lp = ltf.paragraphs[0]
        lp.alignment = PP_ALIGN.CENTER
        set_run(lp.add_run(), str(node.get("label") or ""), label_fs, bold=True, color="ink")

        # 날짜 (점 아래)
        dtb, dtf = _add_textbox(
            slide, bx(cx - lbl_w / 2), by(line_y + 0.18), L(lbl_w), L(0.5),
        )
        dp = dtf.paragraphs[0]
        dp.alignment = PP_ALIGN.CENTER
        set_run(dp.add_run(), f"({node.get('date') or ''})", date_fs, color="g400")

    return y_cm + area_h


# ============================================================
# compare 블록 — 큰 열 비교 그리드. 셀에 텍스트 또는 타임라인을 담을 수 있다(일정 행).
# (일반 표 셀에는 도형을 못 넣으므로 표가 아니라 직접 그린 격자.)
# ============================================================
_COMPARE_LABEL_W = 1.9  # 좌측 라벨(구분) 열 폭 cm
_COMPARE_HDR_H = 0.65
_COMPARE_TL_H = _TIMELINE_H  # 타임라인이 든 행 높이
_COMPARE_MIN_ROW = 1.0
_COMPARE_PAD = 0.18


def _compare_cell_is_timeline(cell) -> bool:
    return isinstance(cell, dict) and str(cell.get("type")) == "timeline"


def _compare_cell_lines(cell) -> list[str]:
    """비교 셀(문자열/{lines}/{bullets}/{text}) → 표시 줄 리스트."""
    if isinstance(cell, str):
        return _BR_RE.split(cell) or [""]
    if isinstance(cell, dict):
        if isinstance(cell.get("lines"), list):
            out: list[str] = []
            for ln in cell["lines"]:
                out.extend(_BR_RE.split(str(ln)))
            return out
        if isinstance(cell.get("bullets"), list):
            return [f"• {b}" for b in cell["bullets"]]
        if cell.get("text") is not None:
            return _BR_RE.split(str(cell["text"]))
        if cell.get("t") is not None:
            return _BR_RE.split(str(cell["t"]))
    return [str(cell)]


def _compare_text_height(cell, col_w: float) -> float:
    lines = [s for s in _compare_cell_lines(cell) if s.strip()] or [""]
    total = sum(_wrap_lines(s, col_w - 2 * _COMPARE_PAD, BODY_FS) for s in lines)
    return max(_COMPARE_MIN_ROW, total * _TEXT_LINE_CM + 2 * _COMPARE_PAD)


def _compare_cells(r) -> list:
    """비교표 한 행의 cells 를 리스트로 정규화.

    정상은 ["셀", …] 이지만 LLM 이 cells 를 문자열로 보내면 len/인덱싱이 **문자 단위**로 쪼개져
    한 셀이 여러 컬럼으로 흩어진다 → 단일 셀 리스트로 감싼다(_as_cells 와 동일 취지, 크래시·왜곡 방지)."""
    if not isinstance(r, dict):
        return []
    cells = r.get("cells")
    if isinstance(cells, list):
        return cells
    if isinstance(cells, tuple):
        return list(cells)
    if cells is None or cells == "":
        return []
    return [cells]


def _compare_ncol(rows: list, headers: list) -> int:
    ncol = max((len(_compare_cells(r)) for r in rows), default=1)
    if headers:
        ncol = max(ncol, len(headers) - 1)
    return max(1, ncol)


def _estimate_compare_height(block: dict, w_cm: float = BODY_W_CM) -> float:
    rows = list(block.get("rows") or [])
    headers = list(block.get("headers") or [])
    if not rows:
        return 0.0
    ncol = _compare_ncol(rows, headers)
    col_w = (w_cm - _COMPARE_LABEL_W) / ncol
    tot = _COMPARE_HDR_H if headers else 0.0
    for r in rows:
        cells = _compare_cells(r)
        if any(_compare_cell_is_timeline(c) for c in cells):
            tot += _COMPARE_TL_H
        else:
            tot += max([_COMPARE_MIN_ROW, *(_compare_text_height(c, col_w) for c in cells)])
    return tot


def _compare_box(slide, x: float, y: float, w: float, h: float, *, fill=None) -> None:
    _add_rect(slide, bx(x), by(y), L(w), L(h), fill=fill, line_color="808080", line_pt=0.75)


def _compare_cell_text(slide, x: float, y: float, w: float, h: float, cell, *, label: bool = False, header: bool = False) -> None:
    _compare_box(slide, x, y, w, h, fill="hdr" if header else None)
    anchor = MSO_ANCHOR.MIDDLE if (label or header) else MSO_ANCHOR.TOP
    pad = 0.0 if (label or header) else _COMPARE_PAD
    tb, tf = _add_textbox(slide, bx(x + pad), by(y + pad), L(w - 2 * pad), L(h - 2 * pad), anchor=anchor)
    tf.word_wrap = True
    lines = [s for s in _compare_cell_lines(cell) if s.strip()] or [""]
    for i, s in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.CENTER if (label or header) else PP_ALIGN.LEFT
        set_run(p.add_run(), s, BODY_FS, bold=(label or header), color="ink")


def _compare(slide, y_cm: float, block: dict, x_cm: float = 0.0, w_cm: float = BODY_W_CM, fill_h: float | None = None) -> float:
    rows = list(block.get("rows") or [])
    if not rows:
        return y_cm
    headers = list(block.get("headers") or [])
    ncol = _compare_ncol(rows, headers)
    label_w = _COMPARE_LABEL_W
    col_w = (w_cm - label_w) / ncol
    has_header = bool(headers)

    cy = y_cm
    if has_header:
        _compare_cell_text(slide, x_cm, cy, label_w, _COMPARE_HDR_H, headers[0] if headers else "구분", header=True)
        for j in range(ncol):
            lab = headers[j + 1] if j + 1 < len(headers) else ""
            _compare_cell_text(slide, x_cm + label_w + j * col_w, cy, col_w, _COMPARE_HDR_H, lab, header=True)
        cy += _COMPARE_HDR_H

    for r in rows:
        cells = _compare_cells(r)
        is_tl = any(_compare_cell_is_timeline(c) for c in cells)
        rh = _COMPARE_TL_H if is_tl else max([_COMPARE_MIN_ROW, *(_compare_text_height(c, col_w) for c in cells)])
        label = str((r.get("label") if isinstance(r, dict) else "") or "")
        _compare_cell_text(slide, x_cm, cy, label_w, rh, label, label=True)
        for j in range(ncol):
            cx = x_cm + label_w + j * col_w
            cell = cells[j] if j < len(cells) else ""
            if _compare_cell_is_timeline(cell):
                # 타임라인이 자기 테두리 박스를 그려 셀 경계가 된다(별도 셀 박스 생략).
                _timeline(slide, cy, cell, BODY_H_CM, cx, col_w, fill_h=rh)
            else:
                _compare_cell_text(slide, cx, cy, col_w, rh, cell)
        cy += rh

    return cy


# ============================================================
# outline 블록 — 번호가 붙는 계층 목록 (1) 대항목 + ①②③ 하위항목 + 들여쓰기
# ============================================================
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_OUTLINE_FS = 12.5
_OUTLINE_LINE = _OUTLINE_FS * 0.03528 * 1.45
_OUTLINE_INDENT = {1: 0.6, 2: 1.5, 3: 2.4}  # 레벨별 좌측 들여쓰기 cm(■ → 1) → ① 계층 또렷이)
_OUTLINE_GAP = 0.12


def _outline_lines(block: dict) -> list[tuple[int, str, str, bool]]:
    """items → (level, marker, text, bold) 리스트. 레벨1=1)2), 레벨2=①②③(상위마다 리셋), 레벨3=-."""
    out: list[tuple[int, str, str, bool]] = []
    c1 = c2 = 0
    for it in block.get("items") or []:
        if isinstance(it, str):
            text, level, bold = it.strip(), 1, None
        elif isinstance(it, dict):
            text = str(it.get("text") or "").strip()
            level = int(it.get("level") or 1)
            bold = it.get("bold")
        else:
            continue
        if not text:
            continue
        level = 1 if level < 1 else (3 if level > 3 else level)
        if level == 1:
            c1 += 1
            c2 = 0
            marker = f"{c1})"
        elif level == 2:
            c2 += 1
            marker = _CIRCLED[c2 - 1] if c2 <= len(_CIRCLED) else f"({c2})"
        else:
            marker = "-"
        out.append((level, marker, text, (level == 1) if bold is None else bool(bold)))
    return out


def _estimate_outline_height(block: dict, w_cm: float = BODY_W_CM) -> float:
    lines = _outline_lines(block)
    if not lines:
        return 0.0
    total = 0.0
    for level, marker, text, _bold in lines:
        indent = _OUTLINE_INDENT.get(level, 0.3)
        n = _wrap_lines(f"{marker} {text}", w_cm - indent, _OUTLINE_FS)
        total += n * _OUTLINE_LINE
    return total + _OUTLINE_GAP * (len(lines) - 1)


def _outline(slide, y_cm: float, block: dict, x_cm: float = 0.0, w_cm: float = BODY_W_CM, fill_h: float | None = None) -> float:
    """번호 계층 목록을 **하나의 텍스트 상자**에 여러 문단으로 그린다(사내 요청: 줄마다 상자 만들지

    말 것 — 박스 사이 군더더기 여백 제거). 레벨 들여쓰기는 문단 marL 로 준다(a:pPr).
    """
    lines = _outline_lines(block)
    if not lines:
        return y_cm
    metas = []
    total = 0.0
    for level, marker, text, bold in lines:
        indent = _OUTLINE_INDENT.get(level, 0.3)
        n = _wrap_lines(f"{marker} {text}", w_cm - indent, _OUTLINE_FS)
        metas.append((marker, text, bold, indent, n * _OUTLINE_LINE))
        total += n * _OUTLINE_LINE
    total += _OUTLINE_GAP * (len(metas) - 1)
    total = max(_OUTLINE_LINE, total)
    tb, tf = _add_textbox(slide, bx(x_cm), by(y_cm), L(w_cm), L(total), anchor=MSO_ANCHOR.TOP)
    tf.word_wrap = True
    gap_pt = _OUTLINE_GAP / 2.54 * 72
    for i, (marker, text, bold, indent, _h) in enumerate(metas):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.line_spacing = 1.0  # 줄 간격 단일 — 항목 세로 여백 최소화
        p.space_before = Pt(0)
        if i < len(metas) - 1:
            p.space_after = Pt(gap_pt)
        pPr = p._p.get_or_add_pPr()  # 문단 좌측 들여쓰기(레벨별) — marL EMU(1cm=360000)
        pPr.set("marL", str(int(indent * 360000)))
        pPr.set("indent", "0")
        _emit_emph_runs(p, f"{marker} {text}", _OUTLINE_FS, bold=bold, color="ink")
    return y_cm + total


# ============================================================
# 레이아웃 엔진 — 블록 세로 누적
# ============================================================
_BLOCK_GAP = 0.25


_COL_GAP = 0.5  # 2단 컬럼 사이 간격(cm)


def _row_children(block: dict) -> list[dict]:
    """row 블록의 좌우 자식 블록(최대 3개). 'blocks' 또는 'cols' 키 허용.

    중첩 row 도 **그대로 둔다**(평탄화하지 않음). 평탄화하면 LLM 이 묶은 그룹(예: row[row[A,B], C]
    의 [A,B])이 풀려 잘못 배치되므로, 렌더(_render_row)·추정에서 중첩을 직접 처리한다.
    """
    kids = block.get("blocks") or block.get("cols") or []
    return [b for b in kids if isinstance(b, dict)][:3]


def _text_width_cm(s: str, fs: float = BODY_FS) -> float:
    """문자열을 한 줄로 그릴 때 폭(cm) 추정 — 줄바꿈 추정과 같은 글자 폭 계수(한글 1.25/ascii 0.6em)."""
    em = fs * 0.03528
    w = 0.0
    for ch in _strip_emph(s):
        w += _ASCII_EM if (ord(ch) < 0x2500 and ch.isascii()) else _KO_EM
    return w * em


def _text_width_wrap_cm(s: str, fs: float = BODY_FS) -> float:
    """'한 줄' 필요 폭(cm) — **줄바꿈 추정(_wrap_lines)과 같은 글자폭 계수(한글 1.3em)**로 계산.

    전역 _text_width_cm 은 컬럼 폭 산정용으로 좁은 계수(1.1em)를 써, 이 폭을 '1줄 필요폭'으로 쓰면
    실제로는 그 폭에서 줄바꿈이 일어난다(표를 옆에 붙였다가 행이 커지는 원인). side-by-side 판정·
    2단 폭 배분엔 렌더와 동일한 계수로 잡아야 정확하다.
    """
    em = fs * 0.03528
    return sum(_char_wrap_w(ch) for ch in _strip_emph(s)) * em


# 섹션 제목(15.5pt bold)의 실제 렌더 한글 폭 — COM(BoundWidth) 실측 보정. 본문 12pt 기준 1.03em 보다
# 좁다(제목 크기/자간). 똑딱이 아이콘을 제목 글자 바로 옆(0.5cm)에 붙이는 위치 계산에만 쓴다.
_HEAD_KO_EM = 0.90


def _heading_width_cm(s: str, fs: float = 15.5) -> float:
    """섹션 제목을 한 줄로 그릴 때 실제 렌더 폭(cm) — 아이콘 위치용(한글 0.90em, 나머지는 _char_wrap_w)."""
    em = fs * 0.03528
    w = 0.0
    for ch in _strip_emph(s):
        if ch == " " or ch in _WRAP_NARROW:
            w += _WRAP_NARROW_EM
        elif ord(ch) < 0x2500 and ch.isascii():
            w += _WRAP_ASCII_EM
        else:
            w += _HEAD_KO_EM
    return w * em


def _block_natural_width(block: dict, fs: float = BODY_FS) -> float:
    """블록 내용이 '한 줄'로 들어가려면 필요한 폭(cm) 추정 — 2단 폭 자동 배분·side-by-side 판정용.

    렌더 줄바꿈과 동일한 글자폭(_text_width_wrap_cm, 한글 1.3em)으로 잡아, 이 폭을 줬을 때 실제로
    1줄로 렌더되도록 한다(좁게 잡아 옆에 붙였다가 줄바꿈으로 행이 커지는 것 방지).
    """
    if not isinstance(block, dict):
        return 2.0
    btype = block.get("type")
    if btype == "row":
        # 중첩 row 는 자식을 가로로 나란히 둔다고 보고 자연 폭 합(+ 컬럼 간격).
        kids = _row_children(block)
        if not kids:
            return 2.0
        return sum(_block_natural_width(k, fs) for k in kids) + _COL_GAP * (len(kids) - 1)
    if btype == "compare":
        return BODY_W_CM  # 비교 그리드는 항상 풀폭(2단 row 로 옆에 두지 않음)
    if btype == "outline":
        segs = [t for _l, _m, t, _b in _outline_lines(block)]
        return max(2.0, max((_text_width_wrap_cm(s, _OUTLINE_FS) for s in segs), default=2.0) + 1.0)
    if btype == "table":
        rows = list(block.get("rows") or [])
        header = list(block.get("header") or [])
        cols = len(header) if header else (len(_as_cells(rows[0])) if rows else 1)
        colw = [0.0] * cols
        for c in range(cols):
            if c < len(header):
                colw[c] = max(colw[c], _text_width_wrap_cm(str(header[c]), fs))
        for r in rows:
            rr = _as_cells(r)
            for c in range(min(cols, len(rr))):
                segs = _cell_segments(rr[c])  # {lines:[...]} 등은 줄별 → 최대 줄 폭
                mw = max((_text_width_wrap_cm(s, fs) for s in segs), default=0.0)
                colw[c] = max(colw[c], mw)
        return max(2.0, sum(w + 0.35 for w in colw))  # 열마다 셀 여백 가산(margin 0.28+여유)
    if btype == "chart":
        is_pie = str(block.get("chart", "column")).lower() in ("pie", "doughnut")
        return 10.0 if is_pie else 14.0
    if btype in ("text", "lead", "conclusion"):
        if isinstance(block.get("bullets"), list):
            segs = [str(b) for b in block["bullets"]]
        else:
            segs = [str(block.get("text", ""))]
        return max(2.0, max((_text_width_wrap_cm(s, fs) for s in segs), default=2.0) + 0.5)
    return 5.0


def _row_widths(block: dict, n: int, w_cm: float) -> list[float]:
    """컬럼 폭 분배(사이 간격 _COL_GAP 제외).

    명시적 ratio 가 있으면 그대로 따르고, 없으면 **내용 기반 자동 배분**한다: 각 컬럼이 한 줄로
    들어갈 자연 폭을 추정해 비례 배분한다. 내용이 많은 표(긴 셀)는 넓게, 짧은 표는 좁게 →
    한쪽이 2줄로 넘치지 않는 선에서 옆을 늘려 한 줄로 깔끔하게 맞춘다.
    """
    avail = w_cm - _COL_GAP * (n - 1)
    ratio = block.get("ratio")
    if isinstance(ratio, list) and len(ratio) >= n and any(
        isinstance(r, (int, float)) and r > 0 for r in ratio[:n]
    ):
        ratio = [float(r) if isinstance(r, (int, float)) and r > 0 else 1.0 for r in ratio[:n]]
        tot = sum(ratio) or n
        return [avail * (ratio[i] / tot) for i in range(n)]
    # 내용 기반 자동 배분.
    kids = _row_children(block)
    nats = [_block_natural_width(kids[i]) if i < len(kids) else avail / n for i in range(n)]
    tot = sum(nats) or n
    if tot <= avail:
        # 남는 폭 분배: 차트/타임라인 같은 **표가 아닌 블록이 있으면 그쪽이 흡수**하고 표는 자연 폭을
        # 유지한다(내용 적은 표가 옆 블록 자리까지 과하게 넓어지는 것 방지). **표(박스 포함)만 있는
        # 줄이면 표들이 남는 폭을 비례로 나눠 가져 가로를 가득 채운다**(우측 여백 제거).
        extra = avail - tot
        grow = [i for i in range(n) if i < len(kids) and kids[i].get("type") != "table"]
        if not grow:
            grow = list(range(n))
        gtot = sum(nats[i] for i in grow) or len(grow)
        return [nats[i] + (extra * nats[i] / gtot if i in grow else 0.0) for i in range(n)]
    return [avail * (nats[i] / tot) for i in range(n)]


def _render_block(slide, y_cm: float, block: dict, x_cm: float, w_cm: float, fill_h: float | None = None) -> float:
    """블록 1개(섹션 헤딩 포함)를 (x_cm, w_cm) 영역에 그리고 새 y 를 반환.

    fill_h 가 주어지면 이 블록의 **총 높이(섹션 포함)**를 그 값까지 채운다(2단 row 세로 맞춤).
    """
    btype = block.get("type")
    section = block.get("section")
    y = y_cm
    if section and btype != "lead":
        # 이 블록이 섹션 제목을 그리면, 'ole' 마커가 있을 때 제목 옆에 똑딱이 아이콘을 함께 그린다.
        ole = block.get("ole") if isinstance(block.get("ole"), dict) else None
        y = _section(slide, y, str(section), x_cm, w_cm, ole=ole) + _SECTION_GAP  # 제목-내용 사이 간격
    # 섹션 헤딩이 쓴 높이를 빼고 본문이 채워야 할 목표 높이를 구한다.
    body_fill = (fill_h - (y - y_cm)) if fill_h is not None else None
    if btype == "heading":
        pass  # 섹션 헤딩 전용(리패킹이 강등한 제목) — 위 _section 만
    elif btype == "lead":
        y = _lead(slide, y, block, x_cm, w_cm)
    elif btype == "table":
        y = _table(slide, y, block, BODY_H_CM, x_cm, w_cm, fill_h=body_fill)
    elif btype == "chart":
        y = _chart(slide, y, block, BODY_H_CM, x_cm, w_cm, fill_h=body_fill)
    elif btype == "text":
        y = _text(slide, y, block, BODY_H_CM, x_cm, w_cm)
    elif btype == "timeline":
        y = _timeline(slide, y, block, BODY_H_CM, x_cm, w_cm, fill_h=body_fill)
    elif btype == "conclusion":
        y = _conclusion(slide, y, block, x_cm, w_cm)
    elif btype == "compare":
        y = _compare(slide, y, block, x_cm, w_cm, fill_h=body_fill)
    elif btype == "outline":
        y = _outline(slide, y, block, x_cm, w_cm, fill_h=body_fill)
    elif btype == "row":
        # 중첩 row(LLM 이 row 안에 row 를 넣은 경우) — 주어진 (x,w) 영역 안에서 다시 배치한다.
        y = _render_row(slide, y, block, x_cm, w_cm)
    return y


# 표가 아닌 블록의 최소 폭(cm) — 차트·타임라인은 좁아져도 깨지지 않으므로 최소만 차지한다고 본다.
_NONTABLE_MIN_W = {"chart": 7.0, "timeline": 5.0, "text": 4.0, "lead": 4.0, "conclusion": 4.0, "outline": 5.0}
# 가로 배치 허용 여유 — 자연폭 합이 (가용폭 × 이 값) 이내면 옆으로 붙인다. 사내 요청(2026-07):
# 텍스트 많은 표를 좌우로 붙이면 컬럼이 반토막나 셀이 2~3줄로 줄바꿈되고, 행 높이가 max줄수로 커져
# ('행 풍선') 짧은 셀에 세로 공백이 크게 남아 보기 싫다(실측: side-by-side 2.04cm vs full-width 0.84cm).
# → 자연폭 합이 가용폭에 **실제로 들어가는 쌍(≤1.0배)만** 옆으로 붙인다(그래야 옆에 놔도 줄바꿈 없이
# 1줄=컴팩트). 조금이라도 넘으면(>1.0) 붙였을 때 줄바꿈→행 팽창이므로 full-width 로 쌓는다. full-width
# 표는 _norm_colw 가 가로를 꽉 채워 좌우 여백도 안 남는다. (자연폭은 실측 1.08em 기준이라 정확.)
_ROW_FIT_FACTOR = 1.0
# 표가 없는 row(outline/text 만)는 완화한다. 사내 요청(2026-07-01): 짧은 outline 두 개를 세로로
# 쌓으면 각 박스가 full-width 라 우측 여백이 크게 남아('상자가 좌우로 너무 넓다') 보기 싫다. 표와 달리
# outline/text 는 폭이 조금 줄어도 줄 하나 늘 뿐(행 풍선 아님)이라, 자연폭이 가용폭을 다소 넘어도
# 좌우로 붙여 가로 공간을 쓴다. 표가 하나라도 섞이면 엄격(1.0)으로 되돌린다(표 행 팽창 방지).
_ROW_FIT_FACTOR_SOFT = 1.4


# 좁아져도 안 깨지는(줄바꿈 없이 축소되는) 블록 — 이들만 최소폭으로 잡는다. 표·목록·텍스트는
# 폭이 줄면 줄바꿈돼 행/줄이 늘어나므로 '1줄 자연폭'으로 잡아야 옆에 붙일지 정확히 판정된다.
_ROW_COMPRESSIBLE = {"chart", "timeline"}


def _row_side_by_side(kids: list[dict], avail: float) -> bool:
    """row 자식들을 가로로 나란히 둘지 — 자연폭 합이 가용폭의 _ROW_FIT_FACTOR 배 이내면 가로.

    표·목록·텍스트는 폭이 줄면 **줄바꿈돼 세로로 커지므로** 1줄 자연 폭을 요구한다(옆에 붙였을 때
    줄바꿈으로 행이 풍선처럼 커지는 것 방지). 차트·타임라인만 좁아져도 안 깨지므로 최소 폭으로 본다.
    """
    if len(kids) <= 1:
        return True
    need = 0.0
    for k in kids:
        t = k.get("type")
        if t in _ROW_COMPRESSIBLE:
            need += _NONTABLE_MIN_W.get(t, 4.0)
        else:
            need += _block_natural_width(k)  # 표·목록·텍스트·중첩 row — 1줄 자연 폭 필요
    # 표가 섞이면 엄격(1.0, 행 풍선 방지), 표 없이 outline/text 만이면 완화(가로 공간 활용).
    has_table = any(isinstance(k, dict) and k.get("type") == "table" for k in kids)
    factor = _ROW_FIT_FACTOR if has_table else _ROW_FIT_FACTOR_SOFT
    return need <= avail * factor


def _render_row(slide, y_cm: float, block: dict, x_cm: float = 0.0, w_cm: float = BODY_W_CM) -> float:
    """row 블록 — 자식들을 (x_cm, w_cm) 영역 안에서 좌우로 나란히 그리고, 가장 키 큰 컬럼 기준 y 전진.

    자식 자연 폭 합이 가용폭을 크게 넘으면(넓은 표 여러 개 등) 가로로 욱여넣지 않고 **세로로 쌓는다**.
    중첩 row 도 그대로 처리한다(평탄화하지 않음 → LLM 이 묶은 그룹 유지). 예: row[row[A,B], C] 는
    바깥이 안 맞으면 세로로 쌓되, 안쪽 [A,B] 는 옆으로 유지된다.
    """
    kids = _row_children(block)
    if not kids:
        return y_cm
    if len(kids) == 1:
        return _render_block(slide, y_cm, kids[0], x_cm, w_cm)
    avail = w_cm - _COL_GAP * (len(kids) - 1)
    if not _row_side_by_side(kids, avail):
        y = y_cm
        for k in kids:
            y = _render_block(slide, y, k, x_cm, w_cm)
            y += _BLOCK_GAP
        return y - _BLOCK_GAP
    widths = _row_widths(block, len(kids), w_cm)
    # 컬럼별 자연 높이를 추정해 가장 큰 값으로 맞춘다(표2개·차트+표의 세로 높이 정렬).
    target = max(_estimate_block_height(k, widths[i]) for i, k in enumerate(kids))
    x = x_cm
    y_max = y_cm
    for i, child in enumerate(kids):
        yc = _render_block(slide, y_cm, child, x, widths[i], fill_h=target)
        y_max = max(y_max, yc)
        x += widths[i] + _COL_GAP
    return y_max


def _layout_blocks(slide, blocks: list[dict]) -> None:
    # 블록을 위에서부터 자연 높이로 **빽빽이** 쌓는다(컴팩트). row 블록은 좌우 2단.
    # 하단 공백은 간격을 벌려(늘려) 메우지 않는다 — 리패킹이 더 많은 블록을 끌어올려 채운다.
    items = [b for b in blocks if isinstance(b, dict)]
    y = 0.0
    for idx, block in enumerate(items):
        if block.get("type") == "row":
            y = _render_row(slide, y, block)
        else:
            y = _render_block(slide, y, block, 0.0, BODY_W_CM)
        y += _BLOCK_GAP  # 블록 간 고정 간격
        if y > BODY_H_CM + 0.5:  # 넘침 경고(비치명적) — 캔버스 초과
            break


# ============================================================
# 컴팩트 리패킹 — 언더필 슬라이드 병합으로 페이지 수 최소화
# ============================================================
# 사내 정책: PPT 는 최대한 컴팩트하게(여백·페이지 수 최소화). LLM 이 한 페이지를 다 채우지
# 못하고 내용을 여러 슬라이드로 흩뜨리는 경향이 있어, 렌더 전에 슬라이드 단위로 다시 묶는다.
# 한 슬라이드는 절대 분할하지 않고(섹션-표 분리 방지), 추정 높이가 본문 영역에 들어맞을 때만
# 다음 슬라이드를 끌어올려 합친다. 합쳐지는 슬라이드의 ▣ 제목은 ■ 섹션 헤딩으로 강등한다.
def _estimate_table_height(block: dict, w_cm: float = BODY_W_CM) -> float:
    _regroup_flat_table_rows(block)  # 추정도 재그룹 후 계산해야 렌더 높이와 일치(겹침 방지)
    header = list(block.get("header") or [])
    rows = list(block.get("rows") or [])
    cols = len(header) if header else (len(_as_cells(rows[0])) if rows else 1)
    col_w = _norm_colw(block, cols, w_cm)
    fs = BODY_FS  # _table 와 동일하게 본문 12pt 고정
    header_h = float(block.get("headerH", 0.6)) if header else 0.0  # 헤더 없으면 0
    row_h = block.get("rowH")
    if row_h is None:
        # _table 의 배치용 추정과 동일(넉넉히). 리패킹이 페이지에 들어갈지 일관되게 판단.
        return header_h + _estimate_body_rows(rows, cols, col_w, fs, w_cm) + _TABLE_SAFETY_CM
    rh = [float(h) for h in row_h]
    if len(rh) < len(rows):
        rh += [rh[-1] if rh else 0.9] * (len(rows) - len(rh))
    return header_h + sum(rh) + _TABLE_SAFETY_CM


def _estimate_block_height(block: dict, w_cm: float = BODY_W_CM) -> float:
    """블록 1개의 렌더 높이(cm) 추정 — _layout_blocks 의 각 블록 함수와 동일 공식.

    w_cm 는 블록이 놓일 영역 폭(2단 컬럼이면 컬럼 폭) — 표/text 줄바꿈 추정에 쓴다.
    """
    if not isinstance(block, dict):
        return 0.0
    btype = block.get("type")
    if btype == "row":
        kids = _row_children(block)
        if not kids:
            return 0.0
        avail = w_cm - _COL_GAP * (len(kids) - 1) if len(kids) > 1 else w_cm
        if not _row_side_by_side(kids, avail):
            # 세로 스택: 각 블록 풀폭 높이 합(+ 블록 간격). _render_row 의 스택 분기와 일치.
            return sum(_estimate_block_height(k, w_cm) for k in kids) + _BLOCK_GAP * (len(kids) - 1)
        # 좌우 컬럼 중 가장 높은 컬럼 기준.
        widths = _row_widths(block, len(kids), w_cm) if len(kids) > 1 else [w_cm]
        return max(_estimate_block_height(k, widths[i]) for i, k in enumerate(kids))
    h = 0.0
    if block.get("section") and btype != "lead":
        h += _SECTION_H + _SECTION_GAP
    if btype == "lead":
        h += _LEAD_H
    elif btype == "table":
        h += _estimate_table_height(block, w_cm)
    elif btype == "chart":
        if block.get("series"):
            is_pie = str(block.get("chart", "column")).lower() in ("pie", "doughnut")
            ch = float(block.get("h") or (_CHART_H_PIE if is_pie else _CHART_H))
            h += max(3.0, min(ch, 8.0))
    elif btype == "text":
        total_lines = sum(
            _wrap_lines(s, w_cm, _TEXT_FS) for s, _ in _text_lines(block)
        )
        h += max(_TEXT_LINE_CM, total_lines * _TEXT_LINE_CM + 0.10)
    elif btype == "timeline":
        h += _TIMELINE_H
    elif btype == "conclusion":
        h += _CONCLUSION_H
    elif btype == "compare":
        h += _estimate_compare_height(block, w_cm)
    elif btype == "outline":
        h += _estimate_outline_height(block, w_cm)
    return h


def _estimate_blocks_height(blocks: list[dict]) -> float:
    """블록 묶음 총 높이(cm) — _layout_blocks 와 동일하게 블록마다 _BLOCK_GAP 가산."""
    return sum(
        _estimate_block_height(b) + _BLOCK_GAP for b in blocks if isinstance(b, dict)
    )


# 하단 공백 backfill 시 앞쪽으로 살펴볼 블록 수(클수록 더 빽빽하게 끌어올림).
_PACK_LOOKAHEAD = 8


def _provides_section(b: dict) -> bool:
    """블록이 이미 자기 ■ 섹션 제목을 갖는가(2단 row 는 자식 중 하나라도 섹션이 있으면 True)."""
    if not isinstance(b, dict):
        return False
    if b.get("section"):
        return True
    if b.get("type") == "row":
        return any(isinstance(k, dict) and k.get("section") for k in _row_children(b))
    return False


def _pack_house_run(items: list[tuple[str, dict]], body_h_cm: float) -> list[dict]:
    """house 블록 스트림 [(원본제목, 블록)] 을 페이지로 채운다.

    다음 블록이 잔여 공간에 안 들어가면 바로 페이지를 넘기지 않고, 가까운 뒤쪽(window)에서
    그 공간에 들어가는 작은 블록을 끌어올려 하단 공백을 메운다. 블록은 쪼개지 않으며(원자),
    잔여 공간이 작으니 자연히 작은 블록(lead/짧은 text·표·차트)만 올라온다. 끌어올린 블록도
    원본 제목이 바뀌면 ■ 헤딩을 달아 어느 절 내용인지 유지한다.
    """
    n = len(items)
    used = [False] * n
    pages: list[dict] = []
    cur: list[dict] = []
    cur_title = ""
    cur_h = 0.0
    last_src = ""

    def _flush() -> None:
        nonlocal cur, cur_title, cur_h, last_src
        if cur:
            pages.append({"layout": "house-report", "data": {"title": cur_title, "blocks": cur}})
        cur = []
        cur_title = ""
        cur_h = 0.0
        last_src = ""

    def _need_heading(b: dict, src: str) -> bool:
        # 원본 슬라이드가 바뀌는 경계에 제목 헤딩을 끼울지. 단, 합쳐지는 블록이 이미 자기 ■ 섹션을
        # 가지면(표/차트/2단 row 등) 제목 헤딩은 중복이라 넣지 않는다(덩그러니 빈 제목 방지).
        return bool(cur) and bool(src) and src != last_src and not _provides_section(b)

    def _fits(idx: int) -> bool:
        src, b = items[idx]
        head = (_SECTION_H + _SECTION_GAP + _BLOCK_GAP) if _need_heading(b, src) else 0.0
        return cur_h + head + _estimate_block_height(b) + _BLOCK_GAP <= body_h_cm

    def _place(idx: int) -> None:
        nonlocal cur_title, cur_h, last_src
        src, b = items[idx]
        if not cur:
            cur_title = src
        elif _need_heading(b, src):
            cur.append({"type": "heading", "section": src})
            cur_h += _SECTION_H + _SECTION_GAP + _BLOCK_GAP
        cur.append(b)
        cur_h += _estimate_block_height(b) + _BLOCK_GAP
        last_src = src
        used[idx] = True

    i = 0
    while i < n:
        if used[i]:
            i += 1
            continue
        if not cur or _fits(i):
            _place(i)
            i += 1
            continue
        # i 가 현재 페이지에 안 들어감 → 뒤쪽 window 에서 빈 공간에 맞는 블록을 끌어올린다.
        filled = False
        for k in range(i + 1, min(n, i + 1 + _PACK_LOOKAHEAD)):
            # 결론(conclusion)은 끝에 와야 하므로 앞으로 끌어올리지 않는다.
            if not used[k] and items[k][1].get("type") != "conclusion" and _fits(k):
                _place(k)
                filled = True
                break
        if not filled:
            _flush()  # 더 채울 게 없으면 페이지 마감 후 i 를 새 페이지에 올린다.
    _flush()
    return pages


def house_slide_used_cm(data: dict) -> float:
    """house 슬라이드 본문이 차지하는 세로 높이(cm) 추정 — 채움률 계산용(_layout_blocks 와 동일 공식)."""
    if not isinstance(data, dict):
        return 0.0
    blocks = [b for b in (data.get("blocks") or []) if isinstance(b, dict)]
    if not blocks:
        return 0.0
    total = sum(_estimate_block_height(b, BODY_W_CM) for b in blocks)
    total += _BLOCK_GAP * (len(blocks) - 1)
    return total


def house_body_height_cm() -> float:
    """house 본문 영역 높이(cm) — 채움률 분모."""
    return BODY_H_CM


def repack_house_slides(slides: list[dict], body_h_cm: float = BODY_H_CM) -> list[dict]:
    """house-report 본문을 **블록 단위로** 다시 채워 아래 여백·페이지 수를 최소화한다.

    사내 정책(최대한 컴팩트): LLM 이 흩뜨린 블록(표/lead/timeline/conclusion/차트/2단)을
    위에서부터 한 페이지가 본문 높이를 채울 때까지 끌어올리고, 하단에 남는 공간은 뒤쪽 블록을
    당겨와(backfill) 메운다. 실제 채움 로직은 _pack_house_run 참고.

    - **블록 단위**라 한 슬라이드의 표가 다음 페이지로 넘어가 빈 공간을 채울 수 있다.
      단, 표 등 블록 1개는 쪼개지 않는다(원자 단위).
    - 페이지의 첫 블록이 속한 원본 슬라이드 제목이 그 페이지의 ▣ 제목이 된다. 한 페이지 안에서
      원본 슬라이드가 바뀌면 그 지점에 ``{"type":"heading","section": 제목}`` 을 끼워 ■ 로 표시.
    - house-report 가 아닌 레이아웃은 그대로 통과(연속된 house 블록 run 단위로 채운다).
    호출측에서 meta.no/total 재정규화를 수행한다.
    """
    out: list[dict] = []
    run: list[tuple[str, dict]] = []

    def _flush_run() -> None:
        nonlocal run
        if run:
            out.extend(_pack_house_run(run, body_h_cm))
            run = []

    for sl in slides:
        if not isinstance(sl, dict) or sl.get("layout") != "house-report":
            _flush_run()
            out.append(sl)
            continue
        data = sl.get("data") or {}
        src = str(data.get("title") or "").strip()
        for b in data.get("blocks") or []:
            if isinstance(b, dict):
                run.append((src, b))
    _flush_run()
    return out


# ============================================================
# 슬라이드/덱 진입점
# ============================================================
def _draw_ole_icon(slide, icon: dict) -> None:
    """'똑딱이'(OLE) 표면 아이콘을 본문 우하단에 그린다. finalize 가 이 그림 자리를 OLE 로 교체한다.

    icon = {"src": "data:image/png;base64,...", "label": "상세 보기"}. 그린 그림 바이트가 finalize
    의 아이콘 바이트와 같아야 위치 매칭이 되므로, 생성 단계가 저장한 동일 PNG 의 data URI 를 쓴다.
    """
    import base64
    from io import BytesIO

    src = str((icon or {}).get("src") or "")
    if not src.startswith("data:") or "," not in src:
        return
    try:
        img = base64.b64decode(src.split(",", 1)[1])
    except Exception:  # noqa: BLE001
        return
    # 사내 요청: 똑딱이는 작은 정사각 아이콘만(0.6×0.6cm). 옆 '▶ 상세 보기' 라벨/삼각형은 제거.
    w = h = 0.6
    x = BODY_W_CM - w - 0.1
    y = BODY_H_CM - h - 0.1
    try:
        pic = slide.shapes.add_picture(BytesIO(img), bx(x), by(y), L(w), L(h))
        idx = (icon or {}).get("idx")  # shape 이름 표식(OLE 주입 1순위 매칭 키)
        if isinstance(idx, int):
            pic.name = f"ole-icon-{idx}"
    except Exception:  # noqa: BLE001
        return


def build_house_report_slide(prs, data: dict, logo_path=None):
    """하우스 스타일 본문 1장. data 모델은 모듈 docstring 참고."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    data = data or {}
    _draw_frame(slide, data, logo_path=logo_path)
    _layout_blocks(slide, list(data.get("blocks") or []))
    if isinstance(data.get("ole_icon"), dict):
        _draw_ole_icon(slide, data["ole_icon"])
    return slide


LAYOUT_BUILDERS_HOUSE = {
    "house-report": build_house_report_slide,
}


def build_slide_house(prs, layout_type, data, logo_path=None):
    builder = LAYOUT_BUILDERS_HOUSE.get(layout_type)
    if builder is None:
        raise ValueError(f"Unknown house layout: {layout_type}")
    return builder(prs, data, logo_path=logo_path)
