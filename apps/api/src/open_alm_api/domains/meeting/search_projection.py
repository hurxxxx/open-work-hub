from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from open_alm_api.domains.auth.models import Workspace
from open_alm_api.domains.meeting.app_catalog import MEETING_WORKSPACE_APP
from open_alm_api.domains.meeting.models import Meeting, MeetingAttendee, MeetingRecording
from open_alm_api.domains.recording.models import Recording, RecordingTarget
from open_alm_api.domains.retrieval.partition_adapter_ids import (
    MEETING_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_alm_api.domains.search.index_document import (
    build_search_document,
    search_person,
    trim_search_text,
)
from open_alm_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    SearchIndexLifecycleHooks,
)
from open_alm_api.domains.search.schemas import SearchEntityType
from open_alm_api.domains.source_access.resource_types import MEETING_RESOURCE_TYPE


def load_workspace_meeting_search_documents(
    db: Session, *, workspace: Workspace
) -> list[dict[str, Any]]:
    meetings = db.scalars(
        select(Meeting)
        .options(
            selectinload(Meeting.organizer),
            selectinload(Meeting.attendees).selectinload(MeetingAttendee.user),
        )
        .where(Meeting.workspace_id == workspace.id)
    ).all()
    return [_meeting_row(db, workspace=workspace, meeting=meeting) for meeting in meetings]


def load_meeting_search_document(db: Session, *, meeting_id: str) -> dict[str, Any] | None:
    meeting = db.scalar(
        select(Meeting)
        .options(
            selectinload(Meeting.organizer),
            selectinload(Meeting.attendees).selectinload(MeetingAttendee.user),
        )
        .where(Meeting.id == meeting_id)
    )
    if meeting is None:
        return None
    workspace = db.scalar(
        select(Workspace).where(Workspace.id == meeting.workspace_id, Workspace.active.is_(True))
    )
    if workspace is None:
        return None
    return _meeting_row(db, workspace=workspace, meeting=meeting)


def load_meeting_search_document_for_entity(
    db: Session,
    *,
    entity_type: SearchEntityType,
    entity_id: str,
) -> dict[str, Any] | None:
    if entity_type != SearchEntityType.MEETING:
        return None
    return load_meeting_search_document(db, meeting_id=entity_id)


def _meeting_row(db: Session, *, workspace: Workspace, meeting: Meeting) -> dict[str, Any]:
    recording = _latest_meeting_recording_for_search(db, meeting=meeting)
    recording_summary = (getattr(recording, "summary_text", None) or "").strip()
    attendees = [
        search_person("participant", attendee.user_id, getattr(attendee.user, "full_name", None))
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
    return build_search_document(
        workspace_id=workspace.id,
        entity_type=SearchEntityType.MEETING,
        entity_id=meeting.id,
        title=meeting.title,
        summary=trim_search_text(recording_summary or meeting.agenda, 240),
        body=body,
        keywords=" ".join([meeting.status, getattr(meeting.organizer, "full_name", "") or ""]),
        status=meeting.status,
        status_label=_labelize(meeting.status),
        visibility="workspace",
        people=[
            search_person(
                "owner", meeting.organizer_id, getattr(meeting.organizer, "full_name", None)
            ),
            *attendees,
        ],
        targets=[],
        owner_user_id=meeting.organizer_id,
        team_ids=[],
        participant_user_ids=[attendee.user_id for attendee in meeting.attendees],
        shared_user_ids=[],
        granted_user_ids=[],
        date_markers={
            "event_start_at": meeting.start_at.isoformat(),
            "start_date": meeting.start_at.date().isoformat(),
        },
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
            .join(RecordingTarget)
            .where(
                Recording.workspace_id == meeting.workspace_id,
                Recording.trashed_at.is_(None),
                RecordingTarget.target_app == "meeting",
                RecordingTarget.target_type == "meeting",
                RecordingTarget.target_id == meeting.id,
            )
            .order_by(RecordingTarget.sort_order.desc(), Recording.started_at.desc())
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
            RecordingTarget.__tablename__
        )
    except Exception:  # noqa: BLE001
        return False


def _labelize(value: str) -> str:
    return value.replace("_", " ").title()


MEETING_WORKSPACE_KEYWORD_SEARCH_ADAPTER = SearchEntityAdapter(
    owner_app=MEETING_WORKSPACE_APP,
    entity_type=SearchEntityType.MEETING.value,
    resource_type=MEETING_RESOURCE_TYPE,
    label="회의",
    label_key="ai.search.entityMeeting",
    workspace_loader=load_workspace_meeting_search_documents,
    document_loader=load_meeting_search_document_for_entity,
    partition_adapter_id=MEETING_RETRIEVAL_PARTITION_ADAPTER_ID,
    index_hooks=SearchIndexLifecycleHooks(
        create=("meeting.enqueue_meeting_search_index",),
        update=(
            "meeting.enqueue_meeting_search_index",
            "meeting.enqueue_meeting_search_index_by_id",
        ),
        delete=("meeting.enqueue_meeting_search_index",),
    ),
    person_roles=("owner", "participant"),
)


__all__ = [
    "MEETING_WORKSPACE_KEYWORD_SEARCH_ADAPTER",
    "load_meeting_search_document",
    "load_meeting_search_document_for_entity",
    "load_workspace_meeting_search_documents",
]
