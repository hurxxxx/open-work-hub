from __future__ import annotations

from collections import Counter
from datetime import datetime, time
from typing import Any
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.core.settings import get_settings
from aidoo_api.core.telemetry import current_trace_id
from aidoo_api.domains.auth.models import Team, User, Workspace
from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.meeting.models import Meeting, MeetingAttendee, MeetingRecording
from aidoo_api.domains.pms.models import Issue, IssueComment, IssueLabel, TaskList, TaskListStatus
from aidoo_api.domains.planner.models import PlannerEvent
from aidoo_api.domains.rag.access_filter import can_user_access_resource
from aidoo_api.domains.search.opensearch import OpenSearchError, OpenSearchKeywordClient
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

DEFAULT_PMS_STATUS_LABELS = {
    "backlog": "Backlog",
    "todo": "Todo",
    "in_progress": "In Progress",
    "done": "Done",
    "canceled": "Canceled",
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
        refresh_workspace_keyword_index(db, workspace=workspace)
        candidate_rows = _load_ranked_candidates(workspace_id=workspace.id, request=request)
    except OpenSearchError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
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
    rows = [
        *_doc_rows(db, workspace),
        *_meeting_rows(db, workspace),
        *_pms_issue_rows(db, workspace),
        *_planner_event_rows(db, workspace),
    ]
    _search_client().rebuild_workspace(workspace_id=workspace.id, documents=rows)


def _load_ranked_candidates(
    *,
    workspace_id: str,
    request: KeywordSearchRequest,
) -> list[dict[str, Any]]:
    query_text = request.query.strip()
    filters: list[dict[str, Any]] = [{"term": {"workspace_id": workspace_id}}]
    if request.entity_types:
        filters.append({"terms": {"entity_type": [item.value for item in request.entity_types]}})

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


def _doc_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    docs = db.scalars(
        select(NativeDoc)
        .options(selectinload(NativeDoc.owner), selectinload(NativeDoc.pages), selectinload(NativeDoc.containers))
        .where(NativeDoc.workspace_id == workspace.id, NativeDoc.trashed_at.is_(None))
    ).all()
    rows: list[dict[str, Any]] = []
    for doc in docs:
        body_parts = []
        for page in doc.pages:
            if page.trashed_at is not None:
                continue
            body_parts.append(page.title)
            body_parts.append(_extract_blocks_text(page.content_blocks))
        containers = [
            {
                "type": container.container_type,
                "id": container.container_id,
                "label": _container_label(container.container_type, container.container_id),
            }
            for container in doc.containers
        ]
        rows.append(
            _row(
                workspace_id=workspace.id,
                entity_type=SearchEntityType.DOC,
                entity_id=doc.id,
                title=doc.title,
                summary=_trim(" ".join(part for part in body_parts if part), 240),
                body="\n".join(part for part in body_parts if part),
                keywords=" ".join([doc.source_kind, doc.source_app, getattr(doc.owner, "full_name", "") or ""]),
                status=None,
                status_label=None,
                visibility="shared" if doc.user_shares or doc.link_shares else "private",
                people=[_person("owner", doc.owner_id, getattr(doc.owner, "full_name", None))],
                containers=containers,
                date_markers={},
                deep_link=f"/w/{workspace.key}/docs/{doc.id}",
                metadata={"source_kind": doc.source_kind, "source_ref": doc.source_ref},
                source_updated_at=doc.updated_at,
            )
        )
    return rows


def _meeting_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    meetings = db.scalars(
        select(Meeting)
        .options(selectinload(Meeting.organizer), selectinload(Meeting.attendees).selectinload(MeetingAttendee.user))
        .where(Meeting.workspace_id == workspace.id)
    ).all()
    rows: list[dict[str, Any]] = []
    for meeting in meetings:
        recording = db.scalar(
            select(MeetingRecording)
            .where(MeetingRecording.meeting_id == meeting.id)
            .order_by(MeetingRecording.created_at.desc())
        )
        attendees = [
            _person("participant", attendee.user_id, getattr(attendee.user, "full_name", None))
            for attendee in meeting.attendees
        ]
        body = "\n".join(
            part
            for part in [
                meeting.agenda,
                recording.summary_text if recording else "",
                recording.transcript_text if recording else "",
            ]
            if part
        )
        rows.append(
            _row(
                workspace_id=workspace.id,
                entity_type=SearchEntityType.MEETING,
                entity_id=meeting.id,
                title=meeting.title,
                summary=_trim(recording.summary_text if recording else meeting.agenda, 240),
                body=body,
                keywords=" ".join([meeting.status, getattr(meeting.organizer, "full_name", "") or ""]),
                status=meeting.status,
                status_label=_labelize(meeting.status),
                visibility="workspace",
                people=[_person("owner", meeting.organizer_id, getattr(meeting.organizer, "full_name", None)), *attendees],
                containers=[],
                date_markers={"event_start_at": meeting.start_at.isoformat(), "start_date": meeting.start_at.date().isoformat()},
                deep_link=f"/w/{workspace.key}/meeting/{meeting.id}",
                metadata={"attendee_count": len(meeting.attendees)},
                source_updated_at=meeting.updated_at,
            )
        )
    return rows


def _pms_issue_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    issues = db.scalars(
        select(Issue)
        .options(
            selectinload(Issue.task_list).selectinload(TaskList.statuses),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments).selectinload(IssueComment.author),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
        )
        .join(TaskList, Issue.list_id == TaskList.id)
        .join(Team, TaskList.team_id == Team.id)
        .where(Team.workspace_id == workspace.id, Issue.archived.is_(False))
    ).all()
    rows: list[dict[str, Any]] = []
    for issue in issues:
        task_list = issue.task_list
        status_label = _pms_status_label(issue.status, task_list.statuses if task_list else [])
        label_names = [link.label.name for link in issue.label_links if link.label is not None]
        body = "\n".join(
            part
            for part in [
                issue.description,
                _extract_blocks_text(issue.description_blocks),
                " ".join(comment.body for comment in issue.comments),
                " ".join(label_names),
            ]
            if part
        )
        containers = [
            {"type": "list", "id": issue.list_id, "label": getattr(task_list, "name", None) or issue.list_id}
        ]
        people = [_person("owner", issue.reporter_id, getattr(issue.reporter, "full_name", None))]
        if issue.assignee_id:
            people.append(_person("assignee", issue.assignee_id, getattr(issue.assignee, "full_name", None)))
        rows.append(
            _row(
                workspace_id=workspace.id,
                entity_type=SearchEntityType.PMS_ISSUE,
                entity_id=issue.id,
                title=issue.title,
                summary=_trim(issue.description or " ".join(label_names), 240),
                body=body,
                keywords=" ".join([issue.status, issue.priority, status_label, getattr(task_list, "name", "") or "", *label_names]),
                status=issue.status,
                status_label=status_label,
                visibility="workspace",
                people=people,
                containers=containers,
                date_markers={
                    "start_date": issue.start_date.isoformat() if issue.start_date else None,
                    "due_date": issue.due_date.isoformat() if issue.due_date else None,
                },
                deep_link=f"/tool/pms-list-{issue.list_id}?workspace={workspace.key}&issue={issue.id}",
                metadata={"list_id": issue.list_id, "issue_number": issue.issue_number, "priority": issue.priority},
                source_updated_at=issue.updated_at,
            )
        )
    return rows


