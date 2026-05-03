from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
import uuid

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.domains.auth.models import Team, Workspace
from aidoo_api.domains.docs.models import DocMeetingAccess, NativeDoc
from aidoo_api.domains.meeting.models import Meeting, MeetingAttendee, MeetingRecording
from aidoo_api.domains.pms.models import Issue, IssueComment, IssueLabel, IssueUserAccess, TaskList, TaskListStatus
from aidoo_api.domains.planner.models import PlannerEvent
from aidoo_api.domains.recording.models import Recording, RecordingContainer
from aidoo_api.domains.search.schemas import SearchEntityType


DEFAULT_PMS_STATUS_LABELS = {
    "backlog": "Backlog",
    "todo": "Todo",
    "in_progress": "In Progress",
    "done": "Done",
    "canceled": "Canceled",
}


def document_id(document: dict[str, Any]) -> str:
    return f"{document['workspace_id']}:{document['entity_type']}:{document['entity_id']}"


def all_workspace_search_documents(db: Session, *, workspace: Workspace) -> list[dict[str, Any]]:
    return [
        *_doc_rows(db, workspace),
        *_meeting_rows(db, workspace),
        *_pms_issue_rows(db, workspace),
        *_planner_event_rows(db, workspace),
    ]


def load_search_document(
    db: Session,
    *,
    entity_type: SearchEntityType | str,
    entity_id: str,
) -> dict[str, Any] | None:
    resolved_entity_type = SearchEntityType(str(entity_type))
    if resolved_entity_type == SearchEntityType.DOC:
        return load_doc_search_document(db, doc_id=entity_id)
    if resolved_entity_type == SearchEntityType.MEETING:
        return load_meeting_search_document(db, meeting_id=entity_id)
    if resolved_entity_type == SearchEntityType.PMS_ISSUE:
        return load_pms_issue_search_document(db, issue_id=entity_id)
    if resolved_entity_type == SearchEntityType.PLANNER_EVENT:
        return load_planner_event_search_document(db, event_id=entity_id)
    return None


def load_doc_search_document(db: Session, *, doc_id: str) -> dict[str, Any] | None:
    doc = db.scalar(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.containers),
            selectinload(NativeDoc.user_shares),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.meeting_access_grants),
        )
        .where(NativeDoc.id == doc_id, NativeDoc.trashed_at.is_(None))
    )
    if doc is None:
        return None
    workspace = db.scalar(select(Workspace).where(Workspace.id == doc.workspace_id, Workspace.active.is_(True)))
    if workspace is None:
        return None
    return _doc_row(db, workspace=workspace, doc=doc)


def load_meeting_search_document(db: Session, *, meeting_id: str) -> dict[str, Any] | None:
    meeting = db.scalar(
        select(Meeting)
        .options(selectinload(Meeting.organizer), selectinload(Meeting.attendees).selectinload(MeetingAttendee.user))
        .where(Meeting.id == meeting_id)
    )
    if meeting is None:
        return None
    workspace = db.scalar(select(Workspace).where(Workspace.id == meeting.workspace_id, Workspace.active.is_(True)))
    if workspace is None:
        return None
    return _meeting_row(db, workspace=workspace, meeting=meeting)


def load_pms_issue_search_document(db: Session, *, issue_id: str) -> dict[str, Any] | None:
    issue = db.scalar(
        select(Issue)
        .options(
            selectinload(Issue.task_list).selectinload(TaskList.statuses),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments).selectinload(IssueComment.author),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.user_access_grants),
        )
        .join(TaskList, Issue.list_id == TaskList.id)
        .join(Team, TaskList.team_id == Team.id)
        .where(Issue.id == issue_id, Issue.archived.is_(False))
    )
    if issue is None or issue.task_list is None or issue.task_list.team_id is None:
        return None
    workspace = db.scalar(
        select(Workspace)
        .join(Team, Team.workspace_id == Workspace.id)
        .where(Team.id == issue.task_list.team_id, Workspace.active.is_(True))
    )
    if workspace is None:
        return None
    return _pms_issue_row(workspace=workspace, issue=issue)


def load_planner_event_search_document(db: Session, *, event_id: str) -> dict[str, Any] | None:
    event = db.scalar(
        select(PlannerEvent)
        .options(selectinload(PlannerEvent.owner))
        .where(PlannerEvent.id == event_id)
    )
    if event is None:
        return None
    workspace = db.scalar(select(Workspace).where(Workspace.id == event.workspace_id, Workspace.active.is_(True)))
    if workspace is None:
        return None
    return _planner_event_row(workspace=workspace, event=event)


def _doc_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    docs = db.scalars(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.containers),
            selectinload(NativeDoc.user_shares),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.meeting_access_grants),
        )
        .where(NativeDoc.workspace_id == workspace.id, NativeDoc.trashed_at.is_(None))
    ).all()
    return [_doc_row(db, workspace=workspace, doc=doc) for doc in docs]


