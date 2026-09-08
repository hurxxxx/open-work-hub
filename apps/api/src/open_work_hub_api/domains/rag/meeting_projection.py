from __future__ import annotations

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.domains.meeting.models import Meeting, MeetingAttendee, MeetingRecording
from open_work_hub_api.domains.rag.contracts import RagProjection
from open_work_hub_api.domains.rag.projection_builders import build_text_projection
from open_work_hub_api.domains.recording.models import Recording, RecordingTarget
from open_work_hub_api.domains.source_access.resource_types import MEETING_RESOURCE_TYPE

MEETING_SOURCE_KIND = "meeting"


def load_meeting_projection(
    db: Session,
    *,
    meeting_id: str,
) -> RagProjection | None:
    meeting = db.scalar(
        select(Meeting)
        .options(
            selectinload(Meeting.organizer),
            selectinload(Meeting.attendees).selectinload(MeetingAttendee.user),
            selectinload(Meeting.task_links),
            selectinload(Meeting.doc_links),
        )
        .where(Meeting.id == meeting_id)
    )
    if meeting is None:
        return None
    latest_recording = _latest_meeting_recording_for_projection(db, meeting=meeting)
    return build_meeting_projection(meeting, latest_recording=latest_recording)


def build_meeting_projection(
    meeting: Meeting,
    *,
    latest_recording: Recording | MeetingRecording | None = None,
) -> RagProjection:
    attendee_names = [
        attendee.user.full_name.strip()
        for attendee in sorted(meeting.attendees, key=lambda item: item.created_at)
        if attendee.user is not None and attendee.user.full_name.strip()
    ]
    if isinstance(latest_recording, Recording):
        transcript_excerpt = (
            latest_recording.result.transcript_text.strip()[:8000]
            if latest_recording.result is not None
            else ""
        )
        recording_summary = (
            (latest_recording.result.summary_text or "").strip()[:4000]
            if latest_recording.result is not None
            else ""
        )
    else:
        transcript_excerpt = (
            (latest_recording.transcript_text or "").strip()[:8000] if latest_recording else ""
        )
        recording_summary = (getattr(latest_recording, "summary_text", None) or "").strip()[:4000]
    linked_doc_id = (
        getattr(latest_recording, "linked_doc_id", None) if latest_recording is not None else None
    )
    text_sections = [
        meeting.title.strip(),
        (meeting.agenda or "").strip(),
        "참석자: " + ", ".join(attendee_names) if attendee_names else "",
        recording_summary,
        transcript_excerpt,
    ]
    summary = recording_summary or (meeting.agenda or "").strip() or meeting.title.strip()

    return build_text_projection(
        resource_type=MEETING_RESOURCE_TYPE,
        resource_id=meeting.id,
        source_kind=MEETING_SOURCE_KIND,
        title=meeting.title,
        summary=_trim_summary(summary),
        text_sections=text_sections,
        owner_label=getattr(meeting.organizer, "full_name", None),
        visibility_refs=_build_visibility_refs(meeting),
        metadata={
            "status": meeting.status,
            "start_at": meeting.start_at.isoformat(),
            "end_at": meeting.end_at.isoformat(),
            "attendee_count": len(meeting.attendees),
            "task_link_count": len(meeting.task_links),
            "doc_link_count": len(meeting.doc_links),
            "latest_recording_id": latest_recording.id if latest_recording is not None else None,
            "linked_doc_id": linked_doc_id,
        },
    )


def _latest_meeting_recording_for_projection(
    db: Session,
    *,
    meeting: Meeting,
) -> Recording | MeetingRecording | None:
    if _canonical_recording_tables_available(db):
        recording = db.scalar(
            select(Recording)
            .join(RecordingTarget)
            .options(selectinload(Recording.result))
            .where(
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


def _build_visibility_refs(meeting: Meeting) -> list[str]:
    refs = {
        f"meeting_organizer:{meeting.organizer_id}",
    }
    for attendee in meeting.attendees:
        refs.add(f"meeting_attendee:{attendee.user_id}")
    return sorted(refs)


def _trim_summary(text: str, *, max_chars: int = 240) -> str | None:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
