from __future__ import annotations

from datetime import datetime
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.domains.auth.access import load_active_workspace_by_key
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.meeting.models import (
    Meeting,
    MeetingAttendee,
    MeetingDocLink,
    MeetingTaskLink,
)
from aidoo_api.domains.meeting.permissions import (
    ensure_doc_readable,
    ensure_issue_readable,
)
from aidoo_api.domains.meeting.schemas import (
    MeetingAttendeeInput,
    MeetingAttendeeOut,
    MeetingCreateRequest,
    MeetingDetail,
    MeetingDocLinkOut,
    MeetingListItem,
    MeetingListResponse,
    MeetingRecordingOut,
    MeetingTaskLinkOut,
    MeetingUpdateRequest,
)
from aidoo_api.domains.pms.models import Issue, Project


MEETING_WORKSPACE_KEY = "meeting"


def _get_meeting_workspace(db: Session) -> Workspace:
    workspace = load_active_workspace_by_key(db, MEETING_WORKSPACE_KEY)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Meeting workspace is not provisioned.",
        )
    return workspace


def _validate_time_range(start_at: datetime, end_at: datetime) -> None:
    if end_at <= start_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_at must be after start_at.",
        )


def _validate_attendee_users(db: Session, user_ids: Iterable[str]) -> dict[str, User]:
    unique_ids = list({uid for uid in user_ids})
    if not unique_ids:
        return {}
    users = db.scalars(
        select(User).where(User.id.in_(unique_ids), User.status == "active")
    ).all()
    found = {user.id: user for user in users}
    missing = set(unique_ids) - set(found.keys())
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or inactive attendee user(s): {sorted(missing)}",
        )
    return found


def _serialize_attendee(attendee: MeetingAttendee) -> MeetingAttendeeOut:
    return MeetingAttendeeOut(
        id=attendee.id,
        user_id=attendee.user_id,
        email=attendee.user.email,
        full_name=attendee.user.full_name,
        role=attendee.role,  # type: ignore[arg-type]
        response=attendee.response,  # type: ignore[arg-type]
    )


def _serialize_task_link(
    db: Session, link: MeetingTaskLink
) -> MeetingTaskLinkOut:
    issue = db.scalar(
        select(Issue).where(Issue.id == link.issue_id)
    )
    project_key = ""
    issue_title = ""
    issue_number = 0
    if issue is not None:
        issue_title = issue.title
        issue_number = issue.issue_number
        project = db.scalar(select(Project).where(Project.id == issue.project_id))
        if project is not None:
            project_key = project.key
    return MeetingTaskLinkOut(
        id=link.id,
        issue_id=link.issue_id,
        issue_title=issue_title,
        project_key=project_key,
        issue_number=issue_number,
        added_by_id=link.added_by_id,
        created_at=link.created_at,
    )


def _serialize_doc_link(db: Session, link: MeetingDocLink) -> MeetingDocLinkOut:
    doc = db.scalar(select(NativeDoc).where(NativeDoc.id == link.doc_id))
    return MeetingDocLinkOut(
        id=link.id,
        doc_id=link.doc_id,
        doc_title=doc.title if doc is not None else "",
        added_by_id=link.added_by_id,
        created_at=link.created_at,
    )


def _serialize_recording(recording) -> MeetingRecordingOut:
    return MeetingRecordingOut.model_validate(recording)


def _serialize_meeting(db: Session, meeting: Meeting) -> MeetingDetail:
    return MeetingDetail(
        id=meeting.id,
        workspace_id=meeting.workspace_id,
        organizer_id=meeting.organizer_id,
        organizer_name=meeting.organizer.full_name if meeting.organizer else "",
        title=meeting.title,
        agenda=meeting.agenda,
        start_at=meeting.start_at,
        end_at=meeting.end_at,
        status=meeting.status,  # type: ignore[arg-type]
        attendees=[_serialize_attendee(a) for a in meeting.attendees],
        task_links=[_serialize_task_link(db, link) for link in meeting.task_links],
        doc_links=[_serialize_doc_link(db, link) for link in meeting.doc_links],
        recordings=[_serialize_recording(r) for r in meeting.recordings],
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )


def _load_meeting(db: Session, meeting_id: str) -> Meeting:
    meeting = db.scalar(
        select(Meeting)
        .options(
            selectinload(Meeting.attendees).selectinload(MeetingAttendee.user),
            selectinload(Meeting.task_links),
            selectinload(Meeting.doc_links),
            selectinload(Meeting.recordings),
            selectinload(Meeting.organizer),
        )
        .where(Meeting.id == meeting_id)
    )
    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meeting not found.",
        )
    return meeting


