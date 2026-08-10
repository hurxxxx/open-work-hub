from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import time
from typing import Iterable, Literal
from urllib.parse import quote

from fastapi import UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.access import (
    bind_current_workspace,
    resolve_workspace_role,
)
from open_work_hub_api.domains.auth.models import (
    User,
    Workspace,
)
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.retrieval.partitioning import assign_default_partition
from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.docs.rag_sync import (
    collect_meeting_visibility_doc_ids,
    enqueue_meeting_visibility_recompute,
)
from open_work_hub_api.domains.meeting import file_storage
from open_work_hub_api.domains.meeting.attachment_grants import (
    bump_attachment_grant_expiry_for_meeting,
    detach_deleted_meeting_grant_fks,
    grant_doc_attachment_to_attendees,
    grant_existing_attachments_to_new_attendees,
    grant_task_attachment_to_attendees,
    revoke_attachment_grants_for_deleted_meeting,
    revoke_attachment_grants_for_removed_attendee,
    revoke_doc_attachment_grants,
    revoke_task_attachment_grants,
)
from open_work_hub_api.domains.meeting import notes_lifecycle
from open_work_hub_api.domains.meeting.availability_projection import build_meeting_availability
from open_work_hub_api.domains.meeting.models import (
    Meeting,
    MeetingAttendee,
    MeetingDocLink,
    MeetingFileAttachment,
    MeetingTaskLink,
)
from open_work_hub_api.domains.meeting.detail_projection import (
    build_meeting_detail,
    serialize_attendee,
    serialize_doc_link,
    serialize_file_attachment,
    serialize_task_link,
    serialize_whiteboard_link,
)
from open_work_hub_api.domains.meeting.permissions import (
    ensure_doc_attachable,
    ensure_link_remover,
    ensure_meeting_participant,
)
from open_work_hub_api.domains.meeting.rag_sync import enqueue_meeting_rag_sync
from open_work_hub_api.domains.meeting.schemas import (
    MeetingAvailabilityResponse,
    MeetingAttendeeInput,
    MeetingAttendeeOut,
    MeetingCreateRequest,
    MeetingDetail,
    MeetingDocLinkOut,
    MeetingFileAttachmentOut,
    MeetingListItem,
    MeetingListResponse,
    MeetingTaskLinkOut,
    MeetingUpdateRequest,
    MeetingWhiteboardLinkOut,
)
from open_work_hub_api.domains.pms.access import ensure_task_attachable
from open_work_hub_api.domains.pms.models import Task
from open_work_hub_api.domains.rag.contracts import RagSyncOperation
from open_work_hub_api.domains.recording import service as recording_service
from open_work_hub_api.domains.source_access import can_read_meeting
from open_work_hub_api.domains.whiteboard.models import Whiteboard, WhiteboardTarget


MAX_FILE_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
MEETING_ATTACHMENT_CONTENT_URL_EXPIRES_SECONDS = 60 * 60
MEETING_ATTACHMENT_CONTENT_CHUNK_SIZE = 1024 * 1024
MeetingAttachmentDisposition = Literal["attachment", "inline"]


@dataclass(frozen=True)
class MeetingAttachmentContent:
    body: Iterable[bytes]
    media_type: str
    headers: dict[str, str]


def _bind_workspace_context(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
) -> None:
    bind_current_workspace(db, workspace)
    if principal.workspace_id != workspace.id:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="meeting.principal_workspace_mismatch",
        )
    if principal.kind == "user" and principal.user_id not in {None, user.id}:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="meeting.principal_user_mismatch",
        )


def _meeting_notes_doc_title(meeting: Meeting) -> str:
    return notes_lifecycle.meeting_notes_doc_title(meeting)


def _meeting_notes_page_title() -> str:
    return notes_lifecycle.meeting_notes_page_title()


def _validate_time_range(start_at: datetime, end_at: datetime) -> None:
    if end_at <= start_at:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.end_after_start",
        )


def _require_user_write_principal(principal: CallerPrincipal) -> None:
    if principal.kind != "user":
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="meeting.write_user_principal_required",
        )


