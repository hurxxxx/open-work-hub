from __future__ import annotations

from collections import Counter
from datetime import datetime, time
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.i18n import localized_http_exception
from aidoo_api.core.settings import get_settings
from aidoo_api.core.telemetry import current_trace_id
from aidoo_api.domains.auth.models import Team, TeamMember, User, Workspace
from aidoo_api.domains.rag.access_filter import can_user_access_resource
from aidoo_api.domains.search.opensearch import OpenSearchError, OpenSearchKeywordClient
from aidoo_api.domains.search.projections import all_workspace_search_documents
from aidoo_api.domains.search.schemas import (
    ContainerFacet,
    EntityTypeFacet,
    KeywordSearchRequest,
    KeywordSearchResponse,
    SearchContainerRef,
    SearchEntityType,
    SearchFacets,
    SearchHighlight,
    SearchHit,
    SearchPerson,
    SearchSnippet,
    StatusFacet,
)


ENTITY_LABELS = {
    SearchEntityType.DOC: "문서",
    SearchEntityType.MEETING: "회의",
    SearchEntityType.PMS_ISSUE: "PMS",
    SearchEntityType.PLANNER_EVENT: "일정",
}

RESOURCE_TYPE_BY_ENTITY = {
    SearchEntityType.DOC: "docs_native_doc",
    SearchEntityType.MEETING: "meeting",
    SearchEntityType.PMS_ISSUE: "pms_issue",
    SearchEntityType.PLANNER_EVENT: "planner_event",
}

def query_workspace_keyword_search(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: KeywordSearchRequest,
) -> KeywordSearchResponse:
    if request.workspace_id and request.workspace_id != workspace.id:
        # Route workspace remains authoritative; mismatches simply cannot widen scope.
        request.workspace_id = workspace.id
    try:
        _ensure_workspace_keyword_index_ready(workspace_id=workspace.id)
        candidate_rows = _load_ranked_candidates(
            workspace_id=workspace.id,
            user_acl=_build_user_acl_scope(db, user=user, workspace_id=workspace.id),
            request=request,
        )
    except OpenSearchError as error:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="search.keyword_backend_unavailable",
            reason=str(error),
        ) from error
    accessible_rows = [
        row
        for row in candidate_rows
        if can_user_access_resource(
            db,
            user=user,
            workspace_id=str(row["workspace_id"]),
            resource_type=RESOURCE_TYPE_BY_ENTITY[SearchEntityType(str(row["entity_type"]))],
            resource_id=str(row["entity_id"]),
        )
    ]
    total = len(accessible_rows)
    page_rows = accessible_rows[request.offset : request.offset + request.limit]
    hits = [_hit_from_row(row, query=request.query) for row in page_rows]
    next_offset = request.offset + request.limit if request.offset + request.limit < total else None
    return KeywordSearchResponse(
        query=request.query,
        hits=hits,
        facets=_build_facets(accessible_rows),
        total=total,
        has_more=next_offset is not None,
        next_offset=next_offset,
        trace_id=current_trace_id(),
    )


def refresh_workspace_keyword_index(db: Session, *, workspace: Workspace) -> None:
    rows = all_workspace_search_documents(db, workspace=workspace)
    _search_client().rebuild_workspace(workspace_id=workspace.id, documents=rows)


def _ensure_workspace_keyword_index_ready(*, workspace_id: str) -> None:
    client = _search_client()
    if not client.index_exists():
        raise OpenSearchError("Keyword search index is not initialized. Run keyword search backfill first.")
    if client.count_workspace_documents(workspace_id=workspace_id) == 0:
        raise OpenSearchError("Keyword search index is empty for this workspace. Run keyword search backfill first.")


