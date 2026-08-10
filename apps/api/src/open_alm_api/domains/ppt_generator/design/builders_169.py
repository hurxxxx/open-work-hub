# -*- coding: utf-8 -*-
"""
pptgen2_design.py — Open ALM PPT Design System v2

Open ALM AI TFT 전용 16:9 프레젠테이션 빌더.
캔버스 17.778" × 10.0" (1920×1080 px 등비), 단일 폰트 "Pretendard",
corporate-blue 메인 + corporate-red 액센트.

본 모듈은 Open ALM 사내 표준 PPT 양식을 정확히 재현하기 위한 사양이며,
표지 슬라이드는 빌더가 직접 그리고(원본 PPT 없음),
본문 콘텐츠 슬라이드는 동일한 헤더 구도(좌 ▣+제목 / 우 Confidential+로고+날짜
/ 횡선 가로 분리선)를 공유한다.

본 모듈은 외부 네트워크 호출 0건 — python-pptx 만 사용.
"""
from datetime import datetime
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree


# ============================================================
# 캔버스 & 좌표 변환 — 1920×1080 px → inches
# ============================================================
SLIDE_W_IN = 17.778
SLIDE_H_IN = 10.0
SLIDE_W = Inches(SLIDE_W_IN)
SLIDE_H = Inches(SLIDE_H_IN)

# 1px → inch 변환 (디자인 그리드 1920px 기준)
PX_TO_IN = SLIDE_W_IN / 1920.0


def px(value):
    """디자인 px 값을 EMU(Inches) 객체로 변환."""
    return Inches(value * PX_TO_IN)


# ============================================================
# 컬러 토큰 — Open ALM v2 명세 1:1
# ============================================================
COLORS = {
    # Open ALM 브랜드 코어
    'corporate_blue':         RGBColor(0x1E, 0x2A, 0x8E),
    'corporate_blue_deep':    RGBColor(0x14, 0x1C, 0x6B),
    'corporate_blue_soft':    RGBColor(0x3B, 0x4A, 0xB8),
    'corporate_red':          RGBColor(0xE2, 0x23, 0x1A),
    'corporate_red_soft':     RGBColor(0xF2, 0x6B, 0x65),
    # 중립
    'canvas':              RGBColor(0xFF, 0xFF, 0xFF),
    'surface':             RGBColor(0xF7, 0xF8, 0xFA),
    'surface_blue_tint':   RGBColor(0xEE, 0xF1, 0xFB),
    'hairline':            RGBColor(0xE5, 0xE7, 0xEB),
    'hairline_soft':       RGBColor(0xEA, 0xEC, 0xF0),
    'header_divider':      RGBColor(0xAE, 0xAE, 0xAE),
    'ink':                 RGBColor(0x0A, 0x0A, 0x0A),
    'charcoal':            RGBColor(0x22, 0x22, 0x22),
    'slate':               RGBColor(0x45, 0x51, 0x5E),
    'steel':               RGBColor(0x5F, 0x5F, 0x5F),
    'white':               RGBColor(0xFF, 0xFF, 0xFF),
    # 시맨틱
    'success_bg':          RGBColor(0xE8, 0xFF, 0xEA),
    'success_text':        RGBColor(0x1B, 0xA6, 0x73),
    'warning_bg':          RGBColor(0xFF, 0xF4, 0xE0),
    'warning_text':        RGBColor(0xB8, 0x76, 0x00),
    'danger_bg':           RGBColor(0xFF, 0xE8, 0xE6),
    'danger_text':         RGBColor(0xC4, 0x1E, 0x1A),
}


# ============================================================
# 폰트
# ============================================================
FONT_KR = 'Pretendard'   # 단일 폰트 (사용자 PC에 설치 필요)
FONT_EN = 'Arial'           # Confidential 배지·캡션 등 보조


# ============================================================
# 유틸 — 텍스트박스 + 폰트 강제 (한글 ea/cs 보장)
# ============================================================
def _set_run_font(run, name=FONT_KR, size_pt=14, bold=False, color=None,
                  letter_spacing_pt=None):
    run.font.name = name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    for tag in ('ea', 'cs'):
        old = rPr.find(qn(f'a:{tag}'))
        if old is not None:
            rPr.remove(old)
    ea = etree.SubElement(rPr, qn('a:ea'))
    ea.set('typeface', name)
    cs = etree.SubElement(rPr, qn('a:cs'))
    cs.set('typeface', name)
    if letter_spacing_pt is not None:
        rPr.set('spc', str(int(letter_spacing_pt * 100)))


