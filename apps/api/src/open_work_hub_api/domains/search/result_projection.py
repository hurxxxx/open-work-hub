from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from open_work_hub_api.domains.pms.links import normalize_pms_deep_link
from open_work_hub_api.domains.search.schemas import (
    TargetFacet,
    EntityTypeFacet,
    KeywordSearchRequest,
    KeywordSearchResponse,
    SearchTargetRef,
    SearchFacets,
    SearchHighlight,
    SearchHit,
    SearchPerson,
    SearchSnippet,
    StatusFacet,
)
from open_work_hub_api.domains.search.default_entity_adapters import (
    ensure_search_entity_descriptors_registered,
)
from open_work_hub_api.domains.search.entity_registry import (
    label_for_search_entity,
    search_entity_descriptors,
)
from open_work_hub_api.domains.search.schemas import SearchEntityType

DocPageLookup = Callable[[str], list[dict[str, Any]]]
_SNIPPET_MAX_CHARS = 420
_SNIPPET_CONTEXT_BEFORE = 120
_SNIPPET_QUERY_TOKEN_LIMIT = 24


def project_keyword_search_response(
    accessible_rows: Sequence[dict[str, Any]],
    page_rows: Sequence[dict[str, Any]],
    *,
    request: KeywordSearchRequest,
    trace_id: str | None,
    doc_page_lookup: DocPageLookup,
) -> KeywordSearchResponse:
    total = len(accessible_rows)
    next_offset = request.offset + request.limit if request.offset + request.limit < total else None
    return KeywordSearchResponse(
        query=request.query,
        hits=[
            build_search_hit(row, query=request.query, doc_page_lookup=doc_page_lookup)
            for row in page_rows
        ],
        facets=build_search_facets(accessible_rows),
        total=total,
        has_more=next_offset is not None,
        next_offset=next_offset,
        trace_id=trace_id,
    )


def build_search_facets(rows: Sequence[dict[str, Any]]) -> SearchFacets:
    ensure_search_entity_descriptors_registered()
    entity_counts = Counter(str(row.get("entity_type") or "") for row in rows)
    status_counts: Counter[tuple[str, str, str]] = Counter()
    target_counts: Counter[tuple[str | None, str, str, str]] = Counter()
    for row in rows:
        if row.get("status"):
            status_counts[
                (
                    str(row["entity_type"]),
                    str(row["status"]),
                    str(row.get("status_label") or row["status"]),
                )
            ] += 1
        for target in row.get("targets") or []:
            kind = str(target.get("type") or "")
            item_id = str(target.get("id") or "")
            if not kind or not item_id:
                continue
            target_counts[
                (
                    str(target.get("app") or "") or None,
                    kind,
                    item_id,
                    str(target.get("label") or item_id),
                )
            ] += 1

    return SearchFacets(
        entity_types=[
            EntityTypeFacet(
                value=entity_type,
                label=label_for_search_entity(entity_type),
                count=count,
            )
            for entity_type, count in _ordered_entity_counts(entity_counts)
        ],
        status=[
            StatusFacet(entity_type=entity_type, value=value, label=label, count=count)
            for (entity_type, value, label), count in sorted(status_counts.items())
        ],
        targets=[
            TargetFacet(app=app, type=kind, id=item_id, label=label, count=count)
            for (app, kind, item_id, label), count in sorted(
                target_counts.items(),
                key=_target_facet_sort_key,
            )
        ],
    )


def build_search_hit(
    row: dict[str, Any],
    *,
    query: str,
    doc_page_lookup: DocPageLookup,
) -> SearchHit:
    metadata = dict(row.get("metadata") or {})
    return SearchHit(
        entity_type=str(row["entity_type"]),
        entity_id=str(row["entity_id"]),
        workspace_id=str(row["workspace_id"]),
        title=str(row.get("title") or "Untitled"),
        summary=str(row.get("summary") or ""),
        snippet=_build_snippet(row, query=query),
        score=float(row.get("_search_score") or 0.0),
        status=row.get("status"),
        status_label=row.get("status_label"),
        visibility=row.get("visibility"),
        updated_at=row["source_updated_at"],
        created_at=row["created_at"],
        date_markers=dict(row.get("date_markers") or {}),
        people=[SearchPerson.model_validate(item) for item in row.get("people") or []],
        targets=[
            SearchTargetRef.model_validate(item) for item in row.get("targets") or []
        ],
        deep_link=_deep_link_for_row(row, query=query, doc_page_lookup=doc_page_lookup),
        preview_url=row.get("preview_url"),
        metadata=metadata,
    )


def _deep_link_for_row(
    row: dict[str, Any],
    *,
    query: str,
    doc_page_lookup: DocPageLookup,
) -> str:
    deep_link = normalize_pms_deep_link(str(row["deep_link"])) or str(row["deep_link"])
    if str(row.get("entity_type")) != SearchEntityType.DOC.value:
        return deep_link
    doc_pages = row.get("doc_pages")
    if not isinstance(doc_pages, list):
        doc_pages = doc_page_lookup(str(row["entity_id"]))
    page_id = _best_doc_page_id(doc_pages, query=query)
    return _with_query_param(deep_link, "page", page_id) if page_id else deep_link


