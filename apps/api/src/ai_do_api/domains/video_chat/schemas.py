from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VideoChatSessionStatus = Literal["open", "ended"]
VideoChatRecordingStatus = Literal["idle", "starting", "recording", "stopping", "failed", "saved"]
VideoChatCaptionsStatus = Literal["off", "starting", "on", "stopping", "failed"]


class VideoChatSessionCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    meeting_id: str | None = Field(default=None, max_length=36)


class VideoChatSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    meeting_id: str | None
    room_name: str
    title: str
    status: VideoChatSessionStatus
    provider: str
    started_by_id: str
    started_by_name: str
    started_at: datetime
    ended_at: datetime | None
    recording_status: VideoChatRecordingStatus
    recording_egress_id: str | None
    recording_id: str | None
    captions_status: VideoChatCaptionsStatus
    captions_started_at: datetime | None
    captions_ended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VideoChatSessionListResponse(BaseModel):
    items: list[VideoChatSessionOut]
    total: int


class VideoChatJoinTokenResponse(BaseModel):
    session: VideoChatSessionOut
    livekit_url: str
    token: str
    identity: str
    display_name: str
    expires_at: datetime
