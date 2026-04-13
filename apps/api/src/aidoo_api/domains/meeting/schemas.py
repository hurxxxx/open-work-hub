from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AttendeeRole = Literal["required", "optional"]
AttendeeResponse = Literal["pending", "accepted", "declined", "tentative"]
MeetingStatus = Literal["scheduled", "in_progress", "completed", "cancelled"]


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


class MeetingTaskAttachRequest(BaseModel):
    issue_id: str


class MeetingDocAttachRequest(BaseModel):
    doc_id: str


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
    issue_id: str
    issue_title: str
    project_key: str
    issue_number: int
    added_by_id: str
    created_at: datetime


class MeetingDocLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    doc_id: str
    doc_title: str
    added_by_id: str
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
    storage_key: str
    duration_sec: int | None
    source: str
    transcription_status: str
    failure_reason: str | None
    linked_doc_id: str | None
    created_at: datetime


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


class MeetingDetail(BaseModel):
    id: str
    workspace_id: str
    organizer_id: str
    organizer_name: str
    title: str
    agenda: str
    start_at: datetime
    end_at: datetime
    status: MeetingStatus
    attendees: list[MeetingAttendeeOut]
    task_links: list[MeetingTaskLinkOut]
    doc_links: list[MeetingDocLinkOut]
    file_attachments: list[MeetingFileAttachmentOut]
    recordings: list[MeetingRecordingOut]
    created_at: datetime
    updated_at: datetime


class MeetingUserItem(BaseModel):
    id: str
    email: str
    full_name: str
