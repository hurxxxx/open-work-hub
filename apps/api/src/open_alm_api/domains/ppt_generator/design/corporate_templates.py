"""Open ALM 양식(사양 비교) — 슬라이드 JSON → Open ALM 사양비교/공용화 현황 본문 HTML 렌더러.

참고 정본: ``HTML - PPT 연동 확인.pptx`` (Open ALM 자동차 쿨링모듈 사양비교/공용화 현황).
Qwen 35B 는 **내용(JSON)만** 만들고, 이 모듈이 그 JSON 을 Open ALM 사양비교 문서 스타일의
본문 ``inner_html`` 로 결정론적으로 렌더한다. 결과는 Open ALM 본문 칸(1244×754px)을 채우는
단일 루트 블록이며 ``corporate_frame.body_section_html`` 의 ``.dw-bodyzone`` 에 들어간다.

시각 언어(원본 deck 공통):
  - 회색 헤더바(#D9D9D9) + 좌측 라벨열(#F2F2F2) + 얇은 회색 테두리(#BFBFBF)
  - 그룹 컬럼헤더(제품군→변형 colspan) / 그룹 행헤더(구분 rowspan)
  - 마커: ← (좌동), - (없음), ↓ (목표/감소), N종, C/O 코드 — 셀 값 그대로
  - 강조셀(피치 #FCE4D6), 강조 그룹(연청회색 #E8EDF5)
  - 단위 주석(우상), ※ 주석(하단)

지원 패턴:
  - ``spec_compare``   : 그룹 컬럼헤더 + 행라벨 사양표 (원본 1·8 슬라이드)
  - ``commonization``  : 그룹 행헤더(구분) + PART NAME + 변형컬럼 + 공용화율 footer (4·5)
  - ``component_grid`` : 번호 부품 카드(형상 placeholder + 사양 + 종) (2)
  - ``schedule``       : 개발일정 타임라인(트랙별 마일스톤) (3)
  - ``issue_table``    : 요약표 + 개선 반영표 (7)
  - ``bullets``        : 폴백(텍스트 위주)
"""

from __future__ import annotations

import re

from open_alm_api.domains.ppt_generator.design.corporate_frame import BODY_H_PX, BODY_W_PX

PXCM = 48.0
_PT = PXCM * 2.54 / 72.0  # pt → px (≈1.6933)


def _pt(p: float) -> float:
    return round(p * _PT, 1)


# ── Open ALM 사양비교 색/스타일 토큰 ──────────────────────────────
HEADER_BG = "#D9D9D9"  # 헤더바 회색
GROUP_BG = "#E8EDF5"  # 강조 그룹 헤더(연청회색)
LABEL_BG = "#F2F2F2"  # 좌측 라벨열
BORDER = "#BFBFBF"  # 테두리
INK = "#222222"
SUBINK = "#444444"
HILITE = "#FCE4D6"  # 강조셀(피치)
NAVY = "#1B2C6B"
RED = "#C00000"
MUTED = "#888888"
PLACEHOLDER_BG = "#F7F8FA"
SURFACE_SOFT = "#FAFAFB"

# 폰트 스택 주의:
#  - 브라우저(DirectWrite)는 typographic family 이름 'Pretendard'/'Pretendard'(공백 없음)로만 인식.
#  - PowerPoint(GDI)는 등록명 'Pretendard'(공백 포함)으로 인식 → html_to_pptx 가 첫 토큰을 사용.
#  따라서 'Pretendard' 을 첫째(=pptx용)로, 그 뒤 'Pretendard'/'Pretendard'(=브라우저용)를 둔다.
FONT = "'Pretendard','Pretendard','Pretendard','Pretendard','Malgun Gothic',sans-serif"


def _esc(s) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _root(inner: str, *, gap: int = 10) -> str:
    """본문 칸을 가득 채우는 세로 플렉스 루트."""
    return (
        f'<div style="display:flex;flex-direction:column;gap:{gap}px;width:100%;height:100%;'
        f'box-sizing:border-box;font-family:{FONT};color:{INK};">{inner}</div>'
    )


def _unit_note(text: str) -> str:
    if not text:
        return ""
    return (
        f'<div style="text-align:right;font-size:{_pt(9)}px;color:{SUBINK};'
        f'margin-bottom:-2px;">{_esc(text)}</div>'
    )


def _foot_note(text: str) -> str:
    t = str(text or "").strip()
    # LLM 이 스키마의 선택 표시("(선택) ...")를 그대로 출력하는 경우 마커 제거.
    for marker in ("(선택)", "(선택 사항)", "(optional)", "(Optional)"):
        if t.startswith(marker):
            t = t[len(marker) :].strip()
    if not t or t in ("-", "—", "없음"):
        return ""
    return f'<div style="font-size:{_pt(9.5)}px;color:{SUBINK};margin-top:2px;">{_esc(t)}</div>'


def _cell_bg(value: str) -> str:
    """마커별 배경 보정 — 강조는 피치, 그 외 흰색."""
    return "#FFFFFF"


def _td(value, *, bg="#FFFFFF", bold=False, color=INK, fs=None, align="center") -> str:
    weight = 700 if bold else 400
    fs = fs if fs is not None else _pt(10.5)
    return (
        f'<td style="border:1px solid {BORDER};background:{bg};color:{color};'
        f"font-weight:{weight};font-size:{fs}px;text-align:{align};padding:4px 6px;"
        f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{_esc(value)}</td>'
    )


def _th(value, *, bg=HEADER_BG, fs=None, colspan=1, rowspan=1, align="center") -> str:
    fs = fs if fs is not None else _pt(10.5)
    cs = f' colspan="{colspan}"' if colspan > 1 else ""
    rs = f' rowspan="{rowspan}"' if rowspan > 1 else ""
    return (
        f'<th{cs}{rs} style="border:1px solid {BORDER};background:{bg};color:{INK};'
        f"font-weight:700;font-size:{fs}px;text-align:{align};padding:5px 6px;"
        f'white-space:nowrap;">{_esc(value)}</th>'
    )


def _table_open(extra: str = "") -> str:
    return f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;{extra}">'


def _compact_fs(n_rows: int) -> float:
    """행 수에 따라 본문 셀 폰트 축소(넘침 방지)."""
    if n_rows <= 8:
        return _pt(11)
    if n_rows <= 14:
        return _pt(9.5)
    if n_rows <= 20:
        return _pt(8.5)
    return _pt(7.5)


# ── 패턴 1: spec_compare (원본 1·8) ──────────────────────────
EMPH_BLUE = "#2F5597"  # 강조 제품군 파란 테두리 박스


def _fmt_cell(value) -> str:
    """셀 값 — 리스트/줄바꿈은 <br> 로(여러 줄 셀 지원)."""
    if isinstance(value, (list, tuple)):
        return "<br>".join(_esc(v) for v in value)
    return _esc(value).replace("\n", "<br>")


_LEAD_MARKERS = "✓✔☑→➡⇒▶▷►●○◦•·‣∙-–—*»➤·"


def _strip_lead_marker(value) -> str:
    """선행 불릿/화살표 기호 제거 — 렌더러가 다시 붙이므로 중복 방지."""
    s = str(value or "").lstrip()
    while s and s[0] in _LEAD_MARKERS:
        s = s[1:].lstrip()
        if s[:1] == ".":  # "-. " 같은 잔여 마침표
            s = s[1:].lstrip()
    return s


# 결과보고서 본문 줄의 계층 마커 분류(참고 양식: 1)·→·- 다단계 들여쓰기).
_NUM_LEAD_RE = re.compile(r"^(\(?\d+[.)]|[가-힣하]\)|[①-⑳]|[ⓐ-ⓩ]|[A-Z][.)])")


def _result_line_html(value, *, fs: float, color: str = INK, lh: float = 1.5, mb: int = 2) -> str:
    """본문 한 줄 → 들여쓰기 계층 div. 선행 마커로 단계 판별(GD&T 결과보고서 양식).

    - "1)"·"2)"·"①"·"가)" 등 번호 소항목 → 1단 들여쓰기, 마커 유지
    - "→"·"⇒"·"▶" 결론 화살표 → 2단 들여쓰기, 마커 유지
    - "-"·"·"·"•" 세부 대시 → 2단 들여쓰기, "- " 로 통일
    - 마커 없는 일반 줄 → 1단 들여쓰기, 서버가 "→ " 결론 마커 부여
    각 줄은 자식 요소 없는 단일 텍스트 노드라 html_to_pptx 변환에도 안전.
    """
    s = str(value).strip()
    if not s:
        return ""
    if s[0] == ":":
        indent, text = 18, ": " + s[1:].lstrip()
    elif _NUM_LEAD_RE.match(s):
        indent, text = 18, s
    elif s[0] in "→⇒▶➡":
        indent, text = 34, s
    elif s[0] in "-–—·•◦*‣∙":
        indent, text = 34, "- " + s[1:].lstrip()
    else:
        indent, text = 18, "→ " + s
    return (
        f'<div style="font-size:{fs}px;color:{color};line-height:{lh};'
        f"padding-left:{indent}px;text-indent:-12px;margin-bottom:{mb}px;"
        f'white-space:normal;word-break:keep-all;">{_esc(text)}</div>'
    )


SPEC_FIXED_ROWS = ("라디에이터", "콘덴서", "쿨링팬", "오일쿨러", "점프튜브", "기타")


