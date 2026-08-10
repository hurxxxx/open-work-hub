from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from open_alm_api.domains.meal_invoice_ocr.state import (
    _as_list,
    mutate_state,
    read_state_field,
)

# 품명 사전(자동 교정용). 워크스페이스별 정규 품명 목록을 DB 행(vocab_json)에 둔다.
# 시드(엑셀 등에서 가져온 품명) + 사람이 '확인'한 교정 품명이 누적되며 성장한다.
_MAX = 5000

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


def load_vocab(workspace_id: str) -> list[str]:
    return [str(x) for x in _as_list(read_state_field(workspace_id, "vocab_json", []))]


def add_names(workspace_id: str, names: list[str]) -> int:
    """정규 품명들을 사전에 합집합으로 추가하고 총 개수를 돌려준다(DB 행 잠금으로 원자적)."""
    cleaned = [n.strip() for n in names if n and n.strip()]
    if not cleaned:
        return len(load_vocab(workspace_id))

    def _apply(state: Any) -> int:
        existing = [str(x) for x in _as_list(state.vocab_json)]
        seen = set(existing)
        for n in cleaned:
            if n not in seen:
                existing.append(n)
                seen.add(n)
        existing = existing[-_MAX:]
        state.vocab_json = existing
        return len(existing)

    return mutate_state(workspace_id, _apply)


def _jamo(text: str) -> str:
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            i = code - 0xAC00
            out.append(_CHO[i // 588])
            out.append(_JUNG[(i % 588) // 28])
            jong = _JONG[i % 28]
            if jong != " ":
                out.append(jong)
        elif not ch.isspace():
            out.append(ch)
    return "".join(out)


def _norm(text: str) -> str:
    # 매칭 안정화를 위해 한글/영숫자만 남긴다(괄호·공백·기호 제거).
    return re.sub(r"[^가-힣A-Za-z0-9]", "", str(text or ""))


def _score(a: str, b: str) -> float:
    return SequenceMatcher(None, _jamo(_norm(a)), _jamo(_norm(b))).ratio()


def initials(text: str) -> str:
    """한글 초성 열을 돌려준다(비한글 문자는 그대로 유지).

    같은 손글씨를 달리 읽은 오독 변형은 초성이 대체로 보존되지만('고칫갸루'↔'고찻가루'),
    서로 다른 짧은 품목은 초성이 갈린다('부추' ㅂㅊ ↔ '후추' ㅎㅊ). 2~3음절 한글 품명에서는
    자모 유사도만으로 이 둘을 가를 수 없어(부추↔후추 0.75 > 고춧가루 임계값) 초성 열을 보조
    판별자로 쓴다.
    """
    out: list[str] = []
    for ch in _norm(text):
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            out.append(_CHO[(code - 0xAC00) // 588])
        else:
            out.append(ch)
    return "".join(out)


def best_match(name: str, vocab: list[str]) -> tuple[str, float]:
    """사전에서 가장 유사한 품명과 점수(0~1)를 돌려준다. 사전이 비면 ('', 0)."""
    target = _norm(name)
    if not target or not vocab:
        return ("", 0.0)
    best = ""
    best_score = 0.0
    for candidate in vocab:
        s = _score(name, candidate)
        if s > best_score:
            best_score = s
            best = candidate
    return (best, best_score)


# 첫 음절이 같은 '헷갈리는 대안' 후보의 최소 유사도. 너무 낮으면 무관한 품목까지 칩이 떠 노이즈가 되고,
# 너무 높으면 양파(2음절)↔양상추(3음절)처럼 길이가 다른 실제 혼동쌍을 놓친다.
_CONFUSABLE_MIN = 0.55


def confusable_alt(name: str, vocab: list[str]) -> tuple[str, float]:
    """읽은 품명이 사전에 그대로 있어도, 첫 글자가 같고 충분히 비슷한 '다른' 사전 품명이 있으면 그 대안을 돌려준다.

    양파↔양상추처럼 첫 음절이 같은 오독은 결과가 실재하는 정상 품명이라 best_match 제안이 침묵한다.
    이때 검수자가 원클릭으로 뒤집도록 대안 칩을 제안하기 위한 함수다(값은 바꾸지 않는다, 제안만).
    조건: (1) 읽은 품명이 사전에 정확히 존재(정상 품명으로 읽힘), (2) 첫 글자가 같은 '다른' 후보,
    (3) 유사도 >= _CONFUSABLE_MIN. 없으면 ('', 0). 읽은 품명이 사전에 없으면 best_match 가 이미
    담당하므로 여기선 대안을 내지 않는다.
    """
    target = _norm(name)
    if not target or not vocab:
        return ("", 0.0)
    if not any(_norm(candidate) == target for candidate in vocab):
        return ("", 0.0)
    first = target[0]
    best = ""
    best_score = 0.0
    for candidate in vocab:
        cnorm = _norm(candidate)
        if not cnorm or cnorm == target or cnorm[0] != first:
            continue
        s = _score(name, candidate)
        if s > best_score:
            best_score = s
            best = candidate
    if best_score >= _CONFUSABLE_MIN:
        return (best, best_score)
    return ("", 0.0)
