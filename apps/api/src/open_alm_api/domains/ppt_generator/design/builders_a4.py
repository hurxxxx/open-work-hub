# -*- coding: utf-8 -*-
"""
pptgen2_design_a4.py - Open ALM A4 경영진 보고 양식 v3.5 (pptgen2 A4 패밀리)

캔버스: A4 landscape (27.517 × 19.05 cm)
폰트: Pretendard (Pretendard M) — Arial Bold 예외 4곳
공통 chrome:
  - 표지: 좌상 워터마크 + Confidential 배지 + 우하 로고
  - 본문: ▣ 제목 + 분할 가로선 (gap 안 로고) + 우상 날짜 + 사선 DCC 워터마크 + 하단 저작권

구현 단순화:
  - .md §5의 master/layout migration 패턴 대신 일반 슬라이드에 직접 chrome 그림
  - 시각 결과는 동일, 코드 훨씬 단순. python-pptx 안정성 확보.
"""
from datetime import datetime
from pptx.util import Cm, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from lxml import etree


# ============================================================
# 캔버스 — A4 landscape
# ============================================================
SLIDE_W_CM = 27.517
SLIDE_H_CM = 19.05
SLIDE_W = Cm(SLIDE_W_CM)
SLIDE_H = Cm(SLIDE_H_CM)


# ============================================================
# 색상 토큰 (§10)
# ============================================================
COLORS = {
    # 브랜드 코어
    'brand_navy':       RGBColor(0x1B, 0x2C, 0x6B),
    'brand_red':        RGBColor(0xD7, 0x26, 0x1E),

    # 표지 전용
    'cover_title':      RGBColor(0x33, 0x33, 0x33),
    'cover_rule':       RGBColor(0x80, 0x80, 0x80),
    'cover_watermark':  RGBColor(0xE5, 0xE5, 0xE5),
    'ver_label':        RGBColor(0x66, 0x66, 0x66),

    # 본문 전용
    'body_rule':        RGBColor(0x80, 0x80, 0x80),
    'body_title':       RGBColor(0x1A, 0x1A, 0x1A),
    'dcc_watermark':    RGBColor(0xF0, 0xE0, 0xE0),
    'copyright':        RGBColor(0xC8, 0xC8, 0xC8),
    'date_text':        RGBColor(0x00, 0x00, 0x00),

    # 표면 / 헤어라인
    'canvas':           RGBColor(0xFF, 0xFF, 0xFF),
    'surface':          RGBColor(0xF5, 0xF6, 0xF8),
    'surface_soft':     RGBColor(0xFA, 0xFA, 0xFB),
    'hairline':         RGBColor(0xE2, 0xE4, 0xE9),
    'hairline_soft':    RGBColor(0xEE, 0xEF, 0xF2),
    'cool_mist':        RGBColor(0xEA, 0xEE, 0xF5),
    'progress_track':   RGBColor(0xE8, 0xEC, 0xF2),

    # 상태 색 (스코어카드 / 회의록)
    'amber':            RGBColor(0xD7, 0xB0, 0x17),
    'green':            RGBColor(0x2D, 0x86, 0x59),
    'navy_subtle':      RGBColor(0xA8, 0xB4, 0xD9),
    'navy_text':        RGBColor(0xD9, 0xDE, 0xEC),

    # 텍스트 스케일
    'charcoal':         RGBColor(0x2A, 0x2E, 0x36),
    'slate':            RGBColor(0x4A, 0x51, 0x60),
    'steel':            RGBColor(0x6B, 0x72, 0x80),
    'stone':            RGBColor(0x9C, 0xA3, 0xAF),

    'white':            RGBColor(0xFF, 0xFF, 0xFF),
}


# ============================================================
# 폰트 (§4)
# ============================================================
# PowerPoint(GDI) 등록명은 'Pretendard'(공백 포함). latin/ea/cs 모두 이 이름으로 통일해
# 폰트박스에 'Pretendard'으로 표시되게 한다. 굵기는 bold 속성으로 처리(별도 'B' 폰트명 미사용).
FONT_KR = 'Pretendard'        # Pretendard (PowerPoint 등록명)
FONT_KR_ALT = 'Pretendard'    # ea(한글) typeface
FONT_KR_BOLD = 'Pretendard'   # 굵은 텍스트도 동일 폰트명 + bold 속성
FONT_EN = 'Arial'


# ============================================================
# §3 Fixed Strings — 절대 변경 금지
# ============================================================
COVER_WATERMARK_TEXT = 'Open ALM  Confidential Documents'  # "Control" "Confidential" 사이 더블 스페이스
CONFIDENTIAL_BADGE_TEXT = 'Confidential'
DCC_WATERMARK_TEXT = 'DCC Confidential Documents'
COPYRIGHT_TEXT = (
    'Open ALM : This information is exclusive property of '
    'Open ALM. Without their consent, it may not be required or given to '
    'third parties.'
)


# ============================================================
# §6.3 — 표지 제목 한 줄 fit validator
# ============================================================
TITLE_MAX_WIDTH_CM = 17.50

def title_visual_width_cm(s):
    total = 0.0
    for ch in s:
        if '가' <= ch <= '힣':
            total += 1.10
        elif ch.isspace():
            total += 0.40
        elif ch.isascii() and ch.isalnum():
            total += 0.55
        else:
            total += 0.50
    return total


def fit_title_to_box(text, box_cm, base_pt=25, min_pt=15):
    """제목을 한 줄 박스(box_cm)에 맞춘다.
    1) base_pt 에서 넘치면 폭 비례로 폰트 축소(min_pt 하한).
    2) min_pt 에서도 넘치면 글자수 제한(… 말줄임)으로 박스 안에 강제로 넣는다.
    반환: (표시 텍스트, 폰트 pt)
    """
    text = str(text or "")
    vw32 = title_visual_width_cm(text)
    if vw32 <= 0:
        return text, base_pt
    pt = base_pt
    if vw32 * (base_pt / 32.0) > box_cm:
        pt = max(min_pt, int(32.0 * box_cm / vw32))
    if vw32 * (pt / 32.0) > box_cm:  # 하한에서도 넘침 → 말줄임
        allowed_vw32 = box_cm * 32.0 / pt - title_visual_width_cm("…")
        acc, out = 0.0, []
        for ch in text:
            cw = title_visual_width_cm(ch)
            if acc + cw > allowed_vw32:
                break
            acc += cw
            out.append(ch)
        text = "".join(out).rstrip() + "…"
    return text, pt


# ▣ 헤더 제목의 가용 텍스트 폭(cm). 박스 폭에서 ▣ 마커 여백(1.20cm)을 빼고, ×1.10 실제
# 렌더 보정으로 나눈다. 네이티브 헤더(apply_body_chrome)와 HTML 헤더(corporate_frame)가
# 같은 규칙을 쓰도록 한 곳에 둔다 — 박스 폭/로고 위치 변경 시 여기만 고치면 양쪽이 일치.
_TITLE_MARKER_PAD_CM = 1.20
_TITLE_RENDER_FACTOR = 1.10


def title_text_width_cm(box_cm: float) -> float:
    """▣ 제목 박스 폭(cm) → 말줄임 판정에 쓰는 가용 텍스트 폭(cm)."""
    return (box_cm - _TITLE_MARKER_PAD_CM) / _TITLE_RENDER_FACTOR


# ============================================================
# §9.1 (d) — 그림자 제거
# ============================================================
def _kill_shadow(shape):
    """모든 도형의 자동 그림자 제거."""
    try:
        sp_el = shape._element
        spPr = sp_el.find('.//' + qn('p:spPr'))
        if spPr is None:
            return
        for tag in ('a:effectLst', 'a:effectDag'):
            for existing in spPr.findall(qn(tag)):
                spPr.remove(existing)
        effect_lst = spPr.makeelement(qn('a:effectLst'), {})
        spPr.append(effect_lst)
    except Exception:
        pass


def _kill_chart_shadows(chart):
    try:
        chart_el = chart._chartSpace
        nsmap = {
            'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
            'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
        }
        for spPr in chart_el.findall('.//c:spPr', nsmap):
            for tag in ('a:effectLst', 'a:effectDag'):
                for existing in spPr.findall(qn(tag)):
                    spPr.remove(existing)
            effect_lst = spPr.makeelement(qn('a:effectLst'), {})
            spPr.append(effect_lst)
    except Exception:
        pass


# ============================================================
# §4 — 폰트 강제 적용 (rPr 자식 순서: solidFill → latin → ea → cs)
# ============================================================
def _set_run_font(run, name=FONT_KR, size_pt=10, bold=False, color=None):
    run.font.name = name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color

    rPr = run._r.get_or_add_rPr()
    # 기존 ea/cs 제거
    for tag in ('ea', 'cs'):
        old = rPr.find(qn(f'a:{tag}'))
        if old is not None:
            rPr.remove(old)
    # ea (East Asian) = 한국어 fallback
    ea = etree.SubElement(rPr, qn('a:ea'))
    ea.set('typeface', FONT_KR_ALT)  # PowerPoint 표시용 한글 이름
    # cs (Complex Script)
    cs = etree.SubElement(rPr, qn('a:cs'))
    cs.set('typeface', name)