def render_spec_compare(slide: dict) -> str:
    groups = slide.get("groups") or []  # [{label, cols:[...], emphasis}]
    row_label_header = "구 분"  # 고정 스캐폴드 라벨(좌상단)
    # 행 주제는 고정(구분/형상/라디에이터/콘덴서/쿨링팬/오일쿨러/점프튜브/기타) — Qwen 은 셀 값만 채운다.
    rows = slide.get("rows")
    unit = slide.get("unit") or ""
    note = slide.get("note") or ""

    # 전체 변형 컬럼 평탄화 + 강조 그룹의 컬럼 범위(파란 박스용) 산출
    flat_cols: list[str] = []
    emph_range: tuple[int, int] | None = None
    for g in groups:
        cols = g.get("cols") or []
        if g.get("emphasis") and cols and emph_range is None:
            emph_range = (len(flat_cols), len(flat_cols) + len(cols) - 1)
        flat_cols.extend(cols)
    ncol = max(1, len(flat_cols))

    def _emph_border(col_i: int, *, top=False, bottom=False) -> str:
        """flat col 인덱스가 강조 그룹 경계면 해당 변을 파란 테두리로."""
        if emph_range is None:
            return ""
        a, b = emph_range
        if not (a <= col_i <= b):
            return ""
        sides = []
        if col_i == a:
            sides.append(f"border-left:2px solid {EMPH_BLUE}")
        if col_i == b:
            sides.append(f"border-right:2px solid {EMPH_BLUE}")
        if top:
            sides.append(f"border-top:2px solid {EMPH_BLUE}")
        if bottom:
            sides.append(f"border-bottom:2px solid {EMPH_BLUE}")
        return (";" + ";".join(sides)) if sides else ""

    # ── 헤더 ─────────────────────────────────────────────
    has_groups = any((g.get("label") or "") for g in groups)
    head_rows = ""
    if has_groups:
        gh = (
            f'<th rowspan="2" style="border:1px solid {BORDER};background:{LABEL_BG};'
            f"font-weight:700;font-size:{_pt(12)}px;letter-spacing:3px;text-align:center;"
            f'padding:6px;width:130px;white-space:nowrap;">{_esc(row_label_header)}</th>'
        )
        ci = 0
        for g in groups:
            cols = g.get("cols") or []
            if not cols:
                continue
            emph = bool(g.get("emphasis"))
            # 강조 그룹: 바깥(상/좌/우)만 파란 테두리, 아래는 회색(서브헤더와의 경계는 회색선).
            bd = (
                f";border-top:2px solid {EMPH_BLUE};border-left:2px solid {EMPH_BLUE};"
                f"border-right:2px solid {EMPH_BLUE};border-bottom:1px solid {BORDER}"
                if emph
                else f";border:1px solid {BORDER}"
            )
            gh += (
                f'<th colspan="{len(cols)}" style="background:{HEADER_BG};color:{INK};'
                f'font-weight:700;font-size:{_pt(12)}px;text-align:center;padding:6px{bd};">'
                f"{_esc(g.get('label') or '')}</th>"
            )
            ci += len(cols)
        # 변형 서브헤더
        sub = ""
        for i, c in enumerate(flat_cols):
            sub += (
                f'<th style="border:1px solid {BORDER};background:{HEADER_BG};'
                f"font-weight:700;font-size:{_pt(11)}px;text-align:center;padding:5px"
                f'{_emph_border(i)};">{_esc(c)}</th>'
            )
        head_rows = f"<tr>{gh}</tr><tr>{sub}</tr>"
    else:
        sub = "".join(
            f'<th style="border:1px solid {BORDER};background:{HEADER_BG};font-weight:700;'
            f'font-size:{_pt(11)}px;text-align:center;padding:5px{_emph_border(i)};">{_esc(c)}</th>'
            for i, c in enumerate(flat_cols)
        )
        head_rows = (
            "<tr>" + f'<th style="border:1px solid {BORDER};background:{LABEL_BG};font-weight:700;'
            f'font-size:{_pt(12)}px;letter-spacing:3px;padding:6px;width:130px;">{_esc(row_label_header)}</th>'
            + sub
            + "</tr>"
        )

    # ── 셀 값 맵 구성 — rows 는 {행이름: [셀...]} 또는 [{label, cells}] 둘 다 허용 ──
    cellmap: dict[str, list] = {}
    if isinstance(rows, dict):
        cellmap = {str(k).strip(): v for k, v in rows.items()}
    elif isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict) and r.get("label"):
                cellmap[str(r.get("label")).strip()] = r.get("cells")

    def _cells_for(name: str) -> list:
        c = cellmap.get(name) or cellmap.get(name.replace(" ", "")) or []
        c = list(c)[:ncol]
        return c + [""] * (ncol - len(c))

    # ── 고정 행 렌더: 형 상(사진) → 라디에이터/콘덴서/쿨링팬/오일쿨러/점프튜브/기타 ──
    fs = _pt(11)
    body = ""
    # 형 상 행 (사진 자리, 남는 높이 흡수)
    fig_cells = _cells_for("형상") or [""] * ncol
    fig_tds = "".join(
        f'<td style="border:1px solid {BORDER};background:{PLACEHOLDER_BG};'
        f"text-align:center;vertical-align:middle;color:{MUTED};font-size:{_pt(9)}px;"
        f'padding:6px;{_emph_border(i)};">{_fmt_cell(c) if c else "［형상］"}</td>'
        for i, c in enumerate(fig_cells)
    )
    body += (
        f'<tr style="height:38%;"><td style="border:1px solid {BORDER};background:{LABEL_BG};'
        f'font-weight:700;font-size:{fs}px;text-align:center;padding:6px;">형 상</td>{fig_tds}</tr>'
    )
    # 고정 사양 행
    for ri, name in enumerate(SPEC_FIXED_ROWS):
        is_last = ri == len(SPEC_FIXED_ROWS) - 1
        cells = _cells_for(name)
        lab = (
            f'<td style="border:1px solid {BORDER};background:{LABEL_BG};font-weight:700;'
            f'font-size:{fs}px;text-align:center;padding:6px;">{_esc(name)}</td>'
        )
        tds = "".join(
            f'<td style="border:1px solid {BORDER};background:#FFFFFF;color:{INK};'
            f"font-size:{fs}px;text-align:center;vertical-align:middle;padding:6px;"
            f"white-space:normal;word-break:keep-all;line-height:1.4;"
            f'{_emph_border(i, bottom=is_last)};">{_fmt_cell(c)}</td>'
            for i, c in enumerate(cells)
        )
        body += f"<tr>{lab}{tds}</tr>"

    table = (
        _table_open("height:100%;")
        + "<thead>"
        + head_rows
        + "</thead><tbody>"
        + body
        + "</tbody></table>"
    )
    return _root(_unit_note(unit) + table + _foot_note(note))


# ── 패턴 2: commonization (원본 4·5) ─────────────────────────
def render_commonization(slide: dict) -> str:
    columns = slide.get("columns") or []  # 셀별 변형 컬럼명
    # 전체 행을 가로지르는 단일 병합 컬럼(예: "KAPPA 1.0T" 한 칸에 "←"). [{name, value}]
    merged_columns = slide.get("merged_columns") or []
    groups = slide.get("groups") or []  # [{label, parts:[{name, cells:[...]}]}]
    footer = slide.get("footer") or {}  # {label, cells:[...]}
    note = slide.get("note") or ""
    ncol = max(1, len(columns))
    nmerged = len(merged_columns)

    total_rows = sum(len(g.get("parts") or []) for g in groups)
    fs = _compact_fs(total_rows)

    # 컬럼 폭: 구분/PART NAME 고정, 나머지 균등
    val_w = max(8, int((100 - 10 - 22) / max(1, ncol + nmerged)))
    colgroup = (
        '<colgroup><col style="width:10%"><col style="width:22%">'
        + "".join(f'<col style="width:{val_w}%">' for _ in range(ncol + nmerged))
        + "</colgroup>"
    )

    head = "<tr>" + _th("구분", bg=LABEL_BG) + _th("PART NAME", bg=LABEL_BG)
    head += "".join(_th(c) for c in columns)
    head += "".join(_th(m.get("name") or "") for m in merged_columns) + "</tr>"

    body = ""
    for g in groups:
        parts = g.get("parts") or []
        if not parts:
            continue
        for pi, p in enumerate(parts):
            row = ""
            if pi == 0:
                row += (
                    f'<td rowspan="{len(parts)}" style="border:1px solid {BORDER};'
                    f"background:{LABEL_BG};font-weight:700;font-size:{fs}px;text-align:center;"
                    f'vertical-align:middle;padding:4px 6px;">{_esc(g.get("label") or "")}</td>'
                )
            row += _td(p.get("name") or "", fs=fs, align="left", bg="#FFFFFF")
            cells = (p.get("cells") or [])[:ncol]
            cells += [""] * (ncol - len(cells))
            for c in cells:
                row += _td(c, fs=fs)
            # 병합 안 함: 행마다 따로 셀로 표시
            for m in merged_columns:
                row += _td(m.get("value") or "←", fs=fs)
            body += f"<tr>{row}</tr>"

    if footer.get("label") or footer.get("cells"):
        fcells = (footer.get("cells") or [])[:ncol]
        fcells += [""] * (ncol - len(fcells))
        frow = (
            f'<td colspan="2" style="border:1px solid {BORDER};background:{HEADER_BG};'
            f'font-weight:700;font-size:{fs}px;text-align:center;padding:5px 6px;">'
            f"{_esc(footer.get('label') or '공용화율')}</td>"
        )
        for c in fcells:
            frow += _td(c, bg=HEADER_BG, bold=True, fs=fs)
        for m in merged_columns:
            frow += _td(m.get("footer") or "-", bg=HEADER_BG, bold=True, fs=fs)
        body += f"<tr>{frow}</tr>"

    table = (
        _table_open("height:100%;")
        + colgroup
        + "<thead>"
        + head
        + "</thead><tbody>"
        + body
        + "</tbody></table>"
    )
    return _root(table + _foot_note(note))


