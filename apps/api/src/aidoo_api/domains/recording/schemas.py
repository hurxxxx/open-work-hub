from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RecordingAudioStatus = Literal["local_only", "uploading", "saved", "failed"]
RecordingProcessingStatus = Literal["pending", "transcribing", "done", "failed"]
RecordingDocStatus = Literal["pending", "creating", "done", "failed"]
RecordingMeetingInsightStatus = Literal["none", "pending", "extracting", "done", "failed"]


class RecordingContainerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recording_id: str
    container_app: str
    container_type: str
    container_id: str
    is_primary: bool
    sort_order: int
    added_by_id: str
    created_at: datetime


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    owner_id: str
    title: str
    started_at: datetime
    ended_at: datetime | None
    duration_sec: int | None
    source: str
    storage_key: str | None
    file_size: int
    mime_type: str
    audio_status: str
    transcript_status: str
    raw_transcript_doc_status: str
    minutes_doc_status: str
    meeting_insight_status: str
    progress_pct: int
    failure_reason: str | None
    raw_transcript_doc_id: str | None
    minutes_doc_id: str | None
    transcribe_started_at: datetime | None
    transcribe_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None
    containers: list[RecordingContainerOut] = Field(default_factory=list)


class RecordingListResponse(BaseModel):
    items: list[RecordingOut]


class RecordingUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)


class RecordingPlaybackResponse(BaseModel):
    url: str
    expires_at: datetime


class RecordingContainerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container_app: str = Field(..., min_length=1, max_length=64)
    container_type: str = Field(..., min_length=1, max_length=64)
    container_id: str = Field(..., min_length=1, max_length=128)
    is_primary: bool = False
    sort_order: int = 0
