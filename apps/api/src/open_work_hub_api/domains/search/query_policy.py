"""Keyword search request filtering, sorting, and backend query policy."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any, Iterable

from open_work_hub_api.domains.search.backend_contracts import (
    KeywordAclFilter,
    KeywordDateFilter,
    KeywordPeopleFilter,
    KeywordSearchQuery,
    KeywordSearchSortSpec,
    KeywordSearchTextOperator,
)
from open_work_hub_api.domains.search.schemas import KeywordSearchRequest
from open_work_hub_api.domains.search.target_keys import search_target_filter_keys

DEFAULT_KEYWORD_SEARCH_CANDIDATE_SIZE = 10000
KEYWORD_SEARCH_TEXT_FIELDS = (
    "title.exact^6",
    "title^5",
    "keywords.exact^4",
    "keywords^3",
    "summary^2",
    "title.partial^1.5",
    "keywords.partial",
    "body",
    "search_text",
    "summary.partial^0.75",
    "body.partial^0.25",
    "search_text.partial^0.25",
)


def build_keyword_search_query(
    *,
    retrieval_partition_ids: tuple[str, ...] | None = None,
    acl_filter: KeywordAclFilter | None,
    request: KeywordSearchRequest,
    size: int = DEFAULT_KEYWORD_SEARCH_CANDIDATE_SIZE,
    request_timeout_seconds: float | None = None,
    text_operator: KeywordSearchTextOperator = "and",
    text_minimum_should_match: str | int | None = None,
) -> KeywordSearchQuery:
    return KeywordSearchQuery(
        retrieval_partition_ids=retrieval_partition_ids,
        text=request.query.strip(),
        entity_types=tuple(str(item) for item in request.entity_types),
        acl_filter=acl_filter,
        status_by_type=tuple(
            (str(entity_type), tuple(str(status) for status in statuses))
            for entity_type, statuses in sorted(request.status_by_type.items())
        ),
        people=KeywordPeopleFilter(
            role=request.people.role,
            user_ids=tuple(request.people.user_ids),
        ),
        target_keys=(
            tuple(
                key
                for item in request.target_refs
                for key in search_target_filter_keys(
                    app=item.app,
                    target_type=item.type,
                    target_id=item.id,
                )
            )
            if request.target_ref_match == "any"
            else ()
        ),
        target_key_groups=(
            tuple(
                search_target_filter_keys(
                    app=item.app,
                    target_type=item.type,
                    target_id=item.id,
                )
                for item in request.target_refs
            )
            if request.target_ref_match == "all"
            else ()
        ),
        date_filters=tuple(
            KeywordDateFilter(
                field=date_filter.field,
                from_value=(
                    _date_marker_value(date_filter.from_) if date_filter.from_ is not None else None
                ),
                to_value=(
                    _date_marker_value(date_filter.to) if date_filter.to is not None else None
                ),
            )
            for date_filter in request.date_filters
        ),
        sort=keyword_search_sort_specs(request),
        size=size,
        text_operator=text_operator,
        text_minimum_should_match=text_minimum_should_match,
        request_timeout_seconds=request_timeout_seconds,
    )


def keyword_search_sort_specs(
    request: KeywordSearchRequest,
) -> tuple[KeywordSearchSortSpec, ...]:
    if request.sort.field == "updated_at":
        return (
            KeywordSearchSortSpec(
                field="source_updated_at",
                direction=request.sort.direction,
                unmapped_type="date",
            ),
            KeywordSearchSortSpec(field="score", direction="desc"),
        )
    if request.sort.field == "created_at":
        return (
            KeywordSearchSortSpec(
                field="created_at",
                direction=request.sort.direction,
                unmapped_type="date",
            ),
            KeywordSearchSortSpec(field="score", direction="desc"),
        )
    if request.sort.field != "relevance":
        return (
            KeywordSearchSortSpec(
                field=f"date_markers.{request.sort.field}",
                direction=request.sort.direction,
                unmapped_type="date",
            ),
            KeywordSearchSortSpec(field="score", direction="desc"),
        )
    return (
        KeywordSearchSortSpec(field="score", direction="desc"),
        KeywordSearchSortSpec(
            field="source_updated_at",
            direction="desc",
            unmapped_type="date",
        ),
    )


def filter_and_sort_keyword_search_rows(
    rows: Iterable[dict[str, Any]],
    request: KeywordSearchRequest,
) -> list[dict[str, Any]]:
    return sort_keyword_search_rows(
        [row for row in rows if keyword_search_row_matches_request(row, request)],
        request,
    )


def keyword_search_row_matches_request(row: dict[str, Any], request: KeywordSearchRequest) -> bool:
    if request.entity_types and row.get("entity_type") not in {
        str(item) for item in request.entity_types
    }:
        return False
    for entity_type, statuses in request.status_by_type.items():
        if (
            statuses
            and row.get("entity_type") == str(entity_type)
            and row.get("status") not in statuses
        ):
            return False
    if request.people.user_ids:
        people = row.get("people") or []
        wanted_users = set(request.people.user_ids)
        if request.people.role == "any":
            if not any(person.get("user_id") in wanted_users for person in people):
                return False
        elif not any(
            person.get("role") == request.people.role and person.get("user_id") in wanted_users
            for person in people
        ):
            return False
    if request.target_refs:
        wanted_groups = [
            set(
                search_target_filter_keys(
                    app=item.app,
                    target_type=item.type,
                    target_id=item.id,
                )
            )
            for item in request.target_refs
        ]
        row_keys = set(row.get("target_keys") or [])
        matches = [bool(group.intersection(row_keys)) for group in wanted_groups]
        if request.target_ref_match == "all" and not all(matches):
            return False
        if request.target_ref_match == "any" and not any(matches):
            return False
    for date_filter in request.date_filters:
        value = _parse_date_marker(_row_date_value(row, date_filter.field))
        if value is None:
            return False
        if date_filter.from_ is not None and value < _normalize_datetime(date_filter.from_):
            return False
        if date_filter.to is not None and value > _normalize_datetime(date_filter.to):
            return False
    return True


def sort_keyword_search_rows(
    rows: Iterable[dict[str, Any]],
    request: KeywordSearchRequest,
) -> list[dict[str, Any]]:
    if request.sort.field == "updated_at":
        return sorted(
            rows,
            key=lambda row: (
                str(row.get("source_updated_at") or ""),
                float(row.get("_search_score") or 0.0),
            ),
            reverse=request.sort.direction == "desc",
        )
    if request.sort.field == "created_at":
        return sorted(
            rows,
            key=lambda row: (
                str(row.get("created_at") or ""),
                float(row.get("_search_score") or 0.0),
            ),
            reverse=request.sort.direction == "desc",
        )
    if request.sort.field != "relevance":
        return sorted(
            rows,
            key=lambda row: (
                str(_row_date_value(row, request.sort.field) or ""),
                float(row.get("_search_score") or 0.0),
            ),
            reverse=request.sort.direction == "desc",
        )
    return sorted(
        rows,
        key=lambda row: (
            float(row.get("_search_score") or 0.0),
            str(row.get("source_updated_at") or ""),
        ),
        reverse=True,
    )


def _date_marker_value(value: datetime) -> str:
    return _normalize_datetime(value).isoformat()


def _row_date_value(row: dict[str, Any], field: str) -> str | None:
    if field == "updated_at":
        value = row.get("source_updated_at")
    elif field == "created_at":
        value = row.get("created_at")
    else:
        value = (row.get("date_markers") or {}).get(field)
    return str(value) if value else None


def _parse_date_marker(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _normalize_datetime(parsed)


def _normalize_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