# ── 패턴 3: component_grid (원본 2) ──────────────────────────
def _component_card(c: dict) -> str:
    """부품 카드 — 번호+이름 제목 + '사양구성' 표(형상 이미지 행 + 사양 행, 변형 N열)."""
    no = _esc(c.get("no") or "")
    name = _esc(c.get("name") or "")
    variants = c.get("variants")
    if not variants:  # 구버전 호환: spec/count 단일
        sp = c.get("spec") or ""
        variants = [{"spec": sp}] if sp or not c.get("count") else [{"spec": c.get("count")}]
    variants = list(variants)[:3] or [{"spec": "-"}]
    nc = len(variants)
    title = (
        f'<div style="font-weight:700;font-size:{_pt(11)}px;color:{INK};margin-bottom:3px;">'
        f"{no} {name}</div>"
    )
    head = (
        f'<tr><th colspan="{nc + 1}" style="border:1px solid {BORDER};background:{LABEL_BG};'
        f'font-weight:700;font-size:{_pt(9)}px;text-align:center;padding:3px;">사양구성</th></tr>'
    )
    fig_cells = "".join(
        f'<td style="border:1px solid {BORDER};background:{PLACEHOLDER_BG};text-align:center;'
        f'vertical-align:middle;color:{MUTED};font-size:{_pt(7.5)}px;height:54px;">［형상］</td>'
        for _ in variants
    )
    spec_cells = "".join(
        f'<td style="border:1px solid {BORDER};background:#fff;text-align:center;'
        f"vertical-align:middle;font-size:{_pt(8.5)}px;padding:3px;white-space:normal;"
        f'word-break:keep-all;">{_fmt_cell(v.get("spec") or "-")}</td>'
        for v in variants
    )
    rowlab = (
        f'<td style="border:1px solid {BORDER};background:{LABEL_BG};font-weight:700;'
        f'font-size:{_pt(8.5)}px;text-align:center;width:30px;">{{}}</td>'
    )
    table = (
        f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
        f"{head}"
        f"<tr>{rowlab.format('형상')}{fig_cells}</tr>"
        f"<tr>{rowlab.format('사양')}{spec_cells}</tr>"
        f"</table>"
    )
    return f'<div style="display:flex;flex-direction:column;">{title}{table}</div>'


def render_component_grid(slide: dict) -> str:
    comps = slide.get("components") or []  # [{no, name, variants:[{spec}]}]
    note = slide.get("note") or ""
    n = len(comps)
    # 원본 배치: 좌/우 균등, 홀수 1장은 가운데-아래(조립도 밑)에. (예 7개 → 좌3/가운데1/우3)
    center_n = 1 if n % 2 == 1 else 0
    side = (n - center_n) // 2
    left = comps[:side]
    center_cards = comps[side : side + center_n]
    right = comps[side + center_n :]

    def _stack(cards: list) -> str:
        return "".join(_component_card(c) for c in cards)

    def _col(cards: list) -> str:
        return (
            f'<div style="display:flex;flex-direction:column;gap:10px;justify-content:space-between;'
            f'flex:1;min-width:0;">{_stack(cards)}</div>'
        )

    # 가운데 조립 구성도 자리표시 + 번호 범례
    legend = "".join(
        f'<div style="font-size:{_pt(8.5)}px;color:{SUBINK};margin:2px 0;white-space:nowrap;">'
        f"{_esc(c.get('no') or '')} {_esc(c.get('name') or '')}</div>"
        for c in comps
    )
    diagram = (
        f'<div style="flex:1;min-height:0;display:flex;flex-direction:column;border:1px solid {BORDER};'
        f'background:{PLACEHOLDER_BG};align-items:center;justify-content:center;color:{MUTED};">'
        f'<div style="font-size:{_pt(11)}px;margin-bottom:6px;">［조립 구성도］</div>'
        f'<div style="display:flex;flex-direction:column;align-items:flex-start;">{legend}</div></div>'
    )
    center_bottom = (
        f'<div style="display:flex;flex-direction:column;gap:10px;">{_stack(center_cards)}</div>'
        if center_cards
        else ""
    )
    center = (
        f'<div style="flex:1.2;min-width:0;display:flex;flex-direction:column;gap:10px;">'
        f"{diagram}{center_bottom}</div>"
    )
    body = (
        f'<div style="display:flex;gap:10px;width:100%;height:100%;box-sizing:border-box;'
        f'align-items:stretch;">{_col(left)}{center}{_col(right)}</div>'
    )
    return _root(body + _foot_note(note))


# ── 패턴 4: schedule (원본 3 = 개발 일정 타임라인 + 사양 비교표) ──
def _section_label(text: str) -> str:
    return (
        f'<div style="font-weight:700;font-size:{_pt(12)}px;color:{INK};margin-bottom:4px;">'
        f"▶ {_esc(text)}</div>"
    )


def _flex_spec_table(table: dict) -> str:
    """단일 컬럼(그룹 없음) + 유동 행 사양표. rows=[{label, cells, figure?}]."""
    columns = table.get("columns") or []
    rows = table.get("rows") or []
    rlh = table.get("row_label_header") or "구 분"
    ncol = max(1, len(columns))
    fs = _pt(11) if len(rows) <= 9 else _compact_fs(len(rows))

    head = (
        f'<tr><th style="border:1px solid {BORDER};background:{LABEL_BG};font-weight:700;'
        f'font-size:{fs}px;text-align:center;padding:6px;width:150px;">{_esc(rlh)}</th>'
        + "".join(
            f'<th style="border:1px solid {BORDER};background:{HEADER_BG};font-weight:700;'
            f'font-size:{fs}px;text-align:center;padding:6px;">{_esc(c)}</th>'
            for c in columns
        )
        + "</tr>"
    )
    body = ""
    for r in rows:
        label = r.get("label") or ""
        cells = (r.get("cells") or [])[:ncol]
        cells += [""] * (ncol - len(cells))
        lab = (
            f'<td style="border:1px solid {BORDER};background:{LABEL_BG};font-weight:700;'
            f'font-size:{fs}px;text-align:center;padding:6px;">{_esc(label)}</td>'
        )
        if r.get("figure"):
            tds = "".join(
                f'<td style="border:1px solid {BORDER};background:{PLACEHOLDER_BG};text-align:center;'
                f'vertical-align:middle;color:{MUTED};font-size:{_pt(9)}px;padding:6px;">'
                f"{_fmt_cell(c) if c else '［형상］'}</td>"
                for c in cells
            )
            body += f'<tr style="height:34%;">{lab}{tds}</tr>'
        else:
            tds = "".join(
                f'<td style="border:1px solid {BORDER};background:#fff;color:{INK};'
                f"font-size:{fs}px;text-align:center;vertical-align:middle;padding:6px;"
                f'white-space:normal;word-break:keep-all;line-height:1.4;">{_fmt_cell(c)}</td>'
                for c in cells
            )
            body += f"<tr>{lab}{tds}</tr>"
    return (
        _table_open("height:100%;")
        + "<thead>"
        + head
        + "</thead><tbody>"
        + body
        + "</tbody></table>"
    )


def _timeline_block(tracks: list) -> str:
    track_html = ""
    for t in tracks:
        pts = t.get("points") or []
        n = max(1, len(pts))
        dots = ""
        for i, p in enumerate(pts):
            left = (i + 0.5) / n * 100
            state = (p.get("state") or "").lower()
            dot_color = RED if state in ("done", "current") else NAVY
            dots += (
                f'<div style="position:absolute;left:{left:.1f}%;top:50%;transform:translate(-50%,-50%);'
                f'display:flex;flex-direction:column;align-items:center;">'
                f'<div style="font-size:{_pt(8.5)}px;color:{INK};white-space:nowrap;margin-bottom:3px;">'
                f"{_esc(p.get('date') or '')}</div>"
                f'<div style="width:11px;height:11px;border-radius:50%;background:{dot_color};'
                f'border:2px solid #fff;box-shadow:0 0 0 1px {dot_color};"></div>'
                f'<div style="font-size:{_pt(8.5)}px;color:{SUBINK};white-space:nowrap;margin-top:3px;">'
                f"{_esc(p.get('label') or '')}</div></div>"
            )
        track_html += (
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<div style="width:78px;font-weight:700;font-size:{_pt(9.5)}px;color:{NAVY};">'
            f"{_esc(t.get('name') or '')}</div>"
            f'<div style="position:relative;flex:1;height:50px;">'
            f'<div style="position:absolute;left:0;right:0;top:50%;height:2px;background:{BORDER};"></div>'
            f"{dots}</div></div>"
        )
    return (
        f'<div style="display:flex;flex-direction:column;gap:10px;border:1px solid {BORDER};'
        f'background:{SURFACE_SOFT};padding:10px 14px;">{track_html}</div>'
    )


def render_schedule(slide: dict) -> str:
    tracks = slide.get("tracks") or []  # [{name, points:[{date,label,state}]}]
    table = slide.get("table") or {}
    note = slide.get("note") or ""
    schedule_label = slide.get("schedule_label") or "개발 일정"

    timeline = _section_label(schedule_label) + _timeline_block(tracks) if tracks else ""

    if table.get("columns") and table.get("rows"):
        # 상단 타임라인(고정 높이) + 하단 사양표(남는 높이 채움)
        body = (
            f'<div style="display:flex;flex-direction:column;gap:12px;width:100%;height:100%;'
            f'box-sizing:border-box;">{timeline}'
            f'<div style="flex:1;min-height:0;display:flex;">{_flex_spec_table(table)}</div></div>'
        )
    else:
        # 타임라인만 — 세로 가운데로 채움
        body = (
            f'<div style="display:flex;flex-direction:column;justify-content:center;gap:14px;'
            f'width:100%;height:100%;box-sizing:border-box;">{timeline}</div>'
        )
    return _root(body + _foot_note(note))


