"""PPT 자동 생성 — LLM 응답 → 검증된 슬라이드 spec 파싱.

Flask ``routes/pptgen2.py`` 의 파서를 이식했다. 코드블록/잡담을 흡수하고, 잘린 JSON을 복구하며,
layout 유효성 검사와 A4 family의 cover+body 2장 정규화를 수행한다.
"""

from __future__ import annotations

import json
import re

from open_alm_api.domains.ppt_generator.families import DEFAULT_FAMILY, resolve_family

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json_object(text: str | None) -> str:
    """LLM 응답에서 JSON 객체 부분만 추출. 코드블록·잡담 모두 흡수."""
    text = (text or "").strip()
    m = _JSON_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def try_repair_truncated_json(text: str) -> str:
    """잘린 JSON 응답을 닫기 시도 — 괄호 개수가 맞을 때까지 } / ] 추가."""
    stripped = text.rstrip()
    in_str = False
    esc = False
    stack: list[str] = []  # 문자열 밖에서 아직 닫히지 않은 여는 괄호(중첩 순서)
    for ch in stripped:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            # 문자열 값 안의 { } [ ] 는 구조가 아니므로 세지 않는다.
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
    if in_str:
        stripped += '"'
    while stripped.endswith(","):
        stripped = stripped[:-1].rstrip()
    if re.search(r":\s*$", stripped):
        stripped += " null"
    # 열린 괄호를 중첩 역순으로 닫는다(안쪽부터).
    for opener in reversed(stack):
        stripped += "}" if opener == "{" else "]"
    return stripped


def parse_slides_json(text: str, family: str = DEFAULT_FAMILY) -> list[dict]:
    """LLM 응답에서 슬라이드 JSON 추출 + 잘림/오류 복구 시도.

    반환: ``[{"layout": str, "data": dict}, ...]``. 실패 시 예외.
    """
    raw = extract_json_object(text)

    obj = None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e1:
        repaired = try_repair_truncated_json(raw)
        try:
            obj = json.loads(repaired)
        except json.JSONDecodeError:
            m = re.search(r'"slides"\s*:\s*\[(.*?)\](?:\s*[},])', repaired, re.DOTALL)
            if m:
                array_body = m.group(1)
                try:
                    obj = {"slides": json.loads("[" + array_body + "]")}
                except Exception:
                    raise e1 from None
            else:
                raise e1 from None

    slides = obj.get("slides") if isinstance(obj, dict) else None
    if not isinstance(slides, list) or not slides:
        raise ValueError('응답 JSON에 "slides" 배열이 없음')

    _, fam = resolve_family(family)
    valid_layouts = set(fam["builders"].keys())
    fallback_layout = (
        fam["body_layouts"][0] if fam["body_layouts"] else fam["cover_layout"]
    )

    cleaned: list[dict] = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        layout = s.get("layout") or s.get("type") or fallback_layout
        if layout not in valid_layouts:
            layout = fallback_layout
        data = s.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        cleaned.append({"layout": layout, "data": data})

    if not cleaned:
        raise ValueError("유효한 슬라이드가 없음")

    # A4 패밀리는 cover + body 1장 = 2장으로 강제 정규화
    if not fam.get("multi_body", True):
        cover_layout = fam["cover_layout"]
        body_layout = fam["body_layouts"][0]
        cover = next((x for x in cleaned if x["layout"] == cover_layout), None)
        body = next((x for x in cleaned if x["layout"] == body_layout), None)
        if cover is None:
            cover = {"layout": cover_layout, "data": {}}
        if body is None:
            non_cover = [x for x in cleaned if x["layout"] != cover_layout]
            if non_cover:
                body = {"layout": body_layout, "data": non_cover[0]["data"]}
            else:
                body = {"layout": body_layout, "data": {}}
        cleaned = [cover, body]

    return cleaned


def parse_json_object(text: str | None) -> dict:
    """LLM 응답에서 JSON 객체 하나 추출(코드블록·잡담 흡수 + 잘림 복구). 실패 시 예외."""
    raw = extract_json_object(text)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = json.loads(try_repair_truncated_json(raw))
    if not isinstance(obj, dict):
        raise ValueError("JSON 객체가 아님")
    return obj


_BRANDLOGY_GEOMETRY_KEYS = {"i", "type", "x", "y", "w", "h"}
_BRANDLOGY_ROLE_KEYS = {"ROLE", "SERIES_N", "COLS", "ROWS_N"}