def _load_ranked_candidates(
    *,
    workspace_id: str,
    user_acl: dict[str, Any],
    request: KeywordSearchRequest,
) -> list[dict[str, Any]]:
    query_text = request.query.strip()
    filters: list[dict[str, Any]] = [{"term": {"workspace_id": workspace_id}}]
    if request.entity_types:
        filters.append({"terms": {"entity_type": [item.value for item in request.entity_types]}})
    filters.append(_acl_filter(user_acl))

    if query_text:
        query: dict[str, Any] = {
            "bool": {
                "filter": filters,
                "must": [
                    {
                        "multi_match": {
                            "query": query_text,
                            "fields": ["title^5", "keywords^3", "summary^2", "body", "search_text"],
                            "operator": "and",
                            "type": "best_fields",
                        }
                    }
                ],
            }
        }
    else:
        query = {"bool": {"filter": filters, "must": [{"match_all": {}}]}}

    if request.sort.field == "updated_at":
        sort_spec: list[dict[str, Any]] = [
            {"source_updated_at": {"order": request.sort.direction, "unmapped_type": "date"}},
            {"_score": {"order": "desc"}},
        ]
    elif request.sort.field == "created_at":
        sort_spec = [
            {"created_at": {"order": request.sort.direction, "unmapped_type": "date"}},
            {"_score": {"order": "desc"}},
        ]
    else:
        sort_spec = [{"_score": {"order": "desc"}}, {"source_updated_at": {"order": "desc", "unmapped_type": "date"}}]

    response = _search_client().search(
        {
            "track_total_hits": True,
            "query": query,
            "sort": sort_spec,
            "size": 10000,
        }
    )
    rows: list[dict[str, Any]] = []
    for hit in response.get("hits", {}).get("hits", []):
        source = dict(hit.get("_source") or {})
        source["_search_score"] = float(hit.get("_score") or 0.0)
        if _matches_request_filters(source, request):
            rows.append(source)
    return _sort_rows(rows, request)


def _date_marker_value(value: datetime) -> str:
    return value.date().isoformat() if value.time() == time.min else value.isoformat()


def _build_user_acl_scope(db: Session, *, user: User, workspace_id: str) -> dict[str, Any]:
    team_ids = db.scalars(
        select(TeamMember.team_id)
        .join(Team, TeamMember.team_id == Team.id)
        .where(
            TeamMember.user_id == user.id,
            Team.workspace_id == workspace_id,
            Team.active.is_(True),
            Team.trashed_at.is_(None),
        )
    ).all()
    return {"user_id": user.id, "team_ids": [team_id for team_id in team_ids if team_id]}


def _acl_filter(user_acl: dict[str, Any]) -> dict[str, Any]:
    user_id = str(user_acl["user_id"])
    team_ids = [str(team_id) for team_id in user_acl.get("team_ids", []) if team_id]
    branches = [
        _entity_acl_branch(
            SearchEntityType.DOC,
            [
                {"term": {"owner_user_id": user_id}},
                {"term": {"shared_user_ids": user_id}},
                {"term": {"granted_user_ids": user_id}},
                *([{"terms": {"team_ids": team_ids}}] if team_ids else []),
            ],
        ),
        _entity_acl_branch(
            SearchEntityType.MEETING,
            [
                {"term": {"owner_user_id": user_id}},
                {"term": {"participant_user_ids": user_id}},
            ],
        ),
        _entity_acl_branch(
            SearchEntityType.PMS_ISSUE,
            [
                {"term": {"granted_user_ids": user_id}},
                *([{"terms": {"team_ids": team_ids}}] if team_ids else []),
            ],
        ),
        _entity_acl_branch(
            SearchEntityType.PLANNER_EVENT,
            [
                {"term": {"owner_user_id": user_id}},
                {"term": {"visibility": "public"}},
            ],
        ),
    ]
    return {"bool": {"should": branches, "minimum_should_match": 1}}


def _entity_acl_branch(entity_type: SearchEntityType, clauses: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "bool": {
            "filter": [{"term": {"entity_type": entity_type.value}}],
            "should": clauses,
            "minimum_should_match": 1,
        }
    }