def _validate_attendee_users(
    db: Session,
    user_ids: Iterable[str],
    *,
    workspace_id: str,
) -> dict[str, User]:
    unique_ids = list({uid for uid in user_ids})
    if not unique_ids:
        return {}
    users = db.scalars(select(User).where(User.id.in_(unique_ids), User.status == "active")).all()
    found = {user.id: user for user in users}
    missing = set(unique_ids) - set(found.keys())
    if missing:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.unknown_attendees",
            user_ids=", ".join(sorted(missing)),
        )
    non_members = sorted(
        user.id for user in users if resolve_workspace_role(db, user, workspace_id) is None
    )
    if non_members:
        raise localized_http_exception(
            status_code=422,
            code="meeting.attendees_workspace_required",
            user_ids=", ".join(non_members),
        )
    return found


def _grant_notes_doc_to_attendee(
    db: Session,
    *,
    meeting: Meeting,
    doc: NativeDoc,
    attendee_user: User,
    granted_by_user_id: str,
) -> None:
    notes_lifecycle.grant_notes_doc_to_attendee(
        db,
        meeting=meeting,
        doc=doc,
        attendee_user=attendee_user,
        granted_by_user_id=granted_by_user_id,
    )


def _load_active_native_doc(
    db: Session, *, workspace_id: str, doc_id: str | None
) -> NativeDoc | None:
    return notes_lifecycle.load_active_native_doc(db, workspace_id=workspace_id, doc_id=doc_id)


def _ensure_meeting_notes_state(
    db: Session,
    *,
    meeting: Meeting,
):
    return notes_lifecycle.ensure_meeting_notes_state(db, meeting=meeting)


def _attach_task_link(
    db: Session,
    *,
    meeting: Meeting,
    task: Task,
    added_by_id: str,
) -> None:
    existing = db.scalar(
        select(MeetingTaskLink).where(
            MeetingTaskLink.meeting_id == meeting.id,
            MeetingTaskLink.task_id == task.id,
        )
    )
    if existing is None:
        db.add(
            MeetingTaskLink(
                id=new_id(),
                meeting_id=meeting.id,
                task_id=task.id,
                added_by_id=added_by_id,
            )
        )
        db.flush()

    grant_task_attachment_to_attendees(
        db,
        meeting=meeting,
        task=task,
        added_by_id=added_by_id,
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

    grant_doc_attachment_to_attendees(
        db,
        meeting=meeting,
        doc=doc,
        added_by_id=added_by_id,
    )


def _serialize_attendee(attendee: MeetingAttendee) -> MeetingAttendeeOut:
    return serialize_attendee(attendee)


def _serialize_task_link(
    link: MeetingTaskLink,
    *,
    tasks_by_id: dict[str, Task],
) -> MeetingTaskLinkOut:
    return serialize_task_link(link, tasks_by_id=tasks_by_id)


def _serialize_doc_link(
    link: MeetingDocLink,
    *,
    docs_by_id: dict[str, NativeDoc],
) -> MeetingDocLinkOut:
    return serialize_doc_link(link, docs_by_id=docs_by_id)


def _load_task_link_task_map(
    db: Session,
    task_links: list[MeetingTaskLink],
) -> dict[str, Task]:
    task_ids = [link.task_id for link in task_links]
    if not task_ids:
        return {}
    tasks = db.scalars(
        select(Task).where(Task.id.in_(task_ids)).options(selectinload(Task.task_list))
    ).all()
    return {task.id: task for task in tasks}


def _load_doc_link_doc_map(
    db: Session,
    doc_links: list[MeetingDocLink],
) -> dict[str, NativeDoc]:
    doc_ids = [link.doc_id for link in doc_links]
    if not doc_ids:
        return {}
    docs = db.scalars(select(NativeDoc).where(NativeDoc.id.in_(doc_ids))).all()
    return {doc.id: doc for doc in docs}


def _build_file_download_url(
    attachment: MeetingFileAttachment,
    *,
    disposition: MeetingAttachmentDisposition = "attachment",
    now: float | None = None,
    expires_seconds: int = MEETING_ATTACHMENT_CONTENT_URL_EXPIRES_SECONDS,
) -> str:
    expires = int(time.time() if now is None else now) + expires_seconds
    signature = _sign_file_content_url(
        attachment,
        expires=expires,
        disposition=disposition,
    )
    return (
        f"{get_settings().api_prefix}/meeting/files/{attachment.id}/content"
        f"?expires={expires}&signature={signature}&disposition={disposition}"
    )


def _serialize_file_attachment(
    attachment: MeetingFileAttachment,
) -> MeetingFileAttachmentOut:
    return serialize_file_attachment(
        attachment,
        download_url=_build_file_download_url(attachment),
    )


def _sign_file_content_url(
    attachment: MeetingFileAttachment,
    *,
    expires: int,
    disposition: MeetingAttachmentDisposition,
) -> str:
    secret = get_settings().minio_secret_key.encode("utf-8")
    message = (
        f"v1:{attachment.id}:{attachment.meeting_id}:{attachment.storage_key}:"
        f"{expires}:{disposition}"
    ).encode("utf-8")
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _validate_file_content_signature(
    attachment: MeetingFileAttachment,
    *,
    expires: int,
    disposition: MeetingAttachmentDisposition,
    signature: str,
    now: float | None = None,
) -> bool:
    if expires < int(time.time() if now is None else now):
        return False
    expected = _sign_file_content_url(
        attachment,
        expires=expires,
        disposition=disposition,
    )
    return hmac.compare_digest(signature, expected)


def open_file_attachment_content(
    db: Session,
    *,
    file_id: str,
    expires: int,
    signature: str,
    disposition: MeetingAttachmentDisposition,
) -> MeetingAttachmentContent:
    attachment = db.get(MeetingFileAttachment, file_id)
    if attachment is None:
        raise localized_http_exception(status_code=404, code="meeting.file_not_found")
    if not _validate_file_content_signature(
        attachment,
        expires=expires,
        disposition=disposition,
        signature=signature,
    ):
        raise localized_http_exception(
            status_code=403,
            code="meeting.file_proxy_url_invalid",
        )

    try:
        body = file_storage.open_attachment_object(
            storage_key=attachment.storage_key,
            chunk_size=MEETING_ATTACHMENT_CONTENT_CHUNK_SIZE,
        )
    except Exception as exc:
        raise localized_http_exception(
            status_code=502,
            code="meeting.file_download_failed",
        ) from exc

    encoded_filename = quote(attachment.filename or "attachment", safe="")
    return MeetingAttachmentContent(
        body=body,
        media_type=attachment.content_type or file_storage.DEFAULT_ATTACHMENT_CONTENT_TYPE,
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": (f"{disposition}; filename*=UTF-8''{encoded_filename}"),
            "X-Content-Type-Options": "nosniff",
        },
    )