def merge_brandlogy_layout_and_fill(
    skeleton_slides: list[dict],
    fill_obj: dict,
) -> list[dict]:
    """Claude 레이아웃 스켈레톤(기하/스타일) + Qwen 내용(인덱스별)을 병합해 최종 슬라이드 spec 생성.

    기하(type/x/y/w/h)는 스켈레톤 값을 보존하고, Qwen 이 준 내용 필드만 덮어쓴다.
    ROLE/SERIES_N/COLS/ROWS_N 같은 설계용 힌트 키는 제거한다.
    """
    fills = fill_obj.get("slides") if isinstance(fill_obj, dict) else None
    fills = fills if isinstance(fills, list) else []
    fill_by_i: dict[int, dict] = {}
    for idx, f in enumerate(fills):
        if isinstance(f, dict):
            key = f.get("i")
            fill_by_i[int(key) if isinstance(key, (int, float)) else idx] = f

    out: list[dict] = []
    for si, s in enumerate(skeleton_slides):
        data = dict(s.get("data") or {})
        f = fill_by_i.get(si) or (fills[si] if si < len(fills) and isinstance(fills[si], dict) else {})

        head = f.get("HEADLINE") or data.get("HEADLINE_ROLE") or data.get("HEADLINE") or ""
        sub = f.get("SUBTITLE") or data.get("SUBTITLE_ROLE") or data.get("SUBTITLE") or ""
        data.pop("HEADLINE_ROLE", None)
        data.pop("SUBTITLE_ROLE", None)
        data["HEADLINE"] = head
        data["SUBTITLE"] = sub

        els = data.get("ELEMENTS") if isinstance(data.get("ELEMENTS"), list) else []
        e_fills = f.get("elements") if isinstance(f.get("elements"), list) else []
        e_fill_by_i: dict[int, dict] = {}
        for k, e in enumerate(e_fills):
            if isinstance(e, dict):
                key = e.get("i")
                e_fill_by_i[int(key) if isinstance(key, (int, float)) else k] = e

        new_els: list[dict] = []
        for ei, el in enumerate(els):
            if not isinstance(el, dict):
                continue
            el = {k: v for k, v in el.items() if k not in _BRANDLOGY_ROLE_KEYS}
            ef = e_fill_by_i.get(ei) or {}
            for k, v in ef.items():
                if k in _BRANDLOGY_GEOMETRY_KEYS:
                    continue
                el[k] = v
            new_els.append(el)
        data["ELEMENTS"] = new_els
        out.append({"layout": "brandlogy", "data": data})

    if not out:
        raise ValueError("병합 결과 슬라이드가 없음")
    return out


_CORPORATE_QWEN_PATTERNS = (
    "spec_compare",
    "commonization",
    "component_grid",
    "schedule",
    "issue_table",
    "seminar_report",
    "trip_schedule",
    "bullets",
)


def parse_corporate_qwen_outline(
    text: str | None, n_body: int
) -> tuple[str, list[dict]]:
    """Open ALM(Qwen 자동) 아웃라인 응답 → (덱 제목, [{title, pattern, brief}]).

    슬라이드 수를 정확히 ``n_body`` 로 맞춘다(부족하면 bullets 로 채우고, 넘치면 자른다).
    유효하지 않은 pattern 은 bullets 로 보정.
    """
    obj = parse_json_object(text)
    deck_title = str(obj.get("title") or "").strip()
    raw = obj.get("slides")
    slides: list[dict] = []
    if isinstance(raw, list):
        for s in raw:
            if not isinstance(s, dict):
                continue
            pattern = str(s.get("pattern") or "").strip()
            if pattern not in _CORPORATE_QWEN_PATTERNS:
                pattern = "bullets"
            slides.append({
                "title": str(s.get("title") or "").strip(),
                "pattern": pattern,
                "brief": str(s.get("brief") or "").strip(),
            })
    n_body = max(1, int(n_body or 1))
    if len(slides) > n_body:
        slides = slides[:n_body]
    while len(slides) < n_body:
        slides.append({"title": "", "pattern": "bullets", "brief": ""})
    return deck_title, slides


def parse_corporate_qwen_slide(text: str | None, fallback: dict) -> dict:
    """Open ALM(Qwen 자동) 슬라이드 채움 응답 → 슬라이드 dict. 실패 시 fallback(title/pattern) 사용."""
    try:
        obj = parse_json_object(text)
    except Exception:
        obj = {}
    if not obj.get("title"):
        obj["title"] = fallback.get("title") or ""
    pattern = str(obj.get("pattern") or "").strip()
    if pattern not in _CORPORATE_QWEN_PATTERNS:
        obj["pattern"] = fallback.get("pattern") or "bullets"
    return obj


def parse_chat_edit_json(text: str | None) -> dict:
    """chat-edit 응답 파싱 — slides 키 없어도 통과. JSON 객체 하나 추출."""
    text = (text or "").strip()
    m = _JSON_BLOCK_RE.search(text)
    if m:
        text = m.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


__all__ = [
    "DEFAULT_FAMILY",
    "extract_json_object",
    "try_repair_truncated_json",
    "parse_slides_json",
    "parse_json_object",
    "merge_brandlogy_layout_and_fill",
    "parse_corporate_qwen_outline",
    "parse_corporate_qwen_slide",
    "parse_chat_edit_json",
]