def _doc_row(db: Session, *, workspace: Workspace, doc: NativeDoc) -> dict[str, Any]:
    task_list_team_ids = _task_list_team_lookup(db, workspace)
    active_link_shares = [share for share in doc.link_shares if share.active]
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
    return _row(
        workspace_id=workspace.id,
        entity_type=SearchEntityType.DOC,
        entity_id=doc.id,
        title=doc.title,
        summary=_trim(" ".join(part for part in body_parts if part), 240),
        body="\n".join(part for part in body_parts if part),
        keywords=" ".join([doc.source_kind, doc.source_app, getattr(doc.owner, "full_name", "") or ""]),
        status=None,
        status_label=None,
        visibility="shared" if doc.user_shares or active_link_shares else "private",
        people=[_person("owner", doc.owner_id, getattr(doc.owner, "full_name", None))],
        containers=containers,
        owner_user_id=doc.owner_id,
        team_ids=_container_team_ids(containers, task_list_team_ids),
        participant_user_ids=[],
        shared_user_ids=[share.user_id for share in doc.user_shares],
        granted_user_ids=_active_doc_grant_user_ids(doc.meeting_access_grants),
        date_markers={},
        deep_link=f"/w/{workspace.key}/docs/{doc.id}",
        metadata={"source_kind": doc.source_kind, "source_ref": doc.source_ref},
        source_updated_at=doc.updated_at,
    )


def _meeting_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    meetings = db.scalars(
        select(Meeting)
        .options(selectinload(Meeting.organizer), selectinload(Meeting.attendees).selectinload(MeetingAttendee.user))
        .where(Meeting.workspace_id == workspace.id)
    ).all()
    return [_meeting_row(db, workspace=workspace, meeting=meeting) for meeting in meetings]


def _meeting_row(db: Session, *, workspace: Workspace, meeting: Meeting) -> dict[str, Any]:
    recording = _latest_meeting_recording_for_search(db, meeting=meeting)
    recording_summary = (getattr(recording, "summary_text", None) or "").strip()
    attendees = [
        _person("participant", attendee.user_id, getattr(attendee.user, "full_name", None))
        for attendee in meeting.attendees
    ]
    body = "\n".join(
        part
        for part in [
            meeting.agenda,
            recording_summary,
            recording.transcript_text if recording else "",
        ]
        if part
    )
    return _row(
        workspace_id=workspace.id,
        entity_type=SearchEntityType.MEETING,
        entity_id=meeting.id,
        title=meeting.title,
        summary=_trim(recording_summary or meeting.agenda, 240),
        body=body,
        keywords=" ".join([meeting.status, getattr(meeting.organizer, "full_name", "") or ""]),
        status=meeting.status,
        status_label=_labelize(meeting.status),
        visibility="workspace",
        people=[_person("owner", meeting.organizer_id, getattr(meeting.organizer, "full_name", None)), *attendees],
        containers=[],
        owner_user_id=meeting.organizer_id,
        team_ids=[],
        participant_user_ids=[attendee.user_id for attendee in meeting.attendees],
        shared_user_ids=[],
        granted_user_ids=[],
        date_markers={"event_start_at": meeting.start_at.isoformat(), "start_date": meeting.start_at.date().isoformat()},
        deep_link=f"/w/{workspace.key}/meeting/{meeting.id}",
        metadata={"attendee_count": len(meeting.attendees)},
        source_updated_at=meeting.updated_at,
    )


def _latest_meeting_recording_for_search(
    db: Session,
    *,
    meeting: Meeting,
) -> Recording | MeetingRecording | None:
    if _canonical_recording_tables_available(db):
        recording = db.scalar(
            select(Recording)
            .join(RecordingContainer)
            .where(
                Recording.workspace_id == meeting.workspace_id,
                Recording.trashed_at.is_(None),
                RecordingContainer.container_app == "meeting",
                RecordingContainer.container_type == "meeting",
                RecordingContainer.container_id == meeting.id,
            )
            .order_by(RecordingContainer.sort_order.desc(), Recording.started_at.desc())
        )
        if recording is not None:
            return recording
    return db.scalar(
        select(MeetingRecording)
        .where(MeetingRecording.meeting_id == meeting.id)
        .order_by(MeetingRecording.sequence_no.desc(), MeetingRecording.created_at.desc())
    )


def _canonical_recording_tables_available(db: Session) -> bool:
    try:
        inspector = inspect(db.get_bind())
        return inspector.has_table(Recording.__tablename__) and inspector.has_table(
            RecordingContainer.__tablename__
        )
    except Exception:  # noqa: BLE001
        return False