def _planner_event_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    events = db.scalars(
        select(PlannerEvent)
        .options(selectinload(PlannerEvent.owner))
        .where(PlannerEvent.workspace_id == workspace.id)
    ).all()
    rows: list[dict[str, Any]] = []
    for event in events:
        rows.append(
            _row(
                workspace_id=workspace.id,
                entity_type=SearchEntityType.PLANNER_EVENT,
                entity_id=event.id,
                title=event.title,
                summary=_trim(" | ".join(part for part in [event.description, event.location] if part), 240),
                body="\n".join(part for part in [event.description, event.location] if part),
                keywords=" ".join([event.visibility, event.location, getattr(event.owner, "full_name", "") or ""]),
                status=event.visibility,
                status_label="공개" if event.visibility == "public" else "비공개",
                visibility=event.visibility,
                people=[_person("owner", event.owner_id, getattr(event.owner, "full_name", None))],
                containers=[],
                date_markers={
                    "event_start_at": event.start_at.isoformat(),
                    "start_date": event.start_at.date().isoformat(),
                },
                deep_link=f"/w/{workspace.key}/planner?event={event.id}",
                metadata={"location": event.location, "all_day": event.all_day},
                source_updated_at=event.updated_at,
            )
        )
    return rows


def _row(
    *,
    workspace_id: str,
    entity_type: SearchEntityType,
    entity_id: str,
    title: str,
    summary: str,
    body: str,
    keywords: str,
    status: str | None,
    status_label: str | None,
    visibility: str | None,
    people: list[dict[str, str]],
    containers: list[dict[str, str]],
    date_markers: dict[str, Any],
    deep_link: str,
    metadata: dict[str, Any],
    source_updated_at: datetime,
) -> dict[str, Any]:
    search_text = _weighted_search_text(title=title, keywords=keywords, summary=summary, body=body)
    return {
        "id": str(uuid.uuid4()),
        "workspace_id": workspace_id,
        "entity_type": entity_type.value,
        "entity_id": entity_id,
        "title": title or "Untitled",
        "summary": summary or "",
        "body": body or "",
        "keywords": keywords or "",
        "search_text": search_text,
        "status": status,
        "status_label": status_label,
        "visibility": visibility,
        "people": [person for person in people if person["user_id"]],
        "containers": containers,
        "container_keys": [f"{item['type']}:{item['id']}" for item in containers],
        "date_markers": {key: value for key, value in date_markers.items() if value is not None},
        "deep_link": deep_link,
        "preview_url": None,
        "metadata": metadata,
        "rank_boost": 0.0,
        "source_updated_at": source_updated_at.isoformat(),
        "created_at": source_updated_at.isoformat(),
    }