# ── 패턴 5: issue_table (원본 7) ─────────────────────────────
def render_issue_table(slide: dict) -> str:
    summary = slide.get("summary") or {}  # {columns:[], row:[], highlight_col:int}
    issues = slide.get("issues") or []  # [{no, problem, improvement, applied, note}]
    note = slide.get("note") or ""

    blocks = ""
    if summary.get("columns"):
        cols = summary.get("columns") or []
        row = summary.get("row") or []
        hi = summary.get("highlight_col")
        head = "<tr>" + "".join(_th(c) for c in cols) + "</tr>"
        cells = (row + [""] * len(cols))[: len(cols)]
        trow = ""
        for i, c in enumerate(cells):
            bg = HILITE if (hi is not None and i == hi) else "#FFFFFF"
            trow += _td(c, bg=bg, fs=_pt(10.5))
        blocks += (
            _table_open()
            + "<thead>"
            + head
            + "</thead><tbody><tr>"
            + trow
            + "</tr></tbody></table>"
        )

    if issues:
        fs = _compact_fs(len(issues) + 1)
        head = (
            "<tr>"
            + _th("NO", bg=LABEL_BG)
            + _th("문제점")
            + _th("개선 내용")
            + _th("반영 내용")
            + _th("비고")
            + "</tr>"
        )
        body = ""
        for it in issues:
            body += (
                "<tr>"
                + _td(it.get("no") or "", bg=LABEL_BG, bold=True, fs=fs)
                + _td(it.get("problem") or "", fs=fs, align="left")
                + _td(it.get("improvement") or "", fs=fs, align="left")
                + _td(it.get("applied") or "", fs=fs, align="left")
                + _td(it.get("note") or "", fs=fs)
                + "</tr>"
            )
        blocks += (
            _table_open("margin-top:8px;")
            + "<thead>"
            + head
            + "</thead><tbody>"
            + body
            + "</tbody></table>"
        )
    return _root(blocks + _foot_note(note))


# ── 패턴 6: bullets (폴백) ───────────────────────────────────
def render_bullets(slide: dict) -> str:
    groups = slide.get("groups") or []
    if not groups and slide.get("items"):
        groups = [{"heading": "", "items": slide.get("items")}]
    blocks = ""
    for g in groups:
        items = "".join(
            f'<li style="font-size:{_pt(11.5)}px;color:{INK};line-height:1.5;margin-bottom:5px;">'
            f"{_esc(it)}</li>"
            for it in (g.get("items") or [])
        )
        head = (
            f'<div style="font-size:{_pt(13)}px;font-weight:700;color:{NAVY};'
            f'border-left:4px solid {NAVY};padding-left:8px;margin-bottom:8px;">'
            f"{_esc(g.get('heading') or '')}</div>"
            if g.get("heading")
            else ""
        )
        blocks += (
            f'<div style="border:1px solid {BORDER};background:#fff;padding:12px 14px;flex:1;">'
            f'{head}<ul style="margin:0;padding-left:18px;">{items}</ul></div>'
        )
    cols = max(1, min(2, len(groups)))
    grid = (
        f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);gap:10px;'
        f'grid-auto-rows:1fr;width:100%;height:100%;box-sizing:border-box;">{blocks}</div>'
    )
    return _root(grid)


# ── 패턴: seminar_report (세미나 참석 보고 단일 본문) ───────────
def _sq_label(text: str) -> str:
    return (
        f'<div style="font-weight:400;font-size:{_pt(11)}px;color:#000000;'
        f'margin:2px 0 4px;">■ {_esc(text)}</div>'
    )


def _seminar_meta(meta: dict) -> str:
    """상단 정보 블록 — 참관 목적 / 일정·장소 / 참관자."""
    lab = (
        "border:1px solid {b};background:{bg};color:#000000;font-weight:400;font-size:{fs}px;"
        "text-align:center;vertical-align:middle;padding:5px 6px;white-space:nowrap;"
    ).format(b=BORDER, bg=HEADER_BG, fs=_pt(11))
    val = (
        "border:1px solid {b};background:#fff;color:#000000;font-size:{fs}px;"
        "text-align:left;vertical-align:middle;padding:5px 8px;line-height:1.45;"
        "white-space:normal;word-break:keep-all;"
    ).format(b=BORDER, fs=_pt(11))
    return (
        f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
        f'<colgroup><col style="width:12%"><col style="width:40%">'
        f'<col style="width:13%"><col style="width:35%"></colgroup>'
        f'<tr><td style="{lab}">참관 목적</td><td style="{val}">{_esc(meta.get("purpose") or "")}</td>'
        f'<td style="{lab}">일정 / 장소</td><td style="{val}">{_esc(meta.get("schedule") or "")}</td></tr>'
        f'<tr><td style="{lab}">참관자</td>'
        f'<td colspan="3" style="{val}">{_esc(meta.get("attendees") or "")}</td></tr>'
        f"</table>"
    )


def _seminar_remark_items(remark) -> list:
    """비고 입력을 항목 리스트 [{label, caption, photo}] 로 정규화.

    신규: remark.items = [{label, caption, photo}]
    하위호환: remark.photos / remark.note (단일/소수 항목으로 변환)
    """
    if isinstance(remark, str):
        remark = {"note": remark}
    remark = remark or {}
    items = remark.get("items")
    if items:
        norm = []
        for it in items:
            if isinstance(it, str):
                it = {"caption": it}
            norm.append(it or {})
        return norm
    photos = remark.get("photos") or []
    note = remark.get("note") or ""
    if photos:
        return [
            {"label": p, "caption": note if i == 0 else "", "photo": True}
            for i, p in enumerate(photos)
        ]
    if note:
        return [{"label": "", "caption": note, "photo": False}]
    return []


def _photo_img(src: str, *, h_cm: float = 2.3) -> str:
    """비고칸 사진 — 셀 폭에 맞춰 object-fit:cover 로 해당 범위만 잘라 표시."""
    h = round(h_cm * PXCM)
    return (
        f'<img src="{src}" alt="" style="display:block;width:100%;height:{h}px;'
        f'object-fit:cover;border:1px solid {BORDER};margin:0 auto;">'
    )


def _seminar_remark_cell(item) -> str:
    """비고 셀 한 칸 — 똑딱이(ole_src)>사진(photo_src)>텍스트 순으로 렌더."""
    if isinstance(item, str):
        item = {"caption": item}
    item = item or {}
    label = item.get("label") or ""
    caption = item.get("caption") or item.get("note") or ""
    ole_src = item.get("ole_src") or ""
    photo_src = item.get("photo_src") or ""
    if ole_src:
        # '똑딱이'(OLE 임베드) 아이콘 — .pptx 변환 시 이 그림 자리에 OLE 개체(첨부 일정표)가 주입됨.
        isz = round(0.6 * PXCM)
        box = (
            f'<img src="{ole_src}" alt="" style="display:block;width:{isz}px;height:{isz}px;'
            f'margin:0 auto 4px;border:1px solid {BORDER};">'
        )
        cap_txt = str(caption or "").strip()
        cap = (
            f'<div style="font-size:{_pt(9)}px;color:#000000;line-height:1.15;text-align:center;'
            f'white-space:normal;word-break:keep-all;">{_fmt_cell(cap_txt)}</div>'
            if cap_txt
            else ""
        )
        return (
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'justify-content:center;">{box}{cap}</div>'
        )
    if photo_src:
        # 사진이 들어가면 캡션은 사진 '아래' 한 줄로만(겹침 방지). 길면 잘라 한 줄 유지.
        cap_txt = (caption or (f"[{label}]" if label else "")).strip()
        if len(cap_txt) > 18:
            cap_txt = cap_txt[:17] + "…"
        cap = (
            f'<div style="font-size:{_pt(9)}px;color:#000000;line-height:1.15;text-align:center;'
            f'margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            f'max-width:100%;">{_fmt_cell(cap_txt)}</div>'
            if cap_txt
            else ""
        )
        return (
            f'<div style="display:flex;flex-direction:column;align-items:center;">'
            f"{_photo_img(photo_src)}{cap}</div>"
        )
    left = ""
    if label:
        left += (
            f'<div style="font-size:{_pt(11)}px;color:#000000;text-align:center;'
            f'white-space:nowrap;line-height:1.25;">[{_esc(label)}]</div>'
        )
    cap = (
        f'<div style="font-size:{_pt(11)}px;color:#000000;line-height:1.25;'
        f'white-space:normal;word-break:keep-all;">{_fmt_cell(caption)}</div>'
        if caption
        else ""
    )
    if left and cap:
        return (
            f'<div style="display:flex;gap:5px;align-items:center;">'
            f'<div style="flex:0 0 auto;">{left}</div>'
            f'<div style="flex:1;min-width:0;">{cap}</div></div>'
        )
    return left + cap