def _load_whiteboard_link(
    db: Session, meeting: Meeting
) -> tuple[WhiteboardTarget, Whiteboard] | None:
    row = db.execute(
        select(WhiteboardTarget, Whiteboard)
        .join(Whiteboard, Whiteboard.id == WhiteboardTarget.whiteboard_id)
        .where(
            WhiteboardTarget.target_app == "meeting",
            WhiteboardTarget.target_type == "meeting",
            WhiteboardTarget.target_id == meeting.id,
            Whiteboard.workspace_id == meeting.workspace_id,
            Whiteboard.trashed_at.is_(None),
        )
        .order_by(WhiteboardTarget.created_at.asc())
        .limit(1)
    ).first()
    if row is None:
        return None
    target, whiteboard = row
    return target, whiteboard


def _serialize_whiteboard_link(
    db: Session,
    meeting: Meeting,
) -> MeetingWhiteboardLinkOut | None:
    loaded = _load_whiteboard_link(db, meeting)
    if loaded is None:
        return None
    target, whiteboard = loaded
    return serialize_whiteboard_link(target=target, whiteboard=whiteboard)


def _serialize_meeting(db: Session, meeting: Meeting) -> MeetingDetail:
    tasks_by_id = _load_task_link_task_map(db, meeting.task_links)
    docs_by_id = _load_doc_link_doc_map(db, meeting.doc_links)
    return build_meeting_detail(
        meeting=meeting,
        attendees=[_serialize_attendee(a) for a in meeting.attendees],
        task_links=[
            _serialize_task_link(link, tasks_by_id=tasks_by_id) for link in meeting.task_links
        ],
        doc_links=[_serialize_doc_link(link, docs_by_id=docs_by_id) for link in meeting.doc_links],
        whiteboard_link=_serialize_whiteboard_link(db, meeting),
        file_attachments=[
            _serialize_file_attachment(att)
            for att in sorted(meeting.file_attachments, key=lambda a: a.created_at)
        ],
        recordings=recording_service.list_meeting_recording_outs(db, meeting=meeting),
        active_recording_lock=recording_service.resolve_active_recording_lock(db, meeting=meeting),
    )