def _person(role: str, user_id: str | None, label: str | None) -> dict[str, str]:
    return {"role": role, "user_id": user_id or "", "label": label or "Unknown"}


def _pms_status_label(slug: str, statuses: list[TaskListStatus]) -> str:
    for task_status in statuses:
        if task_status.slug == slug:
            return task_status.name
    return DEFAULT_PMS_STATUS_LABELS.get(slug, _labelize(slug))


def _labelize(value: str) -> str:
    return value.replace("_", " ").title()


def _container_label(kind: str, item_id: str) -> str:
    return f"{kind}:{item_id}"


def _trim(value: str | None, max_chars: int) -> str:
    normalized = " ".join((value or "").split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _extract_blocks_text(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""
    parts: list[str] = []
    for block in blocks:
        _collect_text_parts(block, parts)
    return " ".join(parts)


def _collect_text_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        if normalized:
            parts.append(normalized)
        return
    if isinstance(value, list):
        for item in value:
            _collect_text_parts(item, parts)
        return
    if isinstance(value, dict):
        text_value = value.get("text")
        if isinstance(text_value, str) and text_value.strip():
            parts.append(" ".join(text_value.split()))
        for key in ("content", "children"):
            if key in value:
                _collect_text_parts(value[key], parts)


def _weighted_search_text(*, title: str, keywords: str, summary: str, body: str) -> str:
    # Repeat higher-signal fields so ngram scoring still favors object titles.
    return " ".join(
        part
        for part in [
            title,
            title,
            title,
            title,
            title,
            keywords,
            keywords,
            keywords,
            summary,
            summary,
            body,
        ]
        if part
    )