def render_seminar_report(slide: dict) -> str:
    meta = slide.get("meta") or {}
    rows = slide.get("sections") or []  # [{no, topic, points:[], remark:{photos,note}}]
    conclusion = slide.get("conclusion") or []  # [str, ...]
    action = slide.get("action") or ""
    # 본문이 길면 워커가 여러 페이지로 나눈다. page_role: single(전부) | first(헤더+행) |
    # middle(행만) | last(행+소감). 정보헤더는 first/single 에만, 소감은 last/single 에만.
    role = str(slide.get("page_role") or "single")
    show_meta = role in ("single", "first")
    show_concl = role in ("single", "last")
    has_rows = bool(rows)

    fs = _pt(11)
    cell = (
        "border:1px solid {b};background:#fff;color:#000000;font-size:{fs}px;"
        "vertical-align:middle;padding:5px 7px;"
    ).format(b=BORDER, fs=fs)
    th = (
        f'<th style="border:1px solid {BORDER};background:{HEADER_BG};color:#000000;'
        f'font-weight:400;font-size:{fs}px;text-align:center;padding:5px 6px;">{{}}</th>'
    )
    head = (
        "<tr>"
        + th.format("NO")
        + th.format("항목")
        + th.format("주제 및 주요 내용")
        + th.format("비고")
        + "</tr>"
    )
    rcell = cell + "text-align:left;vertical-align:middle;"
    # 사진이 들어간 비고 셀은 캡션을 '바닥' 정렬로 둔다. html_to_pptx 가 셀 위에 사진을
    # 덮어 올리고 캡션은 셀 텍스트로 들어가므로, 가운데 정렬이면 캡션이 사진 뒤에 겹쳐
    # 안 보인다. 바닥 정렬이면 사진(위)·캡션(아래)이 분리돼 겹치지 않는다.
    rcell_photo = cell + "text-align:center;vertical-align:bottom;"

    def _remark_td(item) -> str:
        va = rcell_photo if isinstance(item, dict) and item.get("photo_src") else rcell
        return f'<td style="{va}">{_seminar_remark_cell(item)}</td>'

    body = ""
    for r in rows:
        pts = "".join(
            f'<div style="font-size:{fs}px;color:#000000;line-height:1.25;margin-bottom:3px;'
            f'padding-left:14px;text-indent:-14px;white-space:normal;word-break:keep-all;">'
            f'<span style="color:#000000;font-weight:400;">▶</span> {_fmt_cell(p)}</div>'
            for p in (r.get("points") or [])
        )
        items = _seminar_remark_items(r.get("remark"))
        span = max(1, len(items))
        rs = f' rowspan="{span}"' if span > 1 else ""
        first_remark_td = _remark_td(items[0]) if items else f'<td style="{rcell}"></td>'
        body += (
            "<tr>"
            f'<td{rs} style="{cell}text-align:center;font-weight:400;">{_esc(r.get("no") or "")}</td>'
            f'<td{rs} style="{cell}text-align:center;font-weight:400;white-space:normal;'
            f'word-break:keep-all;">{_fmt_cell(r.get("topic") or "")}</td>'
            f'<td{rs} style="{cell}text-align:left;vertical-align:middle;">{pts}</td>'
            f'{first_remark_td}'
            "</tr>"
        )
        for it in items[1:]:
            body += f"<tr>{_remark_td(it)}</tr>"
    # "■ 주요 내용" 을 표의 첫 행(전체 병합 셀)로 넣어 표 안의 글씨가 되게 한다.
    # 단일 <table> → html_to_pptx 가 하나의 네이티브 표로 변환(별도 텍스트 상자 X).
    title_cell = (
        "border:1px solid {b};background:{bg};color:#000000;font-size:{fs}px;"
        "font-weight:400;text-align:left;vertical-align:middle;padding:6px 10px;"
    ).format(b=BORDER, bg=LABEL_BG, fs=_pt(12))
    main_title = "■ 주요 내용 (계속)" if role in ("middle", "last") else "■ 주요 내용"
    title_row = f'<tr><td colspan="4" style="{title_cell}">&nbsp;{main_title}</td></tr>'
    main_table = (
        (
            f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
            f'<colgroup><col style="width:5%"><col style="width:13%">'
            f'<col style="width:57%"><col style="width:25%"></colgroup>'
            f"<thead>{title_row}{head}</thead><tbody>{body}</tbody></table>"
        )
        if has_rows
        else ""
    )

    concl_items = "".join(
        f'<div style="font-size:{_pt(11)}px;color:#000000;line-height:1.25;margin-bottom:3px;'
        f'padding-left:15px;text-indent:-15px;white-space:normal;word-break:keep-all;">'
        f'<span style="color:#000000;font-weight:400;">✓</span> {_fmt_cell(_strip_lead_marker(c))}</div>'
        for c in conclusion
    )
    action_text = _strip_lead_marker(action)
    action_html = (
        f'<div style="font-size:{_pt(11)}px;color:#000000;font-weight:400;line-height:1.25;'
        f"margin-top:4px;padding-left:28px;text-indent:-14px;white-space:normal;"
        f'word-break:keep-all;">→ {_fmt_cell(action_text)}</div>'
        if action_text
        else ""
    )
    # 참석 소감 — 2행 표: 위 행=라벨(헤더), 아래 행=내용(✓ 항목 + 후속 액션).
    hdr_cell = (
        "border:1px solid {b};background:{bg};color:#000000;font-size:{fs}px;"
        "text-align:left;vertical-align:middle;padding:6px 10px;"
    ).format(b=BORDER, bg=HEADER_BG, fs=_pt(12))
    cc = (
        "border:1px solid {b};background:#fff;color:#000000;font-size:{fs}px;"
        "text-align:left;vertical-align:middle;padding:7px 10px;"
    ).format(b=BORDER, fs=_pt(11))
    concl_box = (
        f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
        f'<tr><td style="{hdr_cell}">&nbsp;■ 참석 소감 (결론)</td></tr>'
        f'<tr><td style="{cc}">{concl_items}{action_html}</td></tr></table>'
    )

    meta_html = _seminar_meta(meta) if show_meta else ""
    table_block = main_table if has_rows else ""
    concl_html = concl_box if show_concl else ""
    # 출장 일정 합치기: 워커가 마지막 report 페이지에 여유가 있다고 판단하면 slide["trip"] 에
    # 출장 일정 데이터를 넣는다 → 별도 (빈) 페이지 대신 이 페이지 하단에 이어 붙인다.
    trip = slide.get("trip")
    trip_html = ""
    if isinstance(trip, dict) and trip.get("days"):
        # 제목을 표 첫 행으로 넣어 '■ 출장 일정' + 표를 하나의 표로 합친다(2개로 쪼개짐 방지).
        trip_html = _trip_table_html(trip, title="■ 출장 일정")
    # '약하게만 채움' + 겹침 방지: 표는 내용 크기대로(자연 높이) 쌓는다. 표를 flex 로 늘리면
    # 내용보다 작게 줄어들며(min-height:0) 아래 섹션과 겹치거나, 반대로 대형 빈 행으로 쫙
    # 늘어나므로 사용하지 않는다. 대신 행에 편안한 최소 높이를 줘 성기게 보이지 않게만 채우고,
    # 남는 공간은 하단 여백으로 둔다(내용을 지어내거나 표를 억지로 늘리지 않는다).
    if table_block or trip_html:
        grow_block = (
            f'<div style="display:flex;flex-direction:column;gap:6px;">'
            f"{table_block}{trip_html}</div>"
        )
    else:
        grow_block = '<div style="flex:1 1 auto;min-height:0;"></div>'
    body_html = (
        f'<div style="display:flex;flex-direction:column;gap:6px;width:100%;height:100%;'
        f'box-sizing:border-box;">{meta_html}{grow_block}{concl_html}</div>'
    )
    return _root(body_html)


# ── 패턴: trip_schedule (출장 일정 — 세미나 보고 2번째 본문) ──────
def _trip_table_html(slide: dict, *, title: str | None = None) -> str:
    """출장 일정 표 HTML 을 반환 — 단독 페이지(render_trip_schedule)와 세미나 보고
    페이지에 합쳐 넣을 때(render_seminar_report) 공용으로 쓴다.

    title 을 주면 표 첫 행(colspan)에 제목을 넣어 '제목+표'를 하나의 표로 만든다
    (별도 제목 표를 두면 pptx 에서 표가 2개로 쪼개져 보임). (참고) 각주는 렌더하지 않는다.
    """
    days = slide.get("days") or []  # [{date, rows:[{group, content:[줄...], attendees}]}]
    fs = _pt(11)
    base = (
        f"border:1px solid {BORDER};color:#000000;font-size:{fs}px;"
        f"vertical-align:middle;padding:6px 8px;"
    )
    th = (
        f'<th style="border:1px solid {BORDER};background:{HEADER_BG};color:#000000;'
        f'font-weight:400;font-size:{fs}px;text-align:center;padding:6px;">{{}}</th>'
    )
    head = (
        "<tr>"
        + th.format("일 정")
        + th.format("구 분")
        + th.format("내 용")
        + th.format("참석 인원")
        + "</tr>"
    )
    body = ""
    for d in days:
        rows = d.get("rows") or []
        if not rows:
            continue
        n = len(rows)
        for i, r in enumerate(rows):
            tr = ""
            if i == 0:
                tr += (
                    f'<td rowspan="{n}" style="{base}background:{LABEL_BG};text-align:center;">'
                    f"{_fmt_cell(d.get('date') or '')}</td>"
                )
            tr += f'<td style="{base}background:#fff;text-align:center;">{_esc(r.get("group") or "")}</td>'
            content = r.get("content") or []
            if isinstance(content, str):
                content = [content]
            lines = ""
            for ln in content:
                ind = 16 if str(ln).strip().startswith(("ㄴ", "└", "↳")) else 0
                lines += (
                    f'<div style="line-height:1.45;padding-left:{ind}px;'
                    f'white-space:normal;word-break:keep-all;">{_fmt_cell(ln)}</div>'
                )
            tr += f'<td style="{base}background:#fff;text-align:left;">{lines}</td>'
            tr += (
                f'<td style="{base}background:#fff;text-align:center;'
                f'white-space:normal;word-break:keep-all;">{_fmt_cell(r.get("attendees") or "")}</td>'
            )
            body += f"<tr>{tr}</tr>"
    title_row = ""
    if title:
        title_cell = (
            "border:1px solid {b};background:{bg};color:#000000;font-size:{fs}px;"
            "font-weight:400;text-align:left;vertical-align:middle;padding:6px 10px;"
        ).format(b=BORDER, bg=LABEL_BG, fs=_pt(12))
        title_row = f'<tr><td colspan="4" style="{title_cell}">&nbsp;{title}</td></tr>'
    # 표는 내용 크기대로(자연 높이). height:100% 로 늘리면 단독 출장 페이지에서 대형 빈 행이
    # 생기므로 두지 않는다(합쳐 넣을 때도 자연 높이가 맞다).
    table = (
        f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
        f'<colgroup><col style="width:9%"><col style="width:11%">'
        f'<col style="width:43%"><col style="width:37%"></colgroup>'
        f"<thead>{title_row}{head}</thead><tbody>{body}</tbody></table>"
    )
    return table


def render_trip_schedule(slide: dict) -> str:
    return _root(_trip_table_html(slide))


# ── 패턴: education_report (교육 보고서 — 단일 본문 표) ──────────
def _edu_label_cell(label: str, *, fs) -> str:
    """구분 열 라벨 — 2글자 라벨은 자간을 벌려 양식 느낌(예: '목 적')."""
    spaced = str(label or "").replace(" ", "")
    ls = ";letter-spacing:0.5em;padding-left:0.5em;" if len(spaced) == 2 else ";"
    return (
        f'<td style="border:1px solid {BORDER};background:{LABEL_BG};color:#000000;'
        f"font-weight:700;font-size:{fs}px;text-align:center;vertical-align:middle;"
        f'padding:11px 6px;white-space:nowrap{ls}">{_esc(spaced)}</td>'
    )