def _load_meeting(db: Session, workspace: Workspace, meeting_id: str) -> Meeting:
    from open_work_hub_api.domains.meeting.models import MeetingRecordingStaging

    meeting = db.scalar(
        select(Meeting)
        .options(
            selectinload(Meeting.attendees).selectinload(MeetingAttendee.user),
            selectinload(Meeting.task_links),
            selectinload(Meeting.doc_links),
            selectinload(Meeting.file_attachments).selectinload(MeetingFileAttachment.added_by),
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
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="meeting.not_found",
        )
    return meeting


def _ensure_user_can_view(user: User, meeting: Meeting) -> None:
    if meeting.organizer_id == user.id:
        return
    if any(att.user_id == user.id for att in meeting.attendees):
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="meeting.access_required",
    )


def can_read_meeting_for_rag(
    db: Session,
    *,
    user: User,
    workspace_id: str,
    meeting_id: str,
) -> bool:
    return can_read_meeting(
        db,
        user=user,
        workspace_id=workspace_id,
        meeting_id=meeting_id,
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
            revoke_attachment_grants_for_removed_attendee(
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

    grant_existing_attachments_to_new_attendees(
        db,
        meeting=meeting,
        attendee_user_ids=added_user_ids,
        granted_by_user_id=acting_user_id,
    )
    notes_doc = _load_active_native_doc(
        db, workspace_id=meeting.workspace_id, doc_id=meeting.notes_doc_id
    )
    for attendee in meeting.attendees:
        if attendee.user_id not in added_user_ids or attendee.user is None:
            continue
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
    meeting_id: str | None = None,
) -> MeetingDetail:
    _validate_time_range(payload.start_at, payload.end_at)

    if meeting_id is not None:
        existing = db.scalar(
            select(Meeting).where(
                Meeting.id == meeting_id,
                Meeting.workspace_id == workspace.id,
            )
        )
        if existing is not None:
            fresh = _load_meeting(db, workspace, existing.id)
            return _serialize_meeting(db, fresh)

    attendees_input = list(payload.attendees)
    if not any(item.user_id == organizer.id for item in attendees_input):
        attendees_input.append(MeetingAttendeeInput(user_id=organizer.id, role="required"))
    _validate_attendee_users(
        db,
        [item.user_id for item in attendees_input],
        workspace_id=workspace.id,
    )

    meeting = Meeting(
        id=meeting_id or new_id(),
        workspace_id=workspace.id,
        organizer_id=organizer.id,
        title=payload.title.strip(),
        agenda=payload.agenda,
        start_at=payload.start_at,
        end_at=payload.end_at,
        status="scheduled",
    )
    assign_default_partition(
        db,
        target=meeting,
        source_namespace="meeting",
        candidate_scope_kind="workspace",
        workspace_id=workspace.id,
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
                response=("accepted" if item.user_id == organizer.id else "pending"),
            )
        )
    db.flush()
    meeting = _load_meeting(db, workspace, meeting.id)

    tasks = [ensure_task_attachable(db, organizer, task_id) for task_id in payload.task_ids]
    docs = [
        ensure_doc_attachable(db, organizer, doc_id, workspace=workspace)
        for doc_id in payload.doc_ids
    ]
    for task in tasks:
        _attach_task_link(db, meeting=meeting, task=task, added_by_id=organizer.id)
    for doc in docs:
        _attach_doc_link(db, meeting=meeting, doc=doc, added_by_id=organizer.id)
    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )
    if docs:
        enqueue_meeting_visibility_recompute(
            db,
            workspace_id=workspace.id,
            meeting_id=meeting.id,
        )
    db.commit()

    fresh = _load_meeting(db, workspace, meeting.id)
    return _serialize_meeting(db, fresh)