def _add_textbox(slide, left, top, width, height, text='', *,
                 font=FONT_KR, size_pt=14, bold=False, color=None,
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 letter_spacing_pt=None, line_spacing=None,
                 multi_paragraphs=False):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    lines = text.split('\n') if multi_paragraphs else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if line_spacing is not None:
            p.line_spacing = line_spacing
        run = p.add_run()
        run.text = line
        _set_run_font(run, name=font, size_pt=size_pt, bold=bold,
                      color=color, letter_spacing_pt=letter_spacing_pt)
    return tb


def _add_filled_rect(slide, left, top, width, height, *,
                     fill_color, line_color=None, line_width_pt=0,
                     shape_type=MSO_SHAPE.RECTANGLE):
    shape = slide.shapes.add_shape(shape_type, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(line_width_pt)
    shape.shadow.inherit = False
    return shape


def _add_outlined_rect(slide, left, top, width, height, *,
                       line_color, line_width_pt=1, fill_color=None,
                       shape_type=MSO_SHAPE.RECTANGLE):
    shape = slide.shapes.add_shape(shape_type, left, top, width, height)
    if fill_color is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill_color
    shape.line.color.rgb = line_color
    shape.line.width = Pt(line_width_pt)
    shape.shadow.inherit = False
    return shape


def _add_circle(slide, left, top, diameter, *,
                fill_color=None, line_color=None, line_width_pt=0):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, diameter, diameter)
    if fill_color is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill_color
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(line_width_pt)
    shape.shadow.inherit = False
    return shape


def _add_left_rule(slide, left, top, height, color, width_pt=4):
    """좌측 수직 강조 룰 (4px wide × 본문 높이)."""
    _add_filled_rect(slide, left, top, Pt(width_pt), height, fill_color=color)