def _best_doc_page_id(value: Any, *, query: str) -> str | None:
    if not isinstance(value, list):
        return None
    pages = [page for page in value if isinstance(page, dict) and isinstance(page.get("id"), str)]
    if not pages:
        return None

    tokens = [part.casefold() for part in query.split() if part]
    if not tokens:
        return str(pages[0]["id"])

    best_page_id: str | None = None
    best_score = 0
    for page in pages:
        haystack = f"{page.get('title') or ''} {page.get('text') or ''}".casefold()
        score = sum(1 for token in tokens if token in haystack)
        if score == len(tokens):
            return str(page["id"])
        if score > best_score:
            best_score = score
            best_page_id = str(page["id"])

    return best_page_id or str(pages[0]["id"])


def _with_query_param(url: str, key: str, value: str | None) -> str:
    if not value:
        return url
    parts = urlsplit(url)
    query = [
        (item_key, item_value)
        for item_key, item_value in parse_qsl(parts.query, keep_blank_values=True)
        if item_key != key
    ]
    query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _build_snippet(row: dict[str, Any], *, query: str) -> SearchSnippet:
    sources = [
        ("summary", str(row.get("summary") or "")),
        ("body", str(row.get("body") or "")),
        ("keywords", str(row.get("keywords") or "")),
        ("title", str(row.get("title") or "")),
    ]
    tokens = _snippet_query_tokens(query)
    text_value = _best_snippet_window(sources, query=query, tokens=tokens)
    highlights: list[SearchHighlight] = []
    for token in tokens:
        match = re.search(re.escape(token), text_value, flags=re.IGNORECASE)
        if match is not None:
            highlights.append(
                SearchHighlight(
                    start=_utf16_offset(text_value, match.start()),
                    end=_utf16_offset(text_value, match.end()),
                )
            )
            break
    return SearchSnippet(text=text_value, highlights=highlights)


def _best_snippet_window(
    sources: list[tuple[str, str]],
    *,
    query: str,
    tokens: list[str],
) -> str:
    normalized_sources = [
        (field, " ".join(value.split())) for field, value in sources if value.strip()
    ]
    if not normalized_sources:
        return ""
    if not tokens:
        return normalized_sources[0][1][:_SNIPPET_MAX_CHARS]

    normalized_query = " ".join(query.split())
    phrase_pattern = re.compile(re.escape(normalized_query), flags=re.IGNORECASE)
    token_pattern = re.compile(
        "|".join(re.escape(token) for token in tokens),
        flags=re.IGNORECASE,
    )
    field_priority = {
        field: len(normalized_sources) - index
        for index, (field, _) in enumerate(normalized_sources)
    }
    best: tuple[tuple[int, int, int, int], str] | None = None
    for field, source in normalized_sources:
        anchors = _snippet_match_anchors(
            source,
            phrase_pattern=phrase_pattern,
            token_pattern=token_pattern,
            token_count=len(tokens),
        )
        for anchor in anchors:
            window = _snippet_window(source, anchor=anchor)
            coverage = sum(
                re.search(re.escape(token), window, flags=re.IGNORECASE) is not None
                for token in tokens
            )
            phrase_match = int(phrase_pattern.search(window) is not None)
            score = (
                coverage,
                phrase_match,
                field_priority[field],
                -anchor,
            )
            if best is None or score > best[0]:
                best = (score, window)
    if best is not None:
        return best[1]
    return normalized_sources[0][1][:_SNIPPET_MAX_CHARS]


def _snippet_match_anchors(
    source: str,
    *,
    phrase_pattern: re.Pattern[str],
    token_pattern: re.Pattern[str],
    token_count: int,
) -> set[int]:
    anchors: set[int] = set()
    phrase_match = phrase_pattern.search(source)
    if phrase_match is not None:
        anchors.add(phrase_match.start())
    matched_tokens: set[str] = set()
    for match in token_pattern.finditer(source):
        token = match.group(0).casefold()
        if token in matched_tokens:
            continue
        matched_tokens.add(token)
        anchors.add(match.start())
        if len(matched_tokens) == token_count:
            break
    return anchors


def _snippet_window(source: str, *, anchor: int) -> str:
    start = max(0, anchor - _SNIPPET_CONTEXT_BEFORE)
    end = min(len(source), start + _SNIPPET_MAX_CHARS)
    if end - start < _SNIPPET_MAX_CHARS:
        start = max(0, end - _SNIPPET_MAX_CHARS)
    if start > 0:
        boundary = source.find(" ", start, min(anchor, start + 40))
        if boundary >= 0:
            start = boundary + 1
    return source[start : start + _SNIPPET_MAX_CHARS]


def _snippet_query_tokens(query: str) -> list[str]:
    unique: dict[str, str] = {}
    for token in query.split():
        if token:
            unique.setdefault(token.casefold(), token)
    return sorted(
        unique.values(),
        key=lambda token: (-len(token), token.casefold()),
    )[:_SNIPPET_QUERY_TOKEN_LIMIT]


def _utf16_offset(value: str, codepoint_offset: int) -> int:
    return len(value[:codepoint_offset].encode("utf-16-le")) // 2


def _ordered_entity_counts(entity_counts: Counter[str]) -> list[tuple[str, int]]:
    descriptor_order = {
        descriptor.entity_type: index
        for index, descriptor in enumerate(search_entity_descriptors())
    }
    return [
        (entity_type, count)
        for entity_type, count in sorted(
            entity_counts.items(),
            key=lambda item: (descriptor_order.get(item[0], len(descriptor_order)), item[0]),
        )
        if entity_type and count > 0
    ]


def _target_facet_sort_key(
    item: tuple[tuple[str | None, str, str, str], int],
) -> tuple[str, str, str, str]:
    (app, kind, item_id, label), _count = item
    return (app or "", kind, item_id, label)