def create_meeting_for_ai(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    title: str,
    start_at: datetime,
    end_at: datetime,
    attendee_user_ids: list[str] | None = None,
    description: str = "",
    location: str | None = None,
    approved_call_id: str | None = None,
) -> dict[str, object]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    if location is not None and location.strip():
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.location_unsupported",
        )
    payload = MeetingCreateRequest(
        title=title,
        agenda=description,
        start_at=start_at,
        end_at=end_at,
        attendees=[
            MeetingAttendeeInput(user_id=attendee_user_id, role="required")
            for attendee_user_id in attendee_user_ids or []
        ],
        task_ids=[],
        doc_ids=[],
    )
    result = create_meeting(
        db,
        workspace=workspace,
        organizer=user,
        payload=payload,
        meeting_id=approved_call_id,
    )
    return result.model_dump(mode="json", by_alias=True)


def update_meeting(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
    payload: MeetingUpdateRequest,
) -> MeetingDetail:
    from open_work_hub_api.domains.meeting.permissions import ensure_meeting_organizer

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
                MeetingAttendeeInput(user_id=meeting.organizer_id, role="required")
            )
        _replace_attendees(
            db,
            meeting,
            attendees_input,
            acting_user_id=user.id,
        )

    if meeting.end_at != original_end_at:
        bump_attachment_grant_expiry_for_meeting(
            db,
            meeting_id=meeting.id,
            new_end_at=meeting.end_at,
        )

    if payload.attendees is not None or meeting.end_at != original_end_at:
        enqueue_meeting_visibility_recompute(
            db,
            workspace_id=workspace.id,
            meeting_id=meeting.id,
        )
    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )

    db.add(meeting)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting.id)
    return _serialize_meeting(db, fresh)


def delete_meeting(db: Session, *, workspace: Workspace, user: User, meeting_id: str) -> None:
    from open_work_hub_api.domains.meeting.permissions import ensure_meeting_organizer
    from open_work_hub_api.domains.meeting.recordings import cleanup_meeting_recordings

    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_organizer(db, user, meeting)
    cleanup_meeting_recordings(db, meeting=meeting)
    affected_doc_ids = collect_meeting_visibility_doc_ids(db, meeting_id=meeting.id)
    revoke_attachment_grants_for_deleted_meeting(
        db,
        meeting_id=meeting.id,
        revoked_by_user_id=user.id,
        reason="meeting_deleted",
    )
    detach_deleted_meeting_grant_fks(db, meeting_id=meeting.id)
    if affected_doc_ids:
        enqueue_meeting_visibility_recompute(
            db,
            workspace_id=workspace.id,
            meeting_id=meeting.id,
            doc_ids=affected_doc_ids,
        )
    for target in db.scalars(
        select(WhiteboardTarget).where(
            WhiteboardTarget.target_app == "meeting",
            WhiteboardTarget.target_type == "meeting",
            WhiteboardTarget.target_id == meeting.id,
        )
    ):
        db.delete(target)
    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.DELETE,
    )
    db.delete(meeting)
    db.commit()


def get_meeting(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    meeting_id: str,
) -> MeetingDetail:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    meeting = _load_meeting(db, workspace, meeting_id)
    _ensure_user_can_view(user, meeting)
    return _serialize_meeting(db, meeting)


def build_meeting_scope_prompt(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    meeting_id: str,
) -> str:
    meeting = load_meeting_for_participant(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        meeting_id=meeting_id,
    )
    latest_recording = recording_service.latest_meeting_recording(
        db,
        workspace_id=meeting.workspace_id,
        meeting_id=meeting.id,
        require_transcript=True,
    )
    summary = ""
    transcript_excerpt = ""
    if latest_recording is not None:
        summary = ""
        transcript_excerpt = (latest_recording.transcript_text or "").strip()[:8000]
    agenda = (meeting.agenda or "").strip()[:2000]
    lines = [
        "[회의 컨텍스트]",
        "이 대화는 특정 회의에 바인딩되어 있다. 회의 사실은 아래 범위 안에서만 사용하고, 부족한 정보는 추정하지 말고 도구나 사용자에게 확인한다.",
        f"회의 ID: {meeting.id}",
        f"회의 제목: {meeting.title}",
        f"시작 시각: {meeting.start_at.isoformat()}",
        f"종료 시각: {meeting.end_at.isoformat()}",
        f"상태: {meeting.status}",
    ]
    if agenda:
        lines.extend(["", "[안건]", agenda])
    if summary:
        lines.extend(["", "[요약]", summary])
    if transcript_excerpt:
        lines.extend(["", "[전사 발췌]", transcript_excerpt])
    return "\n".join(lines)