def _ensure_user_can_view(user: User, meeting: Meeting) -> None:
    if meeting.organizer_id == user.id:
        return
    if any(att.user_id == user.id for att in meeting.attendees):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this meeting.",
    )


def _replace_attendees(
    db: Session,
    meeting: Meeting,
    new_attendees: list[MeetingAttendeeInput],
) -> None:
    user_lookup = _validate_attendee_users(
        db, [item.user_id for item in new_attendees]
    )

    existing_by_user = {att.user_id: att for att in meeting.attendees}
    incoming_user_ids = {item.user_id for item in new_attendees}

    for user_id, attendee in list(existing_by_user.items()):
        if user_id not in incoming_user_ids:
            db.delete(attendee)

    for item in new_attendees:
        existing = existing_by_user.get(item.user_id)
        if existing is not None:
            existing.role = item.role
            db.add(existing)
            continue
        db.add(
            MeetingAttendee(
                id=new_id(),
                meeting_id=meeting.id,
                user_id=item.user_id,
                role=item.role,
                response="pending",
            )
        )

    db.flush()
    # Refresh attendees collection so callers see canonical state.
    db.refresh(meeting)
    for attendee in meeting.attendees:
        # Force load `.user` so serialization sees the relationship.
        _ = attendee.user_id
        _ = user_lookup.get(attendee.user_id)


def create_meeting(
    db: Session,
    *,
    organizer: User,
    payload: MeetingCreateRequest,
) -> MeetingDetail:
    _validate_time_range(payload.start_at, payload.end_at)
    workspace = _get_meeting_workspace(db)

    attendees_input = list(payload.attendees)
    if not any(item.user_id == organizer.id for item in attendees_input):
        attendees_input.append(
            MeetingAttendeeInput(user_id=organizer.id, role="required")
        )
    _validate_attendee_users(db, [item.user_id for item in attendees_input])

    meeting = Meeting(
        id=new_id(),
        workspace_id=workspace.id,
        organizer_id=organizer.id,
        title=payload.title.strip(),
        agenda=payload.agenda,
        start_at=payload.start_at,
        end_at=payload.end_at,
        status="scheduled",
    )
    db.add(meeting)
    db.flush()

    for item in attendees_input:
        db.add(
            MeetingAttendee(
                id=new_id(),
                meeting_id=meeting.id,
                user_id=item.user_id,
                role=item.role,
                response=(
                    "accepted" if item.user_id == organizer.id else "pending"
                ),
            )
        )
    db.commit()

    fresh = _load_meeting(db, meeting.id)
    return _serialize_meeting(db, fresh)


def update_meeting(
    db: Session,
    *,
    user: User,
    meeting_id: str,
    payload: MeetingUpdateRequest,
) -> MeetingDetail:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer

    meeting = _load_meeting(db, meeting_id)
    ensure_meeting_organizer(db, user, meeting)

    if payload.title is not None:
        meeting.title = payload.title.strip()
    if payload.agenda is not None:
        meeting.agenda = payload.agenda
    if payload.start_at is not None:
        meeting.start_at = payload.start_at
    if payload.end_at is not None:
        meeting.end_at = payload.end_at
    _validate_time_range(meeting.start_at, meeting.end_at)
    if payload.status is not None:
        meeting.status = payload.status

    if payload.attendees is not None:
        attendees_input = list(payload.attendees)
        if not any(item.user_id == meeting.organizer_id for item in attendees_input):
            attendees_input.append(
                MeetingAttendeeInput(
                    user_id=meeting.organizer_id, role="required"
                )
            )
        _replace_attendees(db, meeting, attendees_input)

    db.add(meeting)
    db.commit()

    fresh = _load_meeting(db, meeting.id)
    return _serialize_meeting(db, fresh)


def delete_meeting(db: Session, *, user: User, meeting_id: str) -> None:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer

    meeting = _load_meeting(db, meeting_id)
    ensure_meeting_organizer(db, user, meeting)
    db.delete(meeting)
    db.commit()


def get_meeting(db: Session, *, user: User, meeting_id: str) -> MeetingDetail:
    meeting = _load_meeting(db, meeting_id)
    _ensure_user_can_view(user, meeting)
    return _serialize_meeting(db, meeting)


