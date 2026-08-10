from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RecordingAudioStatus = Literal["local_only", "uploading", "saved", "failed"]
RecordingProcessingStatus = Literal["pending", "transcribing", "done", "failed"]
RecordingDocStatus = Literal["pending", "creating", "done", "failed"]
RecordingMeetingInsightStatus = Literal["none", "pending", "extracting", "done", "failed"]


class RecordingTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recording_id: str
    target_app: str
    target_type: str
    target_id: str
    target_title: str | None = None
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
    targets: list[RecordingTargetOut] = Field(default_factory=list)


class RecordingListResponse(BaseModel):
    items: list[RecordingOut]


class RecordingUploadInitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(..., min_length=1, max_length=80)
    mime_type: str = Field(..., min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=200)
    initial_target_app: str | None = Field(default=None, min_length=1, max_length=64)
    initial_target_type: str | None = Field(default=None, min_length=1, max_length=64)
    initial_target_id: str | None = Field(default=None, min_length=1, max_length=128)
    linked_task_id: str | None = Field(default=None, max_length=36)


class RecordingUploadOut(BaseModel):
    id: str
    workspace_id: str
    uploaded_by_id: str
    idempotency_key: str
    status: str
    mime_type: str
    bytes_received: int
    chunk_count: int
    highest_seq: int
    initial_target_app: str | None
    initial_target_type: str | None
    initial_target_id: str | None
    linked_task_id: str | None = None
    started_at: datetime
    last_chunk_at: datetime
    completed_at: datetime | None


class RecordingUploadChunkAck(BaseModel):
    seq: int
    bytes_received: int
    highest_seq: int


class RecordingUploadCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    duration_sec_estimate: int | None = Field(default=None, ge=0)
    source: Literal["quick_record", "live_recording"] = "quick_record"


class RecordingUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)


class RecordingPlaybackResponse(BaseModel):
    url: str
    expires_at: datetime


class RecordingTargetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_app: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    target_id: str = Field(..., min_length=1, max_length=128)
    is_primary: bool = False
    sort_order: int | None = None