def _to_float(v):
    """LLM 이 '1,284' / '1284억' / '-5.0%' 처럼 콤마·단위가 섞인 문자열로 숫자를 보내도
    선행 숫자 부분만 안전하게 float 로 추출. 실패 시 None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace(',', '')
    num = ''
    for ch in s:
        if ch.isdigit() or ch in '.-+':
            num += ch
        elif num:
            break
    try:
        return float(num)
    except ValueError:
        return None


def _add_text(slide, left, top, width, height, text, *,
              font=FONT_KR, size_pt=10, bold=False, color=None,
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
              line_spacing=None, multi=False, margins=True, wrap=True):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame
    tf.word_wrap = wrap
    if not margins:
        tf.margin_left = Emu(0)
        tf.margin_right = Emu(0)
        tf.margin_top = Emu(0)
        tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor

    # LLM 이 문자열 기대 필드를 dict/숫자/리스트로 보내도 슬라이드 전체가 죽지 않도록 강제 변환.
    text = '' if text is None else str(text)
    lines = text.split('\n') if multi else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if line_spacing is not None:
            p.line_spacing = line_spacing
        run = p.add_run()
        run.text = line
        _set_run_font(run, name=font, size_pt=size_pt, bold=bold, color=color)
    return tb


def _add_rect(slide, left, top, width, height, *,
              fill=None, line_color=None, line_pt=0):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(line_pt)
    _kill_shadow(shape)
    return shape


def _add_rounded_rect(slide, left, top, width, height, *,
                     fill=None, line_color=None, line_pt=0, adj=0.18):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    try:
        shape.adjustments[0] = adj
    except Exception:
        pass
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(line_pt)
    _kill_shadow(shape)
    return shape


def _rotate_shape(shape, degrees):
    """도형 회전 (-30° 사선 DCC 워터마크용)."""
    sp = shape._element
    spPr = sp.find('.//' + qn('p:spPr'))
    if spPr is None:
        return
    xfrm = spPr.find(qn('a:xfrm'))
    if xfrm is None:
        # python-pptx가 add_shape 시 xfrm 자동 생성하지만 안전장치
        xfrm = spPr.makeelement(qn('a:xfrm'), {})
        spPr.insert(0, xfrm)
    xfrm.set('rot', str(int(degrees * 60000)))


# ============================================================
# §8.2 Case B — 검정 배경 PNG → 투명 PNG 자동 변환
# ============================================================
def ensure_transparent_logo(src_path, dst_path=None):
    """입력 PNG가 검정 배경이면 투명 처리 후 dst_path에 저장. 이미 투명이면 그대로 반환."""
    from PIL import Image
    if dst_path is None:
        dst_path = src_path
    src = Image.open(src_path).convert('RGBA')
    pixels = src.load()
    w, h = src.size
    # 코너 픽셀들로 배경 색상 추정
    corners = [pixels[0, 0], pixels[w - 1, 0], pixels[0, h - 1], pixels[w - 1, h - 1]]
    is_dark_bg = all(c[0] < 40 and c[1] < 40 and c[2] < 40 for c in corners)
    if not is_dark_bg:
        # 이미 적절히 처리됨 — 변환 없이 반환
        if src_path != dst_path:
            src.save(dst_path, 'PNG')
        return dst_path
    # 검정 픽셀 투명화
    THRESHOLD = 40
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r < THRESHOLD and g < THRESHOLD and b < THRESHOLD:
                pixels[x, y] = (0, 0, 0, 0)
    src.save(dst_path, 'PNG')
    return dst_path


# ============================================================
# 공통 chrome — 마스터 (Confidential 배지)
# ============================================================
def add_confidential_badge(slide):
    """모든 슬라이드(표지+본문) 우상단 Confidential 배지.

    좌표: left = SLIDE_W - 3.60 - 0.30, top = 0.30, w = 3.60, h = 0.78
    """
    badge_w = Cm(2.90)
    badge_h = Cm(0.66)
    badge_left = SLIDE_W - badge_w - Cm(0.30)
    badge_top = Cm(0.30)

    _add_rounded_rect(slide, badge_left, badge_top, badge_w, badge_h,
                      fill=COLORS['white'], line_color=COLORS['brand_red'],
                      line_pt=1.25, adj=0.18)
    _add_text(slide, badge_left, badge_top, badge_w, badge_h,
              CONFIDENTIAL_BADGE_TEXT,
              font=FONT_EN, size_pt=12, bold=True, color=COLORS['brand_red'],
              align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, wrap=False,
              margins=False)


# ============================================================
# 공통 chrome — 본문 layout
# ============================================================
def add_dcc_watermark_to_master(prs):
    """DCC 사선 워터마크(-30°)를 슬라이드 마스터에 1회 추가.

    마스터 도형은 모든 슬라이드의 배경(본문 콘텐츠 뒤)으로 상속되므로, 본문마다 그리던
    워터마크를 마스터로 올리면 슬라이드에서 선택·이동되지 않는 진짜 워터마크가 된다.
    표지처럼 워터마크가 없어야 하는 슬라이드는 ``set_show_master_shapes(slide, False)`` 로 가린다.

    python-pptx 의 MasterShapes 는 add_textbox 를 지원하지 않으므로 <p:sp> 를 직접 만들어
    마스터 spTree 에 append 한다. 좌표·회전·색상은 apply_body_chrome 의 L4 와 동일.
    """
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls

    color = str(COLORS['dcc_watermark'])  # 'F0E0E0'
    off_x, off_y = int(Cm(4.00)), int(Cm(8.60))
    ext_cx, ext_cy = int(Cm(20.00)), int(Cm(1.80))
    rot = int(-30 * 60000)  # -30° (60000 EMU/도)
    xml = (
        f'<p:sp {nsdecls("p", "a")}>'
        '<p:nvSpPr>'
        '<p:cNvPr id="900" name="DCC Watermark"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/>'
        '</p:nvSpPr>'
        '<p:spPr>'
        f'<a:xfrm rot="{rot}"><a:off x="{off_x}" y="{off_y}"/>'
        f'<a:ext cx="{ext_cx}" cy="{ext_cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>'
        '</p:spPr>'
        '<p:txBody>'
        '<a:bodyPr wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="ctr"/>'
        '<a:lstStyle/>'
        '<a:p><a:pPr algn="ctr"/><a:r>'
        f'<a:rPr lang="en-US" sz="3200" b="1">'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:latin typeface="{FONT_EN}"/></a:rPr>'
        f'<a:t>{DCC_WATERMARK_TEXT}</a:t>'
        '</a:r></a:p>'
        '</p:txBody>'
        '</p:sp>'
    )
    sp = parse_xml(xml)
    prs.slide_masters[0].element.spTree.append(sp)
    return sp


def add_copyright_footer_to_master(prs):
    """하단 영문 저작권(L5)을 슬라이드 마스터에 1회 추가 — DCC 워터마크와 동일 원리.

    마스터 도형은 모든 본문 슬라이드가 배경으로 상속하므로, 본문마다 그리던 저작권 문구를 마스터로
    올리면 PowerPoint 에서 **선택·이동/편집되지 않는 진짜 워터마크**가 된다. 본문 chrome 은
    ``apply_body_chrome(footer=False)`` 로 이 문구를 그리지 않고 마스터에 위임한다. 표지처럼 없어야
    하는 슬라이드는 ``set_show_master_shapes(slide, False)`` 로 가린다(DCC 워터마크와 함께 숨겨짐).

    좌표·색상·폰트는 apply_body_chrome 의 L5 와 동일(x0.80 y18.50 w25.92 h0.45, Arial 7pt #C8C8C8).
    """
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls

    color = str(COLORS['copyright'])  # 'C8C8C8'
    off_x, off_y = int(Cm(0.80)), int(Cm(18.50))
    ext_cx, ext_cy = int(Cm(25.92)), int(Cm(0.45))
    text = (
        COPYRIGHT_TEXT.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    )
    xml = (
        f'<p:sp {nsdecls("p", "a")}>'
        '<p:nvSpPr>'
        '<p:cNvPr id="901" name="Copyright Footer"/>'
        '<p:cNvSpPr txBox="1"/><p:nvPr/>'
        '</p:nvSpPr>'
        '<p:spPr>'
        f'<a:xfrm><a:off x="{off_x}" y="{off_y}"/>'
        f'<a:ext cx="{ext_cx}" cy="{ext_cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/>'
        '</p:spPr>'
        '<p:txBody>'
        '<a:bodyPr wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="ctr"/>'
        '<a:lstStyle/>'
        '<a:p><a:pPr algn="l"/><a:r>'
        f'<a:rPr lang="en-US" sz="700" b="0">'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
        f'<a:latin typeface="{FONT_EN}"/></a:rPr>'
        f'<a:t>{text}</a:t>'
        '</a:r></a:p>'
        '</p:txBody>'
        '</p:sp>'
    )
    sp = parse_xml(xml)
    prs.slide_masters[0].element.spTree.append(sp)
    return sp


def set_show_master_shapes(slide, show):
    """슬라이드의 마스터 도형 상속 on/off (<p:sld showMasterSp="0|1">)."""
    slide._element.set('showMasterSp', '1' if show else '0')


def apply_body_chrome(slide, header_title, logo_path=None, date_str=None, *,
                      watermark=True, footer=True, title_fixed_pt=None):
    """본문 슬라이드 chrome — §7 사양 그대로.

    포함:
      - S1: ▣ 슬라이드 제목 (좌상)
      - L1: 날짜 (우상, 로고 오른쪽)
      - L2a: 가로선 좌 segment (0 ~ 22.40)
      - L2b: 가로선 우 segment (24.86 ~ slide_end)
      - L3: OPEN ALM 로고 (gap 안)
      - L4: 사선 DCC 워터마크 (-30°) — ``watermark=False`` 면 그리지 않음(마스터에 위임).
      - L5: 하단 영문 저작권 — ``footer=False`` 면 그리지 않음(마스터에 위임).
      + Confidential 배지 (master)

    title_fixed_pt 를 주면 자동 축소 없이 그 크기로 제목을 고정한다(예: Open ALM 덱 24pt).
    """
    # 날짜는 항상 오늘 기준 (LLM 이 넣은 DATE 는 무시)
    date_str = datetime.now().strftime('%Y.%m.%d')

    # S1 — ▣ 제목 (PretendardM Bold). 기본은 24pt 에서 길면 자동 축소하지만,
    # title_fixed_pt 가 주어지면 축소 없이 그 크기로 고정한다.
    # ▣ 중복 제거 — LLM 이 프롬프트를 어기고 HEADER에 ▣을 미리 붙여 보내는 경우 방어.
    clean_header = str(header_title or '').lstrip()
    while clean_header.startswith('▣'):
        clean_header = clean_header[1:].lstrip()
    if title_fixed_pt:
        # 로고(x=22.50)/Confidential 배지 앞에서 끝나도록 박스를 제한.
        _TITLE_BOX_W = 21.50  # cm
        title_pt = title_fixed_pt
        # 폰트는 고정(축소 없음). 폭을 넘기면 글자수 제한(… 말줄임)으로 우측 요소 침범 방지.
        clean_header, _ = fit_title_to_box(
            clean_header, title_text_width_cm(_TITLE_BOX_W),
            base_pt=title_pt, min_pt=title_pt,
        )
    else:
        _TITLE_BOX_W = 21.00  # cm
        # 표지처럼 24pt 기본. 제목은 프롬프트에서 짧게 생성됨. 혹시 길면 "…" 없이 살짝만 축소(최소 16pt).
        # ×1.10 실제 렌더 보정 + ▣ 여백 1.20cm 고려 → 옆으로 넘치지 않게.
        _box_txt = _TITLE_BOX_W - 1.20
        title_pt = 24
        _w_at_base = title_visual_width_cm(clean_header) * (title_pt / 32.0) * 1.10
        if _w_at_base > _box_txt:
            title_pt = max(16, int(title_pt * _box_txt / _w_at_base))
    title_text = f'▣ {clean_header}'
    _add_text(slide, Cm(0.70), Cm(0.30), Cm(_TITLE_BOX_W), Cm(1.30),
              title_text,
              font=FONT_KR_BOLD, size_pt=title_pt, bold=True, color=COLORS['body_title'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)

    # L1 — 날짜 (우상, 우측 정렬, Reg 10pt #000, 로고 오른쪽). 박스 넓히고 내부 여백 제거 +
    # wrap=False 로 한 줄 보장. (우측 끝에서 0.5cm 더 왼쪽으로)
    _add_text(slide, Cm(24.50), Cm(1.30), Cm(2.45), Cm(0.60),
              date_str,
              font=FONT_KR, size_pt=10, bold=False, color=COLORS['date_text'],
              align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)

    # L2a — 가로선 좌 segment (0 ~ 22.40, #808080)
    _add_rect(slide, Cm(0), Cm(1.85), Cm(22.40), Cm(0.106),
              fill=COLORS['body_rule'])

    # L2b — 가로선 우 segment (24.86 ~ slide_end)
    _add_rect(slide, Cm(24.86), Cm(1.85), Cm(SLIDE_W_CM - 24.86), Cm(0.106),
              fill=COLORS['body_rule'])

    # L3 — OPEN ALM 로고 (gap 안: x=22.50, h=0.40, w 자동, top=1.65)
    if logo_path:
        try:
            slide.shapes.add_picture(logo_path, Cm(22.50), Cm(1.65), height=Cm(0.40))
        except Exception:
            pass

    # L4 — 사선 DCC 워터마크 (Arial Bold 32pt #F0E0E0, rotate -30°).
    # watermark=False 면 마스터(add_dcc_watermark_to_master)가 배경으로 그리므로 생략.
    if watermark:
        dcc = _add_text(slide, Cm(4.00), Cm(8.60), Cm(20.00), Cm(1.80),
                        DCC_WATERMARK_TEXT,
                        font=FONT_EN, size_pt=32, bold=True, color=COLORS['dcc_watermark'],
                        align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        _rotate_shape(dcc, -30)

    # L5 — 하단 영문 저작권 (Arial 7pt #C8C8C8).
    # footer=False 면 마스터(add_copyright_footer_to_master)가 배경으로 그리므로 생략.
    if footer:
        _add_text(slide, Cm(0.80), Cm(18.50), Cm(25.92), Cm(0.45),
                  COPYRIGHT_TEXT,
                  font=FONT_EN, size_pt=7, bold=False, color=COLORS['copyright'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # Confidential 배지 (master 역할)
    add_confidential_badge(slide)


# ============================================================
# Layout 1 — A4 표지 (§6)
# ============================================================
def build_a4_cover_slide(prs, data, logo_path=None):
    """A4 표지 슬라이드.

    data 필드:
      - TITLE: 표지 제목 (한 줄 fit 검증)
      - DATE: YYYY.MM.DD (옵션, 빈값이면 오늘)
      - AUTHOR: 작성자 (기본 'Open ALM')
      - VERSION: Ver 라벨 (기본 'Ver 1')
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    title = data.get('TITLE', '제목 미정')
    # 날짜는 항상 오늘 기준 (LLM 이 넣은 DATE 는 무시)
    date_str = datetime.now().strftime('%Y.%m.%d')
    author = data.get('AUTHOR', 'Open ALM')
    version = data.get('VERSION', 'Ver 1')

    # title fit validator (warning만)
    w = title_visual_width_cm(title)
    if w > TITLE_MAX_WIDTH_CM:
        print(f'[A4 cover] WARN Title likely wraps: {w:.1f}cm > {TITLE_MAX_WIDTH_CM}cm')
    else:
        print(f'[A4 cover] OK Title fits one line: {w:.1f}cm')

    # 1) 좌상 워터마크 (Arial Bold 20pt #E5E5E5)
    _add_text(slide, Cm(0.80), Cm(0.45), Cm(22.00), Cm(0.90),
              COVER_WATERMARK_TEXT,
              font=FONT_EN, size_pt=20, bold=True, color=COLORS['cover_watermark'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # 2+2a) Confidential 배지 (master)
    add_confidential_badge(slide)

    # 3) 표지 제목 (PretendardM Bold 24pt #333333) — 24pt 기본.
    #    제목은 프롬프트에서 짧게 생성됨. 혹시 길면 "…" 없이 살짝만 축소(최소 17pt). ×1.10 실제 렌더 보정.
    _TITLE_BOX_CM = 18.30
    title_pt = 24
    _w_at_base = w * (title_pt / 32.0) * 1.10
    if _w_at_base > _TITLE_BOX_CM:
        title_pt = max(17, int(title_pt * _TITLE_BOX_CM / _w_at_base))
    _add_text(slide, Cm(1.50), Cm(6.20), Cm(_TITLE_BOX_CM), Cm(1.80),
              title,
              font=FONT_KR_BOLD, size_pt=title_pt, bold=True, color=COLORS['cover_title'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=False)

    # 4) 긴 회색 밑줄 (2pt #808080)
    _add_rect(slide, Cm(1.50), Cm(7.95), Cm(18.30), Cm(0.071),
              fill=COLORS['cover_rule'])

    # 5) 짧은 회색 밑줄
    _add_rect(slide, Cm(20.20), Cm(7.95), Cm(5.20), Cm(0.071),
              fill=COLORS['cover_rule'])

    # 6) Ver 라벨 (PretendardM Reg 16pt #666666, anchor BOTTOM, align CENTER)
    _add_text(slide, Cm(20.20), Cm(6.90), Cm(5.20), Cm(0.90),
              version,
              font=FONT_KR, size_pt=16, bold=False, color=COLORS['ver_label'],
              align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM)

    # 7) 날짜 (PretendardM Bold 22pt #333333)
    _add_text(slide, Cm(1.50), Cm(11.90), Cm(15.00), Cm(1.20),
              date_str,
              font=FONT_KR_BOLD, size_pt=22, bold=True, color=COLORS['cover_title'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # 8) 작성자 (PretendardM Bold 32pt #333333)
    _add_text(slide, Cm(1.50), Cm(14.20), Cm(20.00), Cm(1.80),
              author,
              font=FONT_KR_BOLD, size_pt=32, bold=True, color=COLORS['cover_title'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # 9) 우하단 로고 (투명 PNG, h=0.69, w=aspect 5.66)
    if logo_path:
        try:
            logo_h = Cm(0.69)
            logo_w = Cm(0.69 * 5.66)
            slide.shapes.add_picture(logo_path,
                                     SLIDE_W - logo_w - Cm(0.30),
                                     SLIDE_H - Cm(0.69) - Cm(0.30),
                                     width=logo_w, height=logo_h)
        except Exception:
            pass

    return slide


# ============================================================
# Layout 2 — Executive Summary 본문 (§11)
# 3 섹션: KPI 4카드 + 핵심요약/차트 + 이슈/액션
# ============================================================
def build_a4_exec_kpi_slide(prs, data, logo_path=None):
    """KPI 대시보드 본문 슬라이드.

    data 필드:
      - HEADER: ▣ 좌상 제목 (예: '2026년 05월 경영회의 보고서')
      - DATE: YYYY.MM.DD (옵션)
      - KPIS: [{"label","value","unit","delta","up","vs"}, x4]
      - SUMMARY_TITLE: "핵심 요약" 헤더 (기본값)
      - SUMMARY_ITEMS: ["불릿1", "불릿2", ...]
      - CHART_TITLE: "월별 매출 추이 (억원)" 같은 차트 헤더
      - CHART_LABELS: ["12월","01월",...]
      - CHART_VALUES: [1102, 1085, ...]
      - ISSUES_TITLE: "주요 이슈" 헤더
      - ISSUES: [{"sev":"HIGH","title":"...","desc":"..."}, x3]
      - ACTIONS_TITLE: "차월 액션 아이템"
      - ACTIONS: [{"num":"01","title":"...","owner":"...","desc":"..."}, x3]
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    # 공통 chrome
    apply_body_chrome(slide,
                      header_title=data.get('HEADER', '경영회의 보고서'),
                      logo_path=logo_path,
                      date_str=data.get('DATE'))

    # 본문 영역
    BODY_X = Cm(0.80)
    BODY_W_CM = SLIDE_W_CM - 0.80 * 2  # 25.917

    # ─────────────────────────────────────────────────────
    # Section A — KPI 4 카드 (y=2.60 ~ 5.90, height 3.30)
    # ─────────────────────────────────────────────────────
    KPI_TOP_CM = 2.60
    KPI_H_CM = 3.30
    GAP_CM = 0.30
    n_kpi = 4
    card_w_cm = (BODY_W_CM - GAP_CM * (n_kpi - 1)) / n_kpi  # ≈ 6.10

    kpis = data.get('KPIS', [])
    for i in range(n_kpi):
        kpi = kpis[i] if i < len(kpis) else {
            'label': f'KPI {i+1}', 'value': '—', 'unit': '', 'delta': '', 'up': True, 'vs': ''
        }
        card_x = Cm(0.80 + (card_w_cm + GAP_CM) * i)
        card_y = Cm(KPI_TOP_CM)
        card_w = Cm(card_w_cm)
        card_h = Cm(KPI_H_CM)

        # 카드 surface
        _add_rect(slide, card_x, card_y, card_w, card_h,
                  fill=COLORS['surface'], line_color=COLORS['hairline'], line_pt=0.5)

        # 상단 액센트 바 (Navy, h=0.10)
        _add_rect(slide, card_x, card_y, card_w, Cm(0.10),
                  fill=COLORS['brand_navy'])

        INNER_OFFSET = 0.20
        # 라벨 (12pt #6B7280 Steel)
        _add_text(slide, card_x, Cm(KPI_TOP_CM + 0.30 + INNER_OFFSET), card_w, Cm(0.50),
                  kpi.get('label', ''),
                  font=FONT_KR, size_pt=12, bold=False, color=COLORS['steel'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

        # 값 (32pt Bold #2A2E36 Charcoal) + 단위 (13pt #4A5160)
        # 한 textbox에 multi-run 으로 합쳐 표시
        tb = slide.shapes.add_textbox(card_x, Cm(KPI_TOP_CM + 0.85 + INNER_OFFSET),
                                       card_w, Cm(1.10))
        tf = tb.text_frame
        tf.word_wrap = False
        tf.margin_left = Emu(0)
        tf.margin_right = Emu(0)
        tf.margin_top = Emu(0)
        tf.margin_bottom = Emu(0)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run_v = p.add_run()
        run_v.text = str(kpi.get('value', ''))
        _set_run_font(run_v, name=FONT_KR_BOLD, size_pt=32, bold=True, color=COLORS['charcoal'])
        unit_text = kpi.get('unit', '')
        if unit_text:
            run_u = p.add_run()
            run_u.text = ' ' + str(unit_text)
            _set_run_font(run_u, name=FONT_KR, size_pt=13, bold=False, color=COLORS['slate'])

        # Delta (13pt Bold) — up=Navy / down=Red
        delta_color = COLORS['brand_navy'] if kpi.get('up', True) else COLORS['brand_red']
        _add_text(slide, card_x, Cm(KPI_TOP_CM + 2.05 + INNER_OFFSET), card_w, Cm(0.45),
                  kpi.get('delta', ''),
                  font=FONT_KR_BOLD, size_pt=13, bold=True, color=delta_color,
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

        # vs. 전월 (9pt #9CA3AF Stone)
        _add_text(slide, card_x, Cm(KPI_TOP_CM + 2.50 + INNER_OFFSET), card_w, Cm(0.40),
                  kpi.get('vs', ''),
                  font=FONT_KR, size_pt=9, bold=False, color=COLORS['stone'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    # ─────────────────────────────────────────────────────
    # Section B — 핵심 요약 + 차트 (y=6.30 ~ 11.90, h=5.60)
    # ─────────────────────────────────────────────────────
    SEC_B_TOP_CM = 6.30
    SEC_B_H_CM = 5.60
    LEFT_W_CM = 13.50
    RIGHT_W_CM = BODY_W_CM - LEFT_W_CM - 0.40  # ≈ 12.02
    HEADER_H_CM = 0.55
    HEADER_GAP_CM = 0.80

    # 좌 헤더 ("핵심 요약")
    _add_text(slide, BODY_X, Cm(SEC_B_TOP_CM), Cm(LEFT_W_CM), Cm(HEADER_H_CM),
              data.get('SUMMARY_TITLE', '핵심 요약'),
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # 좌 패널 (Surface Soft + Hairline + Navy 액센트 좌측)
    panel_l_top = Cm(SEC_B_TOP_CM + HEADER_GAP_CM)
    panel_l_h = Cm(SEC_B_H_CM - HEADER_GAP_CM)
    _add_rect(slide, BODY_X, panel_l_top, Cm(LEFT_W_CM), panel_l_h,
              fill=COLORS['surface_soft'], line_color=COLORS['hairline'], line_pt=0.5)
    _add_rect(slide, BODY_X, panel_l_top, Cm(0.10), panel_l_h,
              fill=COLORS['brand_navy'])

    # 핵심 요약 불릿
    summary_items = data.get('SUMMARY_ITEMS', [])
    if summary_items:
        tb = slide.shapes.add_textbox(BODY_X + Cm(0.40),
                                       Cm(SEC_B_TOP_CM + 1.00),
                                       Cm(LEFT_W_CM - 0.60),
                                       Cm(SEC_B_H_CM - 1.20))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = Emu(0)
        tf.margin_right = Emu(0)
        for i, item in enumerate(summary_items[:6]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(4)
            run_bullet = p.add_run()
            run_bullet.text = '■  '
            _set_run_font(run_bullet, name=FONT_KR_BOLD, size_pt=10.5, bold=True,
                          color=COLORS['brand_navy'])
            run_text = p.add_run()
            run_text.text = '' if item is None else str(item)
            _set_run_font(run_text, name=FONT_KR, size_pt=10.5, bold=False,
                          color=COLORS['charcoal'])

    # 우 헤더 ("월별 매출 추이 (억원)")
    right_x = BODY_X + Cm(LEFT_W_CM + 0.40)
    _add_text(slide, right_x, Cm(SEC_B_TOP_CM), Cm(RIGHT_W_CM), Cm(HEADER_H_CM),
              data.get('CHART_TITLE', '월별 추이'),
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # 우 패널 (흰색 + Hairline)
    panel_r_top = Cm(SEC_B_TOP_CM + HEADER_GAP_CM)
    panel_r_h = Cm(SEC_B_H_CM - HEADER_GAP_CM)
    _add_rect(slide, right_x, panel_r_top, Cm(RIGHT_W_CM), panel_r_h,
              fill=COLORS['white'], line_color=COLORS['hairline'], line_pt=0.5)

    # 차트 (간단 막대 차트)
    chart_labels = data.get('CHART_LABELS', [])
    # 문자열 숫자('1,234' 등)도 견고하게 — 라벨과 길이를 맞추기 위해 실패값은 0 으로 대체
    chart_values = [(_to_float(x) or 0) for x in data.get('CHART_VALUES', [])]
    if chart_labels and chart_values:
        try:
            from pptx.chart.data import CategoryChartData
            from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
            chart_data = CategoryChartData()
            chart_data.categories = chart_labels
            chart_data.add_series('매출', chart_values)
            chart = slide.shapes.add_chart(
                XL_CHART_TYPE.COLUMN_CLUSTERED,
                right_x + Cm(0.20), Cm(SEC_B_TOP_CM + 0.95),
                Cm(RIGHT_W_CM - 0.40), Cm(SEC_B_H_CM - 1.10),
                chart_data,
            ).chart
            chart.has_title = False
            chart.has_legend = False
            try:
                chart.plots[0].gap_width = 80
                # series fill = Navy
                ser = chart.plots[0].series[0]
                fill = ser.format.fill
                fill.solid()
                fill.fore_color.rgb = COLORS['brand_navy']
                # data labels
                dl = chart.plots[0].data_labels
                dl.show_value = True
                dl.position = XL_LABEL_POSITION.OUTSIDE_END
                dl.font.size = Pt(9)
                dl.font.color.rgb = COLORS['charcoal']
                # axes
                if chart_values:
                    vmin = min(chart_values)
                    vmax = max(chart_values)
                    chart.value_axis.minimum_scale = vmin * 0.95
                    chart.value_axis.maximum_scale = vmax * 1.10
                chart.value_axis.tick_labels.font.size = Pt(9)
                chart.value_axis.tick_labels.font.color.rgb = COLORS['steel']
                chart.category_axis.tick_labels.font.size = Pt(9)
                chart.category_axis.tick_labels.font.color.rgb = COLORS['steel']
            except Exception:
                pass
            _kill_chart_shadows(chart)
        except Exception as e:
            print(f'[A4 KPI] chart build failed: {e}')

    # ─────────────────────────────────────────────────────
    # Section C — 이슈 + 액션 (y=12.30 ~ 18.00, h=5.70)
    # ─────────────────────────────────────────────────────
    SEC_C_TOP_CM = 12.30
    SEC_C_H_CM = 5.70

    # 좌 헤더 ("주요 이슈")
    _add_text(slide, BODY_X, Cm(SEC_C_TOP_CM), Cm(LEFT_W_CM), Cm(HEADER_H_CM),
              data.get('ISSUES_TITLE', '주요 이슈'),
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    panel_c_l_top = Cm(SEC_C_TOP_CM + HEADER_GAP_CM)
    panel_c_l_h = Cm(SEC_C_H_CM - HEADER_GAP_CM)
    _add_rect(slide, BODY_X, panel_c_l_top, Cm(LEFT_W_CM), panel_c_l_h,
              fill=COLORS['surface_soft'], line_color=COLORS['hairline'], line_pt=0.5)

    # 이슈 아이템 3개
    issues = data.get('ISSUES', [])
    ITEM_TOP_CM = SEC_C_TOP_CM + 1.00
    ITEM_H_CM = 1.30
    ITEM_GAP_CM = 0.10
    SEV_COLORS = {'HIGH': COLORS['brand_red'], 'MID': COLORS['slate'], 'LOW': COLORS['steel']}
    for i, issue in enumerate(issues[:3]):
        y = Cm(ITEM_TOP_CM + (ITEM_H_CM + ITEM_GAP_CM) * i)
        sev = issue.get('sev', 'MID').upper()
        sev_color = SEV_COLORS.get(sev, COLORS['slate'])
        # 심각도 태그
        tag_x = BODY_X + Cm(0.30)
        tag_w = Cm(1.40)
        tag_h = Cm(0.60)
        _add_rect(slide, tag_x, y + Cm(0.10), tag_w, tag_h, fill=sev_color)
        _add_text(slide, tag_x, y + Cm(0.10), tag_w, tag_h, sev,
                  font=FONT_EN, size_pt=10, bold=True, color=COLORS['white'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)
        # 제목
        txt_x = tag_x + tag_w + Cm(0.30)
        txt_w = Cm(LEFT_W_CM - 0.30 - 1.40 - 0.30 - 0.30)
        _add_text(slide, txt_x, y, txt_w, Cm(0.55),
                  issue.get('title', ''),
                  font=FONT_KR_BOLD, size_pt=11, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        # 설명
        _add_text(slide, txt_x, y + Cm(0.50), txt_w, Cm(0.80),
                  issue.get('desc', ''),
                  font=FONT_KR, size_pt=9.5, bold=False, color=COLORS['slate'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.25)

    # 우 헤더 ("차월 액션 아이템")
    _add_text(slide, right_x, Cm(SEC_C_TOP_CM), Cm(RIGHT_W_CM), Cm(HEADER_H_CM),
              data.get('ACTIONS_TITLE', '차월 액션 아이템'),
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    panel_c_r_top = Cm(SEC_C_TOP_CM + HEADER_GAP_CM)
    panel_c_r_h = Cm(SEC_C_H_CM - HEADER_GAP_CM)
    _add_rect(slide, right_x, panel_c_r_top, Cm(RIGHT_W_CM), panel_c_r_h,
              fill=COLORS['surface_soft'], line_color=COLORS['hairline'], line_pt=0.5)

    # 액션 3개
    actions = data.get('ACTIONS', [])
    ACT_TOP_CM = SEC_C_TOP_CM + 1.00
    for i, action in enumerate(actions[:3]):
        y = Cm(ACT_TOP_CM + (ITEM_H_CM + ITEM_GAP_CM) * i)
        # 번호 (22pt Bold Navy)
        num_x = right_x + Cm(0.30)
        num_w = Cm(1.40)
        _add_text(slide, num_x, y, num_w, Cm(1.30),
                  action.get('num', f'{i+1:02d}'),
                  font=FONT_KR_BOLD, size_pt=22, bold=True, color=COLORS['brand_navy'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
                  wrap=False, margins=False)
        # 제목
        txt_x = num_x + num_w + Cm(0.20)
        txt_w = Cm(RIGHT_W_CM - 0.30 - 1.40 - 0.20 - 0.30)
        _add_text(slide, txt_x, y, txt_w, Cm(0.45),
                  action.get('title', ''),
                  font=FONT_KR_BOLD, size_pt=11, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        # 책임자·기한
        _add_text(slide, txt_x, y + Cm(0.40), txt_w, Cm(0.40),
                  action.get('owner', ''),
                  font=FONT_KR, size_pt=9, bold=False, color=COLORS['brand_navy'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        # 설명
        _add_text(slide, txt_x, y + Cm(0.75), txt_w, Cm(0.55),
                  action.get('desc', ''),
                  font=FONT_KR, size_pt=9.5, bold=False, color=COLORS['slate'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.25)

    return slide


# ============================================================
# Layout 3 — 부문별 스코어카드 본문 (경영진 보고 2 / Variant B)
# ============================================================
def build_a4_scorecard_slide(prs, data, logo_path=None):
    """부문별 실적 스코어카드 슬라이드.

    data 필드:
      - HEADER, DATE
      - HEADLINE_EYEBROW, HEADLINE_MAIN, HEADLINE_SUB
      - AGG_KPIS: [{"label","value","unit","delta","up"}, x3] — 우측 미니카드
      - DIVISIONS: [{"name","plan","actual","delta","delta_up","status":"good|warn|bad","bold":bool}, ...]
      - ISSUES: [{"div","title","desc"}, x2~3]
      - DECISIONS: [{"q","owner"}, x2~3]  (회의 의사결정 질문)
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    apply_body_chrome(slide,
                      header_title=data.get('HEADER', '경영회의 보고서'),
                      logo_path=logo_path,
                      date_str=data.get('DATE'))

    BODY_X = Cm(0.80)
    BODY_W_CM = SLIDE_W_CM - 0.80 * 2

    # ─────────────────────────────────────────────────────
    # Section A — Navy 헤드라인 + 종합 KPI 미니카드 (y=2.80~5.20)
    # ─────────────────────────────────────────────────────
    SEC_A_TOP_CM = 2.80
    SEC_A_H_CM = 2.40
    LEFT_W_A_CM = 15.20
    RIGHT_W_A_CM = BODY_W_CM - LEFT_W_A_CM - 0.30

    # Navy 헤드라인 패널
    _add_rect(slide, BODY_X, Cm(SEC_A_TOP_CM), Cm(LEFT_W_A_CM), Cm(SEC_A_H_CM),
              fill=COLORS['brand_navy'])

    _HL_BOX_W = LEFT_W_A_CM - 0.80  # 14.40

    # Eyebrow tag
    _add_text(slide, BODY_X + Cm(0.40), Cm(SEC_A_TOP_CM + 0.18), Cm(_HL_BOX_W), Cm(0.30),
              data.get('HEADLINE_EYEBROW', 'EXECUTIVE HEADLINE'),
              font=FONT_KR_BOLD, size_pt=9, bold=True, color=COLORS['navy_subtle'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=False, margins=False)

    # Main message — 폭 기준으로 폰트를 정해 "항상 박스 안"에 들어오게 한다.
    #   pt_1line = 이 글자수를 한 줄에 정확히 채우는 폰트크기(폭 기준).
    #   여유(0.92)를 둬서 한 줄에 넉넉히 들어가면 1줄, 그래도 작아져야 하면 2줄 허용.
    #   2줄도 세로 1.20cm 한계 때문에 14pt 상한. → wrap 동작과 무관하게 넘치지 않음.
    main_text = data.get('HEADLINE_MAIN', '한 줄 결론')
    vw32 = title_visual_width_cm(main_text)            # 32pt 기준 가로폭(cm)
    pt_1line = (32.0 * _HL_BOX_W / vw32) if vw32 > 0 else 20.0
    if pt_1line >= 16:
        main_pt = int(min(18, pt_1line * 0.92))        # 1줄에 여유있게
    else:
        main_pt = max(11, min(14, int(pt_1line * 1.9)))  # 2줄에 맞춤
    _add_text(slide, BODY_X + Cm(0.40), Cm(SEC_A_TOP_CM + 0.50), Cm(_HL_BOX_W), Cm(1.20),
              main_text,
              font=FONT_KR_BOLD, size_pt=main_pt, bold=True, color=COLORS['white'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=True, margins=False)

    # Sub — 폭 기준 1줄 유지(작아지면 8pt 하한)
    sub_text = data.get('HEADLINE_SUB', '부연 설명')
    vw32_s = title_visual_width_cm(sub_text)
    pt_1line_s = (32.0 * _HL_BOX_W / vw32_s) if vw32_s > 0 else 11.0
    sub_pt = max(8, int(min(11, pt_1line_s * 0.95)))
    _add_text(slide, BODY_X + Cm(0.40), Cm(SEC_A_TOP_CM + 1.78), Cm(_HL_BOX_W), Cm(0.50),
              sub_text,
              font=FONT_KR, size_pt=sub_pt, bold=False, color=COLORS['navy_text'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=True, margins=False)

    # 우측 종합 KPI 미니카드 3개 (세로 스택)
    right_x = BODY_X + Cm(LEFT_W_A_CM + 0.30)
    agg_kpis = data.get('AGG_KPIS', [])
    card_h_cm = (SEC_A_H_CM - 0.20) / 3
    for i in range(3):
        kpi = agg_kpis[i] if i < len(agg_kpis) else {'label': '', 'value': '—', 'unit': '', 'delta': '', 'up': True}
        card_y = Cm(SEC_A_TOP_CM + (card_h_cm + 0.10) * i)
        # 카드 surface
        _add_rect(slide, right_x, card_y, Cm(RIGHT_W_A_CM), Cm(card_h_cm),
                  fill=COLORS['surface'], line_color=COLORS['hairline'], line_pt=0.5)
        # 좌측 Navy 액센트
        _add_rect(slide, right_x, card_y, Cm(0.08), Cm(card_h_cm),
                  fill=COLORS['brand_navy'])

        # 한 줄 가로 정렬: 라벨 / 값+단위 / delta
        # 라벨 (좌) — 칸 폭(LBL_W)에 맞춰 자동 축소해 1줄 유지(값과 겹침 방지)
        LBL_W = 4.20
        label_text = kpi.get('label', '')
        vw32_l = title_visual_width_cm(label_text)
        lbl_pt = int(min(11, max(8, 32.0 * LBL_W / vw32_l * 0.95))) if vw32_l > 0 else 11
        _add_text(slide, right_x + Cm(0.25), card_y, Cm(LBL_W), Cm(card_h_cm),
                  label_text,
                  font=FONT_KR, size_pt=lbl_pt, bold=False, color=COLORS['steel'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)

        # 값 + 단위 (중) — 라벨 칸이 넓어진 만큼 시작 위치 이동
        tb = slide.shapes.add_textbox(right_x + Cm(4.55), card_y,
                                       Cm(RIGHT_W_A_CM - 4.55 - 2.60), Cm(card_h_cm))
        tf = tb.text_frame
        tf.word_wrap = False
        tf.margin_left = Emu(0)
        tf.margin_right = Emu(0)
        tf.margin_top = Emu(0)
        tf.margin_bottom = Emu(0)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        run_v = p.add_run()
        run_v.text = str(kpi.get('value', ''))
        _set_run_font(run_v, name=FONT_KR_BOLD, size_pt=18, bold=True, color=COLORS['charcoal'])
        if kpi.get('unit'):
            run_u = p.add_run()
            run_u.text = ' ' + str(kpi['unit'])
            _set_run_font(run_u, name=FONT_KR, size_pt=10, bold=False, color=COLORS['slate'])

        # delta (우)
        delta_color = COLORS['brand_navy'] if kpi.get('up', True) else COLORS['brand_red']
        _add_text(slide, right_x + Cm(RIGHT_W_A_CM - 2.50), card_y, Cm(2.30), Cm(card_h_cm),
                  kpi.get('delta', ''),
                  font=FONT_KR_BOLD, size_pt=11, bold=True, color=delta_color,
                  align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, wrap=False)

    # ─────────────────────────────────────────────────────
    # Section B — 부문별 스코어카드 테이블 (y=5.60~12.50)
    # ─────────────────────────────────────────────────────
    SEC_B_TOP_CM = 5.60
    SEC_B_H_CM = 6.90

    # 섹션 헤더
    _add_text(slide, BODY_X, Cm(SEC_B_TOP_CM), Cm(BODY_W_CM), Cm(0.55),
              '부문별 실적 (단위: 억원 / 계획 대비 달성률)',
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    # 컬럼 폭 (cm)
    COL_W_CM = {'name': 4.50, 'plan': 3.20, 'actual': 3.20, 'progress': 7.20, 'delta': 3.60, 'status': 4.217}
    col_order = ['name', 'plan', 'actual', 'progress', 'delta', 'status']
    col_align = {'name': PP_ALIGN.LEFT, 'plan': PP_ALIGN.RIGHT, 'actual': PP_ALIGN.RIGHT,
                 'progress': PP_ALIGN.LEFT, 'delta': PP_ALIGN.RIGHT, 'status': PP_ALIGN.CENTER}
    col_labels = {'name': '부문명', 'plan': '계획', 'actual': '실적', 'progress': '달성률', 'delta': 'Δ vs 전월', 'status': '상태'}

    # x 위치 계산
    col_x = {}
    cur_x_cm = 0.80
    for c in col_order:
        col_x[c] = cur_x_cm
        cur_x_cm += COL_W_CM[c]

    TBL_TOP_CM = SEC_B_TOP_CM + 0.80
    HEADER_H_CM = 0.60
    ROW_GAP_CM = 0.10

    divisions = data.get('DIVISIONS', [])
    # 5~6개 사업부 + 마지막 합계(bold) 행을 모두 담을 수 있도록 7행까지 허용
    # (이전 5행 제한은 합계 행을 조용히 잘라냈다).
    _MAX_DIVISION_ROWS = 7
    n_rows = min(len(divisions), _MAX_DIVISION_ROWS) or 5
    TBL_H_CM = SEC_B_H_CM - 0.80
    row_h_cm = (TBL_H_CM - HEADER_H_CM - ROW_GAP_CM * n_rows) / n_rows

    # 헤더 행 (Navy 배경, 흰색 텍스트)
    _add_rect(slide, Cm(0.80), Cm(TBL_TOP_CM), Cm(BODY_W_CM), Cm(HEADER_H_CM),
              fill=COLORS['brand_navy'])
    for c in col_order:
        _add_text(slide, Cm(col_x[c]), Cm(TBL_TOP_CM), Cm(COL_W_CM[c]), Cm(HEADER_H_CM),
                  col_labels[c],
                  font=FONT_KR_BOLD, size_pt=11, bold=True, color=COLORS['white'],
                  align=col_align[c], anchor=MSO_ANCHOR.MIDDLE, wrap=False)

    # 데이터 행
    STATUS_COLORS = {'good': COLORS['brand_navy'], 'warn': COLORS['amber'], 'bad': COLORS['brand_red']}
    STATUS_LABELS = {'good': '양호', 'warn': '주의', 'bad': '부진'}

    for i in range(min(len(divisions), _MAX_DIVISION_ROWS)):
        div = divisions[i]
        row_y_cm = TBL_TOP_CM + HEADER_H_CM + (row_h_cm + ROW_GAP_CM) * i
        row_y = Cm(row_y_cm)
        is_total = bool(div.get('bold', False))
        row_bg = COLORS['cool_mist'] if is_total else COLORS['surface_soft']

        # 행 배경
        _add_rect(slide, Cm(0.80), row_y, Cm(BODY_W_CM), Cm(row_h_cm),
                  fill=row_bg, line_color=COLORS['hairline_soft'], line_pt=0.25)

        # 부문명
        _add_text(slide, Cm(col_x['name'] + 0.20), row_y, Cm(COL_W_CM['name'] - 0.40), Cm(row_h_cm),
                  div.get('name', ''),
                  font=FONT_KR_BOLD if is_total else FONT_KR, size_pt=12, bold=is_total, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

        # 계획
        plan_val = div.get('plan', 0)
        plan_str = f'{plan_val:,}' if isinstance(plan_val, (int, float)) else str(plan_val)
        _add_text(slide, Cm(col_x['plan']), row_y, Cm(COL_W_CM['plan'] - 0.20), Cm(row_h_cm),
                  plan_str,
                  font=FONT_KR_BOLD if is_total else FONT_KR, size_pt=12, bold=is_total, color=COLORS['slate'],
                  align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

        # 실적
        act_val = div.get('actual', 0)
        act_str = f'{act_val:,}' if isinstance(act_val, (int, float)) else str(act_val)
        _add_text(slide, Cm(col_x['actual']), row_y, Cm(COL_W_CM['actual'] - 0.20), Cm(row_h_cm),
                  act_str,
                  font=FONT_KR_BOLD, size_pt=13, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)

        # 달성률 진행바 — 콤마/단위 섞인 문자열도 _to_float 로 견고하게 파싱
        plan_num = _to_float(plan_val)
        act_num = _to_float(act_val)
        pct = (act_num / plan_num) if (plan_num and act_num is not None) else 0
        if pct >= 1.00:
            bar_color = COLORS['brand_navy']
        elif pct >= 0.90:
            bar_color = COLORS['amber']
        else:
            bar_color = COLORS['brand_red']

        bar_x_cm = col_x['progress'] + 0.10
        bar_y_cm = row_y_cm + (row_h_cm - 0.40) / 2
        bar_w_total_cm = COL_W_CM['progress'] - 2.20
        bar_h_cm = 0.40
        # 트랙
        _add_rect(slide, Cm(bar_x_cm), Cm(bar_y_cm), Cm(bar_w_total_cm), Cm(bar_h_cm),
                  fill=COLORS['progress_track'])
        # 채움 (120%에서 cap)
        bar_fill_pct = min(pct, 1.20)
        bar_w_fill_cm = bar_w_total_cm * (bar_fill_pct / 1.20)
        if bar_w_fill_cm > 0:
            _add_rect(slide, Cm(bar_x_cm), Cm(bar_y_cm), Cm(bar_w_fill_cm), Cm(bar_h_cm),
                      fill=bar_color)
        # 100% 마커
        marker_x_cm = bar_x_cm + bar_w_total_cm * (1.00 / 1.20)
        _add_rect(slide, Cm(marker_x_cm), Cm(bar_y_cm - 0.05), Cm(0.04), Cm(bar_h_cm + 0.10),
                  fill=RGBColor(0, 0, 0))
        # % 텍스트 (진행바 우측)
        _add_text(slide, Cm(bar_x_cm + bar_w_total_cm + 0.15), row_y,
                  Cm(COL_W_CM['progress'] - bar_w_total_cm - 0.30), Cm(row_h_cm),
                  f'{pct*100:.0f}%',
                  font=FONT_KR_BOLD, size_pt=12, bold=True, color=bar_color,
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=False)

        # Δ vs 전월
        delta_color = COLORS['brand_navy'] if div.get('delta_up', True) else COLORS['brand_red']
        _add_text(slide, Cm(col_x['delta']), row_y, Cm(COL_W_CM['delta'] - 0.20), Cm(row_h_cm),
                  div.get('delta', ''),
                  font=FONT_KR_BOLD, size_pt=11, bold=True, color=delta_color,
                  align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE, wrap=False)

        # 상태 칩
        status = div.get('status', 'good')
        chip_color = STATUS_COLORS.get(status, COLORS['brand_navy'])
        chip_label = STATUS_LABELS.get(status, '양호')
        chip_w = Cm(1.60)
        chip_h = Cm(0.55)
        chip_x = Cm(col_x['status'] + (COL_W_CM['status'] - 1.60) / 2)
        chip_y = Cm(row_y_cm + (row_h_cm - 0.55) / 2)
        _add_rounded_rect(slide, chip_x, chip_y, chip_w, chip_h,
                          fill=chip_color, adj=0.35)
        _add_text(slide, chip_x, chip_y, chip_w, chip_h,
                  chip_label,
                  font=FONT_EN, size_pt=10, bold=True, color=COLORS['white'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)

    # ─────────────────────────────────────────────────────
    # Section C — 핵심 이슈 + 차월 의사결정 (y=12.85~18.35, 푸터 18.50 바로 위)
    # ─────────────────────────────────────────────────────
    SEC_C_TOP_CM = 12.85
    SEC_C_H_CM = 5.50
    LEFT_W_C_CM = 13.50
    RIGHT_W_C_CM = BODY_W_CM - LEFT_W_C_CM - 0.30
    HEADER_H_CM = 0.55
    HEADER_GAP_CM = 0.80

    # 좌 헤더
    _add_text(slide, BODY_X, Cm(SEC_C_TOP_CM), Cm(LEFT_W_C_CM), Cm(HEADER_H_CM),
              data.get('ISSUES_TITLE', '핵심 이슈 · 위험 신호'),
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    panel_l_top = Cm(SEC_C_TOP_CM + HEADER_GAP_CM)
    panel_l_h = Cm(SEC_C_H_CM - HEADER_GAP_CM)
    _add_rect(slide, BODY_X, panel_l_top, Cm(LEFT_W_C_CM), panel_l_h,
              fill=COLORS['surface_soft'], line_color=COLORS['hairline'], line_pt=0.5)

    issues = data.get('ISSUES', [])
    # 항목 높이를 패널 높이에서 역산 → 3개가 항상 패널 안에 들어오게 한다.
    _N_ITEM = 3
    _PANEL_PAD = 0.22
    ITEM_GAP_CM = 0.20
    _DESC_LS = 1.25  # 설명 줄간격
    ITEM_H_CM = (SEC_C_H_CM - HEADER_GAP_CM - _PANEL_PAD * 2 - ITEM_GAP_CM * (_N_ITEM - 1)) / _N_ITEM
    ITEM_TOP_CM = SEC_C_TOP_CM + HEADER_GAP_CM + _PANEL_PAD
    for i, issue in enumerate(issues[:3]):
        y = Cm(ITEM_TOP_CM + (ITEM_H_CM + ITEM_GAP_CM) * i)
        # 부문 태그
        tag_x = BODY_X + Cm(0.30)
        tag_w = Cm(2.00)
        tag_h = Cm(0.42)
        _add_rect(slide, tag_x, y + Cm(0.02), tag_w, tag_h, fill=COLORS['brand_navy'])
        _add_text(slide, tag_x, y + Cm(0.02), tag_w, tag_h,
                  issue.get('div', ''),
                  font=FONT_KR_BOLD, size_pt=9, bold=True, color=COLORS['white'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)
        # 제목
        txt_x = tag_x + tag_w + Cm(0.30)
        txt_w_cm = LEFT_W_C_CM - 0.30 - 2.00 - 0.30 - 0.30
        _add_text(slide, txt_x, y, Cm(txt_w_cm), Cm(0.44),
                  issue.get('title', ''),
                  font=FONT_KR_BOLD, size_pt=11, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        # 설명 — 폭·높이 둘 다 기준으로 폰트 정해 최대 2줄, 박스 안에 들어오게
        desc_text = issue.get('desc', '')
        vw32_d = title_visual_width_cm(desc_text)
        _desc_box_h = ITEM_H_CM - 0.58
        if vw32_d > 0:
            _pt_w2 = 2 * 32.0 * txt_w_cm / vw32_d                 # 폭: 2줄 안에
            _pt_h2 = _desc_box_h * 72.0 / (2.54 * 2 * _DESC_LS)   # 높이: 2줄 안에
            desc_pt = max(8, int(min(10, _pt_w2, _pt_h2)))
        else:
            desc_pt = 10
        _add_text(slide, txt_x, y + Cm(0.54), Cm(txt_w_cm), Cm(_desc_box_h),
                  desc_text,
                  font=FONT_KR, size_pt=desc_pt, bold=False, color=COLORS['slate'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=_DESC_LS, wrap=True)

    # 우 헤더
    right_x = BODY_X + Cm(LEFT_W_C_CM + 0.30)
    _add_text(slide, right_x, Cm(SEC_C_TOP_CM), Cm(RIGHT_W_C_CM), Cm(HEADER_H_CM),
              data.get('DECISIONS_TITLE', '차월 의사결정 사항'),
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    panel_r_top = Cm(SEC_C_TOP_CM + HEADER_GAP_CM)
    panel_r_h = Cm(SEC_C_H_CM - HEADER_GAP_CM)
    _add_rect(slide, right_x, panel_r_top, Cm(RIGHT_W_C_CM), panel_r_h,
              fill=COLORS['surface_soft'], line_color=COLORS['hairline'], line_pt=0.5)

    decisions = data.get('DECISIONS', [])
    DEC_TOP_CM = ITEM_TOP_CM
    for i, dec in enumerate(decisions[:3]):
        y = Cm(DEC_TOP_CM + (ITEM_H_CM + ITEM_GAP_CM) * i)
        # 원형 Q 마커
        q_d = Cm(0.66)
        q_x = right_x + Cm(0.28)
        q_y = y + Cm(0.06)
        shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, q_x, q_y, q_d, q_d)
        shape.fill.solid()
        shape.fill.fore_color.rgb = COLORS['brand_navy']
        shape.line.fill.background()
        _kill_shadow(shape)
        _add_text(slide, q_x, q_y, q_d, q_d,
                  f'Q{i+1}',
                  font=FONT_KR_BOLD, size_pt=10, bold=True, color=COLORS['white'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)
        # 질문 — 폭 기준 폰트(짧으면 1줄, 길면 9pt 2줄)
        txt_x = q_x + q_d + Cm(0.28)
        q_w_cm = RIGHT_W_C_CM - 0.28 - 0.66 - 0.28 - 0.30
        q_text = dec.get('q', '')
        vw32_q = title_visual_width_cm(q_text)
        pt1_q = (32.0 * q_w_cm / vw32_q) if vw32_q > 0 else 11.0
        q_pt = 11 if pt1_q >= 11 else max(8, min(10, int(pt1_q * 1.9)))
        _add_text(slide, txt_x, y, Cm(q_w_cm), Cm(ITEM_H_CM - 0.50),
                  q_text,
                  font=FONT_KR_BOLD, size_pt=q_pt, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, wrap=True, line_spacing=1.2)
        # 결정권자
        _add_text(slide, txt_x, y + Cm(ITEM_H_CM - 0.42), Cm(q_w_cm), Cm(0.40),
                  f'결정권자: {dec.get("owner", "")}',
                  font=FONT_KR, size_pt=9, bold=False, color=COLORS['slate'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=False, margins=False)

    return slide


# ============================================================
# Helper — 원형 도형 (회의록 / 스코어카드용)
# ============================================================
def _add_circle(slide, left, top, diameter, *, fill_color=None, line_color=None, line_pt=0):
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
        shape.line.width = Pt(line_pt)
    _kill_shadow(shape)
    return shape


# ============================================================
# Layout 4 — 회의록 본문 (Variant E)
# ============================================================
def build_a4_meeting_minutes_slide(prs, data, logo_path=None):
    """회의록 본문 슬라이드.

    data 필드:
      - HEADER, DATE
      - META_ITEMS: [{"label","value"}, x4] — 일시/장소/주관/참석자
      - AGENDAS: [{"num","title","discussion","decision"}, x3]
      - ACTION_ITEMS: [{"no","task","owner","due","status":"in_progress|planned|done"}, x5]
      - NEXT_MEETING: 다음 회의 안내 한 줄
      - SIGNOFF: '작성: OOO / 검토: OOO'
    """
    blank = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank)

    apply_body_chrome(slide,
                      header_title=data.get('HEADER', '경영회의 회의록'),
                      logo_path=logo_path,
                      date_str=data.get('DATE'))

    BODY_X = Cm(0.80)
    BODY_W_CM = SLIDE_W_CM - 0.80 * 2

    # ─────────────────────────────────────────────────────
    # Section A — 메타 정보 바 (y=2.80~4.30)
    # ─────────────────────────────────────────────────────
    SEC_A_TOP_CM = 2.80
    SEC_A_H_CM = 1.50

    _add_rect(slide, BODY_X, Cm(SEC_A_TOP_CM), Cm(BODY_W_CM), Cm(SEC_A_H_CM),
              fill=COLORS['surface'], line_color=COLORS['hairline'], line_pt=0.5)
    # Navy 액센트 스트립
    _add_rect(slide, BODY_X, Cm(SEC_A_TOP_CM), Cm(0.10), Cm(SEC_A_H_CM),
              fill=COLORS['brand_navy'])

    # 4 컬럼
    meta_items = data.get('META_ITEMS', [])
    col_w_cm = (BODY_W_CM - 0.40) / 4
    for i in range(4):
        item = meta_items[i] if i < len(meta_items) else {'label': '', 'value': ''}
        col_x = BODY_X + Cm(0.40 + col_w_cm * i)
        # 라벨
        _add_text(slide, col_x, Cm(SEC_A_TOP_CM + 0.25), Cm(col_w_cm), Cm(0.45),
                  item.get('label', ''),
                  font=FONT_KR_BOLD, size_pt=10, bold=True, color=COLORS['steel'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        # 값
        _add_text(slide, col_x, Cm(SEC_A_TOP_CM + 0.70), Cm(col_w_cm), Cm(0.70),
                  item.get('value', ''),
                  font=FONT_KR, size_pt=11, bold=False, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)

    # ─────────────────────────────────────────────────────
    # Section B — 안건별 논의 카드 3개 (y=4.70~10.90)
    # ─────────────────────────────────────────────────────
    SEC_B_TOP_CM = 4.70
    SEC_B_H_CM = 6.20

    # 섹션 헤더
    _add_text(slide, BODY_X, Cm(SEC_B_TOP_CM), Cm(BODY_W_CM), Cm(0.55),
              '안건별 논의 내용',
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    AGENDA_TOP_CM = SEC_B_TOP_CM + 0.65
    AGENDA_H_CM = SEC_B_H_CM - 0.65
    AGENDA_GAP_CM = 0.20
    card_w_cm = (BODY_W_CM - AGENDA_GAP_CM * 2) / 3

    agendas = data.get('AGENDAS', [])
    for i in range(3):
        ag = agendas[i] if i < len(agendas) else {'num': f'{i+1:02d}', 'title': '', 'discussion': '', 'decision': ''}
        card_x = BODY_X + Cm((card_w_cm + AGENDA_GAP_CM) * i)
        card_y = Cm(AGENDA_TOP_CM)
        # 카드 (흰색 + Hairline)
        _add_rect(slide, card_x, card_y, Cm(card_w_cm), Cm(AGENDA_H_CM),
                  fill=COLORS['white'], line_color=COLORS['hairline'], line_pt=0.5)
        # 상단 Navy 스트립
        _add_rect(slide, card_x, card_y, Cm(card_w_cm), Cm(0.08),
                  fill=COLORS['brand_navy'])

        # 안건 번호 (20pt Navy)
        _add_text(slide, card_x + Cm(0.30), card_y + Cm(0.20), Cm(1.10), Cm(0.85),
                  ag.get('num', f'{i+1:02d}'),
                  font=FONT_KR_BOLD, size_pt=20, bold=True, color=COLORS['brand_navy'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=False)

        # 안건 제목
        _add_text(slide, card_x + Cm(1.55), card_y + Cm(0.25), Cm(card_w_cm - 1.85), Cm(0.85),
                  ag.get('title', ''),
                  font=FONT_KR_BOLD, size_pt=13, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.2)

        # 구분선
        _add_rect(slide, card_x + Cm(0.30), card_y + Cm(1.15),
                  Cm(card_w_cm - 0.60), Cm(0.025),
                  fill=COLORS['hairline'])

        # 논의 내용 (영역 축소 — 결정 박스 확장 만큼 양보)
        _add_text(slide, card_x + Cm(0.30), card_y + Cm(1.30), Cm(card_w_cm - 0.60), Cm(0.40),
                  '▸ 논의 내용',
                  font=FONT_KR_BOLD, size_pt=9, bold=True, color=COLORS['steel'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        _add_text(slide, card_x + Cm(0.30), card_y + Cm(1.70), Cm(card_w_cm - 0.60), Cm(1.70),
                  ag.get('discussion', ''),
                  font=FONT_KR, size_pt=10, bold=False, color=COLORS['slate'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.35, multi=True)

        # 결정 사항 영역 (Cool Mist 배경, 1.50 → 2.10cm 확장)
        DEC_H_CM = 2.10
        dec_top = card_y + Cm(AGENDA_H_CM - DEC_H_CM)
        _add_rect(slide, card_x, dec_top, Cm(card_w_cm), Cm(DEC_H_CM),
                  fill=COLORS['cool_mist'])
        _add_text(slide, card_x + Cm(0.30), dec_top + Cm(0.15), Cm(card_w_cm - 0.60), Cm(0.40),
                  '✓ 결정 사항',
                  font=FONT_KR_BOLD, size_pt=9, bold=True, color=COLORS['brand_navy'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
        _add_text(slide, card_x + Cm(0.30), dec_top + Cm(0.55), Cm(card_w_cm - 0.60), Cm(DEC_H_CM - 0.65),
                  ag.get('decision', ''),
                  font=FONT_KR_BOLD, size_pt=10, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.3, multi=True)

    # ─────────────────────────────────────────────────────
    # Section C — 액션 아이템 테이블 5행 (y=11.30~16.10)
    # ─────────────────────────────────────────────────────
    SEC_C_TOP_CM = 11.30
    SEC_C_H_CM = 4.80

    _add_text(slide, BODY_X, Cm(SEC_C_TOP_CM), Cm(BODY_W_CM), Cm(0.55),
              '액션 아이템 (Action Items)',
              font=FONT_KR_BOLD, size_pt=14, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)

    AC_COL_W_CM = {'no': 1.20, 'task': 11.50, 'owner': 5.20, 'due': 3.80, 'status': 4.217}
    ac_order = ['no', 'task', 'owner', 'due', 'status']
    ac_align = {'no': PP_ALIGN.CENTER, 'task': PP_ALIGN.LEFT, 'owner': PP_ALIGN.LEFT,
                'due': PP_ALIGN.CENTER, 'status': PP_ALIGN.CENTER}
    ac_labels = {'no': 'No.', 'task': 'Task / 실행 항목', 'owner': 'Owner / 담당',
                 'due': 'Due / 기한', 'status': 'Status'}

    ac_col_x = {}
    cur = 0.80
    for c in ac_order:
        ac_col_x[c] = cur
        cur += AC_COL_W_CM[c]

    TBL_TOP_CM = SEC_C_TOP_CM + 0.65
    TBL_H_CM = SEC_C_H_CM - 0.65
    HEADER_H_CM = 0.55
    n_actions = 5
    row_h_cm = (TBL_H_CM - HEADER_H_CM) / n_actions

    # 헤더
    _add_rect(slide, Cm(0.80), Cm(TBL_TOP_CM), Cm(BODY_W_CM), Cm(HEADER_H_CM),
              fill=COLORS['brand_navy'])
    for c in ac_order:
        _add_text(slide, Cm(ac_col_x[c]), Cm(TBL_TOP_CM), Cm(AC_COL_W_CM[c]), Cm(HEADER_H_CM),
                  ac_labels[c],
                  font=FONT_KR_BOLD, size_pt=10, bold=True, color=COLORS['white'],
                  align=ac_align[c], anchor=MSO_ANCHOR.MIDDLE, wrap=False)

    actions = data.get('ACTION_ITEMS', [])
    AC_STATUS_COLORS = {'in_progress': COLORS['brand_navy'], 'planned': COLORS['amber'], 'done': COLORS['green']}
    AC_STATUS_LABELS = {'in_progress': '진행 중', 'planned': '예정', 'done': '완료'}
    for i in range(n_actions):
        act = actions[i] if i < len(actions) else {'no': str(i+1), 'task': '', 'owner': '', 'due': '', 'status': 'planned'}
        row_y_cm = TBL_TOP_CM + HEADER_H_CM + row_h_cm * i
        row_y = Cm(row_y_cm)
        row_bg = COLORS['white'] if i % 2 == 0 else COLORS['surface_soft']
        _add_rect(slide, Cm(0.80), row_y, Cm(BODY_W_CM), Cm(row_h_cm),
                  fill=row_bg, line_color=COLORS['hairline_soft'], line_pt=0.25)

        # No.
        _add_text(slide, Cm(ac_col_x['no']), row_y, Cm(AC_COL_W_CM['no']), Cm(row_h_cm),
                  act.get('no', str(i+1)),
                  font=FONT_KR_BOLD, size_pt=11, bold=True, color=COLORS['brand_navy'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        # Task
        _add_text(slide, Cm(ac_col_x['task'] + 0.20), row_y, Cm(AC_COL_W_CM['task'] - 0.30), Cm(row_h_cm),
                  act.get('task', ''),
                  font=FONT_KR, size_pt=10, bold=False, color=COLORS['charcoal'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.3, multi=True)
        # Owner
        _add_text(slide, Cm(ac_col_x['owner'] + 0.10), row_y, Cm(AC_COL_W_CM['owner'] - 0.20), Cm(row_h_cm),
                  act.get('owner', ''),
                  font=FONT_KR, size_pt=10, bold=False, color=COLORS['slate'],
                  align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE)
        # Due
        _add_text(slide, Cm(ac_col_x['due']), row_y, Cm(AC_COL_W_CM['due']), Cm(row_h_cm),
                  act.get('due', ''),
                  font=FONT_KR_BOLD, size_pt=10, bold=True, color=COLORS['charcoal'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, wrap=False)
        # Status 칩
        st = act.get('status', 'planned')
        chip_color = AC_STATUS_COLORS.get(st, COLORS['amber'])
        chip_label = AC_STATUS_LABELS.get(st, '예정')
        chip_w = Cm(2.20)
        chip_h = Cm(0.50)
        chip_x = Cm(ac_col_x['status'] + (AC_COL_W_CM['status'] - 2.20) / 2)
        chip_y = Cm(row_y_cm + (row_h_cm - 0.50) / 2)
        _add_rounded_rect(slide, chip_x, chip_y, chip_w, chip_h,
                          fill=chip_color, adj=0.35)
        _add_text(slide, chip_x, chip_y, chip_w, chip_h,
                  chip_label,
                  font=FONT_KR_BOLD, size_pt=10, bold=True, color=COLORS['white'],
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, wrap=False, margins=False)

    # ─────────────────────────────────────────────────────
    # Section D — 다음 회의 + 작성/검토 (y=16.20~18.00, 박스 1.80cm)
    # ─────────────────────────────────────────────────────
    SEC_D_TOP_CM = 16.20
    SEC_D_H_CM = 1.80
    NEXT_W_CM = 13.50
    RIGHT_W_D_CM = BODY_W_CM - NEXT_W_CM - 0.30

    # 좌 — 다음 회의 (Cool Mist + Navy 액센트)
    _add_rect(slide, BODY_X, Cm(SEC_D_TOP_CM), Cm(NEXT_W_CM), Cm(SEC_D_H_CM),
              fill=COLORS['cool_mist'])
    _add_rect(slide, BODY_X, Cm(SEC_D_TOP_CM), Cm(0.10), Cm(SEC_D_H_CM),
              fill=COLORS['brand_navy'])
    _add_text(slide, BODY_X + Cm(0.40), Cm(SEC_D_TOP_CM + 0.20), Cm(NEXT_W_CM - 0.60), Cm(0.40),
              '📅 다음 회의',
              font=FONT_KR_BOLD, size_pt=11, bold=True, color=COLORS['brand_navy'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
    _add_text(slide, BODY_X + Cm(0.40), Cm(SEC_D_TOP_CM + 0.60), Cm(NEXT_W_CM - 0.60), Cm(1.15),
              data.get('NEXT_MEETING', ''),
              font=FONT_KR, size_pt=10, bold=False, color=COLORS['charcoal'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.3, multi=True)

    # 우 — 작성/검토 (Surface Soft + Hairline)
    right_x = BODY_X + Cm(NEXT_W_CM + 0.30)
    _add_rect(slide, right_x, Cm(SEC_D_TOP_CM), Cm(RIGHT_W_D_CM), Cm(SEC_D_H_CM),
              fill=COLORS['surface_soft'], line_color=COLORS['hairline'], line_pt=0.5)
    _add_text(slide, right_x + Cm(0.30), Cm(SEC_D_TOP_CM + 0.20), Cm(RIGHT_W_D_CM - 0.60), Cm(0.40),
              '작성 · 검토',
              font=FONT_KR_BOLD, size_pt=10, bold=True, color=COLORS['steel'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
    _add_text(slide, right_x + Cm(0.30), Cm(SEC_D_TOP_CM + 0.60), Cm(RIGHT_W_D_CM - 0.60), Cm(1.15),
              data.get('SIGNOFF', ''),
              font=FONT_KR, size_pt=10, bold=False, color=COLORS['charcoal'],
              align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.3, multi=True)

    return slide


# ============================================================
# Layout 5 — A4 진행사항 보고 본문
#   4 섹션: ① 한 줄 항목  ② 4열 표  ③ 다행 표  ④ 진행 타임라인
#   (build_template.py 이식 — 폰트/크롬은 서버 A4 표준에 맞춤)
# ============================================================
_PROGRESS_GRID  = RGBColor(0xA6, 0xA6, 0xA6)   # 표 테두리 (회색)
_PROGRESS_HDR   = RGBColor(0xDD, 0xEB, 0xF7)   # 헤더 배경 (연파랑)
_PROGRESS_TLBLU = RGBColor(0x1F, 0x4E, 0x9E)   # 타임라인 선 (파랑)
_BLACK          = RGBColor(0x00, 0x00, 0x00)
_NO_STYLE_NO_GRID = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"


def _pad_list(seq, n, fill=''):
    """리스트를 정확히 n개로 정규화 (부족하면 fill 채우고, 넘치면 자름). None→''."""
    out = list(seq) if isinstance(seq, (list, tuple)) else []
    out = ['' if v is None else v for v in out]
    if len(out) < n:
        out += [fill] * (n - len(out))
    return out[:n]


def _no_autofit(tf):
    """텍스트프레임 자동 크기조절 비활성화 (수동 좌표 배치)."""
    el = tf._txBody
    bodyPr = el.find(qn('a:bodyPr'))
    if bodyPr is None:
        return
    for t in ('a:normAutofit', 'a:spAutoFit', 'a:noAutofit'):
        e = bodyPr.find(qn(t))
        if e is not None:
            bodyPr.remove(e)
    bodyPr.append(bodyPr.makeelement(qn('a:noAutofit'), {}))


def _p_addrun(p, text, *, bold=False, size=12, color=None):
    """문단에 run 추가 + 폰트 강제. color 기본 검정."""
    run = p.add_run()
    run.text = str(text)
    _set_run_font(run, name=(FONT_KR_BOLD if bold else FONT_KR),
                  size_pt=size, bold=bold,
                  color=color if color is not None else _BLACK)
    return run


def _progress_textbox(slide, x, y, w, h, *, anchor=MSO_ANCHOR.MIDDLE, wrap=True):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    tf.vertical_anchor = anchor
    tf.word_wrap = wrap
    _no_autofit(tf)
    return tb, tf


def _progress_section_label(slide, x, y, text, *, size=15):
    """■ 라벨 — ■ 기호·글씨 모두 검정 Bold."""
    tb, tf = _progress_textbox(slide, x, y, Cm(20), Cm(0.60),
                               anchor=MSO_ANCHOR.MIDDLE, wrap=False)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    _p_addrun(p, '■ ', bold=True, size=size, color=_BLACK)
    _p_addrun(p, text, bold=True, size=size, color=_BLACK)


def _make_table(slide, x, y, w, h, col_widths, row_heights):
    """네이티브 PPT 표 (스타일/밴딩 제거)."""
    gf = slide.shapes.add_table(len(row_heights), len(col_widths), x, y, w, h)
    tbl = gf.table
    tbl.first_row = tbl.last_row = tbl.first_col = tbl.last_col = False
    tbl.horz_banding = tbl.vert_banding = False
    tblPr = tbl._tbl.tblPr
    sid = tblPr.find(qn('a:tableStyleId'))
    if sid is None:
        sid = tblPr.makeelement(qn('a:tableStyleId'), {})
        tblPr.append(sid)
    sid.text = _NO_STYLE_NO_GRID
    for i, cw in enumerate(col_widths):
        tbl.columns[i].width = cw
    for i, rh in enumerate(row_heights):
        tbl.rows[i].height = rh
    return tbl


def _set_cell(cell, lines, *, size=11, color=None, align=PP_ALIGN.LEFT,
              anchor=MSO_ANCHOR.MIDDLE, bold=False, fill=None, line_gap=2,
              ml=0.15, mr=0.15, mt=0.08, mb=0.08):
    if color is None:
        color = _BLACK
    if fill is None:
        cell.fill.background()
    else:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
    cell.margin_left = Cm(ml)
    cell.margin_right = Cm(mr)
    cell.margin_top = Cm(mt)
    cell.margin_bottom = Cm(mb)
    cell.vertical_anchor = anchor
    tf = cell.text_frame
    tf.word_wrap = True
    tf.clear()
    if not lines:
        lines = ['']
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(line_gap)
        p.space_before = Pt(0)
        _p_addrun(p, ln, bold=bold, size=size, color=color)


def _cell_borders(cell, color, w_pt=1.0, edges="LRTB"):
    tcPr = cell._tc.get_or_add_tcPr()
    order = [("L", "a:lnL"), ("R", "a:lnR"), ("T", "a:lnT"), ("B", "a:lnB")]
    for _, tg in order:
        for e in tcPr.findall(qn(tg)):
            tcPr.remove(e)
    idx = 0
    for key, tg in order:
        if key not in edges:
            continue
        ln = tcPr.makeelement(qn(tg), {'w': str(int(w_pt * 12700)),
                                       'cap': 'flat', 'cmpd': 'sng', 'algn': 'ctr'})
        sf = ln.makeelement(qn('a:solidFill'), {})
        clr = sf.makeelement(qn('a:srgbClr'), {'val': str(color)})
        sf.append(clr)
        ln.append(sf)
        ln.append(ln.makeelement(qn('a:prstDash'), {'val': 'solid'}))
        tcPr.insert(idx, ln)
        idx += 1


def build_a4_progress_slide(prs, data, logo_path=None):
    """A4 진행사항 보고 본문 — 한줄 항목 / 4열 표 / 다행 표 / 타임라인."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])

    header = data.get('HEADER') or '진행사항'
    date_str = data.get('DATE') or datetime.now().strftime('%Y.%m.%d')
    apply_body_chrome(slide, header, logo_path=logo_path, date_str=date_str)

    L = Cm(0.80)
    R = Cm(26.72)
    W = R - L  # 25.92
    WHITE = COLORS['white']

    # ① 한 줄 항목 (목적 등) — 박스 없는 평문
    y = Cm(2.30)
    tb, tf = _progress_textbox(slide, L, y, W, Cm(1.05), anchor=MSO_ANCHOR.MIDDLE)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    _p_addrun(p, '■ ', bold=True, size=15, color=_BLACK)
    _p_addrun(p, (data.get('S1_LABEL') or '') + '   ', bold=True, size=15, color=_BLACK)
    _p_addrun(p, data.get('S1_TEXT') or '', bold=False, size=15, color=_BLACK)

    # ② 4열 표 (헤더 1행 + 내용 1행)
    _progress_section_label(slide, L, Cm(3.50), data.get('S2_LABEL') or '', size=15)
    ty = Cm(4.40)
    w0 = Cm(2.70)
    w1 = Cm(2.70)
    w2 = Cm(7.60)
    w3 = R - (L + w0 + w1 + w2)
    hh = Cm(0.64)
    rh = Cm(4.30)
    s2_headers = _pad_list(data.get('S2_HEADERS'), 4, '')
    tbl = _make_table(slide, L, ty, w0 + w1 + w2 + w3, hh + rh,
                      [w0, w1, w2, w3], [hh, rh])
    for ci, txt in enumerate(s2_headers):
        c = tbl.cell(0, ci)
        _set_cell(c, [txt], size=13, bold=True, color=_BLACK,
                  align=PP_ALIGN.CENTER, fill=_PROGRESS_HDR, mt=0.04, mb=0.04)
        _cell_borders(c, _PROGRESS_GRID, 1.0)
    s2_cols = [
        (0, data.get('S2_COL0') or [], PP_ALIGN.CENTER, 2),
        (1, data.get('S2_COL1') or [], PP_ALIGN.CENTER, 2),
        (2, data.get('S2_COL2') or [], PP_ALIGN.LEFT, 2),
        (3, data.get('S2_COL3') or [], PP_ALIGN.LEFT, 1),
    ]
    for ci, lines, al, gap in s2_cols:
        c = tbl.cell(1, ci)
        _set_cell(c, lines, size=11.5, color=_BLACK, align=al, fill=WHITE, line_gap=gap)
        _cell_borders(c, _PROGRESS_GRID, 1.0)

    # ③ 다행 표 (헤더 + N행, 각 행 = 값 / 값 / 긴 내용 / 상태)
    y3 = ty + hh + rh
    _progress_section_label(slide, L, y3 + Cm(0.22), data.get('S3_LABEL') or '', size=15)
    ty2 = y3 + Cm(1.02)
    dw0 = Cm(2.10)
    dw1 = Cm(3.50)
    d3w = Cm(3.30)
    dw2 = W - (dw0 + dw1 + d3w)
    hh2 = Cm(0.62)
    rh2 = Cm(0.70)
    rows = [_pad_list(r, 4, '') for r in (data.get('S3_ROWS') or [])
            if isinstance(r, (list, tuple))]
    if not rows:
        rows = [['', '', '', '']]
    s3_headers = _pad_list(data.get('S3_HEADERS'), 4, '')
    tbl2 = _make_table(slide, L, ty2, W, hh2 + rh2 * len(rows),
                       [dw0, dw1, dw2, d3w], [hh2] + [rh2] * len(rows))
    for ci, txt in enumerate(s3_headers):
        c = tbl2.cell(0, ci)
        _set_cell(c, [txt], size=12, bold=True, color=_BLACK,
                  align=PP_ALIGN.CENTER, fill=_PROGRESS_HDR, mt=0.04, mb=0.04)
        _cell_borders(c, _PROGRESS_GRID, 1.0)
    row_aligns = [PP_ALIGN.CENTER, PP_ALIGN.CENTER, PP_ALIGN.LEFT, PP_ALIGN.CENTER]
    for ri, row in enumerate(rows, start=1):
        for ci in range(4):
            c = tbl2.cell(ri, ci)
            _set_cell(c, [row[ci]], size=12, color=_BLACK,
                      align=row_aligns[ci], fill=WHITE)
            _cell_borders(c, _PROGRESS_GRID, 1.0)
    ry = ty2 + hh2 + rh2 * len(rows)

    # ④ 진행 타임라인 (단계 노드 + 둘러싼 프레임)
    _progress_section_label(slide, L, ry + Cm(0.42), data.get('S4_LABEL') or '', size=15)
    nodes = [_pad_list(nd, 3, '') for nd in (data.get('S4_NODES') or [])
             if isinstance(nd, (list, tuple))]
    while len(nodes) < 2:           # 타임라인은 최소 2개 노드 필요
        nodes.append(['', '', 'todo'])
    tl_y = ry + Cm(0.42) + Cm(1.85)
    n = len(nodes)
    x0 = L + Cm(1.6)
    x1 = R - Cm(1.6)
    step = (int(x1) - int(x0)) / (n - 1)

    # 프레임 (그래프+라벨+날짜를 감싸는 사각형)
    FR_T = tl_y - Cm(1.15)
    FR_B = tl_y + Cm(0.80)
    _add_rect(slide, L, FR_T, R - L, FR_B - FR_T,
              fill=None, line_color=_PROGRESS_GRID, line_pt=1.0)

    # 기준선 (파랑, 우측 끝 화살표)
    line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                      x0 - Cm(0.7), tl_y, x1 + Cm(0.9), tl_y)
    line.line.color.rgb = _PROGRESS_TLBLU
    line.line.width = Pt(2.5)
    line.shadow.inherit = False
    ln_el = line._element.spPr.find(qn('a:ln'))
    if ln_el is not None:
        ln_el.append(ln_el.makeelement(qn('a:tailEnd'),
                     {'type': 'triangle', 'w': 'med', 'len': 'med'}))

    dotr = Cm(0.20)
    dia = dotr * 2
    for i, (lab, dt, st) in enumerate(nodes):
        cx = Emu(int(x0) + int(step * i))
        left = Emu(int(cx) - int(dotr))
        top = tl_y - dotr
        st = (str(st) or 'todo').strip().lower()
        if st == 'done':            # 완료 — 검정 채움
            d = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, dia, dia)
            d.fill.solid()
            d.fill.fore_color.rgb = _BLACK
            d.line.color.rgb = _BLACK
            d.line.width = Pt(1.25)
            d.shadow.inherit = False
        elif st == 'now':           # 진행중 — 반원 (좌 검정 / 우 흰색)
            d = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, dia, dia)
            d.fill.solid()
            d.fill.fore_color.rgb = COLORS['white']
            d.line.color.rgb = _BLACK
            d.line.width = Pt(1.25)
            d.shadow.inherit = False
            pie = slide.shapes.add_shape(MSO_SHAPE.PIE, left, top, dia, dia)
            pie.fill.solid()
            pie.fill.fore_color.rgb = _BLACK
            pie.line.fill.background()
            pie.shadow.inherit = False
            geom = pie._element.spPr.find(qn('a:prstGeom'))
            avLst = geom.find(qn('a:avLst'))
            if avLst is None:
                avLst = geom.makeelement(qn('a:avLst'), {})
                geom.append(avLst)
            for ch in list(avLst):
                avLst.remove(ch)
            for nm, val in (('adj1', '5400000'), ('adj2', '16200000')):
                avLst.append(avLst.makeelement(qn('a:gd'), {'name': nm, 'fmla': 'val ' + val}))
        else:                       # 예정 — 흰색 + 검정 테두리
            d = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, dia, dia)
            d.fill.solid()
            d.fill.fore_color.rgb = COLORS['white']
            d.line.color.rgb = _BLACK
            d.line.width = Pt(1.25)
            d.shadow.inherit = False
        # 라벨 (노드 위)
        lb, lf = _progress_textbox(slide, Emu(int(cx) - int(Cm(1.55))),
                                   tl_y - Cm(1.70), Cm(3.10), Cm(1.15),
                                   anchor=MSO_ANCHOR.BOTTOM, wrap=True)
        p = lf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        _p_addrun(p, lab, bold=False, size=11, color=_BLACK)
        # 날짜 (노드 아래)
        db, df = _progress_textbox(slide, Emu(int(cx) - int(Cm(1.30))),
                                   tl_y + Cm(0.25), Cm(2.60), Cm(0.45),
                                   anchor=MSO_ANCHOR.TOP, wrap=False)
        p = df.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        _p_addrun(p, dt, bold=False, size=10.5, color=_BLACK)

    return slide


# ============================================================
# 디스패처 (A4 패밀리)
# ============================================================
LAYOUT_BUILDERS_A4 = {
    'a4-cover':              build_a4_cover_slide,
    'a4-exec-kpi-dashboard': build_a4_exec_kpi_slide,
    'a4-division-scorecard': build_a4_scorecard_slide,
    'a4-meeting-minutes':    build_a4_meeting_minutes_slide,
    'a4-progress':           build_a4_progress_slide,
}


def build_slide_a4(prs, layout_type, data, logo_path=None):
    builder = LAYOUT_BUILDERS_A4.get(layout_type)
    if builder is None:
        raise ValueError(f'Unknown A4 layout: {layout_type}')
    return builder(prs, data, logo_path=logo_path)