# ============================================================
# 공통 헤더 (모든 본문 슬라이드 — v2 §5)
# ============================================================
def add_body_header(slide, header_text='{{HEADER}}', subtitle=None,
                    date_str=None, logo_path=None):
    """본문 슬라이드 공통 헤더 (좌 ▣+제목 / 우 Confidential+로고+날짜 / 횡선)."""
    if date_str is None:
        date_str = datetime.now().strftime('%Y.%m.%d')

    # ▣ 중복 제거 — vLLM 응답이 가끔 HEADER에 ▣을 미리 붙여 보냄
    clean = (header_text or '').lstrip()
    while clean.startswith('▣'):
        clean = clean[1:].lstrip()

    # 좌상 ▣ + 제목 — 방향키 10회 위로 ≈ 13px
    _add_textbox(slide, px(39), px(15), px(1600), px(70),
                 text='▣ ' + clean,
                 font=FONT_KR, size_pt=30, bold=True, color=COLORS['ink'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # 우측 상단 Confidential 배지 — px(1700, 9, 202, 46)
    _add_outlined_rect(slide, px(1700), px(9), px(202), px(46),
                       line_color=COLORS['corporate_red'], line_width_pt=2,
                       fill_color=COLORS['canvas'])
    _add_textbox(slide, px(1700), px(9), px(202), px(46),
                 text='Confidential',
                 font=FONT_EN, size_pt=16, bold=True,
                 color=COLORS['corporate_red'],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    # 우측 중단 OPEN ALM 로고 — px(1603, 85, 153, 33)
    if logo_path:
        try:
            slide.shapes.add_picture(logo_path,
                                     px(1603), px(85),
                                     width=px(153), height=px(33))
        except Exception:
            pass

    # 우측 상단 날짜 — px(1770, 66, 133, 30)
    _add_textbox(slide, px(1770), px(66), px(133), px(30),
                 text=date_str,
                 font=FONT_KR, size_pt=12, color=COLORS['steel'],
                 align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

    # 횡선 분리선 좌 — px(0, 101, 1594, 4)
    _add_filled_rect(slide, Emu(0), px(101), px(1594), px(4),
                     fill_color=COLORS['header_divider'])
    # 횡선 분리선 우 (OPEN ALM 로고 + 날짜 영역만) — px(1767, 101, 153, 4)
    _add_filled_rect(slide, px(1767), px(101), px(153), px(4),
                     fill_color=COLORS['header_divider'])

    # 부제 (선택) — 헤더 분리선 가까이 (방향키 10회 위로 ≈ 13px)
    if subtitle:
        _add_textbox(slide, px(80), px(137), px(1500), px(36),
                     text=subtitle,
                     font=FONT_KR, size_pt=13, color=COLORS['slate'],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)


def add_page_number(slide, current, total):
    """우측 하단 페이지 번호 (v2 §6) — px(1780, 1020, 120, 28)."""
    _add_textbox(slide, px(1780), px(1020), px(120), px(28),
                 text=f'{current:02d} / {total:02d}',
                 font=FONT_KR, size_pt=9, color=COLORS['steel'],
                 align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE,
                 letter_spacing_pt=1.0)


def add_takeaway_bar(slide, label, body_text):
    """OPEN ALM 시사점 takeaway 바 — 모든 본문 슬라이드 하단 (v2 §7-1)."""
    # px(64, 855, 1792, 100)
    bar_left = px(64)
    bar_top = px(855)
    bar_w = px(1792)
    bar_h = px(100)
    # 배경 (옵션) — 명세는 배경 없이 좌측 룰만. 그대로.
    # 좌측 수직 룰 4px corporate-blue
    _add_left_rule(slide, bar_left, bar_top, bar_h, COLORS['corporate_blue'], width_pt=4)
    # 라벨 (위)
    _add_textbox(slide, bar_left + px(20), bar_top + px(6),
                 bar_w - px(20), px(22),
                 text='OPEN ALM 시사점',
                 font=FONT_KR, size_pt=11, bold=True,
                 color=COLORS['corporate_blue'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 letter_spacing_pt=3.0)
    # 본문
    _add_textbox(slide, bar_left + px(20), bar_top + px(34),
                 bar_w - px(20), bar_h - px(34),
                 text=body_text,
                 font=FONT_KR, size_pt=12, color=COLORS['charcoal'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.45, multi_paragraphs=True)


# ============================================================
# Layout 1 — Cover Slide (v2 §4) — 빌더가 직접 그림 (원본 없음)
# ============================================================
def build_cover_slide(prs, data, logo_path=None):
    """표지 슬라이드. 빌더가 직접 그린다 (사내 공식 표지 원본 없음).

    data 필드:
      - TITLE: 발표 주제
      - DATE: 발표 날짜 (YYYY.MM.DD, 빈 값이면 오늘)
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    title = data.get('TITLE', '{{TITLE}}')
    date_str = data.get('DATE') or datetime.now().strftime('%Y.%m.%d')

    # Confidential 배지 (우상단)
    _add_outlined_rect(slide, px(1700), px(28), px(202), px(46),
                       line_color=COLORS['corporate_red'], line_width_pt=2,
                       fill_color=COLORS['canvas'])
    _add_textbox(slide, px(1700), px(28), px(202), px(46),
                 text='Confidential',
                 font=FONT_EN, size_pt=16, bold=True,
                 color=COLORS['corporate_red'],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    # Rev.01 표기 (좌상단)
    _add_textbox(slide, px(80), px(40), px(200), px(28),
                 text='Rev.01',
                 font=FONT_KR, size_pt=12, color=COLORS['steel'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # DCC Confidential Documents 워터마크 (대각선, 본문 중앙)
    # PowerPoint COM 없이 python-pptx로 텍스트 회전이 가능 — 텍스트박스 회전.
    wm = slide.shapes.add_textbox(px(280), px(400), px(1360), px(200))
    wm.rotation = -25  # 도(degree)
    wm_tf = wm.text_frame
    wm_tf.margin_left = Emu(0)
    wm_tf.margin_right = Emu(0)
    wm_tf.margin_top = Emu(0)
    wm_tf.margin_bottom = Emu(0)
    p = wm_tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = 'DCC Confidential Documents'
    _set_run_font(r, name=FONT_EN, size_pt=68, bold=True,
                  color=COLORS['hairline'])  # 옅은 회색
    # 투명도 80% 효과는 hairline(#E5E7EB) 회색으로 대체

    # 메인 타이틀 (y=540)
    _add_textbox(slide, px(80), px(540), px(1760), px(96),
                 text=title,
                 font=FONT_KR, size_pt=42, bold=True, color=COLORS['ink'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.BOTTOM)

    # 횡선 가로 분리선 (제목 아래)
    _add_filled_rect(slide, px(80), px(648), px(1760), px(4),
                     fill_color=COLORS['header_divider'])

    # 날짜 (y=680)
    _add_textbox(slide, px(80), px(680), px(600), px(40),
                 text=date_str,
                 font=FONT_KR, size_pt=18, color=COLORS['slate'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)

    # ㈜Open ALM 기술연구소 표기 (y=820)
    _add_textbox(slide, px(80), px(820), px(1200), px(60),
                 text='㈜Open ALM 기술연구소',
                 font=FONT_KR, size_pt=24, bold=True, color=COLORS['ink'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)

    # OPEN ALM 로고 (우하단)
    if logo_path:
        try:
            slide.shapes.add_picture(logo_path,
                                     px(1600), px(900),
                                     width=px(240), height=px(52))
        except Exception:
            pass

    # 하단 카피라이트
    _add_textbox(slide, px(80), px(1030), px(1760), px(28),
                 text='Open ALM : This information is exclusive property of Open ALM',
                 font=FONT_EN, size_pt=8, color=COLORS['steel'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    return slide


# ============================================================
# Body Pattern 1 — 2-Column Comparison (v2 §7-1)
# ============================================================
def build_2col_comparison_slide(prs, data, logo_path=None,
                                page_num=None, total_pages=None):
    """좌 narrative + 우 metric 비교 패널 (PTC vs Heat Pump 식).

    data 필드:
      - HEADER, SUBTITLE (선택)
      - WHY_NOW_LABEL: 좌측 상단 라벨 (예: "WHY NOW")
      - LEAD_PARAGRAPH: 좌측 도입 단락
      - LEFT_BULLETS: [{TITLE, BODY}, x3]
      - PANEL1_LABEL, PANEL1_VALUE, PANEL1_NOTE
      - PANEL2_LABEL, PANEL2_VALUE, PANEL2_NOTE, PANEL2_BADGE (예: "RECOMMENDED")
      - TAKEAWAY: 시사점 본문
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    add_body_header(slide,
                    header_text=data.get('HEADER', '{{HEADER}}'),
                    subtitle=data.get('SUBTITLE'),
                    logo_path=logo_path)

    # ─── 좌측 컬럼 ─── px(64, 200, 880, ~)
    left_x = px(64)
    left_w = px(880)
    cursor_y = px(200)

    # WHY NOW 라벨
    why_label = data.get('WHY_NOW_LABEL', 'WHY NOW')
    _add_textbox(slide, left_x, cursor_y, left_w, px(28),
                 text=why_label,
                 font=FONT_KR, size_pt=11, bold=True,
                 color=COLORS['corporate_red'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE,
                 letter_spacing_pt=3.0)
    cursor_y = px(232)

    # 도입 단락
    lead = data.get('LEAD_PARAGRAPH', '{{LEAD_PARAGRAPH}}')
    _add_textbox(slide, left_x, cursor_y, left_w, px(110),
                 text=lead,
                 font=FONT_KR, size_pt=14, color=COLORS['charcoal'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.5, multi_paragraphs=True)
    cursor_y = px(360)

    # 3개 글머리표 (빨강 dot + 14pt bold 제목 + 12pt 본문)
    bullets = data.get('LEFT_BULLETS') or [
        {'TITLE': f'{{{{B{i}_TITLE}}}}', 'BODY': f'{{{{B{i}_BODY}}}}'} for i in range(1, 4)
    ]
    for b in bullets[:3]:
        dot_d = px(10)
        _add_circle(slide, left_x, cursor_y + px(7), dot_d,
                    fill_color=COLORS['corporate_red'])
        _add_textbox(slide, left_x + px(20), cursor_y, left_w - px(20), px(24),
                     text=b.get('TITLE', ''),
                     font=FONT_KR, size_pt=14, bold=True, color=COLORS['ink'],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        _add_textbox(slide, left_x + px(20), cursor_y + px(28),
                     left_w - px(20), px(110),
                     text=b.get('BODY', ''),
                     font=FONT_KR, size_pt=12, color=COLORS['charcoal'],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                     line_spacing=1.45, multi_paragraphs=True)
        cursor_y += px(150)

    # ─── 우측 패널 ─── px(980, 200, 876, ~)
    right_x = px(980)
    right_w = px(876)
    panel_h = px(280)
    gap = px(30)

    # Panel 1 — baseline
    p1_top = px(200)
    _add_outlined_rect(slide, right_x, p1_top, right_w, panel_h,
                       line_color=COLORS['hairline'], line_width_pt=1,
                       fill_color=COLORS['surface'])
    _add_textbox(slide, right_x + px(24), p1_top + px(20), right_w - px(48), px(22),
                 text=data.get('PANEL1_LABEL', 'BASELINE'),
                 font=FONT_KR, size_pt=11, bold=True, color=COLORS['slate'],
                 align=PP_ALIGN.LEFT, letter_spacing_pt=2.0)
    _add_textbox(slide, right_x + px(24), p1_top + px(60), right_w - px(48), px(80),
                 text=data.get('PANEL1_VALUE', '{{VALUE}}'),
                 font=FONT_KR, size_pt=30, bold=True, color=COLORS['ink'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 letter_spacing_pt=-1.0)
    _add_textbox(slide, right_x + px(24), p1_top + px(160), right_w - px(48), px(100),
                 text=data.get('PANEL1_NOTE', ''),
                 font=FONT_KR, size_pt=12, color=COLORS['steel'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.45, multi_paragraphs=True)

    # Panel 2 — recommended (배지 + 강조)
    p2_top = p1_top + panel_h + gap
    _add_outlined_rect(slide, right_x, p2_top, right_w, panel_h,
                       line_color=COLORS['corporate_blue_soft'], line_width_pt=1.5,
                       fill_color=COLORS['surface_blue_tint'])
    # RECOMMENDED 배지
    badge_text = data.get('PANEL2_BADGE', 'RECOMMENDED')
    badge_w = px(196)
    badge_h = px(28)
    _add_filled_rect(slide, right_x + right_w - badge_w - px(20),
                     p2_top + px(16), badge_w, badge_h,
                     fill_color=COLORS['corporate_red'])
    _add_textbox(slide, right_x + right_w - badge_w - px(20),
                 p2_top + px(16), badge_w, badge_h,
                 text=badge_text,
                 font=FONT_EN, size_pt=9, bold=True, color=COLORS['white'],
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                 letter_spacing_pt=1.0)
    # 라벨
    _add_textbox(slide, right_x + px(24), p2_top + px(20), right_w - px(48), px(22),
                 text=data.get('PANEL2_LABEL', 'PROPOSED'),
                 font=FONT_KR, size_pt=11, bold=True, color=COLORS['corporate_blue'],
                 align=PP_ALIGN.LEFT, letter_spacing_pt=2.0)
    # 큰 숫자/값 — corporate-blue 32pt bold
    _add_textbox(slide, right_x + px(24), p2_top + px(60), right_w - px(48), px(80),
                 text=data.get('PANEL2_VALUE', '{{VALUE}}'),
                 font=FONT_KR, size_pt=32, bold=True, color=COLORS['corporate_blue'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 letter_spacing_pt=-1.0)
    _add_textbox(slide, right_x + px(24), p2_top + px(160), right_w - px(48), px(100),
                 text=data.get('PANEL2_NOTE', ''),
                 font=FONT_KR, size_pt=12, color=COLORS['charcoal'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.45, multi_paragraphs=True)

    # 시사점 바
    add_takeaway_bar(slide, 'OPEN ALM 시사점',
                     data.get('TAKEAWAY', '{{TAKEAWAY}}'))
    if page_num and total_pages:
        add_page_number(slide, page_num, total_pages)
    return slide


# ============================================================
# Body Pattern 2 — Benchmark Case + 4 Metric Tiles (v2 §7-2)
# ============================================================
def build_benchmark_tiles_slide(prs, data, logo_path=None,
                                page_num=None, total_pages=None):
    """벤치마크 사례 + 4개 KPI 타일.

    data 필드:
      - HEADER, SUBTITLE
      - INTRO: 상단 도입 단락
      - BENCH_TITLE, BENCH_BODY: 벤치마크 카드 제목 + 본문
      - TILES: [{KPI, LABEL, BODY}, x4]
      - TAKEAWAY
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    add_body_header(slide,
                    header_text=data.get('HEADER', '{{HEADER}}'),
                    subtitle=data.get('SUBTITLE'),
                    logo_path=logo_path)

    # 도입 단락 — px(64, 270, 1792, 50)
    _add_textbox(slide, px(64), px(270), px(1792), px(50),
                 text=data.get('INTRO', '{{INTRO}}'),
                 font=FONT_KR, size_pt=14, color=COLORS['charcoal'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.4)

    # 벤치마크 카드 — px(64, 340, 1792, 150)
    bench_x, bench_y, bench_w, bench_h = px(64), px(340), px(1792), px(150)
    _add_outlined_rect(slide, bench_x, bench_y, bench_w, bench_h,
                       line_color=COLORS['corporate_blue_soft'], line_width_pt=1,
                       fill_color=COLORS['surface_blue_tint'])
    _add_textbox(slide, bench_x + px(24), bench_y + px(18), px(200), px(20),
                 text='BENCHMARK CASE',
                 font=FONT_KR, size_pt=10, bold=True, color=COLORS['corporate_red'],
                 align=PP_ALIGN.LEFT, letter_spacing_pt=2.0)
    _add_textbox(slide, bench_x + px(24), bench_y + px(42),
                 bench_w - px(48), px(36),
                 text=data.get('BENCH_TITLE', '{{BENCH_TITLE}}'),
                 font=FONT_KR, size_pt=18, bold=True, color=COLORS['corporate_blue'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
    _add_textbox(slide, bench_x + px(24), bench_y + px(84),
                 bench_w - px(48), px(60),
                 text=data.get('BENCH_BODY', ''),
                 font=FONT_KR, size_pt=12, color=COLORS['charcoal'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.45, multi_paragraphs=True)

    # 4개 KPI 타일 — px(64, 520, tile-w 425, tile-h 190, gap 24)
    tiles = data.get('TILES') or [
        {'KPI': f'{{{{N{i}}}}}', 'LABEL': f'{{{{KPI{i}_LABEL}}}}', 'BODY': f'{{{{KPI{i}_BODY}}}}'} for i in range(1, 5)
    ]
    tile_x = px(64)
    tile_y = px(520)
    tile_w = px(425)
    tile_h = px(190)
    gap = px(24)
    for i, t in enumerate(tiles[:4]):
        x = tile_x + (tile_w + gap) * i
        _add_outlined_rect(slide, x, tile_y, tile_w, tile_h,
                           line_color=COLORS['hairline'], line_width_pt=1,
                           fill_color=COLORS['canvas'])
        # top accent corporate-blue 3px
        _add_filled_rect(slide, x, tile_y, tile_w, Pt(3),
                         fill_color=COLORS['corporate_blue'])
        # KPI 큰 숫자
        _add_textbox(slide, x + px(20), tile_y + px(20),
                     tile_w - px(40), px(72),
                     text=t.get('KPI', ''),
                     font=FONT_KR, size_pt=42, bold=True,
                     color=COLORS['corporate_blue'],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                     letter_spacing_pt=-1.5)
        # 라벨
        _add_textbox(slide, x + px(20), tile_y + px(100),
                     tile_w - px(40), px(26),
                     text=t.get('LABEL', ''),
                     font=FONT_KR, size_pt=13, bold=True, color=COLORS['ink'],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        # 본문
        _add_textbox(slide, x + px(20), tile_y + px(130),
                     tile_w - px(40), px(56),
                     text=t.get('BODY', ''),
                     font=FONT_KR, size_pt=11, color=COLORS['steel'],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                     line_spacing=1.4, multi_paragraphs=True)

    add_takeaway_bar(slide, 'OPEN ALM 시사점',
                     data.get('TAKEAWAY', '{{TAKEAWAY}}'))
    if page_num and total_pages:
        add_page_number(slide, page_num, total_pages)
    return slide


# ============================================================
# Body Pattern 3 — Comparison Table + Dual Callouts (v2 §7-3)
# ============================================================
def build_comparison_table_slide(prs, data, logo_path=None,
                                 page_num=None, total_pages=None):
    """전체 폭 비교 표 + 하단 좌우 콜아웃 (industry signal + security warning).

    data 필드:
      - HEADER, SUBTITLE
      - COLUMNS: [컬럼명, ...]  (4~5개 권장)
      - ROWS: [[셀1, 셀2, ...], ...] — 각 행 첫 셀이 행 라벨
      - RECOMMENDED_ROW: 추천 행 인덱스 (0-based, 옵션)
      - INDUSTRY_SIGNAL: 좌측 카드 본문
      - SECURITY_NOTE: 우측 카드 본문
      - TAKEAWAY
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    add_body_header(slide,
                    header_text=data.get('HEADER', '{{HEADER}}'),
                    subtitle=data.get('SUBTITLE'),
                    logo_path=logo_path)

    columns = data.get('COLUMNS') or ['항목', '옵션 A', '옵션 B', '옵션 C']
    rows = data.get('ROWS') or [
        ['{{ROW_LABEL_1}}', '-', '-', '-'],
        ['{{ROW_LABEL_2}}', '-', '-', '-'],
        ['{{ROW_LABEL_3}}', '-', '-', '-'],
    ]
    rec_idx = data.get('RECOMMENDED_ROW')
    if isinstance(rec_idx, int) and not (0 <= rec_idx < len(rows)):
        rec_idx = None

    table_x = px(64)
    table_y = px(270)
    table_w = px(1792)
    header_h = px(50)
    body_h = px(60)
    n_cols = max(2, min(6, len(columns)))
    col_w = table_w / n_cols

    # 헤더 행 — corporate-blue 배경 + 흰 텍스트
    _add_filled_rect(slide, table_x, table_y, table_w, header_h,
                     fill_color=COLORS['corporate_blue'])
    for c, name in enumerate(columns[:n_cols]):
        _add_textbox(slide, table_x + col_w * c, table_y, col_w, header_h,
                     text=str(name),
                     font=FONT_KR, size_pt=12, bold=True, color=COLORS['white'],
                     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    # 바디 행 — 교차 음영, 추천 행 강조
    for r_idx, row in enumerate(rows[:8]):
        y = table_y + header_h + body_h * r_idx
        is_rec = (rec_idx is not None and r_idx == rec_idx)
        fill = COLORS['surface_blue_tint'] if is_rec else (
            COLORS['surface'] if r_idx % 2 else COLORS['canvas'])
        _add_filled_rect(slide, table_x, y, table_w, body_h,
                         fill_color=fill,
                         line_color=COLORS['hairline'], line_width_pt=0.5)
        # 추천 행 좌측 빨강 룰
        if is_rec:
            _add_filled_rect(slide, table_x, y, Pt(4), body_h,
                             fill_color=COLORS['corporate_red'])
        for c in range(n_cols):
            val = row[c] if c < len(row) else ''
            _add_textbox(slide, table_x + col_w * c + px(12), y,
                         col_w - px(24), body_h,
                         text=str(val),
                         font=FONT_KR, size_pt=12,
                         color=(COLORS['corporate_blue'] if is_rec and c == 0
                                else COLORS['charcoal']),
                         bold=(is_rec and c == 0),
                         align=(PP_ALIGN.LEFT if c == 0 else PP_ALIGN.CENTER),
                         anchor=MSO_ANCHOR.MIDDLE)

    # 듀얼 콜아웃 — y=720
    ca_y = px(720)
    ca_h = px(120)
    # 좌: industry signal
    left_w = px(880)
    _add_outlined_rect(slide, px(64), ca_y, left_w, ca_h,
                       line_color=COLORS['hairline'], line_width_pt=1,
                       fill_color=COLORS['canvas'])
    _add_textbox(slide, px(80), ca_y + px(14), left_w - px(32), px(22),
                 text='INDUSTRY SIGNAL',
                 font=FONT_KR, size_pt=10, bold=True, color=COLORS['success_text'],
                 align=PP_ALIGN.LEFT, letter_spacing_pt=2.0)
    _add_textbox(slide, px(80), ca_y + px(40), left_w - px(32), ca_h - px(50),
                 text=data.get('INDUSTRY_SIGNAL', '{{INDUSTRY_SIGNAL}}'),
                 font=FONT_KR, size_pt=12, color=COLORS['charcoal'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.45, multi_paragraphs=True)

    # 우: security warning
    right_x = px(64) + left_w + px(32)
    right_w = table_w - left_w - px(32)
    _add_outlined_rect(slide, right_x, ca_y, right_w, ca_h,
                       line_color=COLORS['danger_text'], line_width_pt=1,
                       fill_color=COLORS['danger_bg'])
    _add_textbox(slide, right_x + px(16), ca_y + px(14), right_w - px(32), px(22),
                 text='규제 및 보안 고려사항',
                 font=FONT_KR, size_pt=10, bold=True, color=COLORS['danger_text'],
                 align=PP_ALIGN.LEFT, letter_spacing_pt=2.0)
    _add_textbox(slide, right_x + px(16), ca_y + px(40), right_w - px(32), ca_h - px(50),
                 text=data.get('SECURITY_NOTE', '{{SECURITY_NOTE}}'),
                 font=FONT_KR, size_pt=12, color=COLORS['danger_text'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.45, multi_paragraphs=True)

    add_takeaway_bar(slide, 'OPEN ALM 시사점',
                     data.get('TAKEAWAY', '{{TAKEAWAY}}'))
    if page_num and total_pages:
        add_page_number(slide, page_num, total_pages)
    return slide


# ============================================================
# Body Pattern 4 — 4-Step Framework (v2 §7-4) — 결론 슬라이드용
# ============================================================
def build_4step_framework_slide(prs, data, logo_path=None,
                                page_num=None, total_pages=None):
    """현황→문제점→AI해결→기대효과 4단계 내러티브.

    data 필드:
      - HEADER, SUBTITLE
      - STEPS: [{LABEL, BODY}, x4]  순서대로 [현황, 문제점, AI 해결, 기대효과]
      - CONCLUSION_TITLE, CONCLUSION_BODY: 하단 결론 블록 (corporate-blue 배경)
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)
    add_body_header(slide,
                    header_text=data.get('HEADER', '결론'),
                    subtitle=data.get('SUBTITLE'),
                    logo_path=logo_path)

    steps = data.get('STEPS') or [
        {'LABEL': '현황', 'BODY': '{{STEP1_BODY}}'},
        {'LABEL': '문제점', 'BODY': '{{STEP2_BODY}}'},
        {'LABEL': 'AI 해결책', 'BODY': '{{STEP3_BODY}}'},
        {'LABEL': '기대 효과', 'BODY': '{{STEP4_BODY}}'},
    ]
    badge_colors = [COLORS['steel'], COLORS['danger_text'],
                    COLORS['corporate_blue'], COLORS['success_text']]

    # 4개 가로 띠 — px(64, 270, 1792, 100), gap 12
    band_x = px(64)
    band_y = px(270)
    band_w = px(1792)
    band_h = px(100)
    gap = px(12)
    for i, step in enumerate(steps[:4]):
        y = band_y + (band_h + gap) * i
        fill = COLORS['surface_blue_tint'] if i == 2 else COLORS['surface']
        _add_filled_rect(slide, band_x, y, band_w, band_h, fill_color=fill)
        # 원 배지
        badge_d = px(48)
        bx = band_x + px(20)
        by = y + (band_h - badge_d) / 2
        _add_circle(slide, bx, by, badge_d, fill_color=badge_colors[i % 4])
        _add_textbox(slide, bx, by, badge_d, badge_d,
                     text=str(i + 1),
                     font=FONT_KR, size_pt=16, bold=True, color=COLORS['white'],
                     align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        # 라벨 + 본문
        text_x = bx + badge_d + px(20)
        _add_textbox(slide, text_x, y + px(16), px(300), px(28),
                     text=step.get('LABEL', ''),
                     font=FONT_KR, size_pt=17, bold=True,
                     color=badge_colors[i % 4],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        _add_textbox(slide, text_x, y + px(48), band_w - px(220), px(50),
                     text=step.get('BODY', ''),
                     font=FONT_KR, size_pt=13, color=COLORS['charcoal'],
                     align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                     line_spacing=1.4, multi_paragraphs=True)

    # 결론 블록 — px(64, 730, 1792, 210) corporate-blue 배경
    cb_x, cb_y, cb_w, cb_h = px(64), px(730), px(1792), px(210)
    _add_filled_rect(slide, cb_x, cb_y, cb_w, cb_h,
                     fill_color=COLORS['corporate_blue'])
    # sunburst arc — 우측 하단 (corporate-red oval + corporate-blue oval 겹침)
    _add_circle(slide, cb_x + cb_w - px(160), cb_y + cb_h - px(160),
                px(180), fill_color=COLORS['corporate_red'])
    _add_circle(slide, cb_x + cb_w - px(120), cb_y + cb_h - px(120),
                px(130), fill_color=COLORS['corporate_blue'])
    # 제목
    _add_textbox(slide, cb_x + px(32), cb_y + px(24), cb_w - px(220), px(36),
                 text=data.get('CONCLUSION_TITLE', '{{CONCLUSION_TITLE}}'),
                 font=FONT_KR, size_pt=16, bold=True, color=COLORS['white'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
    # 본문
    _add_textbox(slide, cb_x + px(32), cb_y + px(72), cb_w - px(220), cb_h - px(96),
                 text=data.get('CONCLUSION_BODY', '{{CONCLUSION_BODY}}'),
                 font=FONT_KR, size_pt=13, color=COLORS['white'],
                 align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
                 line_spacing=1.5, multi_paragraphs=True)

    if page_num and total_pages:
        add_page_number(slide, page_num, total_pages)
    return slide


# ============================================================
# Dispatcher
# ============================================================
LAYOUT_BUILDERS = {
    'cover':              build_cover_slide,
    '2col-comparison':    build_2col_comparison_slide,
    'benchmark-tiles':    build_benchmark_tiles_slide,
    'comparison-table':   build_comparison_table_slide,
    '4step-framework':    build_4step_framework_slide,
}


def build_slide(prs, layout_type, data, logo_path=None,
                page_num=None, total_pages=None):
    """LLM 응답 기반으로 슬라이드 하나 추가. layout_type 잘못되면 2col-comparison fallback."""
    builder = LAYOUT_BUILDERS.get(layout_type, build_2col_comparison_slide)
    # cover 는 page_num/total_pages 안 받음
    if layout_type == 'cover' or builder is build_cover_slide:
        return builder(prs, data, logo_path=logo_path)
    return builder(prs, data, logo_path=logo_path,
                   page_num=page_num, total_pages=total_pages)