def ensure_meeting_scope_access(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    meeting_id: str,
) -> None:
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)


def load_meeting_for_participant(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    meeting_id: str,
) -> Meeting:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    return meeting


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
    principal: CallerPrincipal,
    user: User,
    scope: str = "mine",
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> MeetingListResponse:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
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
        base = base.where(Meeting.end_at >= now)
    elif scope == "all":
        pass
    else:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="meeting.unsupported_scope",
            scope=scope,
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


def list_meeting_availability(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    viewer: User,
    user_ids: list[str],
    from_at: datetime,
    to_at: datetime,
) -> MeetingAvailabilityResponse:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=viewer)
    return build_meeting_availability(
        db,
        workspace=workspace,
        viewer=viewer,
        user_ids=user_ids,
        from_at=from_at,
        to_at=to_at,
    )


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
    enqueue_meeting_visibility_recompute(
        db,
        workspace_id=workspace.id,
        meeting_id=meeting.id,
    )
    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def attach_task(
    db: Session, *, workspace: Workspace, user: User, meeting_id: str, task_id: str
) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)
    ensure_meeting_participant(db, user, meeting)
    task = ensure_task_attachable(db, user, task_id)
    _attach_task_link(db, meeting=meeting, task=task, added_by_id=user.id)
    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)


def detach_task(
    db: Session, *, workspace: Workspace, user: User, meeting_id: str, task_id: str
) -> MeetingDetail:
    meeting = _load_meeting(db, workspace, meeting_id)

    link = db.scalar(
        select(MeetingTaskLink).where(
            MeetingTaskLink.meeting_id == meeting_id,
            MeetingTaskLink.task_id == task_id,
        )
    )
    if link is not None:
        ensure_link_remover(db, user, meeting, link.added_by_id)
        revoke_task_attachment_grants(
            db,
            meeting_id=meeting.id,
            task_id=task_id,
            revoked_by_user_id=user.id,
            reason="detach",
        )
        enqueue_meeting_rag_sync(
            db,
            meeting=meeting,
            operation=RagSyncOperation.UPSERT,
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
    enqueue_meeting_visibility_recompute(
        db,
        workspace_id=workspace.id,
        meeting_id=meeting.id,
    )
    enqueue_meeting_rag_sync(
        db,
        meeting=meeting,
        operation=RagSyncOperation.UPSERT,
    )
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
        revoke_doc_attachment_grants(
            db,
            meeting_id=meeting.id,
            doc_id=doc_id,
            revoked_by_user_id=user.id,
            reason="detach",
        )
        enqueue_meeting_visibility_recompute(
            db,
            workspace_id=workspace.id,
            meeting_id=meeting.id,
            doc_ids=[doc_id],
        )
        enqueue_meeting_rag_sync(
            db,
            meeting=meeting,
            operation=RagSyncOperation.UPSERT,
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
        raise localized_http_exception(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="meeting.file_size_limit_exceeded",
            limit_mb=MAX_FILE_UPLOAD_SIZE // (1024 * 1024),
        )

    attachment_id = new_id()
    safe_name = upload.filename or "unnamed"
    storage_key = file_storage.attachment_storage_key(
        meeting_id=meeting.id,
        attachment_id=attachment_id,
        filename=safe_name,
    )
    file_storage.put_attachment_object(
        storage_key=storage_key,
        data=data,
        content_type=upload.content_type,
    )

    attachment = MeetingFileAttachment(
        id=attachment_id,
        meeting_id=meeting.id,
        filename=safe_name,
        content_type=upload.content_type or file_storage.DEFAULT_ATTACHMENT_CONTENT_TYPE,
        size_bytes=len(data),
        storage_key=storage_key,
        added_by_id=user.id,
    )
    db.add(attachment)
    db.flush()
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
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="meeting.file_attachment_not_found",
        )

    ensure_link_remover(db, user, meeting, attachment.added_by_id)

    try:
        file_storage.remove_attachment_object(attachment.storage_key)
    except Exception:
        # If the storage object is already gone we still want to drop the
        # database row so the UI no longer shows a phantom attachment.
        pass

    db.delete(attachment)
    db.commit()

    fresh = _load_meeting(db, workspace, meeting_id)
    return _serialize_meeting(db, fresh)
