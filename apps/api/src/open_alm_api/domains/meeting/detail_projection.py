from __future__ import annotations

from typing import Any

from open_alm_api.domains.meeting.models import (
    Meeting,
    MeetingAttendee,
    MeetingDocLink,
    MeetingFileAttachment,
    MeetingTaskLink,
)
from open_alm_api.domains.meeting.schemas import (
    MeetingAttendeeOut,
    MeetingDetail,
    MeetingDocLinkOut,
    MeetingFileAttachmentOut,
    MeetingTaskLinkOut,
    MeetingWhiteboardLinkOut,
)
from open_alm_api.domains.pms.models import Task


def serialize_attendee(attendee: MeetingAttendee) -> MeetingAttendeeOut:
    return MeetingAttendeeOut(
        id=attendee.id,
        user_id=attendee.user_id,
        email=attendee.user.email,
        full_name=attendee.user.full_name,
        role=attendee.role,  # type: ignore[arg-type]
        response=attendee.response,  # type: ignore[arg-type]
    )


def serialize_task_link(
    link: MeetingTaskLink,
    *,
    tasks_by_id: dict[str, Task],
) -> MeetingTaskLinkOut:
    task = tasks_by_id.get(link.task_id)
    list_key = task.task_list.key if task and task.task_list else ""
    task_title = task.title if task is not None else ""
    task_number = task.task_number if task is not None else 0
    return MeetingTaskLinkOut(
        id=link.id,
        task_id=link.task_id,
        task_title=task_title,
        list_key=list_key,
        task_number=task_number,
        added_by_id=link.added_by_id,
        created_at=link.created_at,
    )


def serialize_doc_link(
    link: MeetingDocLink,
    *,
    docs_by_id: dict[str, Any],
) -> MeetingDocLinkOut:
    doc = docs_by_id.get(link.doc_id)
    return MeetingDocLinkOut(
        id=link.id,
        doc_id=link.doc_id,
        doc_title=doc.title if doc is not None else "",
        added_by_id=link.added_by_id,
        created_at=link.created_at,
    )


def serialize_file_attachment(
    attachment: MeetingFileAttachment,
    *,
    download_url: str,
) -> MeetingFileAttachmentOut:
    return MeetingFileAttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        download_url=download_url,
        added_by_id=attachment.added_by_id,
        added_by_name=(attachment.added_by.full_name if attachment.added_by else ""),
        created_at=attachment.created_at,
    )


def serialize_whiteboard_link(
    *,
    target: Any,
    whiteboard: Any,
) -> MeetingWhiteboardLinkOut:
    return MeetingWhiteboardLinkOut(
        id=target.id,
        whiteboard_id=whiteboard.id,
        whiteboard_title=whiteboard.title,
        added_by_id=target.created_by_id,
        updated_at=whiteboard.updated_at,
        created_at=target.created_at,
    )


def build_meeting_detail(
    *,
    meeting: Meeting,
    attendees: list[MeetingAttendeeOut],
    task_links: list[MeetingTaskLinkOut],
    doc_links: list[MeetingDocLinkOut],
    whiteboard_link: MeetingWhiteboardLinkOut | None,
    file_attachments: list[MeetingFileAttachmentOut],
    recordings: list[Any],
    active_recording_lock: Any,
) -> MeetingDetail:
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
        attendees=attendees,
        task_links=task_links,
        doc_links=doc_links,
        whiteboard_link=whiteboard_link,
        file_attachments=file_attachments,
        recordings=recordings,
        active_recording_lock=active_recording_lock,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )
