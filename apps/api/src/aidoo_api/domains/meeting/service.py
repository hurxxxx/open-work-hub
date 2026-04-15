from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Iterable

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.core.settings import get_settings
from aidoo_api.core.storage import get_minio_client
from aidoo_api.domains.auth.access import (
    resolve_workspace_role,
)
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.access_grants import (
    bump_doc_grant_expiry_for_meeting,
    grant_doc_access,
    revoke_doc_grants_for_attachment,
    revoke_doc_grants_for_meeting,
    revoke_doc_grants_for_meeting_attendee,
)
from aidoo_api.domains.docs.models import NativeDoc, NativeDocPage
from aidoo_api.domains.docs.service import create_native_doc_for_user
from aidoo_api.domains.meeting.models import (
    Meeting,
    MeetingAttendee,
    MeetingDocLink,
    MeetingFileAttachment,
    MeetingTaskLink,
)
from aidoo_api.domains.meeting.permissions import (
    ensure_doc_attachable,
    ensure_link_remover,
    ensure_meeting_participant,
)
from aidoo_api.domains.meeting.schemas import (
    MeetingAttendeeInput,
    MeetingAttendeeOut,
    MeetingCreateRequest,
    MeetingDetail,
    MeetingDocLinkOut,
    MeetingFileAttachmentOut,
    MeetingListItem,
    MeetingListResponse,
    MeetingRecordingOut,
    MeetingTaskLinkOut,
    MeetingUpdateRequest,
)
from aidoo_api.domains.pms.access import ensure_issue_attachable, has_list_access
from aidoo_api.domains.pms.access_grants import (
    bump_grant_expiry_for_meeting,
    grant_issue_access,
    revoke_grants_for_issue_attachment,
    revoke_grants_for_meeting,
    revoke_grants_for_meeting_attendee,
)
from aidoo_api.domains.pms.models import Issue, TaskList


MAX_FILE_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


def _meeting_notes_doc_title(meeting: Meeting) -> str:
    return f"회의 메모: {meeting.title} ({meeting.start_at:%Y-%m-%d})"


def _meeting_notes_page_title() -> str:
    return "회의 메모"


def _validate_time_range(start_at: datetime, end_at: datetime) -> None:
    if end_at <= start_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_at must be after start_at.",
        )


def _meeting_grant_expires_at(meeting: Meeting) -> datetime:
    return meeting.end_at + timedelta(days=7)


def _validate_attendee_users(
    db: Session,
    user_ids: Iterable[str],
    *,
    workspace_id: str,
) -> dict[str, User]:
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
    non_members = sorted(
        user.id for user in users if resolve_workspace_role(db, user, workspace_id) is None
    )
    if non_members:
        raise HTTPException(
            status_code=422,
            detail=f"Attendees must belong to the meeting workspace: {non_members}",
        )
    return found


def _grant_issue_to_attendee(
    db: Session,
    *,
    meeting: Meeting,
    issue: Issue,
    attendee_user: User,
    granted_by_user_id: str,
) -> None:
    if attendee_user.id == granted_by_user_id:
        return
    if has_list_access(db, attendee_user, issue.list_id):
        return
    grant_issue_access(
        db,
        issue_id=issue.id,
        user_id=attendee_user.id,
        granted_by_user_id=granted_by_user_id,
        granted_by_meeting_id=meeting.id,
        reason="meeting_attendee",
        expires_at=_meeting_grant_expires_at(meeting),
    )


def _grant_doc_to_attendee(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
    attendee_user: User,
    granted_by_user_id: str,
) -> None:
    if attendee_user.id == granted_by_user_id:
        return
    if attendee_user.id == doc.owner_id:
        return
    grant_doc_access(
        db,
        doc_id=doc.id,
        user_id=attendee_user.id,
        granted_by_user_id=granted_by_user_id,
        granted_by_meeting_id=meeting.id,
        reason="meeting_attendee",
        expires_at=_meeting_grant_expires_at(meeting),
    )


def _grant_notes_doc_to_attendee(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
    attendee_user: User,
    granted_by_user_id: str,
) -> None:
    if attendee_user.id == granted_by_user_id:
        return
    if attendee_user.id == doc.owner_id:
        return
    grant_doc_access(
        db,
        doc_id=doc.id,
        user_id=attendee_user.id,
        granted_by_user_id=granted_by_user_id,
        granted_by_meeting_id=meeting.id,
        reason="meeting_notes",
        access_level="edit",
        expires_at=None,
    )


def _load_active_native_doc(db: Session, *, workspace_id: str, doc_id: str | None) -> NativeDoc | None:
    if not doc_id:
        return None
    return db.scalar(
        select(NativeDoc).where(
            NativeDoc.id == doc_id,
            NativeDoc.workspace_id == workspace_id,
            NativeDoc.trashed_at.is_(None),
        )
    )


def _load_active_native_doc_page(
    db: Session,
    *,
    doc_id: str,
    page_id: str | None,
) -> NativeDocPage | None:
    if not page_id:
        return None
    return db.scalar(
        select(NativeDocPage).where(
            NativeDocPage.id == page_id,
            NativeDocPage.doc_id == doc_id,
            NativeDocPage.trashed_at.is_(None),
        )
    )


def _create_meeting_notes_assets(
    db: Session,
    *,
    meeting: Meeting,
) -> tuple[NativeDoc, NativeDocPage]:
    return create_native_doc_for_user(
        db,
        workspace_id=meeting.workspace_id,
        owner_id=meeting.organizer_id,
        title=_meeting_notes_doc_title(meeting),
        first_page_title=_meeting_notes_page_title(),
        content_blocks=[],
    )


def _sync_notes_doc_access(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
) -> None:
    for attendee in meeting.attendees:
        if attendee.user is None:
            continue
        _grant_notes_doc_to_attendee(
            db,
            meeting=meeting,
            doc=doc,
            attendee_user=attendee.user,
            granted_by_user_id=meeting.organizer_id,
        )


def _ensure_meeting_notes_state(
    db: Session,
    *,
    meeting: Meeting,
) -> tuple[NativeDoc, NativeDocPage]:
    # Serialize concurrent notes-ensure calls. Without this lock, two
    # simultaneous requests (e.g. the meeting modal opening + the collab
    # session call firing in parallel) would both observe
    # ``meeting.notes_doc_id is None`` and both call
    # ``_create_meeting_notes_assets``, leaving one orphan NativeDoc row
    # visible in the user's Docs hub forever.
    db.execute(
        select(Meeting.id).where(Meeting.id == meeting.id).with_for_update()
    )
    db.refresh(meeting, attribute_names=["notes_doc_id", "notes_page_id"])

    doc = _load_active_native_doc(db, workspace_id=meeting.workspace_id, doc_id=meeting.notes_doc_id)
    if doc is None:
        doc, page = _create_meeting_notes_assets(db, meeting=meeting)
    else:
        page = _load_active_native_doc_page(db, doc_id=doc.id, page_id=meeting.notes_page_id)
        if page is None:
            page = NativeDocPage(
                id=new_id(),
                doc_id=doc.id,
                parent_id=None,
                title=_meeting_notes_page_title(),
                content_blocks=[],
                sort_order=0,
                created_by_id=meeting.organizer_id,
            )
            db.add(page)
            db.flush()

    meeting.notes_doc_id = doc.id
    meeting.notes_page_id = page.id
    db.add(meeting)
    db.flush()
    _sync_notes_doc_access(db, meeting=meeting, doc=doc)
    return doc, page


def _attach_issue_link(
    db: Session,
    *,
    meeting: Meeting,
    issue: Issue,
    added_by_id: str,
) -> None:
    existing = db.scalar(
        select(MeetingTaskLink).where(
            MeetingTaskLink.meeting_id == meeting.id,
            MeetingTaskLink.issue_id == issue.id,
        )
    )
    if existing is None:
        db.add(
            MeetingTaskLink(
                id=new_id(),
                meeting_id=meeting.id,
                issue_id=issue.id,
                added_by_id=added_by_id,
            )
        )
        db.flush()

    for attendee in meeting.attendees:
        if attendee.user is None:
            continue
        _grant_issue_to_attendee(
            db,
            meeting=meeting,
            issue=issue,
            attendee_user=attendee.user,
            granted_by_user_id=added_by_id,
        )


def _attach_doc_link(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
    added_by_id: str,
) -> None:
    existing = db.scalar(
        select(MeetingDocLink).where(
            MeetingDocLink.meeting_id == meeting.id,
            MeetingDocLink.doc_id == doc.id,
        )
    )
    if existing is None:
        db.add(
            MeetingDocLink(
                id=new_id(),
                meeting_id=meeting.id,
                doc_id=doc.id,
                added_by_id=added_by_id,
            )
        )
        db.flush()

    for attendee in meeting.attendees:
        if attendee.user is None:
            continue
        _grant_doc_to_attendee(
            db,
            meeting=meeting,
            doc=doc,
            attendee_user=attendee.user,
            granted_by_user_id=added_by_id,
        )


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
    link: MeetingTaskLink,
    *,
    issues_by_id: dict[str, Issue],
) -> MeetingTaskLinkOut:
    issue = issues_by_id.get(link.issue_id)
    list_key = issue.task_list.key if issue and issue.task_list else ""
    issue_title = issue.title if issue is not None else ""
    issue_number = issue.issue_number if issue is not None else 0
    return MeetingTaskLinkOut(
        id=link.id,
        issue_id=link.issue_id,
        issue_title=issue_title,
        list_key=list_key,
        issue_number=issue_number,
        added_by_id=link.added_by_id,
        created_at=link.created_at,
    )


def _serialize_doc_link(
    link: MeetingDocLink,
    *,
    docs_by_id: dict[str, NativeDoc],
) -> MeetingDocLinkOut:
    doc = docs_by_id.get(link.doc_id)
    return MeetingDocLinkOut(
        id=link.id,
        doc_id=link.doc_id,
        doc_title=doc.title if doc is not None else "",
        added_by_id=link.added_by_id,
        created_at=link.created_at,
    )


def _load_task_link_issue_map(
    db: Session,
    task_links: list[MeetingTaskLink],
) -> dict[str, Issue]:
    issue_ids = [link.issue_id for link in task_links]
    if not issue_ids:
        return {}
    issues = db.scalars(
        select(Issue)
        .where(Issue.id.in_(issue_ids))
        .options(selectinload(Issue.task_list))
    ).all()
    return {issue.id: issue for issue in issues}


def _load_doc_link_doc_map(
    db: Session,
    doc_links: list[MeetingDocLink],
) -> dict[str, NativeDoc]:
    doc_ids = [link.doc_id for link in doc_links]
    if not doc_ids:
        return {}
    docs = db.scalars(select(NativeDoc).where(NativeDoc.id.in_(doc_ids))).all()
    return {doc.id: doc for doc in docs}


def _build_file_download_url(storage_key: str) -> str:
    """Issue a 1-hour presigned GET URL for a meeting file attachment.

    Wrapped in a module-level function so tests can monkeypatch it without
    spinning up a real MinIO container.
    """
    settings = get_settings()
    client = get_minio_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        storage_key,
        expires=timedelta(hours=1),
    )


def _serialize_file_attachment(
    attachment: MeetingFileAttachment,
) -> MeetingFileAttachmentOut:
    return MeetingFileAttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        download_url=_build_file_download_url(attachment.storage_key),
        added_by_id=attachment.added_by_id,
        added_by_name=(
            attachment.added_by.full_name if attachment.added_by else ""
        ),
        created_at=attachment.created_at,
    )


def _serialize_recording(recording) -> MeetingRecordingOut:
    return MeetingRecordingOut.model_validate(recording)


def _serialize_meeting(db: Session, meeting: Meeting) -> MeetingDetail:
    issues_by_id = _load_task_link_issue_map(db, meeting.task_links)
    docs_by_id = _load_doc_link_doc_map(db, meeting.doc_links)
    return MeetingDetail(
        id=meeting.id,
        workspace_id=meeting.workspace_id,
        organizer_id=meeting.organizer_id,
        organizer_name=meeting.organizer.full_name if meeting.organizer else "",
        notes_doc_id=meeting.notes_doc_id,
        notes_page_id=meeting.notes_page_id,
        title=meeting.title,
        agenda=meeting.agenda,
        start_at=meeting.start_at,
        end_at=meeting.end_at,
        status=meeting.status,  # type: ignore[arg-type]
        attendees=[_serialize_attendee(a) for a in meeting.attendees],
        task_links=[
            _serialize_task_link(link, issues_by_id=issues_by_id)
            for link in meeting.task_links
        ],
        doc_links=[
            _serialize_doc_link(link, docs_by_id=docs_by_id)
            for link in meeting.doc_links
        ],
        file_attachments=[
            _serialize_file_attachment(att)
            for att in sorted(meeting.file_attachments, key=lambda a: a.created_at)
        ],
        recordings=[_serialize_recording(r) for r in meeting.recordings],
        active_recording_lock=_resolve_active_recording_lock(meeting),
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )


def _resolve_active_recording_lock(meeting: Meeting):
    """Return the active staging row that holds the single-recorder lock, if any.

    Stale stagings (no chunk uploaded for ``RECORDING_STALE_AFTER_SECONDS``)
    are treated as released so a crashed recorder doesn't permanently block
    other participants. The abandoned row stays in the DB; only the lock
    relaxes — see ``recordings._staging_is_stale``.

    Used by the frontend to gate the start-recording button so other
    participants see "X 님이 녹음 중" instead of getting a 409 mid-click,
    and to auto-clear the lock client-side when the recorder dies.
    """
    from aidoo_api.domains.meeting.recordings import _staging_is_stale
    from aidoo_api.domains.meeting.schemas import ActiveRecordingLockOut

    if not meeting.recording_staging:
        return None
    active = next(
        (
            s
            for s in meeting.recording_staging
            if s.completed_at is None and not _staging_is_stale(s)
        ),
        None,
    )
    if active is None:
        return None
    user_name = active.uploaded_by.full_name if active.uploaded_by is not None else ""
    return ActiveRecordingLockOut(
        staging_id=active.id,
        user_id=active.uploaded_by_id,
        user_name=user_name,
        started_at=active.started_at,
        last_active_at=active.last_chunk_at,
    )


def _load_meeting(db: Session, workspace: Workspace, meeting_id: str) -> Meeting:
    from aidoo_api.domains.meeting.models import MeetingRecordingStaging

    meeting = db.scalar(
        select(Meeting)
        .options(
            selectinload(Meeting.attendees).selectinload(MeetingAttendee.user),
            selectinload(Meeting.task_links),
            selectinload(Meeting.doc_links),
            selectinload(Meeting.file_attachments).selectinload(
                MeetingFileAttachment.added_by
            ),
            selectinload(Meeting.recordings),
            selectinload(Meeting.recording_staging).selectinload(
                MeetingRecordingStaging.uploaded_by
            ),
            selectinload(Meeting.organizer),
        )
        .where(
            Meeting.id == meeting_id,
            Meeting.workspace_id == workspace.id,
        )
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
    *,
    acting_user_id: str,
) -> None:
    user_lookup = _validate_attendee_users(
        db,
        [item.user_id for item in new_attendees],
        workspace_id=meeting.workspace_id,
    )

    existing_by_user = {att.user_id: att for att in meeting.attendees}
    incoming_user_ids = {item.user_id for item in new_attendees}
    added_user_ids = incoming_user_ids - set(existing_by_user)

    for user_id, attendee in list(existing_by_user.items()):
        if user_id not in incoming_user_ids:
            revoke_grants_for_meeting_attendee(
                db,
                meeting_id=meeting.id,
                user_id=user_id,
                revoked_by_user_id=acting_user_id,
                reason="attendee_removed",
            )
            revoke_doc_grants_for_meeting_attendee(
                db,
                meeting_id=meeting.id,
                user_id=user_id,
                revoked_by_user_id=acting_user_id,
                reason="attendee_removed",
            )
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
        _ = attendee.user

    if not added_user_ids:
        return

    issues_by_id = {
        issue.id: issue
        for issue in db.scalars(
            select(Issue).where(
                Issue.id.in_([link.issue_id for link in meeting.task_links] or ["__none__"])
            )
        )
    }
    docs_by_id = {
        doc.id: doc
        for doc in db.scalars(
            select(NativeDoc).where(
                NativeDoc.id.in_([link.doc_id for link in meeting.doc_links] or ["__none__"])
            )
        )
    }
    notes_doc = _load_active_native_doc(db, workspace_id=meeting.workspace_id, doc_id=meeting.notes_doc_id)
    for attendee in meeting.attendees:
        if attendee.user_id not in added_user_ids or attendee.user is None:
            continue
        for link in meeting.task_links:
            issue = issues_by_id.get(link.issue_id)
            if issue is None:
                continue
            _grant_issue_to_attendee(
                db,
                meeting=meeting,
                issue=issue,
                attendee_user=attendee.user,
                granted_by_user_id=acting_user_id,
            )
        for link in meeting.doc_links:
            doc = docs_by_id.get(link.doc_id)
            if doc is None:
                continue
            _grant_doc_to_attendee(
                db,
                meeting=meeting,
                doc=doc,
                attendee_user=attendee.user,
                granted_by_user_id=acting_user_id,
            )
        if notes_doc is not None:
            _grant_notes_doc_to_attendee(
                db,
                meeting=meeting,
                doc=notes_doc,
                attendee_user=attendee.user,
                granted_by_user_id=meeting.organizer_id,
            )


def create_meeting(
    db: Session,
    *,
    workspace: Workspace,
    organizer: User,
    payload: MeetingCreateRequest,
) -> MeetingDetail:
    _validate_time_range(payload.start_at, payload.end_at)

    attendees_input = list(payload.attendees)
    if not any(item.user_id == organizer.id for item in attendees_input):
        attendees_input.append(
            MeetingAttendeeInput(user_id=organizer.id, role="required")
        )
    _validate_attendee_users(
        db,
        [item.user_id for item in attendees_input],
        workspace_id=workspace.id,
    )

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
    db.flush()
    meeting = _load_meeting(db, workspace, meeting.id)

    issues = [ensure_issue_attachable(db, organizer, issue_id) for issue_id in payload.task_ids]
    docs = [
        ensure_doc_attachable(db, organizer, doc_id, workspace=workspace)
        for doc_id in payload.doc_ids
    ]
    for issue in issues:
        _attach_issue_link(db, meeting=meeting, issue=issue, added_by_id=organizer.id)
    for doc in docs:
        _attach_doc_link(db, meeting=meeting, doc=doc, added_by_id=organizer.id)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting.id)
    return _serialize_meeting(db, fresh)


def update_meeting(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    payload: MeetingUpdateRequest,
) -> MeetingDetail:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer

    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_organizer(db, user, meeting)
    original_end_at = meeting.end_at

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
        _replace_attendees(
            db,
            meeting,
            attendees_input,
            acting_user_id=user.id,
        )

    if meeting.end_at != original_end_at:
        bump_grant_expiry_for_meeting(
            db,
            meeting_id=meeting.id,
            new_end_at=meeting.end_at,
        )
        bump_doc_grant_expiry_for_meeting(
            db,
            meeting_id=meeting.id,
            new_end_at=meeting.end_at,
        )

    db.add(meeting)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting.id)
    return _serialize_meeting(db, fresh)


def delete_meeting(db: Session, *, workspace: Workspace, user: User, meeting_id: str) -> None:
    from aidoo_api.domains.meeting.permissions import ensure_meeting_organizer
    from aidoo_api.domains.meeting.recordings import cleanup_meeting_recordings

    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_organizer(db, user, meeting)
    cleanup_meeting_recordings(db, meeting=meeting)
    revoke_grants_for_meeting(
        db,
        meeting_id=meeting.id,
        revoked_by_user_id=user.id,
        reason="meeting_deleted",
    )
    revoke_doc_grants_for_meeting(
        db,
        meeting_id=meeting.id,
        revoked_by_user_id=user.id,
        reason="meeting_deleted",
    )
    db.delete(meeting)
    db.commit()


def get_meeting(db: Session, *, workspace: Workspace, user: User, meeting_id: str) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)
    _ensure_user_can_view(user, meeting)
    return _serialize_meeting(db, meeting)