def _pms_issue_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    issues = db.scalars(
        select(Issue)
        .options(
            selectinload(Issue.task_list).selectinload(TaskList.statuses),
            selectinload(Issue.assignee),
            selectinload(Issue.reporter),
            selectinload(Issue.comments).selectinload(IssueComment.author),
            selectinload(Issue.label_links).selectinload(IssueLabel.label),
            selectinload(Issue.user_access_grants),
        )
        .join(TaskList, Issue.list_id == TaskList.id)
        .join(Team, TaskList.team_id == Team.id)
        .where(Team.workspace_id == workspace.id, Issue.archived.is_(False))
    ).all()
    return [_pms_issue_row(workspace=workspace, issue=issue) for issue in issues]


def _pms_issue_row(*, workspace: Workspace, issue: Issue) -> dict[str, Any]:
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
    containers = [{"type": "list", "id": issue.list_id, "label": getattr(task_list, "name", None) or issue.list_id}]
    people = [_person("owner", issue.reporter_id, getattr(issue.reporter, "full_name", None))]
    if issue.assignee_id:
        people.append(_person("assignee", issue.assignee_id, getattr(issue.assignee, "full_name", None)))
    return _row(
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
        owner_user_id=issue.reporter_id,
        team_ids=[task_list.team_id] if task_list and task_list.team_id else [],
        participant_user_ids=[],
        shared_user_ids=[],
        granted_user_ids=_active_issue_grant_user_ids(issue.user_access_grants),
        date_markers={
            "start_date": issue.start_date.isoformat() if issue.start_date else None,
            "due_date": issue.due_date.isoformat() if issue.due_date else None,
        },
        deep_link=f"/tool/pms-list-{issue.list_id}?workspace={workspace.key}&issue={issue.id}",
        metadata={"list_id": issue.list_id, "issue_number": issue.issue_number, "priority": issue.priority},
        source_updated_at=issue.updated_at,
    )


def _planner_event_rows(db: Session, workspace: Workspace) -> list[dict[str, Any]]:
    events = db.scalars(
        select(PlannerEvent)
        .options(selectinload(PlannerEvent.owner))
        .where(PlannerEvent.workspace_id == workspace.id)
    ).all()
    return [_planner_event_row(workspace=workspace, event=event) for event in events]


def _planner_event_row(*, workspace: Workspace, event: PlannerEvent) -> dict[str, Any]:
    return _row(
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
        owner_user_id=event.owner_id,
        team_ids=[],
        participant_user_ids=[],
        shared_user_ids=[],
        granted_user_ids=[],
        date_markers={
            "event_start_at": event.start_at.isoformat(),
            "start_date": event.start_at.date().isoformat(),
        },
        deep_link=f"/w/{workspace.key}/planner?event={event.id}",
        metadata={"location": event.location, "all_day": event.all_day},
        source_updated_at=event.updated_at,
    )


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
    owner_user_id: str | None,
    team_ids: list[str],
    participant_user_ids: list[str],
    shared_user_ids: list[str],
    granted_user_ids: list[str],
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
        "owner_user_id": owner_user_id,
        "team_ids": _unique_nonempty(team_ids),
        "participant_user_ids": _unique_nonempty(participant_user_ids),
        "shared_user_ids": _unique_nonempty(shared_user_ids),
        "granted_user_ids": _unique_nonempty(granted_user_ids),
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


def _task_list_team_lookup(db: Session, workspace: Workspace) -> dict[str, str]:
    rows = db.execute(
        select(TaskList.id, TaskList.team_id)
        .join(Team, TaskList.team_id == Team.id)
        .where(Team.workspace_id == workspace.id, TaskList.team_id.is_not(None))
    ).all()
    return {list_id: team_id for list_id, team_id in rows if team_id}


def _container_team_ids(containers: list[dict[str, str]], task_list_team_ids: dict[str, str]) -> list[str]:
    team_ids: list[str] = []
    for container in containers:
        container_type = container.get("type")
        container_id = container.get("id")
        if not container_id:
            continue
        if container_type == "space":
            team_ids.append(container_id)
        if container_type == "list" and container_id in task_list_team_ids:
            team_ids.append(task_list_team_ids[container_id])
    return team_ids


def _active_doc_grant_user_ids(grants: list[DocMeetingAccess]) -> list[str]:
    now = _utcnow()
    return [
        grant.user_id
        for grant in grants
        if grant.revoked_at is None and (grant.expires_at is None or grant.expires_at > now)
    ]


def _active_issue_grant_user_ids(grants: list[IssueUserAccess]) -> list[str]:
    now = _utcnow()
    return [
        grant.user_id
        for grant in grants
        if grant.revoked_at is None and (grant.expires_at is None or grant.expires_at > now)
    ]


def _unique_nonempty(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _date_marker_value(value: datetime) -> str:
    return value.date().isoformat() if value.time() == time.min else value.isoformat()


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
