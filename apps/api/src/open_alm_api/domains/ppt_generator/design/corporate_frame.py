"""Open ALM 양식(chrome) HTML 합성기.

Claude 가 만든 "본문 콘텐츠"(틀 없는 자유 디자인)를 Open ALM 표지/본문 chrome 으로 감싸
하나의 자체완결형 HTML 덱으로 합성한다. 좌표·고정문자열은 ``builders_a4.py`` / v3.9.1
디자인 시스템 §6·§7 사양과 1:1 로 맞췄다(@48px/cm).

핵심 분리:
  - Claude 는 **본문 콘텐츠만** 만든다(1244×754px 본문 칸 기준). 제목·날짜·로고·워터마크·
    저작권 같은 틀은 절대 만들지 않는다.
  - 이 모듈이 그 콘텐츠를 Open ALM 표지 1장 + 본문 N장(각: 틀 + 본문 칸에 콘텐츠)으로 감싼다.

결과 HTML 은 기존 자유 양식과 동일한 ``format:"html"`` 파이프라인(미리보기 iframe +
html_to_pptx 편집형 변환기)을 그대로 탄다. 단 캔버스가 27.517×19.05cm 라 변환 시
``slide_w_cm/slide_h_cm`` 를 함께 넘겨야 한다.
"""

from __future__ import annotations

from datetime import datetime

from open_alm_api.domains.ppt_generator.design.builders_a4 import (
    fit_title_to_box,
    title_text_width_cm,
)

# ── 캔버스/좌표 (48 px = 1 cm) ────────────────────────────────
PXCM = 48.0
SLIDE_W_CM = 27.517
SLIDE_H_CM = 19.05
SLIDE_W_PX = round(SLIDE_W_CM * PXCM)  # 1321
SLIDE_H_PX = round(SLIDE_H_CM * PXCM)  # 914

# 본문 칸 (v3.9.1 §7.3/§14.3: x 0.80~26.72, y 2.30~18.00)
BODY_X_CM = 0.80
BODY_Y_CM = 2.30
BODY_W_CM = 25.92
BODY_H_CM = 15.70
BODY_X_PX = round(BODY_X_CM * PXCM)   # 38
BODY_Y_PX = round(BODY_Y_CM * PXCM)   # 110
BODY_W_PX = round(BODY_W_CM * PXCM)   # 1244
BODY_H_PX = round(BODY_H_CM * PXCM)   # 754

_PT = PXCM * 2.54 / 72.0  # pt → px (≈1.6933)


def _pt(p: float) -> float:
    return round(p * _PT, 1)


# ── §3 고정 문자열 (절대 변경 금지) ──────────────────────────
COVER_WATERMARK_TEXT = "Open ALM  Confidential Documents"
CONFIDENTIAL_BADGE_TEXT = "Confidential"
BRAND_WATERMARK_TEXT = "Open ALM Confidential Documents"
COPYRIGHT_TEXT = (
    "Open ALM : This information is exclusive property of "
    "Open ALM. Without their consent, it may not be required or given to "
    "third parties."
)

_DEFAULT_AUTHOR = "Open ALM"
_DEFAULT_VERSION = "Ver 1"

def _esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ── 덱 전역 CSS ───────────────────────────────────────────────
def _deck_css() -> str:
    w, h = SLIDE_W_PX, SLIDE_H_PX
    return f"""
@page {{ size: {w}px {h}px; margin: 0; }}
html, body {{ margin: 0; padding: 0; background: #e9eef5; }}
body {{ font-family: 'Pretendard','Pretendard','Pretendard','Pretendard','Malgun Gothic',sans-serif; }}
.slide {{ position: relative; width: {w}px; height: {h}px; overflow: hidden;
          background: #ffffff; box-sizing: border-box; }}
.slide + .slide {{ margin-top: 24px; }}
.dw-abs {{ position: absolute; box-sizing: border-box; }}
.dw-bodyzone {{ position: absolute; left: {BODY_X_PX}px; top: {BODY_Y_PX}px;
                width: {BODY_W_PX}px; height: {BODY_H_PX}px; overflow: visible; z-index: 1; }}
.dw-bodyzone > * {{ box-sizing: border-box; }}
@media print {{
  .slide {{ break-after: page; page-break-after: always; margin: 0; }}
  body {{ background: #fff; }}
}}
"""