def _matches_request_filters(row: dict[str, Any], request: KeywordSearchRequest) -> bool:
    if request.entity_types and row.get("entity_type") not in {item.value for item in request.entity_types}:
        return False
    for entity_type, statuses in request.status_by_type.items():
        if statuses and row.get("entity_type") == entity_type.value and row.get("status") not in statuses:
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
    if request.container_refs:
        wanted_keys = {f"{item.type}:{item.id}" for item in request.container_refs}
        if not wanted_keys.intersection(set(row.get("container_keys") or [])):
            return False
    for date_filter in request.date_filters:
        value = _row_date_value(row, date_filter.field)
        if not value:
            return False
        if date_filter.from_ is not None and value < _date_marker_value(date_filter.from_):
            return False
        if date_filter.to is not None and value > _date_marker_value(date_filter.to):
            return False
    return True


def _row_date_value(row: dict[str, Any], field: str) -> str | None:
    if field == "updated_at":
        value = row.get("source_updated_at")
    elif field == "created_at":
        value = row.get("created_at")
    else:
        value = (row.get("date_markers") or {}).get(field)
    return str(value) if value else None


def _sort_rows(rows: list[dict[str, Any]], request: KeywordSearchRequest) -> list[dict[str, Any]]:
    if request.sort.field == "updated_at":
        return sorted(
            rows,
            key=lambda row: (str(row.get("source_updated_at") or ""), float(row.get("_search_score") or 0.0)),
            reverse=request.sort.direction == "desc",
        )
    if request.sort.field == "created_at":
        return sorted(
            rows,
            key=lambda row: (str(row.get("created_at") or ""), float(row.get("_search_score") or 0.0)),
            reverse=request.sort.direction == "desc",
        )
    return sorted(
        rows,
        key=lambda row: (float(row.get("_search_score") or 0.0), str(row.get("source_updated_at") or "")),
        reverse=True,
    )


def _search_client() -> OpenSearchKeywordClient:
    settings = get_settings()
    return OpenSearchKeywordClient(base_url=settings.opensearch_url, index_prefix=settings.opensearch_index_prefix)


def _build_facets(rows: list[dict[str, Any]]) -> SearchFacets:
    entity_counts = Counter(str(row.get("entity_type") or "") for row in rows)
    status_counts: Counter[tuple[str, str, str]] = Counter()
    container_counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        if row.get("status"):
            status_counts[(str(row["entity_type"]), str(row["status"]), str(row.get("status_label") or row["status"]))] += 1
        for container in row.get("containers") or []:
            container_counts[
                (
                    str(container.get("type") or ""),
                    str(container.get("id") or ""),
                    str(container.get("label") or container.get("id") or ""),
                )
            ] += 1

    return SearchFacets(
        entity_types=[
            EntityTypeFacet(value=entity_type, label=ENTITY_LABELS[entity_type], count=entity_counts[entity_type.value])
            for entity_type in SearchEntityType
            if entity_counts[entity_type.value] > 0
        ],
        status=[
            StatusFacet(entity_type=SearchEntityType(entity_type), value=value, label=label, count=count)
            for (entity_type, value, label), count in sorted(status_counts.items())
        ],
        containers=[
            ContainerFacet(type=kind, id=item_id, label=label, count=count)
            for (kind, item_id, label), count in sorted(container_counts.items())
            if kind and item_id
        ],
    )


def _hit_from_row(row: dict[str, Any], *, query: str) -> SearchHit:
    return SearchHit(
        entity_type=SearchEntityType(str(row["entity_type"])),
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
        containers=[SearchContainerRef.model_validate(item) for item in row.get("containers") or []],
        deep_link=str(row["deep_link"]),
        preview_url=row.get("preview_url"),
        metadata=dict(row.get("metadata") or {}),
    )


def _build_snippet(row: dict[str, Any], *, query: str) -> SearchSnippet:
    source = str(row.get("summary") or row.get("body") or row.get("title") or "")
    text_value = " ".join(source.split())[:420]
    lowered = text_value.lower()
    highlights: list[SearchHighlight] = []
    for token in [part for part in query.lower().split() if part]:
        start = lowered.find(token)
        if start >= 0:
            highlights.append(SearchHighlight(start=start, end=start + len(token)))
            break
    return SearchSnippet(text=text_value, highlights=highlights)
