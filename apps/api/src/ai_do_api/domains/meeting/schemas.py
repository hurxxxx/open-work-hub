from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


AttendeeRole = Literal["required", "optional"]
AttendeeResponse = Literal["pending", "accepted", "declined", "tentative"]
MeetingStatus = Literal["scheduled", "in_progress", "completed", "cancelled"]
AvailabilitySourceType = Literal["meeting", "planner_event"]


def _camel_config() -> ConfigDict:
    return ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class MeetingAttendeeInput(BaseModel):
    user_id: str
    role: AttendeeRole = "required"


class MeetingCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    agenda: str = Field(default="", max_length=4000)
    start_at: datetime
    end_at: datetime
    attendees: list[MeetingAttendeeInput] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    doc_ids: list[str] = Field(default_factory=list)


class MeetingUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    agenda: str | None = Field(default=None, max_length=4000)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: MeetingStatus | None = None
    attendees: list[MeetingAttendeeInput] | None = None


class AttendeeResponseUpdateRequest(BaseModel):
    response: AttendeeResponse


class MeetingAttendeesAddRequest(BaseModel):
    """Append one or more attendees to an existing meeting.

    Allowed for any current meeting participant (organizer or existing
    attendee), unlike ``MeetingUpdateRequest.attendees`` which is organizer-only
    because it can also remove people.
    """

    attendees: list[MeetingAttendeeInput] = Field(..., min_length=1)


class MeetingTaskAttachRequest(BaseModel):
    task_id: str


class MeetingDocAttachRequest(BaseModel):
    doc_id: str


class RecordingStagingInitRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8, max_length=80)
    mime_type: str = Field(..., min_length=3, max_length=120)
    linked_task_id: str | None = None


class RecordingCompleteRequest(BaseModel):
    duration_sec_estimate: int | None = Field(default=None, ge=0)


class MeetingAttendeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    email: str
    full_name: str
    role: AttendeeRole
    response: AttendeeResponse


class MeetingTaskLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    task_title: str
    list_key: str
    task_number: int
    added_by_id: str
    created_at: datetime


class MeetingDocLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    doc_id: str
    doc_title: str
    added_by_id: str
    created_at: datetime


class MeetingWhiteboardLinkOut(BaseModel):
    id: str
    whiteboard_id: str
    whiteboard_title: str
    added_by_id: str | None = None
    updated_at: datetime
    created_at: datetime


class MeetingFileAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    size_bytes: int
    download_url: str
    added_by_id: str
    added_by_name: str
    created_at: datetime


class MeetingRecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    meeting_id: str
    uploaded_by_id: str
    storage_key: str
    duration_sec: int | None
    source: str
    transcription_status: str
    sequence_no: int
    progress_pct: int
    file_size: int
    mime_type: str
    failure_reason: str | None
    linked_doc_id: str | None
    raw_transcript_doc_id: str | None = None
    minutes_doc_id: str | None = None
    linked_task_id: str | None
    transcript_extracted: bool
    summary_generated: bool
    transcribe_started_at: datetime | None
    transcribe_completed_at: datetime | None
    created_at: datetime


class RecordingStagingItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    meeting_id: str
    uploaded_by_id: str
    idempotency_key: str
    status: str
    mime_type: str
    bytes_received: int
    chunk_count: int
    highest_seq: int
    linked_task_id: str | None
    started_at: datetime
    last_chunk_at: datetime
    completed_at: datetime | None


class RecordingChunkAck(BaseModel):
    seq: int
    bytes_received: int
    highest_seq: int


class RecordingPlaybackResponse(BaseModel):
    url: str
    expires_at: datetime


class MeetingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    organizer_id: str
    organizer_name: str
    start_at: datetime
    end_at: datetime
    status: MeetingStatus
    attendee_count: int
    task_link_count: int
    doc_link_count: int


class MeetingListResponse(BaseModel):
    items: list[MeetingListItem]
    total: int


class ActiveRecordingLockOut(BaseModel):
    """Indicates that a meeting currently has an in-progress recording.

    When non-null, only the listed user can start / resume a recording on the
    meeting; other participants must wait for the active recorder to stop.
    The lock auto-releases when ``last_active_at`` falls behind the staleness
    window (recorder crashed / network died), so this field is also useful for
    "녹음 중 (마지막 활동: 5초 전)" UX.
    """

    staging_id: str
    user_id: str
    user_name: str
    started_at: datetime
    last_active_at: datetime


class MeetingDetail(BaseModel):
    id: str
    workspace_id: str
    organizer_id: str
    organizer_name: str
    notes_doc_id: str | None
    notes_page_id: str | None
    title: str
    agenda: str
    start_at: datetime
    end_at: datetime
    status: MeetingStatus
    attendees: list[MeetingAttendeeOut]
    task_links: list[MeetingTaskLinkOut]
    doc_links: list[MeetingDocLinkOut]
    whiteboard_link: MeetingWhiteboardLinkOut | None = None
    file_attachments: list[MeetingFileAttachmentOut]
    recordings: list[MeetingRecordingOut]
    active_recording_lock: ActiveRecordingLockOut | None = None
    created_at: datetime
    updated_at: datetime


class MeetingUserItem(BaseModel):
    id: str
    email: str
    full_name: str
    primary_org_unit_name: str | None = None


class MeetingAvailabilityBlock(BaseModel):
    model_config = _camel_config()

    id: str
    start: str
    end: str
    all_day: bool
    source_type: AvailabilitySourceType
    masked: bool
    title: str | None = None
    location: str | None = None


class MeetingAvailabilityItem(BaseModel):
    model_config = _camel_config()

    user_id: str
    full_name: str
    blocks: list[MeetingAvailabilityBlock]


class MeetingAvailabilityResponse(BaseModel):
    model_config = _camel_config()

    items: list[MeetingAvailabilityItem]