# ── 공통 chrome 조각 ─────────────────────────────────────────
def _confidential_badge() -> str:
    w = round(2.90 * PXCM)
    h = round(0.66 * PXCM)
    left = round((SLIDE_W_CM - 2.90 - 0.30) * PXCM)
    top = round(0.30 * PXCM)
    # 텍스트를 span 으로 감싼다 — html_to_pptx 변환기가 div 박스 전체가 아니라 글자에 딱 맞는
    # (가로·세로 가운데) 위치를 텍스트 박스로 잡게 해, pptx 에서도 배지 중앙에 정렬되도록.
    return (
        f'<div class="dw-abs" style="left:{left}px;top:{top}px;width:{w}px;height:{h}px;'
        f"border:2px solid #D7261E;border-radius:{round(0.18*h)}px;background:#fff;color:#D7261E;"
        f"font-weight:700;font-size:{_pt(12)}px;display:flex;align-items:center;"
        f'justify-content:center;letter-spacing:.5px;font-family:Arial,sans-serif;">'
        f"<span>{CONFIDENTIAL_BADGE_TEXT}</span></div>"
    )


def _logo_wordmark(left_px: int, top_px: int, height_px: int) -> str:
    return (
        f'<div class="dw-abs" aria-label="Open ALM" '
        f'style="left:{left_px}px;top:{top_px}px;height:{height_px}px;display:flex;align-items:center;'
        f'color:#1B2C6B;font-weight:800;font-size:{_pt(10)}px;white-space:nowrap;">Open ALM</div>'
    )


# ── 표지 슬라이드 ─────────────────────────────────────────────
def cover_section_html(title: str, author: str, version: str, date_str: str) -> str:
    parts = [_confidential_badge()]
    # 1) 좌상 워터마크 (Arial Bold 20pt #E5E5E5)
    parts.append(
        f'<div class="dw-abs" style="left:{round(0.80*PXCM)}px;top:{round(0.45*PXCM)}px;'
        f"width:{round(22.0*PXCM)}px;height:{round(0.90*PXCM)}px;display:flex;align-items:center;"
        f"color:#E5E5E5;font-weight:700;font-size:{_pt(20)}px;white-space:pre;"
        f'font-family:Arial,sans-serif;">{_esc(COVER_WATERMARK_TEXT)}</div>'
    )
    # 3) 제목 (Bold 32pt #333) — 가급적 한 줄. 길면 폰트 축소 후 nowrap.
    _TITLE_BOX_CM = 18.30
    _t = str(title or "")
    _est = 0.0
    for _ch in _t:
        if '가' <= _ch <= '힣':
            _est += 1.10
        elif _ch.isspace():
            _est += 0.40
        elif _ch.isascii() and _ch.isalnum():
            _est += 0.55
        else:
            _est += 0.50
    # 24pt 기본. 제목은 프롬프트에서 짧게 생성됨. 혹시 길면 "…" 없이 살짝만 축소(최소 17pt). ×1.10 보정.
    title_pt = 24.0
    _w_at_base = _est * (title_pt / 32.0) * 1.10
    if _w_at_base > _TITLE_BOX_CM:
        title_pt = max(17.0, title_pt * (_TITLE_BOX_CM / _w_at_base))
    parts.append(
        f'<div class="dw-abs" style="left:{round(1.50*PXCM)}px;top:{round(6.20*PXCM)}px;'
        f"width:{round(_TITLE_BOX_CM*PXCM)}px;height:{round(1.80*PXCM)}px;display:flex;align-items:center;"
        f"color:#333;font-weight:800;font-size:{_pt(title_pt)}px;line-height:1.1;"
        f"white-space:nowrap;overflow:hidden;\">{_esc(title)}</div>"
    )
    # 4) 긴 회색 밑줄 / 5) 짧은 밑줄
    rule_y = round(7.95 * PXCM)
    parts.append(
        f'<div class="dw-abs" style="left:{round(1.50*PXCM)}px;top:{rule_y}px;'
        f'width:{round(18.30*PXCM)}px;height:3px;background:#808080;"></div>'
    )
    parts.append(
        f'<div class="dw-abs" style="left:{round(20.20*PXCM)}px;top:{rule_y}px;'
        f'width:{round(5.20*PXCM)}px;height:3px;background:#808080;"></div>'
    )
    # 6) Ver 라벨
    parts.append(
        f'<div class="dw-abs" style="left:{round(20.20*PXCM)}px;top:{round(6.90*PXCM)}px;'
        f"width:{round(5.20*PXCM)}px;height:{round(0.90*PXCM)}px;display:flex;align-items:flex-end;"
        f'justify-content:center;color:#666;font-size:{_pt(16)}px;">{_esc(version)}</div>'
    )
    # 7) 날짜 (Bold 22pt)
    parts.append(
        f'<div class="dw-abs" style="left:{round(1.50*PXCM)}px;top:{round(11.90*PXCM)}px;'
        f"width:{round(15.0*PXCM)}px;height:{round(1.20*PXCM)}px;display:flex;align-items:center;"
        f'color:#333;font-weight:800;font-size:{_pt(22)}px;">{_esc(date_str)}</div>'
    )
    # 8) 작성자 (Bold 32pt)
    parts.append(
        f'<div class="dw-abs" style="left:{round(1.50*PXCM)}px;top:{round(14.20*PXCM)}px;'
        f"width:{round(20.0*PXCM)}px;height:{round(1.80*PXCM)}px;display:flex;align-items:center;"
        f'color:#333;font-weight:800;font-size:{_pt(32)}px;">{_esc(author)}</div>'
    )
    # 9) 우하단 로고 (h=0.69cm)
    logo_h = round(0.69 * PXCM)
    logo_top = SLIDE_H_PX - logo_h - round(0.30 * PXCM)
    right = round(0.30 * PXCM)
    parts.append(
        f'<div class="dw-abs" aria-label="Open ALM" '
        f'style="right:{right}px;top:{logo_top}px;height:{logo_h}px;display:flex;align-items:center;'
        f'color:#1B2C6B;font-weight:800;font-size:{_pt(12)}px;white-space:nowrap;">Open ALM</div>'
    )
    return '<section class="slide dw-cover">' + "".join(parts) + "</section>"


# ── 본문 슬라이드 (틀 + 본문 칸) ──────────────────────────────
def body_section_html(title: str, subtitle: str, inner_html: str, date_str: str) -> str:
    clean = str(title or "").lstrip()
    while clean.startswith("▣"):
        clean = clean[1:].lstrip()
    parts = []
    # DCC 사선 워터마크 (뒤, z-index 0)
    parts.append(
        f'<div class="dw-abs" style="left:{round(4.0*PXCM)}px;top:{round(8.60*PXCM)}px;'
        f"width:{round(20.0*PXCM)}px;height:{round(1.80*PXCM)}px;display:flex;align-items:center;"
        f"justify-content:center;color:#F0E0E0;font-weight:700;font-size:{_pt(32)}px;"
        f"font-family:Arial,sans-serif;white-space:nowrap;z-index:0;"
        f'transform:rotate(-30deg);">{_esc(BRAND_WATERMARK_TEXT)}</div>'
    )
    # S1 — ▣ 제목. 24pt 고정(자동 축소 없음). 로고(x=22.50)/배지 앞에서 끝나도록 박스 제한 +
    # 폭 초과 시 글자수 제한(… 말줄임)으로 우측 요소 침범 방지(네이티브 헤더와 동일 규칙).
    _TITLE_BOX_CM = 21.50
    title_pt = 24.0
    clean, _ = fit_title_to_box(
        clean, title_text_width_cm(_TITLE_BOX_CM), base_pt=int(title_pt), min_pt=int(title_pt)
    )
    parts.append(
        f'<div class="dw-abs" style="left:{round(0.70*PXCM)}px;top:{round(0.30*PXCM)}px;'
        f"width:{round(_TITLE_BOX_CM*PXCM)}px;height:{round(1.30*PXCM)}px;display:flex;align-items:center;"
        f"gap:8px;color:#1A1A1A;font-weight:800;font-size:{_pt(title_pt)}px;white-space:nowrap;"
        f"overflow:hidden;z-index:2;\">▣ {_esc(clean)}</div>"
    )
    parts.append(_confidential_badge())
    # L1 — 날짜 (우상, 우측정렬 10pt)
    parts.append(
        f'<div class="dw-abs" style="left:{round(24.50*PXCM)}px;top:{round(1.30*PXCM)}px;'
        f"width:{round(2.45*PXCM)}px;height:{round(0.60*PXCM)}px;display:flex;align-items:center;"
        f'justify-content:flex-end;color:#000;font-size:{_pt(10)}px;white-space:nowrap;z-index:2;">'
        f"{_esc(date_str)}</div>"
    )
    # L2a/L2b — 분할 가로선
    rule_y = round(1.85 * PXCM)
    parts.append(
        f'<div class="dw-abs" style="left:0;top:{rule_y}px;width:{round(22.40*PXCM)}px;'
        f'height:5px;background:#808080;z-index:2;"></div>'
    )
    parts.append(
        f'<div class="dw-abs" style="left:{round(24.86*PXCM)}px;top:{rule_y}px;'
        f'width:{round((SLIDE_W_CM-24.86)*PXCM)}px;height:5px;background:#808080;z-index:2;"></div>'
    )
    # L3 — 로고 (gap 안)
    logo = _logo_img(round(22.50 * PXCM), round(1.65 * PXCM), round(0.40 * PXCM))
    if logo:
        parts.append(logo.replace('class="dw-abs"', 'class="dw-abs" data-z', 1))
        # z-index 보정
        parts[-1] = parts[-1].replace("width:auto;", "width:auto;z-index:2;")
    # L5 — 하단 저작권 (Arial 7pt #C8C8C8)
    parts.append(
        f'<div class="dw-abs" style="left:{round(0.80*PXCM)}px;top:{round(18.50*PXCM)}px;'
        f"width:{round(25.92*PXCM)}px;height:{round(0.45*PXCM)}px;display:flex;align-items:center;"
        f"color:#C8C8C8;font-size:{_pt(7)}px;font-family:Arial,sans-serif;white-space:nowrap;"
        f'overflow:hidden;z-index:2;">{_esc(COPYRIGHT_TEXT)}</div>'
    )
    # 본문 칸 — Claude 콘텐츠
    parts.append(f'<div class="dw-bodyzone">{inner_html}</div>')
    return '<section class="slide dw-body">' + "".join(parts) + "</section>"