def _edu_content_cell(content, *, fs) -> str:
    """내용 셀 — 문자열(개행 <br>) 또는 줄 리스트(줄별 div). 마커(1./▶ 등)는 값 그대로."""
    if isinstance(content, (list, tuple)):
        inner = "".join(
            f'<div style="font-size:{fs}px;color:#000000;line-height:1.5;'
            f'white-space:normal;word-break:keep-all;">{_fmt_cell(c)}</div>'
            for c in content
            if str(c).strip()
        )
    else:
        inner = (
            f'<div style="font-size:{fs}px;color:#000000;line-height:1.5;'
            f'white-space:normal;word-break:keep-all;">{_fmt_cell(content)}</div>'
        )
    return (
        f'<td style="border:1px solid {BORDER};background:#fff;color:#000000;'
        f'font-size:{fs}px;text-align:left;vertical-align:middle;padding:11px 8px;">{inner}</td>'
    )


def _edu_remark_cell(remark, *, fs) -> str:
    """비고 셀 — 빈값 / 문자열 / {photo, caption}(회색 사진 자리 + 캡션)."""
    inner = ""
    if isinstance(remark, dict):
        photo_src = remark.get("photo_src") or ""
        ole_src = remark.get("ole_src") or ""
        box = ""
        if ole_src:
            # '똑딱이'(OLE 임베드) 아이콘 — .pptx 변환 시 이 그림 자리에 OLE 개체가 주입됨.
            # 0.6×0.6cm 정사각 작은 도형으로 표시.
            isz = round(0.6 * PXCM)
            box = (
                f'<img src="{ole_src}" alt="" style="display:block;width:{isz}px;height:{isz}px;'
                f'margin:0 auto 5px;border:1px solid {BORDER};">'
            )
        elif photo_src:
            box = _photo_img(photo_src, h_cm=2.6).replace("margin:0 auto;", "margin:0 auto 5px;")
        elif remark.get("photo"):
            sz = round(0.85 * PXCM)
            box = (
                f'<div style="width:{sz}px;height:{sz}px;background:#808080;'
                f'margin:0 auto 5px;"></div>'
            )
        caption = remark.get("caption") or ""
        cap = (
            f'<div style="font-size:{fs}px;color:#000000;line-height:1.25;text-align:center;'
            f'white-space:normal;word-break:keep-all;">{_fmt_cell(caption)}</div>'
            if caption
            else ""
        )
        if box or cap:
            inner = (
                f'<div style="display:flex;flex-direction:column;align-items:center;'
                f'justify-content:center;">{box}{cap}</div>'
            )
    elif remark:
        inner = (
            f'<div style="font-size:{fs}px;color:#000000;line-height:1.3;text-align:center;'
            f'white-space:normal;word-break:keep-all;">{_fmt_cell(remark)}</div>'
        )
    return (
        f'<td style="border:1px solid {BORDER};background:#fff;color:#000000;'
        f'font-size:{fs}px;text-align:center;vertical-align:middle;padding:11px 8px;">{inner}</td>'
    )


def render_education_report(slide: dict) -> str:
    rows = slide.get("rows") or []
    note = slide.get("note") or ""
    fs = _pt(11)

    th = (
        f'<th style="border:1px solid {BORDER};background:{HEADER_BG};color:#000000;'
        f"font-weight:700;font-size:{fs}px;text-align:center;vertical-align:middle;"
        f'padding:6px;">{{}}</th>'
    )
    head = "<tr>" + th.format("구 분") + th.format("내 용") + th.format("비 고") + "</tr>"

    # grow 표시가 없으면 마지막 행을 자동으로 grow(남는 높이 흡수) 처리.
    grow_idx = {i for i, r in enumerate(rows) if r.get("grow")}
    if not grow_idx and rows:
        grow_idx = {len(rows) - 1}

    # 비-grow 데이터 행 최소 높이 — 한 줄짜리 행이 다닥다닥 붙지 않게 여유를 준다.
    row_min_h = round(1.35 * PXCM)
    body = ""
    for i, r in enumerate(rows):
        # grow 행은 height:100% 로 남는 세로 공간을 흡수(여러 개면 균등 분배).
        tr = ' style="height:100%;"' if i in grow_idx else f' style="height:{row_min_h}px;"'
        body += (
            f"<tr{tr}>"
            + _edu_label_cell(r.get("label") or "", fs=fs)
            + _edu_content_cell(r.get("content"), fs=fs)
            + _edu_remark_cell(r.get("remark"), fs=fs)
            + "</tr>"
        )

    table = (
        f'<table style="width:100%;height:100%;border-collapse:collapse;table-layout:fixed;">'
        f'<colgroup><col style="width:13%"><col style="width:62%"><col style="width:25%"></colgroup>'
        f"<thead>{head}</thead><tbody>{body}</tbody></table>"
    )
    return _root(table + _foot_note(note))


# ── 패턴: toc (교육 결과 보고서 목차) ──────────────────────────
def render_toc(slide: dict) -> str:
    """< 목 차 > — 항목 + 점선 리더 + 페이지 번호. 페이지는 표지1·목차2 다음(본문 3부터)."""
    items = slide.get("items") or []
    start = int(slide.get("page_start") or 3)
    head = (
        f'<div style="font-size:{_pt(28)}px;font-weight:700;color:{INK};'
        f'margin:6px 0 18px;">&lt; 목 차 &gt;</div>'
    )
    # 글씨 색: #808080 (PowerPoint '흰색, 배경 1, 50% 더 어둡게'). 항목 앞 순번(1. 2. …) 표시.
    # 점선 리더는 마침표(.) 텍스트로 직접 채운다 — 빈 <span>(테두리) 리더는 html_to_pptx 가
    # pptx 도형으로 못 옮겨 .pptx 에서 사라지므로, 텍스트 점이라야 변환된다. 폭 초과 시
    # 단일 줄 텍스트는 페이지번호 위로 넘치므로(word_wrap=False), 남는 폭보다 약간 적게 계산.
    # 한 행 = 단일 텍스트 요소("1. 항목 ......... 3")로 묶는다. html_to_pptx 는 요소의
    # '직속 텍스트 노드'만 한 덩어리로 추출하므로, 번호/항목/점선/페이지를 자식 <span> 으로
    # 쪼개면 .pptx 에서 조각조각 분리된다. → 한 <div> 의 텍스트로 합치고 점 개수로 폭을 맞춘다.
    # (letter-spacing 은 pptx 로 전달 안 되므로 쓰지 않고, 추정은 보수적으로 약간 모자라게.)
    GRAY = "#808080"
    F = _pt(24)
    ROW_W = BODY_W_PX - 60  # _root 폭(1244) - TOC 좌우 padding(30*2)
    DOT_ADV = 0.32 * F
    SPACE = 0.4 * F

    def _adv(ch: str) -> float:
        if "가" <= ch <= "힣":
            return 1.05 * F
        if ch.isspace():
            return 0.4 * F
        if ch.isascii() and ch.isalnum():
            return 0.6 * F
        return 0.5 * F

    def _w(s: str) -> float:
        return sum(_adv(c) for c in s)

    rows = ""
    for i, it in enumerate(items):
        num = f"{i + 1}."
        page = str(start + i)
        item = str(it)
        # 번호 + 항목 + 페이지 + 공백 3개가 쓰는 폭을 빼고 남는 폭을 점으로 채운다.
        used = _w(num) + _w(item) + _w(page) + 3 * SPACE + 6
        ndots = max(3, min(240, int((ROW_W - used) / DOT_ADV)))
        line = f"{num} {_esc(item)} {'.' * ndots} {page}"
        rows += (
            f'<div style="font-size:{F}px;color:{GRAY};font-weight:700;line-height:2.0;'
            f'white-space:nowrap;overflow:hidden;">{line}</div>'
        )
    body = (
        f'<div style="display:flex;flex-direction:column;width:100%;height:100%;'
        f'box-sizing:border-box;padding:10px 30px;">{head}{rows}</div>'
    )
    return _root(body)


def _result_table_html(table: dict) -> str:
    """결과보고서 본문 표 — 헤더행 + 본문행. html_to_pptx 가 네이티브 pptx 표로 변환."""
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    if not cols or not rows:
        return ""
    fs = _pt(11)
    title = str(table.get("title") or "").strip()
    cap = (
        f'<div style="font-size:{_pt(12)}px;font-weight:700;color:{INK};'
        f'margin:10px 0 4px;">{_esc(title)}</div>'
        if title
        else ""
    )
    th = "".join(
        f'<th style="border:1px solid {BORDER};background:{HEADER_BG};font-weight:700;'
        f'font-size:{fs}px;color:#000000;padding:5px 7px;text-align:center;">{_esc(str(c))}</th>'
        for c in cols
    )
    body = ""
    for r in rows:
        cells = list(r) if isinstance(r, (list, tuple)) else [r]
        tds = ""
        for ci in range(len(cols)):
            v = cells[ci] if ci < len(cells) else ""
            align = "left" if ci == 0 else "center"
            tds += (
                f'<td style="border:1px solid {BORDER};background:#fff;font-size:{fs}px;'
                f"color:{INK};padding:4px 7px;vertical-align:middle;text-align:{align};"
                f'white-space:normal;word-break:keep-all;">{_fmt_cell(str(v))}</td>'
            )
        body += f"<tr>{tds}</tr>"
    return (
        cap + f'<table style="width:100%;border-collapse:collapse;table-layout:fixed;'
        f'margin-top:4px;"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'
    )


# 흐름도 노드 테두리 팔레트(레퍼런스 톤: 네이비 → 주황 → 청록 → 파랑 순환).
_FLOW_PALETTE = ["#1B2C6B", "#E0815B", "#3FA091", "#4A77B5"]


