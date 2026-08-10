from __future__ import annotations

import re


_TOKEN_RE = re.compile(r"[0-9a-zA-Z][0-9a-zA-Z_.:/#-]*|[가-힣]+")
_HANGUL_RE = re.compile(r"^[가-힣]+$")


def build_korean_sparse_terms(text: str) -> dict[str, float]:
    terms: dict[str, float] = {}
    for token in tokenize_sparse_terms(text):
        terms[token] = terms.get(token, 0.0) + 1.0
    return terms


def tokenize_sparse_terms(text: str) -> list[str]:
    terms: list[str] = []
    for match in _TOKEN_RE.finditer(text.casefold()):
        token = match.group(0).strip()
        if not token:
            continue
        terms.append(token)
        if _HANGUL_RE.fullmatch(token):
            terms.extend(_hangul_ngrams(token, 2))
            terms.extend(_hangul_ngrams(token, 3))
    return terms


def _hangul_ngrams(token: str, size: int) -> list[str]:
    if len(token) <= size:
        return []
    return [token[index : index + size] for index in range(0, len(token) - size + 1)]