def list_meetings(
    db: Session,
    *,
    user: User,
    scope: str = "mine",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> MeetingListResponse:
    workspace = _get_meeting_workspace(db)

    base = select(Meeting).where(Meeting.workspace_id == workspace.id)

    if scope == "mine":
        attendee_meeting_ids = select(MeetingAttendee.meeting_id).where(
            MeetingAttendee.user_id == user.id
        )
        base = base.where(
            or_(
                Meeting.organizer_id == user.id,
                Meeting.id.in_(attendee_meeting_ids),
            )
        )
    elif scope == "upcoming":
        now = datetime.utcnow()
        base = base.where(Meeting.end_at >= now)
    elif scope == "all":
        pass
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported scope: {scope}",
        )

    if from_at is not None:
        base = base.where(Meeting.end_at >= from_at)
    if to_at is not None:
        base = base.where(Meeting.start_at <= to_at)

    base = base.options(
        selectinload(Meeting.attendees),
        selectinload(Meeting.task_links),
        selectinload(Meeting.doc_links),
        selectinload(Meeting.organizer),
    ).order_by(Meeting.start_at.asc())

    meetings = db.scalars(base).all()
    items = [
        MeetingListItem(
            id=m.id,
            title=m.title,
            organizer_id=m.organizer_id,
            organizer_name=m.organizer.full_name if m.organizer else "",
            start_at=m.start_at,
            end_at=m.end_at,
            status=m.status,  # type: ignore[arg-type]
            attendee_count=len(m.attendees),
            task_link_count=len(m.task_links),
            doc_link_count=len(m.doc_links),
        )
        for m in meetings
    ]
    return MeetingListResponse(items=items, total=len(items))


def attach_task(
    db: Session, *, user: User, meeting_id: str, issue_id: str
) -> MeetingDetail:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer

    meeting = _load_meeting(db, meeting_id)
    ensure_meeting_organizer(db, user, meeting)
    ensure_issue_readable(db, user, issue_id)

    existing = db.scalar(
        select(MeetingTaskLink).where(
            MeetingTaskLink.meeting_id == meeting_id,
            MeetingTaskLink.issue_id == issue_id,
        )
    )
    if existing is None:
        db.add(
            MeetingTaskLink(
                id=new_id(),
                meeting_id=meeting_id,
                issue_id=issue_id,
                added_by_id=user.id,
            )
        )
        db.commit()

    fresh = _load_meeting(db, meeting_id)
    return _serialize_meeting(db, fresh)


def detach_task(
    db: Session, *, user: User, meeting_id: str, issue_id: str
) -> MeetingDetail:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer

    meeting = _load_meeting(db, meeting_id)
    ensure_meeting_organizer(db, user, meeting)

    link = db.scalar(
        select(MeetingTaskLink).where(
            MeetingTaskLink.meeting_id == meeting_id,
            MeetingTaskLink.issue_id == issue_id,
        )
    )
    if link is not None:
        db.delete(link)
        db.commit()

    fresh = _load_meeting(db, meeting_id)
    return _serialize_meeting(db, fresh)


def attach_doc(
    db: Session, *, user: User, meeting_id: str, doc_id: str
) -> MeetingDetail:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer

    meeting = _load_meeting(db, meeting_id)
    ensure_meeting_organizer(db, user, meeting)
    ensure_doc_readable(db, user, doc_id)

    existing = db.scalar(
        select(MeetingDocLink).where(
            MeetingDocLink.meeting_id == meeting_id,
            MeetingDocLink.doc_id == doc_id,
        )
    )
    if existing is None:
        db.add(
            MeetingDocLink(
                id=new_id(),
                meeting_id=meeting_id,
                doc_id=doc_id,
                added_by_id=user.id,
            )
        )
        db.commit()

    fresh = _load_meeting(db, meeting_id)
    return _serialize_meeting(db, fresh)


def detach_doc(
    db: Session, *, user: User, meeting_id: str, doc_id: str
) -> MeetingDetail:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer

    meeting = _load_meeting(db, meeting_id)
    ensure_meeting_organizer(db, user, meeting)

    link = db.scalar(
        select(MeetingDocLink).where(
            MeetingDocLink.meeting_id == meeting_id,
            MeetingDocLink.doc_id == doc_id,
        )
    )
    if link is not None:
        db.delete(link)
        db.commit()

    fresh = _load_meeting(db, meeting_id)
    return _serialize_meeting(db, fresh)