def _flow_diagram_html(flow: dict) -> str:
    """가로 흐름도 — 박스(노드) N개 + 단계 라벨 화살표. 배경/테두리가 있어 html_to_pptx 가
    각 박스를 네이티브 도형(rect)으로, 라벨을 네이티브 텍스트로 변환 → .pptx 에서 편집 가능."""
    nodes = flow.get("nodes") if isinstance(flow, dict) else None
    if not isinstance(nodes, list):
        return ""
    nodes = [n for n in nodes if isinstance(n, dict) and str(n.get("label") or "").strip()]
    if len(nodes) < 2:
        return ""
    nodes = nodes[:6]  # 한 줄에 들어갈 상한
    edges = flow.get("edges") or []
    title = str(flow.get("title") or "").strip()

    parts: list[str] = []
    if title:
        parts.append(
            f'<div style="font-size:{_pt(13)}px;font-weight:700;color:{NAVY};'
            f'margin:10px 0 4px;">▷ {_esc(title)}</div>'
        )
    cells: list[str] = []
    for i, nd in enumerate(nodes):
        label = str(nd.get("label") or "").strip()
        sub = str(nd.get("sub") or nd.get("desc") or "").strip()
        color = _FLOW_PALETTE[i % len(_FLOW_PALETTE)]
        filled = i == 0
        bg = color if filled else "#FFFFFF"
        title_color = "#FFFFFF" if filled else NAVY
        sub_color = "#EEEEEE" if filled else SUBINK
        sub_html = (
            f'<div style="font-size:{_pt(9)}px;color:{sub_color};margin-top:3px;'
            f'line-height:1.25;">{_esc(sub)}</div>'
            if sub
            else ""
        )
        cells.append(
            f'<div style="flex:1 1 0;min-width:0;box-sizing:border-box;border:2px solid {color};'
            f'background:{bg};border-radius:10px;padding:9px 6px;text-align:center;display:flex;'
            f'flex-direction:column;justify-content:center;align-items:center;'
            f'min-height:{round(2.0 * PXCM)}px;">'
            f'<div style="font-size:{_pt(13)}px;font-weight:800;color:{title_color};'
            f'line-height:1.2;">{_esc(label)}</div>{sub_html}</div>'
        )
        if i < len(nodes) - 1:
            edge = str(edges[i]).strip() if i < len(edges) and edges[i] else ""
            edge_html = (
                f'<div style="font-size:{_pt(8.5)}px;color:{SUBINK};margin-bottom:2px;'
                f'white-space:nowrap;">{_esc(edge)}</div>'
                if edge
                else ""
            )
            cells.append(
                f'<div style="flex:0 0 auto;display:flex;flex-direction:column;align-items:center;'
                f'justify-content:center;padding:0 5px;">{edge_html}'
                f'<div style="font-size:{_pt(17)}px;font-weight:800;color:{NAVY};'
                f'line-height:1;">&#8594;</div></div>'
            )
    parts.append(
        '<div style="display:flex;align-items:stretch;width:100%;margin:8px 0;">'
        + "".join(cells)
        + "</div>"
    )
    return "".join(parts)


# ── 패턴: result_body (교육 결과 보고서 본문 — 항목당 1장) ──────
def render_result_body(slide: dict) -> str:
    """본문 항목 1장 — ▶헤더 + 번호 소항목(굵은 제목 + → 설명 줄). 이미지 자리표시 선택."""
    header = slide.get("header") or slide.get("topic") or ""
    subs = slide.get("subsections") or []

    blocks = ""
    if header:
        blocks += (
            f'<div style="font-size:{_pt(18)}px;font-weight:700;color:{NAVY};'
            f'margin:2px 0 10px;">▶ {_esc(header)}</div>'
        )
    for si, sub in enumerate(subs):
        heading = sub.get("heading") or ""
        lines = sub.get("lines") or []
        if isinstance(lines, str):
            lines = [lines]
        # 소제목 16pt 고정
        hd = (
            f'<div style="font-size:{_pt(16)}px;font-weight:700;color:{INK};'
            f'margin:{"10px" if si else "0"} 0 4px;">{_esc(heading)}</div>'
            if heading
            else ""
        )
        # 본문 내용 12pt 고정 — 선행 마커(1)·→·-)로 다단계 들여쓰기(참고: GD&T 양식)
        body_lines = "".join(_result_line_html(ln, fs=_pt(12)) for ln in lines)
        # 실제 이미지는 슬라이드 우측 image_src 로 들어간다. 과거의 빈 ［이미지］ 더미 박스는
        # 실물이 안 채워져 혼란을 주므로 렌더하지 않는다.
        blocks += f'<div style="margin-bottom:6px;">{hd}{body_lines}</div>'

    # 선택적 가로 흐름도 — 순차/프로세스(A→B→C) 내용이면 Qwen 이 nodes 로 채운다(네이티브 도형).
    flow = slide.get("flow")
    if isinstance(flow, dict):
        blocks += _flow_diagram_html(flow)

    # 선택적 표 — 자료가 표로 정리하기 자연스러운 경우 Qwen 이 채운다.
    table = slide.get("table")
    if isinstance(table, dict):
        blocks += _result_table_html(table)

    # 첨부 자료 이미지·도식(data URI)이 있으면 **본문 글 아래에 가로로 크게** 배치한다(우측
    # 좁은 칼럼에 쑤셔넣지 않음). 캡쳐 도식은 대부분 가로로 넓어 전체 폭을 쓰는 게 잘 보인다.
    # html_to_pptx 가 <img> 를 pptx 그림으로 변환하므로 미리보기·.pptx 양쪽에 들어간다.
    image_src = slide.get("image_src") or ""
    if image_src:
        img_h = round(8.0 * PXCM)  # 글 아래에 들어갈 최대 높이(글+그림이 본문칸을 넘지 않게)
        blocks += (
            f'<div style="width:100%;text-align:center;margin-top:12px;">'
            f'<img src="{image_src}" alt="" style="max-width:100%;width:auto;'
            f'max-height:{img_h}px;height:auto;object-fit:contain;border:1px solid {BORDER};'
            f'display:inline-block;"></div>'
        )
    body = (
        f'<div style="display:flex;flex-direction:column;width:100%;height:100%;'
        f'box-sizing:border-box;padding:4px 6px;overflow:hidden;">{blocks}</div>'
    )
    return _root(body)


# ── 회의록 (corporate-meeting) — A4 세로 단일 슬라이드, 자체완결형 HTML ──────────
MEETING_W_CM = 21.0
MEETING_H_CM = 29.7
MEETING_W_PX = round(MEETING_W_CM * PXCM)
MEETING_H_PX = round(MEETING_H_CM * PXCM)


def _strip_meeting_attachment(body) -> list[str]:
    """본문에서 첨부 섹션과 그 하위 줄을 제거한다."""
    items = body if isinstance(body, list) else ([body] if body else [])
    out: list[str] = []
    skip = False
    for raw in items:
        s = str(raw).strip()
        if not s:
            continue
        if s[0] in "■◆▣":
            low = s[1:].strip().lower()
            skip = ("첨부" in s) or ("attach" in low)
        if not skip:
            out.append(s)
    return out