def ensure_meeting_notes(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    _ensure_meeting_notes_state(db, meeting=meeting)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def list_meetings(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    scope: str = "mine",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> MeetingListResponse:
    base = select(Meeting).where(Meeting.workspace_id == workspace.id)

    attendee_meeting_ids = select(MeetingAttendee.meeting_id).where(
        MeetingAttendee.user_id == user.id
    )
    base = base.where(
        or_(
            Meeting.organizer_id == user.id,
            Meeting.id.in_(attendee_meeting_ids),
        )
    )

    if scope == "mine":
        pass
    elif scope == "upcoming":
        now = datetime.now(UTC).replace(tzinfo=None)
        base = base.where(
            Meeting.end_at >= now
        )
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


def add_attendees(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    attendees: list[MeetingAttendeeInput],
) -> MeetingDetail:
    """Append attendees to an existing meeting.

    Permission: any meeting participant (organizer or existing attendee).
    Existing attendees in the input are ignored (idempotent). The role is
    updated for already-present users so callers can promote required ↔ optional.
    """
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)

    # Build the merged attendee list: existing rows first, then any new ones
    # from the request that are not already present. Pre-existing attendees
    # whose role is updated keep their slot (handled by _replace_attendees).
    incoming_by_user = {item.user_id: item for item in attendees}
    merged: list[MeetingAttendeeInput] = []
    for att in meeting.attendees:
        override = incoming_by_user.pop(att.user_id, None)
        if override is not None:
            merged.append(override)
        else:
            merged.append(MeetingAttendeeInput(user_id=att.user_id, role=att.role))
    for remaining in incoming_by_user.values():
        merged.append(remaining)

    _replace_attendees(db, meeting, merged, acting_user_id=user.id)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def attach_task(
    db: Session, *, workspace: Workspace, user: User, meeting_id: str, issue_id: str
) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    issue = ensure_issue_attachable(db, user, issue_id)
    _attach_issue_link(db, meeting=meeting, issue=issue, added_by_id=user.id)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def detach_task(
    db: Session, *, workspace: Workspace, user: User, meeting_id: str, issue_id: str
) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)

    link = db.scalar(
        select(MeetingTaskLink).where(
            MeetingTaskLink.meeting_id == meeting_id,
            MeetingTaskLink.issue_id == issue_id,
        )
    )
    if link is not None:
        ensure_link_remover(db, user, meeting, link.added_by_id)
        revoke_grants_for_issue_attachment(
            db,
            meeting_id=meeting.id,
            issue_id=issue_id,
            revoked_by_user_id=user.id,
            reason="detach",
        )
        db.delete(link)
        db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def attach_doc(
    db: Session, *, workspace: Workspace, user: User, meeting_id: str, doc_id: str
) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    doc = ensure_doc_attachable(db, user, doc_id, workspace=workspace)
    _attach_doc_link(db, meeting=meeting, doc=doc, added_by_id=user.id)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def detach_doc(
    db: Session, *, workspace: Workspace, user: User, meeting_id: str, doc_id: str
) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)

    link = db.scalar(
        select(MeetingDocLink).where(
            MeetingDocLink.meeting_id == meeting_id,
            MeetingDocLink.doc_id == doc_id,
        )
    )
    if link is not None:
        ensure_link_remover(db, user, meeting, link.added_by_id)
        revoke_doc_grants_for_attachment(
            db,
            meeting_id=meeting.id,
            doc_id=doc_id,
            revoked_by_user_id=user.id,
            reason="detach",
        )
        db.delete(link)
        db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


async def attach_file(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    upload: UploadFile,
) -> MeetingDetail:
    """Upload a binary file and attach it to the meeting. Any participant
    (organizer or attendee) can upload."""
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)

    data = await upload.read()
    if len(data) > MAX_FILE_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds {MAX_FILE_UPLOAD_SIZE // (1024 * 1024)} MB limit.",
        )

    settings = get_settings()
    client = get_minio_client()
    attachment_id = new_id()
    safe_name = upload.filename or "unnamed"
    storage_key = f"meeting/{meeting.id}/{attachment_id}/{safe_name}"
    client.put_object(
        settings.minio_bucket,
        storage_key,
        BytesIO(data),
        length=len(data),
        content_type=upload.content_type or "application/octet-stream",
    )

    attachment = MeetingFileAttachment(
        id=attachment_id,
        meeting_id=meeting.id,
        filename=safe_name,
        content_type=upload.content_type or "application/octet-stream",
        size_bytes=len(data),
        storage_key=storage_key,
        added_by_id=user.id,
    )
    db.add(attachment)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def detach_file(
    db: Session, *, workspace: Workspace, user: User, meeting_id: str, file_id: str
) -> MeetingDetail:
    """Remove a file attachment. Only the meeting organizer or the user
    who originally uploaded it may remove a file."""
    meeting = _load_meeting(db, workspace, meeting_id)

    attachment = db.scalar(
        select(MeetingFileAttachment).where(
            MeetingFileAttachment.meeting_id == meeting_id,
            MeetingFileAttachment.id == file_id,
        )
    )
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File attachment not found.",
        )

    ensure_link_remover(db, user, meeting, attachment.added_by_id)

    settings = get_settings()
    client = get_minio_client()
    try:
        client.remove_object(settings.minio_bucket, attachment.storage_key)
    except Exception:
        # If the storage object is already gone we still want to drop the
        # database row so the UI no longer shows a phantom attachment.
        pass

    db.delete(attachment)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)