# ── 전체 덱 합성 ─────────────────────────────────────────────
def compose_deck(
    *,
    title: str,
    author: str | None,
    version: str | None,
    sections: list[dict],
    body_style: str = "",
) -> str:
    """표지 1장 + 본문 N장 = 자체완결형 HTML 덱.

    sections: [{"title","subtitle","inner_html"}, ...] (Claude 본문 콘텐츠).
    body_style: Claude 가 본문에 쓴 <style> 내용(덱 head 로 끌어올림).
    """
    date_str = datetime.now().strftime("%Y.%m.%d")
    author = author or _DEFAULT_AUTHOR
    version = version or _DEFAULT_VERSION

    slides = [cover_section_html(title or "제목 미정", author, version, date_str)]
    for s in sections:
        slides.append(
            body_section_html(
                s.get("title") or "",
                s.get("subtitle") or "",
                s.get("inner_html") or "",
                date_str,
            )
        )

    head = (
        "<!DOCTYPE html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        '<link rel="stylesheet" '
        'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@latest/dist/web/static/pretendard.css">'
        f"<style>{_deck_css()}</style>"
        f"<style>{body_style}</style>"
        "</head><body>"
    )
    return head + "".join(slides) + "</body></html>"


def compose_body_only_deck(sections: list[dict], body_style: str = "") -> str:
    """본문 콘텐츠만 담은 덱 — 틀(chrome) 없이, 투명 배경, 본문 칸(BODY_W×BODY_H) 크기.

    .pptx 네이티브 합성용: html_to_pptx 가 이걸 렌더해 본문 요소만 추출하고, 틀은
    builders_a4 가 네이티브로 그린다. 배경을 투명하게 둬 DCC 워터마크가 비치게 한다.
    """
    w, h = BODY_W_PX, BODY_H_PX
    css = (
        f"@page{{size:{w}px {h}px;margin:0;}}"
        "html,body{margin:0;padding:0;background:transparent;}"
        "body{font-family:'Pretendard','Pretendard','Pretendard','Pretendard','Malgun Gothic',sans-serif;}"
        f".slide{{position:relative;width:{w}px;height:{h}px;overflow:hidden;background:transparent;"
        "box-sizing:border-box;}}"
        ".slide + .slide{margin-top:24px;}"
    )
    body = "".join(
        f'<section class="slide">{s.get("inner_html") or ""}</section>' for s in sections
    )
    head = (
        '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
        '<link rel="stylesheet" '
        'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@latest/dist/web/static/pretendard.css">'
        f"<style>{css}</style><style>{body_style}</style></head><body>"
    )
    return head + body + "</body></html>"