def _fit_meeting_body_params(body, avail_px: float, box_w_px: float) -> dict:
    """본문이 박스를 넘치지 않도록 글씨/간격 배율을 정한다."""
    items = [str(x).strip() for x in (body if isinstance(body, list) else [body]) if str(x).strip()]

    def est(fs_pt, lh, mb, htop, hbot):
        fs_px = fs_pt * _PT
        cpl = max(16, int(box_w_px / (fs_px * 0.92)))
        h, first = 0.0, True
        for s in items:
            vlines = max(1, -(-len(s) // cpl))
            if s[0] in "■◆▣":
                h += (2 if first else htop) + fs_px * 1.4 * vlines + hbot
            else:
                h += fs_px * lh * vlines + mb
            first = False
        return h

    sc = 1.0
    fs_pt = lh = mb = htop = hbot = None
    while sc >= 0.6 - 1e-9:
        fs_pt = 12.0 * sc
        lh = 1.35 + 0.35 * sc
        mb = max(1, round(7 * sc))
        htop = max(6, round(24 * sc))
        hbot = max(3, round(9 * sc))
        if est(fs_pt, lh, mb, htop, hbot) <= avail_px:
            break
        sc -= 0.05
    return {
        "fs_pt": round(fs_pt, 1),
        "lh": round(lh, 2),
        "mb": mb,
        "head_top": htop,
        "head_bot": hbot,
    }


def _meeting_body_html(
    body,
    *,
    fs_pt: float = 12.0,
    lh: float = 1.7,
    mb: int = 7,
    head_top: int = 24,
    head_bot: int = 9,
) -> str:
    """회의내용 본문 줄들 → HTML."""
    if isinstance(body, str):
        body = [body]
    lines = body if isinstance(body, list) else []
    hfs = _pt(fs_pt)
    out: list[str] = []
    first = True
    for raw in lines:
        s = str(raw).strip()
        if not s:
            continue
        if s[0] in "■◆▣":
            out.append(
                f'<div style="font-size:{hfs}px;font-weight:700;color:#000;'
                f'line-height:1.4;margin:{(2 if first else head_top)}px 0 {head_bot}px;">■ '
                f"{_esc(s[1:].lstrip())}</div>"
            )
        else:
            out.append(_result_line_html(s, fs=hfs, color="#000", lh=lh, mb=mb))
        first = False
    return "".join(out) or (
        f'<div style="font-size:{_pt(12)}px;color:{MUTED};">회의내용이 비어 있습니다.</div>'
    )


MEETING_CATEGORIES = ["정보전달", "이해조정", "의견교환", "문제해결", "기타"]


def _meeting_selected_categories(slide: dict) -> set[str]:
    """slide 의 meeting_categories/meeting_type 에서 표준 회의 구분을 추출한다."""
    sel: set[str] = set()
    cats = slide.get("meeting_categories")
    if isinstance(cats, str):
        cats = [cats]
    if isinstance(cats, list):
        for c in cats:
            cs = str(c).strip()
            for std in MEETING_CATEGORIES:
                if std and (std in cs or (cs and cs in std)):
                    sel.add(std)
    mt = str(slide.get("meeting_type") or "")
    for std in MEETING_CATEGORIES:
        if std in mt:
            sel.add(std)
    return sel


_ORG_HEAD_FIND = re.compile(r"(?:^|[,，])\s*([가-힣A-Za-z][가-힣A-Za-z0-9()·]{1,11})\s*[:：]")
_ORG_HEAD_AT0 = re.compile(r"^\s*([가-힣A-Za-z][가-힣A-Za-z0-9()·]{1,11})\s*[:：]\s*")


def _split_org_groups(line: str) -> list[str]:
    """한 줄에 '단체명 : 명단' 그룹이 여러 개 섞여 있으면 그룹별로 분리한다."""
    heads = list(_ORG_HEAD_FIND.finditer(line))
    if len(heads) <= 1:
        return [line.strip(" ,，")]
    segs: list[str] = []
    pre = line[: heads[0].start()].strip(" ,，")
    if pre:
        segs.append(pre)
    for i, match in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(line)
        seg = line[match.start(1) : end].strip(" ,，")
        if seg:
            segs.append(seg)
    return segs


def _meeting_attendees_html(attendees, total) -> str:
    """참석자 목록을 소속 단체별 한 줄 HTML로 변환한다."""
    raw: list[str] = []
    if isinstance(attendees, list):
        for attendee in attendees:
            if isinstance(attendee, dict):
                org = str(attendee.get("org") or "").strip()
                members = str(attendee.get("members") or attendee.get("name") or "").strip()
                if org and members:
                    raw.append(f"{org} : {members}")
                elif org or members:
                    raw.append(org or members)
            elif str(attendee).strip():
                raw.append(str(attendee).strip())
    elif isinstance(attendees, str):
        raw = [line.strip() for line in attendees.replace("\r", "").split("\n") if line.strip()]

    lines: list[str] = []
    for line in raw:
        lines.extend(part for part in _split_org_groups(line) if part)

    parts: list[str] = []
    for line in lines:
        match = _ORG_HEAD_AT0.match(line)
        if match:
            org, members = match.group(1), line[match.end() :].strip()
            parts.append(
                f'<span style="font-weight:700;color:{NAVY};">{_esc(org)}:</span> {_esc(members)}'
            )
        else:
            parts.append(_esc(line))
    html = "<br>".join(parts)
    total_text = str(total or "").strip().strip("()").strip()
    if total_text:
        html = (html + " " if html else "") + (
            f'<span style="color:{MUTED};">({_esc(total_text)})</span>'
        )
    return html or "&nbsp;"


def render_meeting_minutes_deck(slide: dict) -> str:
    """회의록 1장 HTML 덱을 렌더한다."""
    get = lambda key: _esc(slide.get(key) or "")  # noqa: E731
    title = get("title")
    team = get("team")
    author = get("author")
    place = get("place")
    meeting_date = get("date")
    meeting_time = get("time")
    attendees_html = _meeting_attendees_html(slide.get("attendees"), slide.get("attendee_total"))
    selected = _meeting_selected_categories(slide)
    body_items = _strip_meeting_attachment(slide.get("body"))
    body_box_h_cm = 19.5
    body_avail_px = body_box_h_cm * PXCM - 26
    body_w_px = MEETING_W_PX - round(0.5 * PXCM) * 2 - 32
    fit = _fit_meeting_body_params(body_items, body_avail_px, body_w_px)
    body_html = _meeting_body_html(body_items, **fit)

    fs = _pt(12)
    row_h = round(0.86 * PXCM, 1)
    label_style = (
        f"border:1px solid {BORDER};background:{HEADER_BG};font-weight:700;"
        f"color:#000;font-size:{fs}px;padding:3px 7px;text-align:center;"
        f"white-space:nowrap;vertical-align:middle;box-sizing:border-box;height:{row_h}px;"
    )
    value_style = (
        f"border:1px solid {BORDER};background:#fff;color:{INK};"
        f"font-size:{fs}px;padding:3px 8px;vertical-align:middle;"
        f"word-break:keep-all;box-sizing:border-box;height:{row_h}px;"
    )
    section_style = (
        f"border:1px solid {BORDER};background:{HEADER_BG};font-weight:700;"
        f"color:#000;font-size:{fs}px;padding:3px 8px;text-align:center;"
        f"box-sizing:border-box;height:{row_h}px;"
    )
    attendee_style = (
        f"border:1px solid {BORDER};background:#fff;color:{INK};"
        f"font-size:{fs}px;padding:4px 9px;vertical-align:middle;"
        f"line-height:1.4;word-break:keep-all;box-sizing:border-box;"
        f"height:{round(1.39 * PXCM, 1)}px;"
    )
    option_fs = _pt(10)
    option_style = (
        f"border:1px solid {BORDER};background:#fff;box-sizing:border-box;height:{row_h}px;"
        f"padding:0 8px;vertical-align:middle;white-space:nowrap;"
        f"font-size:{option_fs}px;color:#000;"
    )

    def option_td(index: int) -> str:
        option = MEETING_CATEGORIES[index]
        weight = "font-weight:700;" if option in selected else ""
        marker = "●" if option in selected else "○"
        return (
            f'<td style="{option_style}{weight}">'
            f'<span style="display:inline-block;width:72%;">{option}</span>'
            f'<span style="display:inline-block;width:24%;text-align:right;'
            f'font-size:{option_fs}px;">{marker}</span></td>'
        )

    fields = [
        ("주관팀", team),
        ("작성자", author),
        ("장 소", place),
        ("회의일", meeting_date),
        ("시 간", meeting_time),
    ]
    field_rows = "".join(
        f'<tr><td style="{label_style}">{field_label}</td>'
        f'<td style="{value_style}">{field_value}</td>{option_td(i)}</tr>'
        for i, (field_label, field_value) in enumerate(fields)
    )
    form_table = (
        '<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
        '<colgroup><col style="width:14%"><col style="width:61%">'
        '<col style="width:25%"></colgroup>'
        f'<tr><td style="{label_style}">주 제</td>'
        f'<td style="{value_style}">{title}</td>'
        f'<td style="{label_style}">회의 구분</td></tr>'
        f"{field_rows}"
        f'<tr><td colspan="3" style="{label_style}">참석자</td></tr>'
        f'<tr><td colspan="3" style="{attendee_style}">{attendees_html}</td></tr>'
        f'<tr><td colspan="3" style="{section_style}">회의내용</td></tr>'
        "</table>"
    )
    content_box = (
        f'<div style="border:1px solid {BORDER};box-sizing:border-box;'
        f"background:#fff;padding:10px 15px 14px;overflow:hidden;"
        f'height:{round(body_box_h_cm * PXCM)}px;">{body_html}</div>'
    )
    foot = (
        f'<div style="position:absolute;left:{round(0.5 * PXCM)}px;'
        f'bottom:{round(0.28 * PXCM)}px;font-size:{_pt(6)}px;color:{MUTED};">'
        f"Open ALM · This information is exclusive property of "
        f"Open ALM.</div>"
    )
    title_head = (
        "<div style=\"font-family:'Pretendard','Pretendard','Pretendard',"
        "'Pretendard','Malgun Gothic',sans-serif;font-weight:700;color:#000;"
        f'font-size:{_pt(24)}px;letter-spacing:9px;line-height:1.1;">회 의 록</div>'
    )
    slide_html = (
        f'<section class="slide" style="position:relative;width:{MEETING_W_PX}px;'
        f"height:{MEETING_H_PX}px;background:#fff;box-sizing:border-box;"
        f'padding:{round(0.5 * PXCM)}px {round(0.5 * PXCM)}px;overflow:hidden;">'
        f'{title_head}<div style="height:{round(0.25 * PXCM)}px;"></div>'
        f"{form_table}{content_box}{foot}</section>"
    )
    css = (
        f"@page{{size:{MEETING_W_PX}px {MEETING_H_PX}px;margin:0;}}"
        "html,body{margin:0;padding:0;background:#fff;}"
        "body{font-family:'Pretendard','Pretendard','Pretendard','Pretendard',"
        "'Malgun Gothic',sans-serif;}"
    )
    return (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        '<link rel="stylesheet" '
        'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@latest/dist/web/static/pretendard.css">'
        f"<style>{css}</style></head><body>{slide_html}</body></html>"
    )


_RENDERERS = {
    "spec_compare": render_spec_compare,
    "commonization": render_commonization,
    "component_grid": render_component_grid,
    "schedule": render_schedule,
    "seminar_report": render_seminar_report,
    "trip_schedule": render_trip_schedule,
    "education_report": render_education_report,
    "toc": render_toc,
    "result_body": render_result_body,
    "issue_table": render_issue_table,
    "bullets": render_bullets,
}

SUPPORTED_PATTERNS = tuple(_RENDERERS.keys())


def render_inner_html(slide: dict) -> str:
    """슬라이드 JSON → 본문 칸(1244×754) inner_html. 알 수 없는 pattern 은 bullets 폴백."""
    pattern = str(slide.get("pattern") or "").strip()
    renderer = _RENDERERS.get(pattern, render_bullets)
    try:
        return renderer(slide)
    except Exception:
        return render_bullets(slide)


def render_section(slide: dict) -> dict:
    """슬라이드 JSON → corporate_frame 섹션 dict {title, subtitle, inner_html}."""
    return {
        "title": str(slide.get("title") or ""),
        "subtitle": str(slide.get("subtitle") or ""),
        "inner_html": render_inner_html(slide),
    }


__all__ = [
    "BODY_H_PX",
    "BODY_W_PX",
    "SUPPORTED_PATTERNS",
    "render_inner_html",
    "render_section",
]
